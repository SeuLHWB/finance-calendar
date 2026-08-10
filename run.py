# -*- coding: utf-8 -*-
"""财经日历提醒系统 —— 统一入口。

用法：
  python run.py preview --days 30 --min-star 4
  python run.py push
  python run.py channels --test wecom_bot
  python run.py check
  python run.py install-task --time 08:00
"""
import io
import os
import sys

# Windows 控制台 UTF-8
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fincal.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
