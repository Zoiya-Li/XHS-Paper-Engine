"""Tests for cross-platform scheduling helpers (no real install performed)."""

from dp_core import scheduler


def test_detect_os_is_known_value():
    assert scheduler.detect_os() in ("macos", "windows", "linux", "unknown")


def test_launchd_plist_contains_command_and_time():
    plist = scheduler._launchd_plist(hour=9, minute=30)
    assert str(scheduler.AUTORUN) in plist
    assert str(scheduler.PYTHON) in plist
    assert "<integer>9</integer>" in plist
    assert "<integer>30</integer>" in plist
    assert scheduler.LAUNCHD_LABEL in plist


def test_cron_line_format():
    line = scheduler._cron_line(hour=9, minute=5)
    assert line.startswith("5 9 * * *")
    assert scheduler.CRON_MARKER in line
    assert str(scheduler.AUTORUN) in line


def test_install_unsupported_os(monkeypatch):
    monkeypatch.setattr(scheduler, "detect_os", lambda: "unknown")
    ok, msg = scheduler.install()
    assert ok is False and "Unsupported" in msg


def test_is_installed_safe_on_unknown(monkeypatch):
    monkeypatch.setattr(scheduler, "detect_os", lambda: "unknown")
    assert scheduler.is_installed() is False
