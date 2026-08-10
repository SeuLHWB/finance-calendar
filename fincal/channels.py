# -*- coding: utf-8 -*-
"""推送渠道。全部基于标准库 urllib，无第三方依赖。

每个渠道实现 send(title, text, markdown, html) -> (ok, message)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------- utils
def _post_json(url: str, payload: dict, timeout: int = 20, headers: dict | None = None) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    hdr = {"Content-Type": "application/json; charset=utf-8", "User-Agent": "fincal/1.0"}
    hdr.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdr, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "ignore")
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return {"raw": raw}


def _get_json(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "fincal/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def split_by_bytes(text: str, limit: int = 3800) -> list[str]:
    """按行切分，保证每块 UTF-8 字节数不超过 limit（企业微信 markdown 上限 4096 字节）。"""
    chunks, cur, size = [], [], 0
    for line in text.split("\n"):
        b = len(line.encode("utf-8")) + 1
        if size + b > limit and cur:
            chunks.append("\n".join(cur))
            cur, size = [], 0
        cur.append(line)
        size += b
    if cur:
        chunks.append("\n".join(cur))
    return chunks or [""]


class Channel:
    name = "base"

    def __init__(self, cfg: dict, ctx: dict | None = None):
        self.cfg = cfg
        self.ctx = ctx or {}

    def send(self, title, text, markdown, html_body):  # pragma: no cover
        raise NotImplementedError


# ---------------------------------------------------------------- 本地文件
class FileChannel(Channel):
    name = "file"

    def send(self, title, text, markdown, html_body):
        outdir = Path(self.ctx.get("output_dir", "out"))
        outdir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        (outdir / f"digest-{stamp}.md").write_text(markdown, encoding="utf-8")
        (outdir / f"digest-{stamp}.html").write_text(html_body, encoding="utf-8")
        (outdir / f"digest-{stamp}.txt").write_text(text, encoding="utf-8")
        (outdir / "latest.html").write_text(html_body, encoding="utf-8")
        return True, f"已写入 {outdir.resolve()}"


# ---------------------------------------------------------------- 企业微信群机器人
class WeComBotChannel(Channel):
    name = "wecom_bot"

    def send(self, title, text, markdown, html_body):
        url = self.cfg["webhook"]
        msgtype = self.cfg.get("msgtype", "markdown")
        body = markdown if msgtype == "markdown" else text
        parts = split_by_bytes(body, 3800)
        results = []
        for i, part in enumerate(parts):
            suffix = f"\n\n<font color=\"comment\">（{i+1}/{len(parts)}）</font>" if len(parts) > 1 else ""
            if msgtype == "markdown":
                payload = {"msgtype": "markdown", "markdown": {"content": part + suffix}}
            else:
                payload = {"msgtype": "text", "text": {
                    "content": part + suffix,
                    "mentioned_mobile_list": self.cfg.get("mentioned_mobile_list", [])}}
            r = _post_json(url, payload)
            results.append(r)
            if r.get("errcode") not in (0, None):
                return False, f"企业微信机器人失败: {r}"
            if i < len(parts) - 1:
                time.sleep(1)  # 20 条/分钟限流
        return True, f"已发送 {len(parts)} 条"


# ---------------------------------------------------------------- 企业微信自建应用
class WeComAppChannel(Channel):
    name = "wecom_app"

    def _token(self) -> str:
        url = ("https://qyapi.weixin.qq.com/cgi-bin/gettoken"
               f"?corpid={self.cfg['corpid']}&corpsecret={self.cfg['corpsecret']}")
        r = _get_json(url)
        if r.get("errcode") != 0:
            raise RuntimeError(f"获取 access_token 失败: {r}")
        return r["access_token"]

    def send(self, title, text, markdown, html_body):
        token = self._token()
        url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
        parts = split_by_bytes(markdown, 1800)  # markdown 上限 2048 字节
        for i, part in enumerate(parts):
            payload = {
                "touser": self.cfg.get("touser", "@all"),
                "msgtype": "markdown",
                "agentid": self.cfg["agentid"],
                "markdown": {"content": part},
                "duplicate_check_interval": 600,
            }
            r = _post_json(url, payload)
            if r.get("errcode") != 0:
                return False, f"企业微信应用消息失败: {r}"
            if i < len(parts) - 1:
                time.sleep(0.5)
        return True, f"已发送 {len(parts)} 条"


# ---------------------------------------------------------------- Server酱
class ServerChanChannel(Channel):
    name = "serverchan"

    def send(self, title, text, markdown, html_body):
        key = self.cfg["sendkey"]
        if key.startswith("sctp"):  # Server酱³ 独立域名
            uid = key.split("t")[1].split("t")[0] if "t" in key else ""
            url = f"https://{uid}.push.ft07.com/send/{key}.send"
        else:
            url = f"https://sctapi.ftqq.com/{key}.send"
        data = urllib.parse.urlencode(
            {"title": title[:32], "desp": markdown[:32000]}).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            r = json.loads(resp.read().decode("utf-8", "ignore"))
        ok = r.get("code") in (0, 200)
        return ok, str(r)


# ---------------------------------------------------------------- WxPusher
class WxPusherChannel(Channel):
    name = "wxpusher"

    def send(self, title, text, markdown, html_body):
        payload = {
            "appToken": self.cfg["app_token"],
            "content": html_body,
            "summary": title[:99],
            "contentType": 2,  # 1=文本 2=html 3=markdown
            "uids": self.cfg.get("uids", []),
            "topicIds": self.cfg.get("topic_ids", []),
        }
        r = _post_json("https://wxpusher.zjiecode.com/api/send/message", payload)
        return bool(r.get("success")), str(r.get("msg", r))


# ---------------------------------------------------------------- PushPlus
class PushPlusChannel(Channel):
    name = "pushplus"

    def send(self, title, text, markdown, html_body):
        tpl = self.cfg.get("template", "markdown")
        content = markdown if tpl == "markdown" else html_body
        payload = {"token": self.cfg["token"], "title": title[:100],
                   "content": content, "template": tpl}
        r = _post_json("http://www.pushplus.plus/send", payload)
        return r.get("code") == 200, str(r.get("msg", r))


# ---------------------------------------------------------------- 邮件
class EmailChannel(Channel):
    name = "email"

    def send(self, title, text, markdown, html_body):
        import smtplib
        from email.header import Header
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        c = self.cfg
        msg = MIMEMultipart("alternative")
        msg["Subject"] = Header(title, "utf-8")
        msg["From"] = c.get("from_addr", c["username"])
        msg["To"] = ", ".join(c["to_addrs"])
        msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        if c.get("use_ssl", True):
            server = smtplib.SMTP_SSL(c["smtp_host"], int(c.get("smtp_port", 465)), timeout=30)
        else:
            server = smtplib.SMTP(c["smtp_host"], int(c.get("smtp_port", 587)), timeout=30)
            server.starttls()
        try:
            server.login(c["username"], c["password"])
            server.sendmail(msg["From"], c["to_addrs"], msg.as_string())
        finally:
            server.quit()
        return True, f"已发送至 {len(c['to_addrs'])} 个收件人"


# ---------------------------------------------------------------- Telegram
class TelegramChannel(Channel):
    name = "telegram"

    def send(self, title, text, markdown, html_body):
        url = f"https://api.telegram.org/bot{self.cfg['bot_token']}/sendMessage"
        opener = None
        if self.cfg.get("proxy"):
            proxy = urllib.request.ProxyHandler({"https": self.cfg["proxy"], "http": self.cfg["proxy"]})
            opener = urllib.request.build_opener(proxy)
            urllib.request.install_opener(opener)
        sent = 0
        for part in split_by_bytes(text, 3500):
            _post_json(url, {"chat_id": self.cfg["chat_id"], "text": part,
                             "disable_web_page_preview": True})
            sent += 1
            time.sleep(0.4)
        return True, f"已发送 {sent} 条"


# ---------------------------------------------------------------- 钉钉
class DingTalkChannel(Channel):
    name = "dingtalk"

    def send(self, title, text, markdown, html_body):
        url = self.cfg["webhook"]
        secret = self.cfg.get("secret")
        if secret:
            ts = str(round(time.time() * 1000))
            sign_str = f"{ts}\n{secret}"
            h = hmac.new(secret.encode(), sign_str.encode(), digestmod=hashlib.sha256).digest()
            sign = urllib.parse.quote_plus(base64.b64encode(h))
            url = f"{url}&timestamp={ts}&sign={sign}"
        for part in split_by_bytes(markdown, 18000):
            r = _post_json(url, {"msgtype": "markdown",
                                 "markdown": {"title": title[:60], "text": part}})
            if r.get("errcode") != 0:
                return False, str(r)
        return True, "ok"


# ---------------------------------------------------------------- 飞书
class FeishuChannel(Channel):
    name = "feishu"

    def send(self, title, text, markdown, html_body):
        r = _post_json(self.cfg["webhook"], {
            "msg_type": "text", "content": {"text": f"{title}\n\n{text}"}})
        ok = (r.get("code") == 0) or (r.get("StatusCode") == 0)
        return bool(ok), str(r)


REGISTRY = {c.name: c for c in [
    FileChannel, WeComBotChannel, WeComAppChannel, ServerChanChannel,
    WxPusherChannel, PushPlusChannel, EmailChannel, TelegramChannel,
    DingTalkChannel, FeishuChannel,
]}


def build_channels(channels_cfg: dict, ctx: dict, only: list[str] | None = None) -> list[Channel]:
    out = []
    for key, conf in channels_cfg.items():
        if key.startswith("_") or not isinstance(conf, dict):
            continue
        if only and key not in only:
            continue
        if not conf.get("enabled") and not (only and key in only):
            continue
        cls = REGISTRY.get(key)
        if cls is None:
            print(f"[warn] 未知渠道 {key}，已跳过")
            continue
        out.append(cls(conf, ctx))
    return out
