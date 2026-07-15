from ...application.file_actions import (
    CollisionResolution,
    FileActionResult,
    move_file_to_subfolder,
    move_file_to_subfolder_as_unique,
)
from ...infrastructure.trash import TrashService


class FileOperationController:
    """ユーザーが選んだ解決方法に従ってファイル操作を実行する。"""

    RETRY_DELAYS = (0.2, 0.5, 1.0, 2.0)

    def __init__(self, trash: TrashService) -> None:
        self._trash = trash

    def execute(
        self,
        file_path: str,
        subfolder_name: str,
        resolution: CollisionResolution,
    ) -> FileActionResult:
        if resolution == CollisionResolution.CANCEL:
            return FileActionResult(file_path, None, resolution)
        if resolution == CollisionResolution.DISCARD:
            self._trash.discard(file_path)
            return FileActionResult(file_path, None, resolution)
        if resolution == CollisionResolution.RENAME:
            target = move_file_to_subfolder_as_unique(
                file_path,
                subfolder_name,
                retry_delays=self.RETRY_DELAYS,
            )
            return FileActionResult(file_path, target, resolution)
        if resolution == CollisionResolution.MOVE:
            target = move_file_to_subfolder(
                file_path,
                subfolder_name,
                retry_delays=self.RETRY_DELAYS,
            )
            return FileActionResult(file_path, target, resolution)
        raise ValueError(f"未対応の解決方法です: {resolution}")
