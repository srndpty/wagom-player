from pathlib import Path

BUILD_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_windows.bat"


def test_build_script_does_not_force_kill_running_player():
    content = BUILD_SCRIPT.read_text(encoding="utf-8")

    assert "taskkill" not in content.lower()
    assert "wagom-player.exe is running" in content
