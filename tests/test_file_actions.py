from pathlib import Path

import pytest

from wagom_player.file_actions import (
    InvalidMoveTargetError,
    TargetFileExistsError,
    move_file_to_path,
    move_file_to_subfolder,
    move_file_to_subfolder_as_unique,
    target_path_for_subfolder,
    unique_target_path_for_subfolder,
    validate_move_to_subfolder,
)


def test_target_path_for_subfolder_keeps_filename(tmp_path: Path):
    source = tmp_path / "movie.mp4"

    assert target_path_for_subfolder(str(source), "_ok") == str(tmp_path / "_ok" / "movie.mp4")


def test_unique_target_path_returns_base_when_free(tmp_path: Path):
    source = tmp_path / "movie.mp4"

    assert unique_target_path_for_subfolder(str(source), "_ok") == str(
        tmp_path / "_ok" / "movie.mp4"
    )


def test_unique_target_path_avoids_existing_names(tmp_path: Path):
    source = tmp_path / "movie.mp4"
    target_dir = tmp_path / "_ok"
    target_dir.mkdir()
    (target_dir / "movie.mp4").write_text("a", encoding="utf-8")
    (target_dir / "movie (1).mp4").write_text("b", encoding="utf-8")

    assert unique_target_path_for_subfolder(str(source), "_ok") == str(
        target_dir / "movie (2).mp4"
    )


def test_move_file_to_path_moves_to_explicit_target(tmp_path: Path):
    source = tmp_path / "movie.mp4"
    source.write_text("video", encoding="utf-8")
    target = tmp_path / "_ok" / "renamed.mp4"

    result = move_file_to_path(str(source), str(target))

    assert result == str(target)
    assert not source.exists()
    assert target.read_text(encoding="utf-8") == "video"


def test_move_file_to_path_rejects_existing_target_without_overwrite(tmp_path: Path):
    source = tmp_path / "movie.mp4"
    source.write_text("source", encoding="utf-8")
    target_dir = tmp_path / "_ok"
    target_dir.mkdir()
    target = target_dir / "renamed.mp4"
    target.write_text("existing", encoding="utf-8")

    with pytest.raises(TargetFileExistsError):
        move_file_to_path(str(source), str(target))

    assert source.read_text(encoding="utf-8") == "source"
    assert target.read_text(encoding="utf-8") == "existing"


def test_move_file_to_path_overwrite_allows_existing_target(tmp_path: Path):
    source = tmp_path / "movie.mp4"
    source.write_text("source", encoding="utf-8")
    target_dir = tmp_path / "_ok"
    target_dir.mkdir()
    target = target_dir / "renamed.mp4"
    target.write_text("existing", encoding="utf-8")

    result = move_file_to_path(str(source), str(target), overwrite=True)

    assert result == str(target)
    assert not source.exists()
    assert target.read_text(encoding="utf-8") == "source"


def test_move_file_to_path_requires_existing_source(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        move_file_to_path(str(tmp_path / "missing.mp4"), str(tmp_path / "_ok" / "x.mp4"))


def test_move_file_to_subfolder_as_unique_picks_free_name(tmp_path: Path):
    source = tmp_path / "movie.mp4"
    source.write_text("source", encoding="utf-8")
    target_dir = tmp_path / "_ok"
    target_dir.mkdir()
    (target_dir / "movie.mp4").write_text("existing", encoding="utf-8")

    result = move_file_to_subfolder_as_unique(str(source), "_ok")

    assert result == str(target_dir / "movie (1).mp4")
    assert not source.exists()
    assert (target_dir / "movie.mp4").read_text(encoding="utf-8") == "existing"
    assert (target_dir / "movie (1).mp4").read_text(encoding="utf-8") == "source"


def test_move_file_to_subfolder_as_unique_recovers_when_target_appears_before_move(
    tmp_path: Path,
):
    source = tmp_path / "movie.mp4"
    source.write_text("source", encoding="utf-8")
    target_dir = tmp_path / "_ok"
    target_dir.mkdir()
    (target_dir / "movie.mp4").write_text("existing", encoding="utf-8")
    exists_calls = []

    def racy_exists(path: str) -> bool:
        exists_calls.append(path)
        if path.endswith("movie (1).mp4") and exists_calls.count(path) == 2:
            Path(path).write_text("sneaked-in", encoding="utf-8")
            return True
        return Path(path).exists()

    def racy_move(src: str, dst: str) -> str:
        Path(src).rename(dst)
        return dst

    result = move_file_to_subfolder_as_unique(
        str(source),
        "_ok",
        move_func=racy_move,
        retry_delays=(),
        exists_func=racy_exists,
    )

    assert result == str(target_dir / "movie (2).mp4")
    assert (target_dir / "movie (1).mp4").read_text(encoding="utf-8") == "sneaked-in"
    assert (target_dir / "movie (2).mp4").read_text(encoding="utf-8") == "source"


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


@pytest.mark.parametrize(
    "subfolder",
    ["", ".", "..", "nested/path", r"nested\path", r"C:\target", "/target"],
)
def test_validate_move_to_subfolder_rejects_unsafe_subfolder(tmp_path: Path, subfolder: str):
    source = tmp_path / "movie.mp4"
    source.write_text("video", encoding="utf-8")

    with pytest.raises(InvalidMoveTargetError):
        validate_move_to_subfolder(str(source), subfolder)

    assert source.exists()


def test_validate_move_to_subfolder_requires_existing_source(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        validate_move_to_subfolder(str(tmp_path / "missing.mp4"), "_ok")
