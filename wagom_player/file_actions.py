import os
import shutil
import time
from collections.abc import Callable


class TargetFileExistsError(FileExistsError):
    pass


def target_path_for_subfolder(file_path: str, subfolder_name: str) -> str:
    file_name = os.path.basename(file_path)
    source_dir = os.path.dirname(file_path)
    return os.path.join(source_dir, subfolder_name, file_name)


def move_file_to_subfolder(
    file_path: str,
    subfolder_name: str,
    *,
    retry_delays: tuple[float, ...] = (0.1, 0.25, 0.5),
    move_func: Callable[[str, str], str] = shutil.move,
    sleep_func: Callable[[float], None] = time.sleep,
) -> str:
    target_file_path = target_path_for_subfolder(file_path, subfolder_name)
    os.makedirs(os.path.dirname(target_file_path), exist_ok=True)

    if os.path.exists(target_file_path):
        raise TargetFileExistsError(target_file_path)

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
