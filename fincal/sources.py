# -*- coding: utf-8 -*-
"""事件数据源：规则源 / 手动补录源 / 龙头财报源 / 可配置 HTTP 源 / 突发事件源。"""
from __future__ import annotations

import json
import re
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path

from .models import Event
from .ruleengine import expand, occurrence_datetime
from .tzsupport import get_tz

MARKET_TZ = {"US": "America/New_York", "CN": "Asia/Shanghai", "HK": "Asia/Hong_Kong",
             "TW": "Asia/Taipei", "JP": "Asia/Tokyo", "EU": "Europe/Frankfurt"}
SESSION_TIME = {"bmo": "07:30", "amc": "16:20", "mid": "12:00"}
SESSION_LABEL = {"bmo": "美股盘前", "amc": "盘后", "mid": "盘中/收盘后"}

# ---- 数据月份标签映射 ----
# 月度数据（发布滞后1个月）：事件落在N月 → 标注(N-1)月
MONTHLY_LAG1 = {
    "us_cpi", "us_ppi", "us_pce", "us_nfp", "us_retail",
    "us_ism_mfg", "us_ism_svc",
    "cn_cpi_ppi", "cn_credit", "cn_monthly_econ", "cn_trade",
}
# 月度数据（当月发布当月值）
MONTHLY_SAME = {
    "cn_lpr", "cn_mlf", "cn_pmi_official", "cn_pmi_caixin",
    "cn_fx_reserve", "cn_index_futures_settle",
}
# 季度数据标签
QUARTERLY = {
    "cn_gdp": "Q{}GDP",
    "us_gdp": "Q{}GDP修正值",
}

def _data_label(rule_id, occ_date):
    """根据规则ID和事件日期生成数据月份/季度后缀标签。"""
    if rule_id in MONTHLY_LAG1:
        prev = occ_date.replace(day=1) - timedelta(days=1)
        return f"({prev.month}月)"
    if rule_id in MONTHLY_SAME:
        return f"({occ_date.month}月)"
    if rule_id in QUARTERLY:
        prev = occ_date.replace(day=1) - timedelta(days=1)
        q = (prev.month - 1) // 3 + 1
        return f"({QUARTERLY[rule_id].format(q)})"
    return ""

def _earning_quarter(d, market):
    """根据发布日期判断财报所属季度（近似，以公司公告为准）。"""
    m = d.month
    if market in ("CN", "HK", "TW"):
        # A股/港股财报季：年报3-4月，一季报4月，中报7-8月，三季报10月
        if m in (3, 4) and d.day <= 30:
            return "年报"
        if m == 4:
            return "一季报"
        if m in (7, 8):
            return "中报"
        if m in (10, 11):
            return "三季报"
        return ""
    else:
        # 美股/其他：Jan-Feb→Q4年报, Mar-May→Q1, Jun-Aug→Q2, Sep-Oct→Q3, Nov-Dec→Q4
        _MAP = {1: 4, 2: 4, 3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 2, 9: 3, 10: 3, 11: 4, 12: 4}
        q = _MAP.get(m, 1)
        return f"Q{q}财报"


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# 1) 规则源
# --------------------------------------------------------------------------
def load_rule_events(base: Path, cfg: dict, start: date, end: date) -> list[Event]:
    spec = cfg["sources"]["rules"]
    if not spec.get("enabled", True):
        return []
    data = _load_json(base / spec["file"])
    rules = data.get("rules", [])
    registry = {r["id"]: r for r in rules}
    holidays = cfg.get("holidays", {})
    events: list[Event] = []

    for rule in rules:
        tz = get_tz(rule.get("tz", "Asia/Shanghai"))
        try:
            occs = expand(rule, start, end, holidays, registry)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] 规则 {rule.get('id')} 展开失败: {exc}")
            continue
        for occ in occs:
            dt, all_day = occurrence_datetime(occ, tz)
            data_suffix = _data_label(rule.get("id", ""), occ.d)
            name = rule["name"] + data_suffix + (f" · {occ.label}" if occ.label else "")
            events.append(Event(
                name=name,
                category=rule.get("category", "macro"),
                region=rule.get("region", "GLOBAL"),
                dt=dt,
                tz_name=rule.get("tz", "Asia/Shanghai"),
                all_day=all_day,
                window=occ.window or rule.get("window", ""),
                importance=rule.get("importance", 3),
                sectors=list(rule.get("sectors", [])),
                note=rule.get("note", ""),
                source=f"rule:{rule['id']}",
                source_url=rule.get("source_url", ""),
                confidence=rule.get("confidence", "high"),
                tags=[rule["id"]],
            ))
    return events


# --------------------------------------------------------------------------
# 2) 手动补录源
# --------------------------------------------------------------------------
def _parse_dt(s: str, tz_name: str):
    tz = get_tz(tz_name)
    s = s.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        d = date.fromisoformat(s)
        return datetime(d.year, d.month, d.day, 9, 0, tzinfo=tz), True
    s2 = s.replace("T", " ")
    dt = datetime.strptime(s2[:16], "%Y-%m-%d %H:%M")
    return dt.replace(tzinfo=tz), False


def load_manual_events(base: Path, cfg: dict, start: date, end: date) -> list[Event]:
    spec = cfg["sources"]["manual"]
    if not spec.get("enabled", True):
        return []
    path = base / spec["file"]
    if not path.exists():
        return []
    data = _load_json(path)
    events = []
    for item in data.get("events", []):
        tz_name = item.get("tz", "Asia/Shanghai")
        try:
            dt, all_day = _parse_dt(item["datetime"], tz_name)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] 手动事件解析失败 {item.get('name')}: {exc}")
            continue
        if not (start <= dt.date() <= end):
            continue
        events.append(Event(
            name=item["name"],
            category=item.get("category", "extra"),
            region=item.get("region", "GLOBAL"),
            dt=dt,
            tz_name=tz_name,
            all_day=item.get("all_day", all_day),
            window=item.get("window", ""),
            importance=item.get("importance", 3),
            prev=item.get("prev", ""),
            forecast=item.get("forecast", ""),
            sectors=list(item.get("sectors", [])),
            note=item.get("note", ""),
            source="manual",
            source_url=item.get("source_url", ""),
            confidence=item.get("confidence", "high"),
        ))
    return events


# --------------------------------------------------------------------------
# 3) 龙头财报源
# --------------------------------------------------------------------------
def _anchor_dates(anchor_md: str, start: date, end: date) -> list[date]:
    """把 'MM-DD' 展开到区间内可能的年份。"""
    mm, dd = (int(x) for x in anchor_md.split("-"))
    out = []
    for y in range(start.year - 1, end.year + 2):
        try:
            out.append(date(y, mm, min(dd, monthrange(y, mm)[1])))
        except ValueError:
            pass
    return out


def load_earnings_events(base: Path, cfg: dict, start: date, end: date) -> list[Event]:
    spec = cfg["sources"]["earnings"]
    if not spec.get("enabled", True):
        return []
    data = _load_json(base / spec["file"])
    only = set(spec.get("industries") or [])
    events: list[Event] = []

    for industry, companies in data.get("industries", {}).items():
        if only and industry not in only:
            continue
        for c in companies:
            market = c.get("market", "US")
            tz_name = MARKET_TZ.get(market, "Asia/Shanghai")
            tz = get_tz(tz_name)
            session = c.get("session", "amc")
            time_s = SESSION_TIME.get(session, "16:20")
            win_days = int(c.get("window_days", 5))
            base_sectors = [industry] + list(c.get("sectors", []))

            # 3a. 已确认的精确日期优先
            confirmed = {d[:10] for d in c.get("confirmed", [])}
            for ds in sorted(confirmed):
                d = date.fromisoformat(ds)
                if start <= d <= end:
                    events.append(_mk_earning(c, industry, d, time_s, tz, tz_name,
                                              base_sectors, session, "", "high"))

            # 3b. 每月营收类
            if c.get("monthly_day"):
                day = int(c["monthly_day"])
                cur = date(start.year, start.month, 1)
                while cur <= end:
                    d = date(cur.year, cur.month, min(day, monthrange(cur.year, cur.month)[1]))
                    if start <= d <= end and d.isoformat() not in confirmed:
                        events.append(_mk_earning(
                            c, industry, d, "14:00", tz, tz_name, base_sectors, "mid",
                            f"预计 {d.month}月{max(1, day - win_days)}-{day + win_days}日 公布",
                            "medium"))
                    cur = (date(cur.year + 1, 1, 1) if cur.month == 12
                           else date(cur.year, cur.month + 1, 1))
                continue

            # 3c. anchors 近似
            for md in c.get("anchors", []):
                for d in _anchor_dates(md, start, end):
                    if start <= d <= end and d.isoformat() not in confirmed:
                        lo = d - timedelta(days=win_days)
                        hi = d + timedelta(days=win_days)
                        events.append(_mk_earning(
                            c, industry, d, time_s, tz, tz_name, base_sectors, session,
                            f"预计 {lo.month}/{lo.day} - {hi.month}/{hi.day}，以公司公告为准",
                            "medium"))
    return events


def _to_weekday(d: date) -> date:
    """财报只会在交易日发布：周六前移到周五，周日后移到周一。"""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def _dedupe_keep_order(items):
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _mk_earning(c, industry, d, time_s, tz, tz_name, sectors, session, window, confidence):
    d = _to_weekday(d)
    sectors = _dedupe_keep_order(sectors)
    hh, mm = time_s.split(":")
    dt = datetime(d.year, d.month, d.day, int(hh), int(mm), tzinfo=tz)
    label = SESSION_LABEL.get(session, "")
    q_label = _earning_quarter(d, c.get("market", "US"))
    name = f"{c['name']}（{c['code']}）{q_label}" + (f" · {label}" if label else "")
    return Event(
        name=name,
        category="earnings",
        region={"US": "US", "CN": "CN", "HK": "HK", "TW": "TW"}.get(c.get("market", "US"), "GLOBAL"),
        dt=dt,
        tz_name=tz_name,
        all_day=False,
        window=window,
        importance=c.get("importance", 4),
        sectors=sectors,
        note=c.get("note", ""),
        source=f"earnings:{c['code']}",
        confidence=confidence,
        tags=[industry, c["code"]],
    )


# --------------------------------------------------------------------------
# 4) 可配置 HTTP 源（自动抓取）
# --------------------------------------------------------------------------
def _dig(obj, path: str):
    cur = obj
    for part in [p for p in path.split(".") if p]:
        if isinstance(cur, list):
            cur = cur[int(part)]
        else:
            cur = cur.get(part)
        if cur is None:
            return None
    return cur


def load_http_events(cfg: dict, start: date, end: date) -> list[Event]:
    import urllib.request

    events: list[Event] = []
    for spec in cfg["sources"].get("http", []):
        if not spec.get("enabled"):
            continue
        try:
            req = urllib.request.Request(spec["url"], headers=spec.get("headers", {}) or
                                         {"User-Agent": "Mozilla/5.0 fincal/1.0"})
            with urllib.request.urlopen(req, timeout=spec.get("timeout", 20)) as resp:
                payload = json.loads(resp.read().decode("utf-8", "ignore"))
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] HTTP 源 {spec.get('name')} 抓取失败: {exc}")
            continue

        rows = _dig(payload, spec.get("root", "")) if spec.get("root") else payload
        if not isinstance(rows, list):
            print(f"[warn] HTTP 源 {spec.get('name')} root 未指向数组")
            continue

        m = spec.get("mapping", {})
        for row in rows:
            try:
                tz_name = m.get("tz", "Asia/Shanghai")
                dt, all_day = _parse_dt(str(_dig(row, m["datetime"])), tz_name)
                if not (start <= dt.date() <= end):
                    continue
                events.append(Event(
                    name=str(_dig(row, m["name"])),
                    category=m.get("category", "macro"),
                    region=str(_dig(row, m["region"])) if m.get("region") else "GLOBAL",
                    dt=dt, tz_name=tz_name, all_day=all_day,
                    importance=int(_dig(row, m["importance"]) or 3) if m.get("importance") else 3,
                    prev=str(_dig(row, m["prev"]) or "") if m.get("prev") else "",
                    forecast=str(_dig(row, m["forecast"]) or "") if m.get("forecast") else "",
                    sectors=list(spec.get("default_sectors", [])),
                    source=f"http:{spec.get('name', 'custom')}",
                    source_url=spec.get("url", ""),
                    confidence="high",
                ))
            except Exception:  # noqa: BLE001
                continue
    return events


# --------------------------------------------------------------------------
# 5) 突发事件源
# --------------------------------------------------------------------------
def load_breaking_events(base: Path, cfg: dict, start: date, end: date) -> list[Event]:
    path = base / cfg.get("breaking_file", "data/events_breaking.json")
    if not path.exists():
        return []
    data = _load_json(path)
    events = []
    for item in data.get("events", []):
        if item.get("resolved"):
            continue
        tz_name = item.get("tz", "Asia/Shanghai")
        try:
            dt, all_day = _parse_dt(item["datetime"], tz_name)
        except Exception:
            continue
        if not (start <= dt.date() <= end):
            continue
        events.append(Event(
            name=f"🚨 {item['name']}",
            category="breaking",
            region=item.get("region", "GLOBAL"),
            dt=dt,
            tz_name=tz_name,
            all_day=item.get("all_day", True),
            window="",
            importance=item.get("importance", 5),
            sectors=list(item.get("sectors", ["全市场"])),
            note=item.get("note", ""),
            source="breaking",
            source_url=item.get("source_url", ""),
            confidence=item.get("confidence", "high"),
            tags=["breaking"],
        ))
    return events


# --------------------------------------------------------------------------
def load_all(base: Path, cfg: dict, start: date, end: date) -> list[Event]:
    events: list[Event] = []
    events += load_rule_events(base, cfg, start, end)
    events += load_manual_events(base, cfg, start, end)
    events += load_earnings_events(base, cfg, start, end)
    events += load_http_events(cfg, start, end)
    events += load_breaking_events(base, cfg, start, end)
    return events
