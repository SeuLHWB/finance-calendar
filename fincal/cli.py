# -*- coding: utf-8 -*-
"""命令行入口。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from . import aggregate, render, sources
from .channels import build_channels
from .render_calendar import generate_html as generate_calendar_html
from .tzsupport import backend

BASE = Path(__file__).resolve().parent.parent


def load_cfg(path: Path | None = None) -> dict:
    p = path or (BASE / "config" / "settings.json")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def load_channels_cfg(cfg: dict) -> dict:
    p = BASE / cfg.get("channels_file", "config/channels.json")
    if not p.exists():
        example = BASE / "config" / "channels.example.json"
        print(f"[info] 未找到 {p.name}，使用 {example.name}（仅本地文件渠道可用）")
        p = example
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def collect(cfg: dict, args) -> list:
    days = int(args.days or cfg.get("horizon_days", 30))
    cfg["horizon_days"] = days
    start = date.today() if not args.start else date.fromisoformat(args.start)
    end = start + timedelta(days=days)
    raw = sources.load_all(BASE, cfg, start, end)
    overrides = {}
    if args.min_star:
        overrides["min_importance"] = int(args.min_star)
    if args.sectors:
        overrides["sectors"] = [s.strip() for s in args.sectors.split(",") if s.strip()]
    if args.categories:
        overrides["categories"] = [s.strip() for s in args.categories.split(",") if s.strip()]
    if args.regions:
        overrides["regions"] = [s.strip() for s in args.regions.split(",") if s.strip()]
    return aggregate.build(raw, cfg, overrides), start


# ------------------------------------------------------------------ 命令
def cmd_preview(args):
    cfg = load_cfg()
    events, start = collect(cfg, args)
    print(render.render_text(events, cfg, start))
    outdir = BASE / cfg.get("output_dir", "out")
    outdir.mkdir(exist_ok=True)
    html_path = outdir / "preview.html"
    html_path.write_text(render.render_html(events, cfg, start), encoding="utf-8")
    (outdir / "preview.md").write_text(render.render_markdown(events, cfg, start), encoding="utf-8")
    (outdir / "events.json").write_text(
        json.dumps([e.to_dict() for e in events], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[ok] HTML 预览 -> {html_path}")
    print(f"[ok] 事件 JSON -> {outdir / 'events.json'}")
    print(f"[info] 时区后端: {backend()}")
    return 0


def cmd_push(args):
    cfg = load_cfg()
    events, start = collect(cfg, args)
    if not events:
        print("[info] 窗口内无符合条件的事件，跳过推送")
        return 0
    title = cfg.get("title", "📅 未来 {days} 天财经日历").format(days=cfg["horizon_days"])
    title = f"{title}（{start.isoformat()}）"
    text = render.render_text(events, cfg, start)
    md = render.render_markdown(events, cfg, start)
    html_body = render.render_html(events, cfg, start)

    ch_cfg = load_channels_cfg(cfg)
    only = [c.strip() for c in args.channels.split(",")] if args.channels else None
    chans = build_channels(ch_cfg, {"output_dir": str(BASE / cfg.get("output_dir", "out"))}, only)
    if not chans:
        print("[warn] 没有启用任何推送渠道，请编辑 config/channels.json")
        return 1

    failed = 0
    for ch in chans:
        try:
            ok, msg = ch.send(title, text, md, html_body)
            print(f"[{'ok' if ok else 'fail'}] {ch.name}: {msg}")
            failed += 0 if ok else 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"[fail] {ch.name}: {exc}")
    _write_state(cfg, len(events), len(chans) - failed)
    return 1 if failed else 0


def _write_state(cfg, n_events, n_ok):
    p = BASE / cfg.get("state_file", "data/state.json")
    p.parent.mkdir(exist_ok=True)
    state = {}
    if p.exists():
        try:
            state = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            state = {}
    state["last_run"] = datetime.now().isoformat(timespec="seconds")
    state["last_events"] = n_events
    state["last_channels_ok"] = n_ok
    state.setdefault("history", []).append(
        {"t": state["last_run"], "events": n_events, "ok": n_ok})
    state["history"] = state["history"][-60:]
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_check(args):
    """列出需要人工核对的事件（confidence != high）。"""
    cfg = load_cfg()
    args.min_star = args.min_star or 1
    events, _ = collect(cfg, args)
    rows = [e for e in events if e.confidence != "high"]
    if not rows:
        print("[ok] 窗口内所有事件日期均为高置信度")
        return 0
    print(f"以下 {len(rows)} 条事件日期需核对官方日程：\n")
    for e in rows:
        print(f"  {e.local_dt(cfg['timezone']).strftime('%Y-%m-%d')}  [{e.confidence:<6}] "
              f"{e.name}\n      来源 {e.source}  {e.source_url}")
    return 0


def cmd_add(args):
    """手动补录一条事件。"""
    if args.breaking:
        p = BASE / "data" / "events_breaking.json"
    else:
        p = BASE / "data" / "events_manual.json"
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"events": []}
    item = {
        "name": args.name,
        "category": args.category,
        "region": args.region,
        "datetime": args.when,
        "tz": args.tz,
        "importance": int(args.importance),
        "sectors": [s.strip() for s in (args.sectors or "").split(",") if s.strip()],
        "prev": args.prev or "",
        "forecast": args.forecast or "",
        "note": args.note or "",
        "confidence": args.confidence,
    }
    data.setdefault("events", []).append(item)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tag = "🚨 突发事件" if args.breaking else "事件"
    print(f"[ok] {tag}已补录：{args.when} {args.name}")
    return 0


def cmd_channels(args):
    cfg = load_cfg()
    ch_cfg = load_channels_cfg(cfg)
    print("已配置渠道：")
    for k, v in ch_cfg.items():
        if k.startswith("_") or not isinstance(v, dict):
            continue
        flag = "✅ 启用" if v.get("enabled") else "⛔ 停用"
        print(f"  {k:<12} {flag}   {v.get('_desc','')}")
    if args.test:
        chans = build_channels(ch_cfg, {"output_dir": str(BASE / "out")},
                               [c.strip() for c in args.test.split(",")])
        for ch in chans:
            try:
                ok, msg = ch.send("【测试】财经日历推送连通性检查",
                                  "这是一条测试消息，说明渠道配置正确。",
                                  "**【测试】财经日历推送**\n> 渠道配置正确 ✅",
                                  "<b>【测试】财经日历推送</b><br>渠道配置正确 ✅")
                print(f"[{'ok' if ok else 'fail'}] {ch.name}: {msg}")
            except Exception as exc:  # noqa: BLE001
                print(f"[fail] {ch.name}: {exc}")
    return 0


def cmd_install_task(args):
    py = sys.executable
    run = BASE / "run.py"
    t = args.time or "08:00"
    cmd = (f'schtasks /Create /SC DAILY /TN "FinCalDailyPush" /ST {t} '
           f'/TR "\\"{py}\\" \\"{run}\\" push" /F /RL HIGHEST')
    print("在【管理员权限】的命令提示符中执行以下命令，即可注册 Windows 每日定时任务：\n")
    print("  " + cmd + "\n")
    print("查看：schtasks /Query /TN FinCalDailyPush /V /FO LIST")
    print("删除：schtasks /Delete /TN FinCalDailyPush /F\n")
    print("Linux/macOS crontab 写法：")
    print(f"  0 {int(t.split(':')[0])} * * *  cd {BASE} && {py} run.py push >> logs/push.log 2>&1")
    return 0


def cmd_calendar(args):
    """生成日历视图 HTML，含倒计时。"""
    cfg = load_cfg()
    events, start = collect(cfg, args)
    if not events:
        print("[info] 窗口内无符合条件的事件")
        return 0
    outdir = BASE / cfg.get("output_dir", "out")
    outdir.mkdir(exist_ok=True)
    events_dict = [e.to_dict() for e in events]
    # Save events.json for calendar renderer
    (outdir / "events.json").write_text(
        json.dumps(events_dict, ensure_ascii=False, indent=2), encoding="utf-8")
    today_str = date.today().isoformat()
    html = generate_calendar_html(events_dict, today_str)
    cal_path = outdir / "calendar.html"
    cal_path.write_text(html, encoding="utf-8")
    print(f"[ok] 日历视图 -> {cal_path}")
    print(f"[ok] 事件数: {len(events)}")
    # Print TOP10 summary
    top10 = sorted(events, key=lambda e: (-e.importance, e.dt))[:10]
    print("\n🔥 TOP10:")
    for i, ev in enumerate(top10, 1):
        bj = ev.local_dt("Asia/Shanghai")
        sc = "★" * ev.importance
        cd = (bj.date() - start).days
        td_days = sum(1 for d in range(0, cd + 1) if (start + timedelta(days=d)).weekday() < 5) - 1
        td_days = max(0, td_days)
        sec = " / ".join(ev.sectors[:3])
        warn = " ⚠️" if ev.confidence != "high" else ""
        print(f"  {bj.month:2d}/{bj.day:2d}  {bj.hour:02d}:{bj.minute:02d}  {ev.name.split(' · ')[0]:<12s}  {sc:<10s} {cd}天/{td_days}交易日 | {sec}{warn}")
    return 0


# ------------------------------------------------------------------ 参数
def _common(sp):
    sp.add_argument("--days", type=int, help="预告窗口天数，默认取配置 30")
    sp.add_argument("--start", help="起始日期 YYYY-MM-DD，默认今天")
    sp.add_argument("--min-star", dest="min_star", type=int, help="最低重要性星级 1-5")
    sp.add_argument("--sectors", help="只看这些行业板块，逗号分隔")
    sp.add_argument("--categories", help="事件类别过滤：monetary,macro,policy,earnings,extra")
    sp.add_argument("--regions", help="地区过滤：CN,US,EU,JP,HK,GLOBAL")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fincal", description="财经日历提醒系统")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("preview", help="预览未来事件并生成 HTML")
    _common(p1)
    p1.set_defaults(func=cmd_preview)

    p2 = sub.add_parser("push", help="渲染并推送到已启用渠道")
    _common(p2)
    p2.add_argument("--channels", help="只推指定渠道，逗号分隔")
    p2.set_defaults(func=cmd_push)

    p3 = sub.add_parser("check", help="列出需要人工核对日期的事件")
    _common(p3)
    p3.set_defaults(func=cmd_check)

    p4 = sub.add_parser("add", help="手动补录事件")
    p4.add_argument("--name", required=True)
    p4.add_argument("--when", required=True, help="YYYY-MM-DD 或 'YYYY-MM-DD HH:MM'")
    p4.add_argument("--tz", default="Asia/Shanghai")
    p4.add_argument("--category", default="extra",
                    choices=["monetary", "macro", "policy", "earnings", "extra"])
    p4.add_argument("--region", default="CN")
    p4.add_argument("--importance", default=4)
    p4.add_argument("--sectors", default="")
    p4.add_argument("--prev", default="")
    p4.add_argument("--forecast", default="")
    p4.add_argument("--note", default="")
    p4.add_argument("--confidence", default="high", choices=["high", "medium", "low"])
    p4.add_argument("--breaking", action="store_true", help="录入为突发事件（存入 events_breaking.json）")
    p4.set_defaults(func=cmd_add)

    p5 = sub.add_parser("channels", help="查看/测试推送渠道")
    p5.add_argument("--test", help="测试指定渠道，逗号分隔")
    p5.set_defaults(func=cmd_channels)

    p6 = sub.add_parser("install-task", help="输出每日定时任务安装命令")
    p6.add_argument("--time", default="08:00")
    p6.set_defaults(func=cmd_install_task)

    p7 = sub.add_parser("calendar", help="生成日历视图 HTML（含倒计时）")
    _common(p7)
    p7.set_defaults(func=cmd_calendar)

    args = ap.parse_args(argv)
    for k in ("days", "start", "min_star", "sectors", "categories", "regions"):
        if not hasattr(args, k):
            setattr(args, k, None)
    return args.func(args)
