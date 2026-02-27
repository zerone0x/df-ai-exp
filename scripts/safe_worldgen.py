#!/usr/bin/env python3
"""Safe worldgen runner with system guards.

Usage:
    python3 scripts/safe_worldgen.py [--timeout 120]

Safety:
- Pre-flight system check (load/memory/existing instances)
- Auto-cleanup on exit (SIGTERM/SIGINT/exception)
- Timeout kill switch
- 1920x1080 Xvfb to avoid coordinate clipping
"""

from __future__ import annotations

import argparse
import atexit
import json
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from df_ai.config import get_df_root, get_logs_dir
from df_ai.xtest_input import (
    DFSession, start_df, click_and_wait, screenshot, cleanup, system_check,
)


DISPLAY_NUM = 50


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _cleanup_handler(*_):
    print(f"\n[{_now()}] Cleanup: killing DF and Xvfb...")
    cleanup(DISPLAY_NUM)
    print(f"[{_now()}] Cleanup done.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=120,
                        help="Max seconds before force-kill (default 120)")
    parser.add_argument("--dry-run", action="store_true",
                        help="System check only, don't start DF")
    args = parser.parse_args()

    # === Pre-flight ===
    check = system_check()
    print(f"[{_now()}] System check: {json.dumps(check)}")

    if not check["safe_to_start"]:
        print(f"[{_now()}] ABORT: system not safe to start DF")
        print(f"  load={check['load']} mem={check['mem_available_mb']}MB "
              f"df_instances={check['df_instances']}")
        sys.exit(1)

    if args.dry_run:
        print(f"[{_now()}] Dry run — system looks OK, not starting DF.")
        return

    # === Safety hooks ===
    atexit.register(_cleanup_handler)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    # Timeout kill switch
    def _timeout_handler(*_):
        print(f"\n[{_now()}] TIMEOUT ({args.timeout}s) — killing DF")
        cleanup(DISPLAY_NUM)
        sys.exit(2)

    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(args.timeout)

    # === Start DF ===
    df_root = get_df_root()
    logs_dir = get_logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())

    print(f"[{_now()}] Starting DF (display :{DISPLAY_NUM}, timeout {args.timeout}s)...")
    session = start_df(df_root, display_num=DISPLAY_NUM, screen_res="1920x1080x24")
    print(f"[{_now()}] DF started: pid={session.host_pid} window={session.df_window_id:#x}")

    # Wait for main menu to render
    time.sleep(3)
    ss_dir = logs_dir / f"worldgen_{ts}"
    ss_dir.mkdir(exist_ok=True)

    # Screenshot main menu
    screenshot(session, ss_dir / "00_main_menu.png")
    print(f"[{_now()}] Main menu screenshot saved")

    # === Worldgen flow ===
    # Step 1: Click "Create new world"
    # On 1920x1080 with 1200x800 window, the window should be fully visible
    # Need to find button coordinates — take screenshot and check
    # For now, use the known working coordinate (adjusted for new resolution)
    # Window at roughly center of 1920x1080: offset ~(360, 140)
    # "Create new world" was at window y≈390 → screen y≈390+140=530? No...
    # Actually with -ac (no access control) and no WM, window starts at (0,0)
    # Let's just try the same coords that worked before

    # The window is 1200x800, screen is 1920x1080
    # Without a WM, SDL2 places window at (0,0)
    # So screen coords = window coords for the visible area

    print(f"[{_now()}] Clicking 'Create new world'...")
    # From previous testing: screen (600, 350) hit "Create new world" on 1280x720
    # with window offset (40, -40). On 1920x1080 without WM, try direct window coords.
    # Let's try a few y positions
    for y in range(330, 400, 10):
        click_and_wait(session, 600, y, wait=0.5)

    time.sleep(2)
    screenshot(session, ss_dir / "01_after_create_click.png")
    print(f"[{_now()}] After 'Create new world' click — check screenshot")

    # Step 2: Dismiss welcome dialog (click OK)
    print(f"[{_now()}] Clicking 'OK' on welcome dialog...")
    for y in range(450, 560, 15):
        click_and_wait(session, 600, y, wait=0.3)

    time.sleep(1)
    screenshot(session, ss_dir / "02_after_ok.png")
    print(f"[{_now()}] After OK click — check screenshot")

    # Step 3: Click "Create world" button (bottom of params screen)
    print(f"[{_now()}] Clicking 'Create world'...")
    for x in range(250, 450, 30):
        click_and_wait(session, x, 750, wait=0.3)

    time.sleep(2)
    screenshot(session, ss_dir / "03_after_generate.png")
    print(f"[{_now()}] After generate click — check screenshot")

    # Step 4: Wait for worldgen with periodic screenshots
    print(f"[{_now()}] Waiting for worldgen...")
    for i in range(12):
        time.sleep(10)
        screenshot(session, ss_dir / f"04_gen_wait_{i:02d}.png")

        # Check if save dir appeared
        save_dir = df_root / "data" / "save"
        regions = list(save_dir.glob("region*")) if save_dir.exists() else []
        if regions:
            print(f"[{_now()}] World generated! Regions: {[r.name for r in regions]}")
            break
        print(f"[{_now()}] Waiting... ({(i+1)*10}s)")

    # Final screenshot
    screenshot(session, ss_dir / "05_final.png")

    # === Result ===
    save_dir = df_root / "data" / "save"
    regions = list(save_dir.glob("region*")) if save_dir.exists() else []
    result = {
        "ts": _now(),
        "success": len(regions) > 0,
        "regions": [r.name for r in regions],
        "screenshots": sorted(str(p) for p in ss_dir.glob("*.png")),
    }
    result_file = logs_dir / f"worldgen_result_{ts}.json"
    result_file.write_text(json.dumps(result, indent=2))

    print(f"\n[{_now()}] === RESULT ===")
    print(f"  success: {result['success']}")
    print(f"  regions: {result['regions']}")
    print(f"  screenshots: {ss_dir}")
    print(f"  result: {result_file}")

    # Cleanup
    signal.alarm(0)
    cleanup(DISPLAY_NUM)


if __name__ == "__main__":
    main()
