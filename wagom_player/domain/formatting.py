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


def format_size(num_bytes: int) -> str:
    """Format a byte count as a human-readable string (B/KB/MB/GB/TB)."""
    if num_bytes < 0:
        return ""
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{int(num_bytes)} B"
