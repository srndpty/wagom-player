from wagom_player.shortcuts import SHORTCUT_ROWS


def test_shortcut_rows_include_existing_keys():
    keys = {row[0] for row in SHORTCUT_ROWS}

    assert {
        "Ctrl+O",
        "Ctrl+C",
        "F1",
        "Space",
        "Left",
        "Right",
        "Num 1",
        "Num 4",
        "Page Up",
        "Page Down",
        "Up",
        "Down",
        "M",
        "R",
        "S",
        "X",
        "C",
        "I",
        "Num 0",
        "Num 7",
        "Num 8",
        "Num 9",
    }.issubset(keys)
