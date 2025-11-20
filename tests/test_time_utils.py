from wagom_player.time_utils import format_ms


def test_format_ms_handles_hours_minutes_seconds():
    assert format_ms(0) == "00:00"
    assert format_ms(1000) == "00:01"
    assert format_ms(61_000) == "01:01"
    assert format_ms(3_661_000) == "01:01:01"
