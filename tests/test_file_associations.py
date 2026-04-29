from pathlib import Path


REG_FILE = Path(__file__).resolve().parents[1] / "windows" / "file-associations.reg"


def test_file_association_commands_use_single_quoted_file_argument():
    content = REG_FILE.read_text(encoding="utf-8")

    assert "%*" not in content
    assert r'"C:\\Program Files\\wagom-player\\wagom-player.exe\" \"%1\"' in content


def test_file_associations_include_m2ts():
    content = REG_FILE.read_text(encoding="utf-8")

    assert r"WagomPlayer.m2ts" in content
    assert '".m2ts"=""' in content
    assert '".m2ts"="WagomPlayer.m2ts"' in content
    assert r"[HKEY_CURRENT_USER\Software\Classes\.m2ts\OpenWithProgids]" in content
