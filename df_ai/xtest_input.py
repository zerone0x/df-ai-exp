"""XTEST-based input injection for DF Premium (SDL2).

This is the ONLY working input method for DF Steam under Xvfb.
See docs/PITFALLS.md #1 for why xdotool/XSendEvent doesn't work.

Dependencies: python-xlib (pip install python-xlib)
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from Xlib import X, display
from Xlib.ext import xtest


@dataclass
class DFSession:
    """A running DF instance under Xvfb."""
    display_num: int
    host_pid: int
    df_window_id: int  # the actual "Dwarf Fortress" child window
    _display: object = None

    @property
    def display_str(self) -> str:
        return f":{self.display_num}"

    def get_display(self) -> display.Display:
        if self._display is None:
            self._display = display.Display(self.display_str)
        return self._display

    def close(self):
        if self._display:
            self._display.close()
            self._display = None


def start_df(df_root: Path, display_num: int = 50) -> DFSession:
    """Start Xvfb + DF and return a DFSession.

    Uses 1200x800 screen — exactly matching DF's default window size.
    This ensures window position (0,0) = screen position (0,0),
    avoiding the coordinate offset nightmare with larger screens.
    """
    import os

    # Kill any existing DF on this display
    cleanup(display_num)
    time.sleep(0.5)

    # Use DF's native resolution to avoid offset issues
    # DF creates a 1200x800 SDL window; match it exactly
    screen_res = "1200x800x24"

    # Start Xvfb
    subprocess.Popen(
        ["Xvfb", f":{display_num}", "-screen", "0", screen_res, "-ac"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(1)

    # Start DF
    env = {**os.environ, "DISPLAY": f":{display_num}"}
    proc = subprocess.Popen(
        [str(df_root / "dfhack")],
        cwd=str(df_root),
        stdout=open(df_root / "stdout.log", "w"),
        stderr=open(df_root / "stderr.log", "w"),
        env=env,
    )
    host_pid = proc.pid

    # Wait for DF window to appear
    d = display.Display(f":{display_num}")
    df_win = _wait_for_df_window(d, timeout=20)

    if df_win is None:
        proc.kill()
        raise RuntimeError("DF window did not appear within timeout")

    # Move window to (0,0) in case it spawned with an offset
    df_win_obj = d.create_resource_object("window", df_win)
    df_win_obj.configure(x=0, y=0)
    d.sync()
    time.sleep(0.3)

    # Also move parent if it exists
    try:
        parent = df_win_obj.query_tree().parent
        if parent and parent.id != d.screen().root.id:
            parent.configure(x=0, y=0)
            d.sync()
    except Exception:
        pass

    # Focus the window
    df_win_obj.set_input_focus(X.RevertToParent, X.CurrentTime)
    d.sync()

    session = DFSession(
        display_num=display_num,
        host_pid=host_pid,
        df_window_id=df_win,
    )
    session._display = d
    return session


def _wait_for_df_window(d: display.Display, timeout: float = 20) -> Optional[int]:
    """Wait for the DF window to appear. Returns window ID or None."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        wid = _find_df_window(d)
        if wid is not None:
            return wid
        time.sleep(1)
    return None


def _find_df_window(d: display.Display) -> Optional[int]:
    """Find the actual DF rendering window by traversing the X tree."""
    root = d.screen().root
    try:
        for child in root.query_tree().children:
            # Check children of each top-level window
            try:
                for subchild in child.query_tree().children:
                    try:
                        name = subchild.get_wm_name()
                        if name and "Dwarf Fortress" in str(name):
                            return subchild.id
                    except Exception:
                        pass
                # Also check the top-level itself
                name = child.get_wm_name()
                if name and "Dwarf Fortress" in str(name):
                    return child.id
            except Exception:
                pass
        # Fallback: find largest non-root window
        best_id, best_area = None, 0
        for child in root.query_tree().children:
            try:
                geom = child.get_geometry()
                area = geom.width * geom.height
                if area > best_area and area > 100000:  # >~316x316
                    best_area = area
                    best_id = child.id
            except Exception:
                pass
        return best_id
    except Exception:
        return None


def click(session: DFSession, x: int, y: int, button: int = 1):
    """Click at screen coordinates."""
    d = session.get_display()
    root = d.screen().root

    root.warp_pointer(x, y)
    d.sync()
    time.sleep(0.1)

    xtest.fake_input(d, X.ButtonPress, detail=button)
    d.sync()
    time.sleep(0.05)
    xtest.fake_input(d, X.ButtonRelease, detail=button)
    d.sync()


def click_and_wait(session: DFSession, x: int, y: int, wait: float = 1.0):
    """Click and wait for UI to respond."""
    click(session, x, y)
    time.sleep(wait)


def screenshot(session: DFSession, output: Path) -> Path:
    """Take a screenshot via scrot."""
    import os
    env = {**os.environ, "DISPLAY": session.display_str}
    subprocess.run(["scrot", str(output)], env=env, check=True,
                   capture_output=True, timeout=10)
    return output


def cleanup(display_num: int = 50):
    """Kill all DF-related processes on the given display."""
    import signal
    # Kill DF
    subprocess.run(["pkill", "-9", "dwarfort"], capture_output=True)
    subprocess.run(["pkill", "-9", "-f", "dfhack"], capture_output=True)
    # Kill Xvfb on this display
    subprocess.run(["pkill", "-9", "-f", f"Xvfb :{display_num}"],
                   capture_output=True)
    subprocess.run(["pkill", "-9", "openbox"], capture_output=True)


def system_check() -> dict:
    """Quick system health check before starting DF."""
    import os

    load = os.getloadavg()[0]
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemAvailable:"):
                mem_mb = int(line.split()[1]) // 1024
                break
        else:
            mem_mb = 0

    df_count = 0
    try:
        result = subprocess.run(["pgrep", "-c", "dwarfort"],
                                capture_output=True, text=True)
        df_count = int(result.stdout.strip()) if result.returncode == 0 else 0
    except Exception:
        pass

    safe = load < 3.0 and mem_mb > 500 and df_count == 0
    return {
        "load": round(load, 1),
        "mem_available_mb": mem_mb,
        "df_instances": df_count,
        "safe_to_start": safe,
    }
