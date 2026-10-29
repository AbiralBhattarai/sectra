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

    @property
    def stream(self) -> str:
        """Redis stream the job is queued on. Rendering gets its own stream so an
        export is never stuck behind a long transcription."""
        return "jobs:render" if self is JobType.EXPORT else "jobs:analysis"

    @property
    def next_stage(self) -> "JobType | None":
        """Stage queued automatically after this one succeeds."""
        return _NEXT_STAGE.get(self)


_NEXT_STAGE = {
    JobType.INGEST: JobType.NORMALIZE,
    JobType.NORMALIZE: JobType.PREPARE,
    JobType.PREPARE: JobType.VAD,
    JobType.VAD: JobType.TRANSCRIBE,
    JobType.TRANSCRIBE: JobType.ANALYZE,
}
