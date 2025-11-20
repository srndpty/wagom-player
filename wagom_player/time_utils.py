"""時間表示関連のヘルパー。"""

def format_ms(value: int) -> str:
    seconds = max(0, int(value // 1000))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
