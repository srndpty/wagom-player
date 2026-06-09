from dataclasses import dataclass


@dataclass(frozen=True)
class MoveOutcome:
    removed_path: str
    target_path: str | None
    next_index: int | None


class FileOrganizerService:
    """Application boundary for file organization workflows.

    The Qt window still owns dialogs and playback timing; this service is the
    stable home for non-UI move orchestration as the refactor continues.
    """

    def outcome(
        self,
        removed_path: str,
        target_path: str | None,
        next_index: int | None,
    ) -> MoveOutcome:
        return MoveOutcome(
            removed_path=removed_path,
            target_path=target_path,
            next_index=next_index,
        )
