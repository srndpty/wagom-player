import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional

LANGUAGE_ALIASES = {
    "ja": ("ja", "jpn", "jp", "japanese", "japan", "日本語", "日本", "日語"),
    "en": ("en", "eng", "english", "英語"),
    "ko": ("ko", "kor", "korean", "韓国語", "朝鮮語"),
    "zh": ("zh", "chi", "zho", "cn", "chinese", "mandarin", "中国語", "中文"),
    "fr": ("fr", "fre", "fra", "french", "フランス語"),
    "de": ("de", "ger", "deu", "german", "ドイツ語"),
    "es": ("es", "spa", "spanish", "スペイン語"),
    "it": ("it", "ita", "italian", "イタリア語"),
    "pt": ("pt", "por", "portuguese", "ポルトガル語"),
    "ru": ("ru", "rus", "russian", "ロシア語"),
}


def normalize_language(value: object, default: str = "ja") -> str:
    normalized = str(value or "").strip().casefold()
    if not normalized:
        return default
    for language, aliases in LANGUAGE_ALIASES.items():
        if normalized == language or normalized in aliases:
            return language
    return normalized


def language_key(name: str) -> str:
    normalized = name.casefold()
    tokens = set(re.findall(r"[a-z0-9]+", normalized))
    for language, aliases in LANGUAGE_ALIASES.items():
        for alias in aliases:
            normalized_alias = alias.casefold()
            if re.search(r"[a-z0-9]", normalized_alias):
                if normalized_alias in tokens:
                    return language
            elif normalized_alias in normalized:
                return language
    return ""


def find_track(tracks: Sequence[tuple[int, str]], language: str) -> Optional[tuple[int, str]]:
    expected = normalize_language(language)
    return next((track for track in tracks if language_key(track[1]) == expected), None)


@dataclass(frozen=True)
class TrackPreferences:
    audio_language: str = "ja"
    subtitle_enabled: bool = False
    subtitle_language: str = "ja"
