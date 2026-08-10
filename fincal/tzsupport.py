# -*- coding: utf-8 -*-
"""时区支持。

优先使用标准库 zoneinfo(需要 tzdata，Windows 上常缺失)；
不可用时回退到内置的固定偏移 + 美/欧夏令时规则实现，保证零依赖可运行。
"""
from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta, tzinfo

_ZONEINFO = None
try:  # pragma: no cover
    from zoneinfo import ZoneInfo as _ZI

    _ZI("America/New_York")  # 探测 tzdata 是否可用
    _ZONEINFO = _ZI
except Exception:  # noqa: BLE001
    _ZONEINFO = None


def nth_weekday(year: int, month: int, weekday: int, n: int) -> datetime:
    """第 n 个星期几。weekday: Mon=0 .. Sun=6；n>=1 正数第 n 个，n=-1 倒数第一个。"""
    if n > 0:
        first = datetime(year, month, 1)
        offset = (weekday - first.weekday()) % 7
        day = 1 + offset + (n - 1) * 7
    else:
        last_day = monthrange(year, month)[1]
        last = datetime(year, month, last_day)
        offset = (last.weekday() - weekday) % 7
        day = last_day - offset - (abs(n) - 1) * 7
    if day < 1 or day > monthrange(year, month)[1]:
        raise ValueError("no such weekday occurrence")
    return datetime(year, month, day)


class _RuleTZ(tzinfo):
    """内置时区：固定标准偏移 + 可选夏令时规则('us' / 'eu' / None)。"""

    def __init__(self, key: str, std_hours: float, rule: str | None,
                 std_name: str, dst_name: str = ""):
        self._key = key
        self._std = std_hours
        self._rule = rule
        self._std_name = std_name
        self._dst_name = dst_name or std_name

    # --- tzinfo 接口 ---
    def utcoffset(self, dt):
        base = timedelta(hours=self._std)
        return base + timedelta(hours=1) if self._is_dst(dt) else base

    def dst(self, dt):
        return timedelta(hours=1) if self._is_dst(dt) else timedelta(0)

    def tzname(self, dt):
        return self._dst_name if self._is_dst(dt) else self._std_name

    def __repr__(self):
        return f"<TZ {self._key}>"

    # --- 内部 ---
    def _is_dst(self, dt) -> bool:
        if not self._rule or dt is None:
            return False
        naive = dt.replace(tzinfo=None)
        y = naive.year
        try:
            if self._rule == "us":
                # 3月第二个周日 02:00 起，11月第一个周日 02:00 止
                start = nth_weekday(y, 3, 6, 2) + timedelta(hours=2)
                end = nth_weekday(y, 11, 6, 1) + timedelta(hours=2)
            else:  # eu：3月最后一个周日 01:00 UTC 起，10月最后一个周日 01:00 UTC 止
                start = nth_weekday(y, 3, 6, -1) + timedelta(hours=1 + self._std)
                end = nth_weekday(y, 10, 6, -1) + timedelta(hours=1 + self._std)
        except ValueError:
            return False
        return start <= naive < end


_FALLBACK = {
    "UTC": (0, None, "UTC"),
    "Asia/Shanghai": (8, None, "CST"),
    "Asia/Hong_Kong": (8, None, "HKT"),
    "Asia/Taipei": (8, None, "CST"),
    "Asia/Tokyo": (9, None, "JST"),
    "Asia/Seoul": (9, None, "KST"),
    "Asia/Singapore": (8, None, "SGT"),
    "America/New_York": (-5, "us", "EST", "EDT"),
    "America/Chicago": (-6, "us", "CST", "CDT"),
    "America/Los_Angeles": (-8, "us", "PST", "PDT"),
    "Europe/London": (0, "eu", "GMT", "BST"),
    "Europe/Berlin": (1, "eu", "CET", "CEST"),
    "Europe/Frankfurt": (1, "eu", "CET", "CEST"),
    "Europe/Paris": (1, "eu", "CET", "CEST"),
    "Europe/Zurich": (1, "eu", "CET", "CEST"),
}

# 面向中文用户的时区口语标签
TZ_LABEL = {
    "Asia/Shanghai": "北京时间",
    "Asia/Hong_Kong": "香港时间",
    "Asia/Taipei": "台北时间",
    "Asia/Tokyo": "东京时间",
    "Asia/Seoul": "首尔时间",
    "America/New_York": "美东时间",
    "America/Chicago": "美中时间",
    "America/Los_Angeles": "美西时间",
    "Europe/London": "伦敦时间",
    "Europe/Berlin": "欧洲中部时间",
    "Europe/Frankfurt": "法兰克福时间",
    "Europe/Paris": "巴黎时间",
    "UTC": "UTC",
}

_CACHE: dict[str, tzinfo] = {}


def get_tz(name: str) -> tzinfo:
    if name in _CACHE:
        return _CACHE[name]
    tz = None
    if _ZONEINFO is not None:
        try:
            tz = _ZONEINFO(name)
        except Exception:  # noqa: BLE001
            tz = None
    if tz is None:
        spec = _FALLBACK.get(name) or _FALLBACK["UTC"]
        tz = _RuleTZ(name, spec[0], spec[1], spec[2], spec[3] if len(spec) > 3 else "")
    _CACHE[name] = tz
    return tz


def tz_label(name: str) -> str:
    return TZ_LABEL.get(name, name)


def backend() -> str:
    return "zoneinfo(tzdata)" if _ZONEINFO is not None else "builtin-rules"
