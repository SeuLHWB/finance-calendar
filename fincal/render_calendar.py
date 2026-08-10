"""Render financial calendar as a visual HTML page with calendar grid + countdown."""
import json, os, sys
from datetime import datetime, timedelta, date

def load_events(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def to_beijing_str(ev):
    """Return (datetime, date_str, time_str) in Beijing time."""
    dt_str = ev["datetime"]
    from datetime import timezone, timedelta as td
    # Parse ISO datetime
    dt = datetime.fromisoformat(dt_str)
    # Convert to +08:00
    tz_beijing = timezone(td(hours=8))
    bj3 = dt.astimezone(tz_beijing)
    d_str = f"{bj3.month}/{bj3.day}"
    if ev.get("all_day"):
        t_str = "全天"
    else:
        t_str = f"{bj3.hour:02d}:{bj3.minute:02d}"
    return bj3, d_str, t_str

def trading_days_between(start_date, end_date):
    """Count Mon-Fri days between two dates (exclusive of start, inclusive of end)."""
    if end_date <= start_date:
        return 0
    days = 0
    cur = start_date + timedelta(days=1)
    while cur <= end_date:
        if cur.weekday() < 5:  # Mon-Fri
            days += 1
        cur += timedelta(days=1)
    return days

def calendar_days_between(start_date, end_date):
    return (end_date - start_date).days

def star_str(n):
    return "★" * n + "☆" * (5 - n)

def star_color(n):
    if n >= 5: return "#e74c3c"
    if n >= 4: return "#e67e22"
    if n >= 3: return "#2980b9"
    return "#7f8c8d"

def category_icon(cat):
    m = {
        "monetary": "🏦",
        "macro": "📊",
        "earnings": "💰",
        "extra": "⚡",
        "policy": "🏛️",
        "breaking": "🚨",
    }
    return m.get(cat, "📌")

def generate_html(events, today_str):
    today = datetime.strptime(today_str, "%Y-%m-%d").date()
    
    # Sort by datetime
    events.sort(key=lambda e: e["datetime"])
    
    # Calculate countdowns
    enriched = []
    for ev in events:
        bj_dt, d_str, t_str = to_beijing_str(ev)
        ev_date = bj_dt.date()
        cal_days = calendar_days_between(today, ev_date)
        t_days = trading_days_between(today, ev_date)
        enriched.append({
            **ev,
            "bj_dt": bj_dt,
            "d_str": d_str,
            "t_str": t_str,
            "cal_days": cal_days,
            "t_days": t_days,
            "ev_date": ev_date,
        })
    
    # TOP10 by importance then by date (breaking events always come first)
    top10 = sorted(enriched, key=lambda e: (-(100 if e.get("category") == "breaking" else 0), -e["importance"], e["datetime"]))[:10]
    
    # Calendar grid: find the range
    start_date = today
    end_date = today + timedelta(days=30)
    
    # Build calendar weeks (starting from Monday)
    # Find the Monday on or before start_date
    cal_start = start_date - timedelta(days=start_date.weekday())
    cal_end = end_date + timedelta(days=(6 - end_date.weekday()))
    
    # Group events by date
    events_by_date = {}
    for ev in enriched:
        key = ev["ev_date"]
        if key not in events_by_date:
            events_by_date[key] = []
        events_by_date[key].append(ev)
    
    # Build calendar weeks
    weeks = []
    cur = cal_start
    while cur <= cal_end:
        week = []
        for i in range(7):
            week.append(cur)
            cur += timedelta(days=1)
        weeks.append(week)
    
    # Month labels
    months_seen = []
    cur = cal_start
    while cur <= cal_end:
        if (cur.year, cur.month) not in months_seen:
            months_seen.append((cur.year, cur.month))
        cur += timedelta(days=1)
    
    total = len(events)
    
    # Generate HTML
    html_parts = []
    html_parts.append(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>财经日历 · {today_str}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ 
    font-family: -apple-system, "Microsoft YaHei", "Segoe UI", sans-serif;
    background: #f0f2f5;
    color: #2c3e50;
    padding: 20px;
    max-width: 1200px;
    margin: 0 auto;
}}
.header {{
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    color: white;
    border-radius: 16px;
    padding: 28px 32px;
    margin-bottom: 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}}
.header h1 {{ font-size: 24px; font-weight: 700; }}
.header .subtitle {{ font-size: 13px; color: #a0aec0; margin-top: 4px; }}
.header .stats {{ text-align: right; }}
.header .stats .big {{ font-size: 32px; font-weight: 800; color: #e74c3c; }}
.header .stats .label {{ font-size: 12px; color: #a0aec0; }}

.top10-section {{
    background: white;
    border-radius: 16px;
    padding: 24px;
    margin-bottom: 20px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}}
.section-title {{
    font-size: 18px;
    font-weight: 700;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
}}
.section-title .fire {{ font-size: 22px; }}

.top10-list {{
    display: grid;
    grid-template-columns: 1fr;
    gap: 2px;
}}
.top10-item {{
    display: grid;
    grid-template-columns: 80px 56px 1fr 90px 100px 140px;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    border-radius: 8px;
    font-size: 14px;
    transition: background 0.15s;
    border-bottom: 1px solid #f0f0f0;
}}
.top10-item:hover {{ background: #f7f8fa; }}
.top10-item .date {{ font-weight: 600; color: #2c3e50; }}
.top10-item .time {{ font-size: 12px; color: #95a5a6; text-align: right; }}
.top10-item .name {{ font-weight: 500; }}
.top10-item .stars {{ font-size: 13px; }}
.top10-item .countdown {{
    font-size: 12px;
    text-align: center;
    padding: 4px 8px;
    border-radius: 6px;
    font-weight: 600;
}}
.countdown-urgent {{ background: #fce4e4; color: #e74c3c; }}
.countdown-soon {{ background: #fff3e0; color: #e67e22; }}
.countdown-normal {{ background: #e8f5e9; color: #27ae60; }}
.top10-item .sectors {{ font-size: 12px; color: #7f8c8d; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.top10-item .warn {{ color: #e74c3c; font-size: 11px; margin-left: 4px; }}

.calendar-section {{
    background: white;
    border-radius: 16px;
    padding: 24px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}}
.cal-month-header {{
    font-size: 16px;
    font-weight: 700;
    margin-bottom: 12px;
    color: #2c3e50;
}}
.cal-grid {{
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 4px;
    margin-bottom: 20px;
}}
.cal-weekday {{
    text-align: center;
    font-size: 12px;
    font-weight: 600;
    color: #95a5a6;
    padding: 6px 0;
}}
.cal-weekday.weekend {{ color: #e74c3c; }}
.cal-day {{
    min-height: 100px;
    border: 1px solid #eee;
    border-radius: 8px;
    padding: 4px;
    font-size: 12px;
    overflow: hidden;
}}
.cal-day.other-month {{ background: #fafafa; color: #ccc; }}
.cal-day.today {{ border: 2px solid #e74c3c; background: #fff5f5; }}
.cal-day .day-num {{
    font-weight: 600;
    font-size: 13px;
    padding: 2px 6px;
    display: inline-block;
}}
.cal-day.today .day-num {{ color: #e74c3c; }}
.cal-day.weekend .day-num {{ color: #e74c3c; }}
.cal-event {{
    margin-top: 3px;
    padding: 2px 5px;
    border-radius: 4px;
    font-size: 10px;
    line-height: 1.3;
    cursor: default;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.cal-event.imp5 {{ background: #fce4e4; color: #c0392b; font-weight: 600; border-left: 3px solid #e74c3c; }}
.cal-event.imp4 {{ background: #fff3e0; color: #d35400; border-left: 3px solid #e67e22; }}
.cal-event.imp3 {{ background: #e8f4fd; color: #2471a3; border-left: 3px solid #2980b9; }}
.cal-event.breaking {{ background: #2c1810; color: #ff6b35; font-weight: 700; border-left: 3px solid #ff4444; animation: blink-border 1.5s ease-in-out infinite; }}
.cal-event .ev-time {{ font-size: 9px; color: #999; }}
.cal-event .ev-countdown {{
    display: inline-block;
    font-size: 9px;
    background: rgba(0,0,0,0.08);
    padding: 0 3px;
    border-radius: 3px;
    margin-left: 2px;
}}

.legend {{
    display: flex;
    gap: 16px;
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid #eee;
    font-size: 12px;
    color: #7f8c8d;
    flex-wrap: wrap;
}}
.legend-item {{ display: flex; align-items: center; gap: 4px; }}
.legend-dot {{ width: 12px; height: 12px; border-radius: 3px; }}

.footer {{
    text-align: center;
    font-size: 11px;
    color: #bdc3c7;
    margin-top: 20px;
    padding: 12px;
}}

@media (max-width: 768px) {{
    body {{ padding: 10px; }}
    .header {{ padding: 20px; }}
    .header h1 {{ font-size: 18px; }}
    .header .stats .big {{ font-size: 24px; }}

    /* TOP10 → stacked cards */
    .top10-item {{
        display: flex;
        flex-wrap: wrap;
        gap: 6px 10px;
        padding: 12px;
        border-radius: 10px;
        border: 1px solid #eee;
        margin-bottom: 6px;
        font-size: 14px;
    }}
    .top10-item .date {{ font-size: 16px; font-weight: 700; }}
    .top10-item .time {{ font-size: 13px; color: #555; }}
    .top10-item .name {{ font-size: 14px; font-weight: 600; width: 100%; }}
    .top10-item .stars {{ font-size: 14px; }}
    .top10-item .countdown {{ font-size: 13px; padding: 3px 8px; }}
    .top10-item .sectors {{
        font-size: 12px;
        color: #666;
        width: 100%;
        white-space: normal;
        overflow: visible;
        background: #f7f8fa;
        padding: 4px 8px;
        border-radius: 4px;
    }}
    .top10-item .warn {{ font-size: 12px; }}

    /* Calendar → horizontally scrollable grid */
    .calendar-section {{ padding: 12px; }}
    .cal-scroll-wrapper {{
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        margin: 0 -12px;
        padding: 0 12px;
    }}
    .cal-grid {{
        min-width: 700px;
        gap: 3px;
    }}
    .cal-day {{
        min-height: 90px;
        padding: 4px 3px;
    }}
    .cal-day .day-num {{ font-size: 12px; }}
    .cal-event {{
        font-size: 10px;
        white-space: normal;
        overflow: visible;
        text-overflow: unset;
        padding: 3px 5px;
        margin-top: 2px;
        line-height: 1.4;
    }}
    .cal-event .ev-time {{ font-size: 9px; display: inline; }}
    .cal-event .ev-countdown {{ font-size: 9px; }}

    .legend {{ flex-direction: column; gap: 4px; }}
}}

@keyframes blink-border {{
    0%, 100% {{ border-left-color: #ff4444; }}
    50% {{ border-left-color: #ffaa00; }}
}}
</style>
</head>
<body>
""")

    # Header
    html_parts.append(f"""
<div class="header">
    <div>
        <h1>📅 财经日历</h1>
        <div class="subtitle">{today_str} · 未来30天 · 北京时间</div>
    </div>
    <div class="stats">
        <div class="big">{total}</div>
        <div class="label">条事件</div>
    </div>
</div>
""")

    # TOP10
    html_parts.append("""
<div class="top10-section">
    <div class="section-title"><span class="fire">🔥</span> 本期最需关注 TOP10</div>
    <div class="top10-list">
""")
    for i, ev in enumerate(top10, 1):
        imp = ev["importance"]
        sc = star_color(imp)
        stars = star_str(imp)
        cd_class = "countdown-urgent" if ev["cal_days"] <= 3 else ("countdown-soon" if ev["cal_days"] <= 7 else "countdown-normal")
        warn = '<span class="warn">⚠️</span>' if ev.get("confidence") != "high" else ""
        sectors_str = " / ".join(ev["sectors"][:3])
        html_parts.append(f"""        <div class="top10-item">
            <span class="date">{ev['d_str']}</span>
            <span class="time">{ev['t_str']}</span>
            <span class="name">{category_icon(ev['category'])} {ev['name'].split(' · ')[0]}{warn}</span>
            <span class="stars" style="color:{sc}">{stars}</span>
            <span class="countdown {cd_class}">{ev['cal_days']}天 / {ev['t_days']}交易日</span>
            <span class="sectors">{sectors_str}</span>
        </div>
""")
    html_parts.append("""    </div>
</div>
""")

    # Calendar grid
    html_parts.append("""
<div class="calendar-section">
    <div class="section-title">📅 日历视图</div>
    <div class="cal-scroll-wrapper">
""")

    for week_idx, week in enumerate(weeks):
        if week_idx == 0:
            html_parts.append("""    <div class="cal-grid">
""")
            for wd in ["一", "二", "三", "四", "五", "六", "日"]:
                cls = "cal-weekday weekend" if wd in ["六", "日"] else "cal-weekday"
                html_parts.append(f'        <div class="{cls}">周{wd}</div>\n')
            html_parts.append("""    </div>
    <div class="cal-grid">
""")
        
        for day in week:
            classes = ["cal-day"]
            if day < start_date or day > end_date:
                classes.append("other-month")
            if day == today:
                classes.append("today")
            if day.weekday() >= 5:
                classes.append("weekend")
            
            cls_str = " ".join(classes)
            day_events = events_by_date.get(day, [])
            day_events.sort(key=lambda e: e["bj_dt"])
            
            ev_html = ""
            for ev in day_events:
                imp = ev["importance"]
                cat = ev.get("category", "")
                ev_cls = f"cal-event breaking" if cat == "breaking" else f"cal-event imp{imp}"
                time_str = ev["t_str"] if not ev.get("all_day") else ""
                cd = f'<span class="ev-countdown">{ev["cal_days"]}天</span>' if ev["cal_days"] > 0 else '<span class="ev-countdown" style="background:#e74c3c;color:white">今天</span>'
                name_short = ev["name"].split(" · ")[0].split("（")[0]
                ev_html += f'        <div class="{ev_cls}" title="{ev["name"]}">{time_str} {name_short} {cd}</div>\n'
            
            html_parts.append(f"""        <div class="{cls_str}">
        <span class="day-num">{day.day}</span>
{ev_html}    </div>
""")
        
        # Check if this is the last day of the week
        if week.index(week[-1]) == 6:
            if week_idx < len(weeks) - 1:
                html_parts.append("""    </div>
    <div class="cal-grid">
""")
            else:
                html_parts.append("""    </div>
""")

    # Legend
    html_parts.append("""
    </div><!-- /cal-scroll-wrapper -->
    <div class="legend">
        <div class="legend-item"><div class="legend-dot" style="background:#e74c3c"></div>★★★★★ 极高</div>
        <div class="legend-item"><div class="legend-dot" style="background:#e67e22"></div>★★★★ 高</div>
        <div class="legend-item"><div class="legend-dot" style="background:#2980b9"></div>★★★ 中</div>
        <div class="legend-item" style="margin-left:auto">⚠️ = 日期待核对</div>
        <div class="legend-item">倒计时格式：自然天数 / 交易日数</div>
    </div>
</div>

<div class="footer">
    交易日数按周一至周五计算，不含节假日 ｜ 数据由本地规则库生成 ｜ ⚠️ 标注条目请以官方公告为准
</div>
</body>
</html>
""")

    return "".join(html_parts)


if __name__ == "__main__":
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    events_path = os.path.join(base, "out", "events.json")
    events = load_events(events_path)
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    html = generate_html(events, today_str)
    
    out_path = os.path.join(base, "out", "calendar.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[ok] HTML 日历 -> {out_path}")
