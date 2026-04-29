import os
import shutil


class TargetFileExistsError(FileExistsError):
    pass


def target_path_for_subfolder(file_path: str, subfolder_name: str) -> str:
    file_name = os.path.basename(file_path)
    source_dir = os.path.dirname(file_path)
    return os.path.join(source_dir, subfolder_name, file_name)


def move_file_to_subfolder(file_path: str, subfolder_name: str) -> str:
    target_file_path = target_path_for_subfolder(file_path, subfolder_name)
    os.makedirs(os.path.dirname(target_file_path), exist_ok=True)

    if os.path.exists(target_file_path):
        raise TargetFileExistsError(target_file_path)

    shutil.move(file_path, target_file_path)
    return target_file_path
