def format_ms(ms: int) -> str:
    """Format milliseconds as MM:SS or HH:MM:SS."""
    if ms <= 0:
        return "00:00"
    seconds = ms // 1000
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"
