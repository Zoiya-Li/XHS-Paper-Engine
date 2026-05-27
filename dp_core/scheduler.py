"""
Cross-platform scheduling for the daily run.

Detects the OS and installs a once-a-day task that runs `auto_run.py`:
  - macOS:   a launchd LaunchAgent (~/Library/LaunchAgents)
  - Windows: a Task Scheduler task (schtasks)
  - Linux:   a crontab line

Used by auto_run.py to offer scheduling after the first successful run.
"""

import os
import sys
import platform
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
AUTORUN = PROJECT_DIR / "auto_run.py"
PYTHON = sys.executable  # the interpreter currently running (e.g. the venv python)

LAUNCHD_LABEL = "com.xhs-paper-engine.daily"
WIN_TASK_NAME = "XHSPaperEngine"
CRON_MARKER = "# xhs-paper-engine-daily"

# Marker so we only prompt once (the user can still install/uninstall via flags)
_PROMPTED_MARKER = Path.home() / ".xhs-paper-engine" / ".schedule_prompted"


def detect_os() -> str:
    """Return 'macos', 'windows', 'linux', or 'unknown'."""
    s = platform.system().lower()
    if s == "darwin":
        return "macos"
    if s == "windows":
        return "windows"
    if s == "linux":
        return "linux"
    return "unknown"


def already_prompted() -> bool:
    return _PROMPTED_MARKER.exists()


def mark_prompted() -> None:
    _PROMPTED_MARKER.parent.mkdir(parents=True, exist_ok=True)
    _PROMPTED_MARKER.touch()


# ----------------------------- macOS (launchd) -----------------------------

def _launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"


def _launchd_plist(hour: int, minute: int) -> str:
    logs = PROJECT_DIR / "logs"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>{LAUNCHD_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{PYTHON}</string>
        <string>{AUTORUN}</string>
    </array>
    <key>WorkingDirectory</key><string>{PROJECT_DIR}</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>{hour}</integer>
        <key>Minute</key><integer>{minute}</integer>
    </dict>
    <key>StandardOutPath</key><string>{logs}/launchd_daily.log</string>
    <key>StandardErrorPath</key><string>{logs}/launchd_daily.err.log</string>
    <key>RunAtLoad</key><false/>
</dict>
</plist>
"""


def _macos_install(hour: int, minute: int):
    (PROJECT_DIR / "logs").mkdir(parents=True, exist_ok=True)
    p = _launchd_plist_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_launchd_plist(hour, minute))
    subprocess.run(["launchctl", "unload", str(p)], capture_output=True)
    r = subprocess.run(["launchctl", "load", str(p)], capture_output=True, text=True)
    if r.returncode != 0:
        return False, f"launchctl load failed: {r.stderr.strip()}"
    return True, f"Installed launchd agent at {p} (daily {hour:02d}:{minute:02d})"


def _macos_is_installed() -> bool:
    r = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    return LAUNCHD_LABEL in (r.stdout or "")


def _macos_uninstall():
    p = _launchd_plist_path()
    subprocess.run(["launchctl", "unload", str(p)], capture_output=True)
    if p.exists():
        p.unlink()
    return True, "Removed launchd agent"


# --------------------------- Windows (schtasks) ----------------------------

def _windows_install(hour: int, minute: int):
    tr = f'"{PYTHON}" "{AUTORUN}"'
    r = subprocess.run(
        ["schtasks", "/Create", "/TN", WIN_TASK_NAME, "/TR", tr,
         "/SC", "DAILY", "/ST", f"{hour:02d}:{minute:02d}", "/F"],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        return False, f"schtasks create failed: {r.stderr.strip() or r.stdout.strip()}"
    return True, f"Created scheduled task '{WIN_TASK_NAME}' (daily {hour:02d}:{minute:02d})"


def _windows_is_installed() -> bool:
    r = subprocess.run(["schtasks", "/Query", "/TN", WIN_TASK_NAME],
                       capture_output=True, text=True)
    return r.returncode == 0


def _windows_uninstall():
    subprocess.run(["schtasks", "/Delete", "/TN", WIN_TASK_NAME, "/F"], capture_output=True)
    return True, "Removed scheduled task"


# ------------------------------ Linux (cron) -------------------------------

def _cron_line(hour: int, minute: int) -> str:
    return f'{minute} {hour} * * * cd "{PROJECT_DIR}" && "{PYTHON}" "{AUTORUN}"  {CRON_MARKER}'


def _read_crontab() -> str:
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def _write_crontab(content: str) -> bool:
    r = subprocess.run(["crontab", "-"], input=content, capture_output=True, text=True)
    return r.returncode == 0


def _linux_install(hour: int, minute: int):
    existing = [ln for ln in _read_crontab().splitlines() if CRON_MARKER not in ln]
    existing.append(_cron_line(hour, minute))
    if _write_crontab("\n".join(existing) + "\n"):
        return True, f"Added crontab entry (daily {hour:02d}:{minute:02d})"
    return False, "Failed to write crontab"


def _linux_is_installed() -> bool:
    return CRON_MARKER in _read_crontab()


def _linux_uninstall():
    kept = [ln for ln in _read_crontab().splitlines() if CRON_MARKER not in ln]
    _write_crontab("\n".join(kept) + "\n")
    return True, "Removed crontab entry"


# --------------------------------- API -------------------------------------

_DISPATCH = {
    "macos": (_macos_install, _macos_is_installed, _macos_uninstall),
    "windows": (_windows_install, _windows_is_installed, _windows_uninstall),
    "linux": (_linux_install, _linux_is_installed, _linux_uninstall),
}


def is_installed() -> bool:
    osname = detect_os()
    if osname not in _DISPATCH:
        return False
    try:
        return _DISPATCH[osname][1]()
    except Exception:
        return False


def install(hour: int = 9, minute: int = 0):
    """Install the daily schedule for the current OS. Returns (ok, message)."""
    osname = detect_os()
    if osname not in _DISPATCH:
        return False, f"Unsupported OS for scheduling: {platform.system()}"
    try:
        return _DISPATCH[osname][0](hour, minute)
    except FileNotFoundError as e:
        return False, f"Scheduler tool not found: {e}"
    except Exception as e:
        return False, f"Install failed: {e}"


def uninstall():
    osname = detect_os()
    if osname not in _DISPATCH:
        return False, f"Unsupported OS: {platform.system()}"
    try:
        return _DISPATCH[osname][2]()
    except Exception as e:
        return False, f"Uninstall failed: {e}"
