from pathlib import Path

import pytest

from wagom_player.file_actions import (
    TargetFileExistsError,
    move_file_to_subfolder,
    target_path_for_subfolder,
)


def test_target_path_for_subfolder_keeps_filename(tmp_path: Path):
    source = tmp_path / "movie.mp4"

    assert target_path_for_subfolder(str(source), "_ok") == str(
        tmp_path / "_ok" / "movie.mp4"
    )


def test_move_file_to_subfolder_moves_file(tmp_path: Path):
    source = tmp_path / "movie.mp4"
    source.write_text("video", encoding="utf-8")

    target = move_file_to_subfolder(str(source), "_ok")

    assert target == str(tmp_path / "_ok" / "movie.mp4")
    assert not source.exists()
    assert Path(target).read_text(encoding="utf-8") == "video"


def test_move_file_to_subfolder_raises_when_target_exists(tmp_path: Path):
    source = tmp_path / "movie.mp4"
    source.write_text("source", encoding="utf-8")
    target_dir = tmp_path / "_ng"
    target_dir.mkdir()
    (target_dir / "movie.mp4").write_text("target", encoding="utf-8")

    with pytest.raises(TargetFileExistsError):
        move_file_to_subfolder(str(source), "_ng")

    assert source.read_text(encoding="utf-8") == "source"
