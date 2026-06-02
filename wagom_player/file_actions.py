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
    move_func: Callable[[str, str], str] = shutil.move,
    sleep_func: Callable[[float], None] = time.sleep,
) -> str:
    target_file_path = validate_move_to_subfolder(file_path, subfolder_name)
    os.makedirs(os.path.dirname(target_file_path), exist_ok=True)

    attempts = len(retry_delays) + 1
    for attempt in range(attempts):
        try:
            move_func(file_path, target_file_path)
            break
        except OSError:
            if attempt >= len(retry_delays):
                raise
            sleep_func(retry_delays[attempt])
    return target_file_path
