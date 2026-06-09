from collections.abc import Callable


class TrashService:
    def __init__(self, send_to_trash: Callable[[str], object] | None):
        self._send_to_trash = send_to_trash

    @property
    def available(self) -> bool:
        return self._send_to_trash is not None

    def discard(self, file_path: str) -> None:
        if self._send_to_trash is None:
            raise RuntimeError("ごみ箱機能が利用できないため、削除できません")
        self._send_to_trash(file_path)
