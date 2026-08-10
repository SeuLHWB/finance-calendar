# -*- coding: utf-8 -*-
"""事件数据模型。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

from .tzsupport import get_tz, tz_label

CATEGORY_LABEL = {
    "monetary": "货币政策",
    "macro": "宏观数据",
    "policy": "政策会议",
    "earnings": "龙头财报",
    "extra": "市场事件",
}

REGION_LABEL = {
    "CN": "🇨🇳 中国",
    "US": "🇺🇸 美国",
    "EU": "🇪🇺 欧元区",
    "JP": "🇯🇵 日本",
    "UK": "🇬🇧 英国",
    "HK": "🇭🇰 中国香港",
    "TW": "中国台湾",
    "GLOBAL": "🌐 全球",
}


@dataclass
class Event:
    """一条财经日历事件。"""

    uid: str = ""
    name: str = ""
    category: str = "macro"          # monetary/macro/policy/earnings/extra
    region: str = "GLOBAL"
    dt: datetime | None = None       # 带时区的事件时间（源时区）
    tz_name: str = "Asia/Shanghai"
    all_day: bool = False            # True 表示只有日期没有具体时刻
    window: str = ""                 # 时间窗口描述，如 "通常 9-15 日之间"
    importance: int = 3              # 1-5
    prev: str = ""                   # 前值
    forecast: str = ""               # 预期值
    actual: str = ""                 # 实际值（回填用）
    sectors: list = field(default_factory=list)   # 可能影响的行业板块
    note: str = ""
    source: str = "rule"             # rule/manual/earnings/http/akshare
    source_url: str = ""
    confidence: str = "high"         # high/medium/low —— low/medium 需人工核对
    tags: list = field(default_factory=list)

    # ---------- 派生属性 ----------
    def __post_init__(self):
        if not self.uid:
            raw = f"{self.name}|{self.dt.date() if self.dt else ''}|{self.region}"
            self.uid = hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]

    def local_dt(self, tz_name: str = "Asia/Shanghai") -> datetime:
        return self.dt.astimezone(get_tz(tz_name))

    @property
    def stars(self) -> str:
        n = max(1, min(5, int(self.importance)))
        return "★" * n + "☆" * (5 - n)

    @property
    def category_label(self) -> str:
        return CATEGORY_LABEL.get(self.category, self.category)

    @property
    def region_label(self) -> str:
        return REGION_LABEL.get(self.region, self.region)

    def time_text(self, tz_name: str = "Asia/Shanghai") -> str:
        """返回『本地时间（源时区标注）』文本。"""
        if self.all_day:
            return self.window or "全天"
        local = self.local_dt(tz_name)
        base = local.strftime("%H:%M")
        if self.tz_name != tz_name:
            src = self.dt.strftime("%H:%M")
            return f"{base}（{tz_label(tz_name)}）/ {src} {tz_label(self.tz_name)}"
        return f"{base}（{tz_label(tz_name)}）"

    def to_dict(self) -> dict:
        d = {
            "uid": self.uid,
            "name": self.name,
            "category": self.category,
            "region": self.region,
            "datetime": self.dt.isoformat() if self.dt else None,
            "tz": self.tz_name,
            "all_day": self.all_day,
            "window": self.window,
            "importance": self.importance,
            "prev": self.prev,
            "forecast": self.forecast,
            "actual": self.actual,
            "sectors": self.sectors,
            "note": self.note,
            "source": self.source,
            "source_url": self.source_url,
            "confidence": self.confidence,
            "tags": self.tags,
        }
        return d
