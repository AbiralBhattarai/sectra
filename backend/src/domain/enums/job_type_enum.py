from enum import StrEnum


class JobType(StrEnum):
    PING = "ping"
    INGEST = "ingest"
    NORMALIZE = "normalize"
    PREPARE = "prepare"
    VAD = "vad"
    TRANSCRIBE = "transcribe"
    ANALYZE = "analyze"
    EXPORT = "export"
    TRACK = "track"
    #: Stories: text → narration.wav (+ lipsync.json), then narration → source.mp4.
    NARRATE = "narrate"
    COMPOSE = "compose"
    #: Adds a gameplay clip to the background library (download or upload, then re-encode).
    BACKGROUND = "background"

    @property
    def stream(self) -> str:
        """Redis stream the job is queued on. Downloads, rendering and face tracking get
        their own streams so none is stuck behind a long transcription, or behind each
        other; ``jobs:analysis`` holds every stage from NORMALIZE to ANALYZE."""
        return _STREAMS.get(self, "jobs:analysis")

    @property
    def next_stage(self) -> "JobType | None":
        """Stage queued automatically after this one succeeds."""
        return _NEXT_STAGE.get(self)


_STREAMS = {
    JobType.INGEST: "jobs:ingest",
    JobType.EXPORT: "jobs:render",
    JobType.TRACK: "jobs:tracking",
    JobType.BACKGROUND: "jobs:ingest",
}

_NEXT_STAGE = {
    JobType.INGEST: JobType.NORMALIZE,
    JobType.NORMALIZE: JobType.PREPARE,
    JobType.PREPARE: JobType.VAD,
    JobType.VAD: JobType.TRANSCRIBE,
    JobType.TRANSCRIBE: JobType.ANALYZE,
    # Stories build source.mp4 themselves, then join the clipping pipeline at PREPARE.
    JobType.NARRATE: JobType.COMPOSE,
    JobType.COMPOSE: JobType.PREPARE,
}
