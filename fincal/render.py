# -*- coding: utf-8 -*-
"""渲染：纯文本 / Markdown（企业微信等） / HTML（邮件与本地预览）。"""
from __future__ import annotations

import html
from datetime import date, datetime

from .aggregate import group_by_date
from .models import Event

WEEK_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
CAT_ICON = {"monetary": "🏦", "macro": "📊", "policy": "🏛️", "earnings": "💰", "extra": "⚡"}
CONF_TAG = {"medium": "（日期待核对）", "low": "（日期为估算）"}


def _day_header(d: date, today: date) -> str:
    delta = (d - today).days
    if delta == 0:
        rel = "今天"
    elif delta == 1:
        rel = "明天"
    elif delta == 2:
        rel = "后天"
    else:
        rel = f"T+{delta}"
    return f"{d.month}月{d.day}日 {WEEK_CN[d.weekday()]} · {rel}"


def _star(e: Event) -> str:
    return "★" * max(1, min(5, e.importance))


def _values(e: Event) -> str:
    parts = []
    if e.forecast:
        parts.append(f"预期 {e.forecast}")
    if e.prev:
        parts.append(f"前值 {e.prev}")
    return " ｜ ".join(parts)


def top_highlights(events: list[Event], cfg: dict, n: int = 5) -> list[Event]:
    tz = cfg.get("timezone", "Asia/Shanghai")
    ranked = sorted(events, key=lambda e: (-e.importance, e.local_dt(tz)))
    return ranked[:n]


# --------------------------------------------------------------------------
def render_markdown(events: list[Event], cfg: dict, today: date | None = None) -> str:
    tz = cfg.get("timezone", "Asia/Shanghai")
    r = cfg.get("render", {})
    today = today or datetime.now().date()
    days = cfg.get("horizon_days", 30)
    lines = [cfg.get("title", "📅 未来 {days} 天财经日历").format(days=days)]
    lines.append(f"> 统计口径：{today.isoformat()} 起 {days} 天 ｜ 共 {len(events)} 条 ｜ 时间为{tz.split('/')[-1]}本地时间")
    lines.append("")

    hi = top_highlights(events, cfg, int(r.get("highlight_top", 5)))
    if hi:
        lines.append("**🔥 本期最需关注**")
        for e in hi:
            d = e.local_dt(tz)
            lines.append(f"> `{d.month}/{d.day}` <font color=\"warning\">{_star(e)}</font> {e.name}")
        lines.append("")

    grouped = group_by_date(events, tz)
    for d, evs in grouped.items():
        lines.append(f"**{_day_header(d, today)}**")
        for e in evs:
            icon = CAT_ICON.get(e.category, "•")
            head = f"{icon} `{e.time_text(tz) if not e.all_day else '全天'}` {e.name} {_star(e)}"
            lines.append(head)
            sub = []
            v = _values(e)
            if v:
                sub.append(v)
            if r.get("show_sectors", True) and e.sectors:
                sub.append("影响：" + "/".join(e.sectors[:6]))
            if r.get("show_confidence", True) and e.confidence in CONF_TAG:
                sub.append(CONF_TAG[e.confidence])
            if e.window:
                sub.append(e.window)
            if sub:
                lines.append(f"> <font color=\"comment\">{' ｜ '.join(sub)}</font>")
        lines.append("")
    lines.append("<font color=\"comment\">数据由本地规则库生成，标注『待核对/估算』的条目请以官方公告为准。</font>")
    return "\n".join(lines)


def render_text(events: list[Event], cfg: dict, today: date | None = None) -> str:
    tz = cfg.get("timezone", "Asia/Shanghai")
    today = today or datetime.now().date()
    days = cfg.get("horizon_days", 30)
    out = [cfg.get("title", "未来 {days} 天财经日历").format(days=days),
           "=" * 46,
           f"生成时间 {datetime.now().strftime('%Y-%m-%d %H:%M')} ｜ 共 {len(events)} 条", ""]
    for d, evs in group_by_date(events, tz).items():
        out.append(f"【{_day_header(d, today)}】")
        for e in evs:
            t = "全天" if e.all_day else e.local_dt(tz).strftime("%H:%M")
            out.append(f"  {t}  {_star(e):<5} {e.name}")
            sub = []
            v = _values(e)
            if v:
                sub.append(v)
            if e.sectors:
                sub.append("影响：" + "/".join(e.sectors[:6]))
            if e.confidence in CONF_TAG:
                sub.append(CONF_TAG[e.confidence])
            if e.window:
                sub.append(e.window)
            if sub:
                out.append("        " + " | ".join(sub))
        out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------
_HTML_CSS = """
:root{--bg:#f6f7f9;--card:#fff;--line:#e6e8eb;--text:#1a1d21;--muted:#6b7280;
--red:#d92b2b;--gold:#b8860b;--blue:#2563eb;--green:#0f9960;}
*{box-sizing:border-box}
body{margin:0;padding:24px 16px;background:var(--bg);color:var(--text);
font-family:-apple-system,"PingFang SC","Microsoft YaHei",Segoe UI,sans-serif;}
.wrap{max-width:760px;margin:0 auto}
.hd{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px 22px;margin-bottom:16px}
.hd h1{margin:0 0 6px;font-size:20px}
.hd .meta{color:var(--muted);font-size:13px}
.hl{background:linear-gradient(180deg,#fff7f0,#fff);border:1px solid #f1d9c4;border-radius:14px;
padding:14px 18px;margin-bottom:16px}
.hl h2{margin:0 0 10px;font-size:14px;color:#a04a00;letter-spacing:.5px}
.hl li{font-size:13.5px;margin:4px 0;list-style:none}
.hl ul{margin:0;padding:0}
.hl .d{display:inline-block;min-width:52px;color:var(--muted);font-variant-numeric:tabular-nums}
.day{background:var(--card);border:1px solid var(--line);border-radius:14px;margin-bottom:12px;overflow:hidden}
.day > .t{padding:10px 18px;background:#f0f2f5;font-size:13px;font-weight:600;border-bottom:1px solid var(--line)}
.day > .t .rel{color:var(--muted);font-weight:400;margin-left:6px}
.ev{padding:12px 18px;border-bottom:1px dashed var(--line)}
.ev:last-child{border-bottom:none}
.ev .row1{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.ev .tm{font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums;min-width:104px}
.ev .nm{font-size:14.5px;font-weight:600;flex:1;min-width:200px}
.ev .st{font-size:12px;color:var(--gold);letter-spacing:1px}
.ev .row2{margin-top:6px;font-size:12.5px;color:var(--muted);line-height:1.7}
.tag{display:inline-block;padding:1px 7px;border-radius:999px;font-size:11px;margin:2px 4px 0 0;
background:#eef2ff;color:#3b4b9a;border:1px solid #dde3ff}
.tag.cat-monetary{background:#fdeaea;color:#a01f1f;border-color:#f5cccc}
.tag.cat-macro{background:#e8f2ff;color:#14539a;border-color:#cfe2fb}
.tag.cat-policy{background:#fff4dd;color:#8a5b00;border-color:#f3e0b6}
.tag.cat-earnings{background:#eaf7ee;color:#186a3b;border-color:#cbe9d5}
.tag.cat-extra{background:#f1eefc;color:#5b3fa3;border-color:#ded5f7}
.warn{color:#b45309}
.ft{color:var(--muted);font-size:12px;text-align:center;padding:14px 0 4px;line-height:1.8}
"""


def render_html(events: list[Event], cfg: dict, today: date | None = None) -> str:
    tz = cfg.get("timezone", "Asia/Shanghai")
    today = today or datetime.now().date()
    days = cfg.get("horizon_days", 30)
    esc = html.escape
    p = []
    p.append("<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>")
    p.append("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    p.append(f"<title>财经日历 {today.isoformat()}</title><style>{_HTML_CSS}</style></head><body><div class='wrap'>")
    p.append("<div class='hd'><h1>" + esc(cfg.get("title", "📅 未来 {days} 天财经日历").format(days=days)) + "</h1>")
    p.append(f"<div class='meta'>生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')} ｜ "
             f"窗口 {today.isoformat()} → {(today.toordinal() + days) and date.fromordinal(today.toordinal() + days).isoformat()} ｜ "
             f"共 {len(events)} 条事件 ｜ 时间默认北京时间</div></div>")

    hi = top_highlights(events, cfg, int(cfg.get("render", {}).get("highlight_top", 5)))
    if hi:
        p.append("<div class='hl'><h2>🔥 本期最需关注</h2><ul>")
        for e in hi:
            d = e.local_dt(tz)
            p.append(f"<li><span class='d'>{d.month}/{d.day}</span> "
                     f"<span style='color:var(--gold)'>{_star(e)}</span> {esc(e.name)}</li>")
        p.append("</ul></div>")

    for d, evs in group_by_date(events, tz).items():
        delta = (d - today).days
        rel = {0: "今天", 1: "明天", 2: "后天"}.get(delta, f"T+{delta}")
        p.append(f"<div class='day'><div class='t'>{d.month}月{d.day}日 {WEEK_CN[d.weekday()]}"
                 f"<span class='rel'>{rel}</span></div>")
        for e in evs:
            tm = "全天" if e.all_day else esc(e.time_text(tz))
            p.append("<div class='ev'><div class='row1'>")
            p.append(f"<span class='tm'>{tm}</span>")
            p.append(f"<span class='nm'>{CAT_ICON.get(e.category,'')} {esc(e.name)}</span>")
            p.append(f"<span class='st'>{_star(e)}</span></div>")
            sub = []
            v = _values(e)
            if v:
                sub.append(esc(v))
            if e.window:
                sub.append(esc(e.window))
            if e.confidence in CONF_TAG:
                sub.append(f"<span class='warn'>{CONF_TAG[e.confidence]}</span>")
            if e.note:
                sub.append(esc(e.note))
            row2 = " ｜ ".join(sub)
            tags = f"<span class='tag cat-{e.category}'>{e.category_label}</span>" \
                   f"<span class='tag'>{esc(e.region_label)}</span>" + \
                   "".join(f"<span class='tag'>{esc(s)}</span>" for s in e.sectors[:8])
            p.append(f"<div class='row2'>{row2}<div>{tags}</div></div></div>")
        p.append("</div>")

    p.append("<div class='ft'>本日历由本地规则引擎生成，标注「日期待核对 / 估算」的条目请以官方公告为准。<br>"
             "配置文件：config/rules.json（宏观事件规则）· config/leaders.json（行业龙头财报）</div>")
    p.append("</div></body></html>")
    return "".join(p)
