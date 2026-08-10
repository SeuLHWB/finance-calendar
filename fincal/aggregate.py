# -*- coding: utf-8 -*-
"""事件聚合：去重、过滤、排序、分组。"""
from __future__ import annotations

from collections import OrderedDict
from datetime import date

from .models import Event


def dedupe(events: list[Event]) -> list[Event]:
    """同一天 + 同名（去掉修饰）视为重复，保留重要性更高、confidence 更高的一条。"""
    rank = {"high": 3, "medium": 2, "low": 1}
    best: dict[tuple, Event] = {}
    for e in events:
        key = (e.dt.date(), e.name.split("（")[0].split(" · ")[0], e.region)
        cur = best.get(key)
        if cur is None or (e.importance, rank.get(e.confidence, 0)) > \
                (cur.importance, rank.get(cur.confidence, 0)):
            best[key] = e
    return list(best.values())


def apply_filters(events: list[Event], f: dict) -> list[Event]:
    min_imp = int(f.get("min_importance", 1))
    cats = set(f.get("categories") or [])
    regions = set(f.get("regions") or [])
    sectors = set(f.get("sectors") or [])
    excl_ids = set(f.get("exclude_rule_ids") or [])
    blacklist = [k for k in (f.get("keyword_blacklist") or []) if k]

    out = []
    for e in events:
        if e.importance < min_imp:
            continue
        if cats and e.category not in cats:
            continue
        if regions and e.region not in regions:
            continue
        if sectors and not (sectors & set(e.sectors) or sectors & set(e.tags)):
            continue
        rid = e.source.split(":", 1)[1] if ":" in e.source else ""
        if rid and rid in excl_ids:
            continue
        if any(k in e.name for k in blacklist):
            continue
        out.append(e)
    return out


def sort_events(events: list[Event], tz_name: str) -> list[Event]:
    return sorted(events, key=lambda e: (e.local_dt(tz_name), -e.importance, e.name))


def group_by_date(events: list[Event], tz_name: str) -> "OrderedDict[date, list[Event]]":
    grouped: "OrderedDict[date, list[Event]]" = OrderedDict()
    for e in sort_events(events, tz_name):
        grouped.setdefault(e.local_dt(tz_name).date(), []).append(e)
    return grouped


def build(events: list[Event], cfg: dict, overrides: dict | None = None) -> list[Event]:
    f = dict(cfg.get("filters", {}))
    f.update({k: v for k, v in (overrides or {}).items() if v is not None})
    evs = dedupe(events)
    evs = apply_filters(evs, f)
    evs = sort_events(evs, cfg.get("timezone", "Asia/Shanghai"))
    max_n = int(cfg.get("render", {}).get("max_events", 60))
    return evs[:max_n]
