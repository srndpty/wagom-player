import ntpath
import os
import shutil
import time
from collections.abc import Callable


class TargetFileExistsError(FileExistsError):
    pass


class InvalidMoveTargetError(ValueError):
    pass


def target_path_for_subfolder(file_path: str, subfolder_name: str) -> str:
    validate_subfolder_name(subfolder_name)
    file_name = os.path.basename(file_path)
    source_dir = os.path.dirname(file_path)
    return os.path.join(source_dir, subfolder_name, file_name)


def unique_target_path_for_subfolder(file_path: str, subfolder_name: str) -> str:
    """移動先に同名ファイルがある場合に衝突しない別名のパスを返す。

    例: ``movie.mp4`` が既にあれば ``movie (1).mp4`` を試し、それも
    あれば ``movie (2).mp4`` …と空いている名前を探す。
    """
    base_target = target_path_for_subfolder(file_path, subfolder_name)
    if not os.path.exists(base_target):
        return base_target

    target_dir = os.path.dirname(base_target)
    stem, ext = os.path.splitext(os.path.basename(base_target))
    counter = 1
    while True:
        candidate = os.path.join(target_dir, f"{stem} ({counter}){ext}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def validate_subfolder_name(subfolder_name: str) -> None:
    if not subfolder_name or subfolder_name in (".", ".."):
        raise InvalidMoveTargetError("subfolder name must be a plain directory name")
    if "/" in subfolder_name or "\\" in subfolder_name:
        raise InvalidMoveTargetError("subfolder name must not contain path separators")
    if (
        os.path.isabs(subfolder_name)
        or ntpath.isabs(subfolder_name)
        or os.path.splitdrive(subfolder_name)[0]
        or ntpath.splitdrive(subfolder_name)[0]
    ):
        raise InvalidMoveTargetError("subfolder name must be relative")
    if os.path.basename(subfolder_name) != subfolder_name:
        raise InvalidMoveTargetError("subfolder name must not contain path separators")


def validate_move_to_subfolder(file_path: str, subfolder_name: str) -> str:
    validate_subfolder_name(subfolder_name)
    if not os.path.isfile(file_path):
        raise FileNotFoundError(file_path)

    source_abs = os.path.abspath(file_path)
    target_abs = os.path.abspath(target_path_for_subfolder(file_path, subfolder_name))
    if source_abs == target_abs:
        raise InvalidMoveTargetError("source and target paths must be different")
    if os.path.exists(target_abs):
        raise TargetFileExistsError(target_abs)
    return target_abs


def move_file_to_subfolder(
    file_path: str,
    subfolder_name: str,
    *,
    retry_delays: tuple[float, ...] = (0.1, 0.25, 0.5),
    move_func: Callable[[str, str], object] = shutil.move,
    sleep_func: Callable[[float], None] = time.sleep,
) -> str:
    target_file_path = validate_move_to_subfolder(file_path, subfolder_name)
    return move_file_to_path(
        file_path,
        target_file_path,
        retry_delays=retry_delays,
        move_func=move_func,
        sleep_func=sleep_func,
    )


def move_file_to_path(
    file_path: str,
    target_file_path: str,
    *,
    overwrite: bool = False,
    retry_delays: tuple[float, ...] = (0.1, 0.25, 0.5),
    move_func: Callable[[str, str], object] = shutil.move,
    sleep_func: Callable[[float], None] = time.sleep,
    exists_func: Callable[[str], bool] = os.path.exists,
) -> str:
    """明示的なパスへファイルを移動する（別名保存などで利用）。

    汎用ユーティリティとして誤用されないよう、移動直前にも最低限の検証を行う:
    source が実在すること、target がディレクトリを含む有効なパスであること、
    そして ``overwrite=False`` の場合は target が未存在であること（移動直前の
    再確認で TOCTOU 窓を狭める）。
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(file_path)
    target_dir = os.path.dirname(target_file_path)
    if not target_dir:
        raise InvalidMoveTargetError("target path must include a directory")
    if os.path.abspath(file_path) == os.path.abspath(target_file_path):
        raise InvalidMoveTargetError("source and target paths must be different")
    os.makedirs(target_dir, exist_ok=True)

    attempts = len(retry_delays) + 1
    for attempt in range(attempts):
        if not overwrite and exists_func(target_file_path):
            raise TargetFileExistsError(target_file_path)
        try:
            move_func(file_path, target_file_path)
            break
        except OSError:
            if attempt >= len(retry_delays):
                raise
            sleep_func(retry_delays[attempt])
    return target_file_path


def move_file_to_subfolder_as_unique(
    file_path: str,
    subfolder_name: str,
    *,
    max_collision_retries: int = 5,
    retry_delays: tuple[float, ...] = (0.1, 0.25, 0.5),
    move_func: Callable[[str, str], object] = shutil.move,
    sleep_func: Callable[[float], None] = time.sleep,
    exists_func: Callable[[str], bool] = os.path.exists,
) -> str:
    """衝突しない別名を採番してサブフォルダへ移動する。

    採番（``unique_target_path_for_subfolder``）と実際の移動の間に同名パスが
    作られる TOCTOU を考慮し、移動直前の存在チェックで衝突を検知したら採番から
    やり直す。
    """
    validate_subfolder_name(subfolder_name)
    if not os.path.isfile(file_path):
        raise FileNotFoundError(file_path)

    last_error: TargetFileExistsError | None = None
    for _ in range(max_collision_retries):
        target_file_path = unique_target_path_for_subfolder(file_path, subfolder_name)
        try:
            return move_file_to_path(
                file_path,
                target_file_path,
                overwrite=False,
                retry_delays=retry_delays,
                move_func=move_func,
                sleep_func=sleep_func,
                exists_func=exists_func,
            )
        except TargetFileExistsError as e:
            # 採番後に誰かが同名を作った -> 別名を採り直して再試行
            last_error = e
    message = f"unique target collision retry limit exceeded: {file_path}"
    raise TargetFileExistsError(message) from last_error
