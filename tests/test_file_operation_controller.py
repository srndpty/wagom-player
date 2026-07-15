from wagom_player.application.file_actions import CollisionResolution
from wagom_player.infrastructure.trash import TrashService
from wagom_player.ui.controllers import file_operation_controller
from wagom_player.ui.controllers.file_operation_controller import FileOperationController


def test_cancel_does_not_move_or_discard_file(monkeypatch):
    calls = []
    monkeypatch.setattr(
        file_operation_controller,
        "move_file_to_subfolder",
        lambda *args, **kwargs: calls.append("move"),
    )
    monkeypatch.setattr(
        file_operation_controller,
        "move_file_to_subfolder_as_unique",
        lambda *args, **kwargs: calls.append("rename"),
    )
    controller = FileOperationController(TrashService(lambda path: calls.append("discard")))

    result = controller.execute("movie.mp4", "_ok", CollisionResolution.CANCEL)

    assert result.resolution == CollisionResolution.CANCEL
    assert result.target_path is None
    assert calls == []
