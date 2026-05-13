from pathlib import Path

import pytest

from wagom_player.file_actions import (
    TargetFileExistsError,
    move_file_to_subfolder,
    target_path_for_subfolder,
)


def test_target_path_for_subfolder_keeps_filename(tmp_path: Path):
    source = tmp_path / "movie.mp4"

    assert target_path_for_subfolder(str(source), "_ok") == str(tmp_path / "_ok" / "movie.mp4")


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


def test_move_file_to_subfolder_retries_transient_move_error(tmp_path: Path):
    source = tmp_path / "movie.mp4"
    source.write_text("video", encoding="utf-8")
    calls = []
    sleeps = []

    def flaky_move(src: str, dst: str) -> str:
        calls.append((src, dst))
        if len(calls) == 1:
            raise PermissionError("locked")
        return Path(src).rename(dst)

    target = move_file_to_subfolder(
        str(source),
        "_ok",
        retry_delays=(0.01,),
        move_func=flaky_move,
        sleep_func=sleeps.append,
    )

    assert target == str(tmp_path / "_ok" / "movie.mp4")
    assert len(calls) == 2
    assert sleeps == [0.01]
    assert not source.exists()
    assert Path(target).read_text(encoding="utf-8") == "video"


def test_move_file_to_subfolder_reraises_after_retries(tmp_path: Path):
    source = tmp_path / "movie.mp4"
    source.write_text("video", encoding="utf-8")

    def locked_move(src: str, dst: str) -> str:
        raise PermissionError("locked")

    with pytest.raises(PermissionError):
        move_file_to_subfolder(
            str(source),
            "_ok",
            retry_delays=(0.01, 0.02),
            move_func=locked_move,
            sleep_func=lambda delay: None,
        )

    assert source.exists()
