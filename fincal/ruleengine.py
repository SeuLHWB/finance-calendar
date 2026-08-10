# -*- coding: utf-8 -*-
"""日期规则引擎：把 rules.json 中的调度规则展开为具体日期。

支持的 schedule.type：
  fixed_dates      固定日期列表          {"dates": ["2026-09-16", ...]}
  month_day        每年某月某日          {"month": 3, "day": 5}
  day_of_month     每月某日              {"day": 20, "months": "*"}
  nth_weekday      每月第 n 个星期几      {"n": 1, "weekday": "FRI", "months": "*"}  n=-1 表示倒数
  nth_business_day 每月第 n 个工作日      {"n": 1, "months": "*"}
  last_day_of_month每月最后一日           {"months": "*"}
  weekly           每周某天              {"weekday": "THU"}
  day_window       每月某个日期区间       {"from": 9, "to": 15, "anchor": 12, "months": "*"}
  annual_window    每年某月的日期区间     {"month": 12, "from": 8, "to": 14}
  offset_days      相对另一规则偏移       {"base": "fomc_meeting", "days": 21}

公共可选字段：
  adjust: none | next_business | prev_business   （遇周末/节假日的顺延方式）
  skip_months: [1, 2]                            （跳过的月份）
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta

from .tzsupport import nth_weekday

WEEKDAYS = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}

# 简易节假日表（可在 config/settings.json -> holidays 覆盖/扩展）
DEFAULT_HOLIDAYS: dict[str, list[str]] = {"CN": [], "US": [], "EU": [], "JP": [], "GLOBAL": []}


def _is_business(d: date, region: str, holidays: dict) -> bool:
    if d.weekday() >= 5:
        return False
    return d.isoformat() not in set(holidays.get(region, []))


def _adjust(d: date, mode: str, region: str, holidays: dict) -> date:
    if mode in (None, "", "none"):
        return d
    step = 1 if mode == "next_business" else -1
    guard = 0
    while not _is_business(d, region, holidays) and guard < 15:
        d = d + timedelta(days=step)
        guard += 1
    return d


def _months_of(sch: dict) -> list[int]:
    m = sch.get("months", "*")
    if m == "*" or m is None:
        return list(range(1, 13))
    if isinstance(m, int):
        return [m]
    return [int(x) for x in m]


def _iter_year_month(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        m += 1
        if m > 12:
            m, y = 1, y + 1


def _clamp(d: date, start: date, end: date) -> bool:
    return start <= d <= end


class Occurrence:
    """一次事件发生：日期 + 可选时刻 + 窗口说明。"""

    __slots__ = ("d", "time", "window", "label", "extra")

    def __init__(self, d: date, time: str | None = None, window: str = "",
                 label: str = "", extra: dict | None = None):
        self.d = d
        self.time = time
        self.window = window
        self.label = label
        self.extra = extra or {}


def expand(rule: dict, start: date, end: date, holidays: dict | None = None,
           registry: dict | None = None) -> list[Occurrence]:
    """把单条规则在 [start, end] 区间内展开。registry 用于 offset_days 引用其他规则。"""
    holidays = holidays or DEFAULT_HOLIDAYS
    sch = rule.get("schedule", {})
    typ = sch.get("type")
    region = rule.get("region", "GLOBAL")
    adjust = sch.get("adjust", "none")
    skip_months = set(sch.get("skip_months", []))
    default_time = rule.get("time")
    out: list[Occurrence] = []

    def add(d: date, time_s=None, window="", label="", extra=None):
        if d.month in skip_months:
            return
        d2 = _adjust(d, adjust, region, holidays)
        if _clamp(d2, start, end):
            out.append(Occurrence(d2, time_s if time_s is not None else default_time,
                                  window, label, extra))

    if typ == "fixed_dates":
        for item in sch.get("dates", []):
            if isinstance(item, dict):
                d = date.fromisoformat(item["date"])
                add(d, item.get("time"), item.get("window", ""), item.get("label", ""))
            else:
                add(date.fromisoformat(item))

    elif typ == "month_day":
        for y in range(start.year, end.year + 1):
            try:
                add(date(y, int(sch["month"]), int(sch["day"])))
            except ValueError:
                pass

    elif typ == "day_of_month":
        months = _months_of(sch)
        day = int(sch["day"])
        for y, m in _iter_year_month(start, end):
            if m not in months:
                continue
            dd = min(day, monthrange(y, m)[1])
            add(date(y, m, dd))

    elif typ == "nth_weekday":
        months = _months_of(sch)
        wd = WEEKDAYS[str(sch.get("weekday", "FRI")).upper()]
        n = int(sch.get("n", 1))
        for y, m in _iter_year_month(start, end):
            if m not in months:
                continue
            try:
                add(nth_weekday(y, m, wd, n).date())
            except ValueError:
                pass

    elif typ == "nth_business_day":
        months = _months_of(sch)
        n = int(sch.get("n", 1))
        for y, m in _iter_year_month(start, end):
            if m not in months:
                continue
            cnt, dd = 0, 1
            last = monthrange(y, m)[1]
            while dd <= last:
                cur = date(y, m, dd)
                if _is_business(cur, region, holidays):
                    cnt += 1
                    if cnt == n:
                        add(cur)
                        break
                dd += 1

    elif typ == "last_day_of_month":
        months = _months_of(sch)
        for y, m in _iter_year_month(start, end):
            if m not in months:
                continue
            add(date(y, m, monthrange(y, m)[1]))

    elif typ == "weekly":
        wd = WEEKDAYS[str(sch.get("weekday", "THU")).upper()]
        cur = start
        while cur <= end:
            if cur.weekday() == wd:
                add(cur)
            cur += timedelta(days=1)

    elif typ == "day_window":
        months = _months_of(sch)
        a, b = int(sch["from"]), int(sch["to"])
        anchor = int(sch.get("anchor", (a + b) // 2))
        for y, m in _iter_year_month(start, end):
            if m not in months:
                continue
            last = monthrange(y, m)[1]
            add(date(y, m, min(anchor, last)),
                window=f"预计 {m}月{a}-{min(b, last)}日 公布")

    elif typ == "annual_window":
        mo = int(sch["month"])
        a, b = int(sch["from"]), int(sch["to"])
        anchor = int(sch.get("anchor", (a + b) // 2))
        for y in range(start.year, end.year + 1):
            add(date(y, mo, anchor), window=f"预计 {mo}月{a}-{b}日 召开")

    elif typ == "offset_days":
        base_id = sch.get("base")
        base_rule = (registry or {}).get(base_id)
        if base_rule:
            wide_start = start - timedelta(days=120)
            wide_end = end + timedelta(days=120)
            for occ in expand(base_rule, wide_start, wide_end, holidays, registry):
                add(occ.d + timedelta(days=int(sch.get("days", 0))))

    else:
        raise ValueError(f"unsupported schedule type: {typ!r}")

    out.sort(key=lambda o: (o.d, o.time or ""))
    return out


def occurrence_datetime(occ: Occurrence, tz) -> tuple[datetime, bool]:
    """把 Occurrence 转成带时区的 datetime；返回 (dt, all_day)。"""
    if occ.time:
        hh, mm = str(occ.time).split(":")[:2]
        return datetime(occ.d.year, occ.d.month, occ.d.day, int(hh), int(mm), tzinfo=tz), False
    return datetime(occ.d.year, occ.d.month, occ.d.day, 9, 0, tzinfo=tz), True
