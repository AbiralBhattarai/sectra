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
}

_NEXT_STAGE = {
    JobType.INGEST: JobType.NORMALIZE,
    JobType.NORMALIZE: JobType.PREPARE,
    JobType.PREPARE: JobType.VAD,
    JobType.VAD: JobType.TRANSCRIBE,
    JobType.TRANSCRIBE: JobType.ANALYZE,
}
