from enum import StrEnum


class VideoKind(StrEnum):
    #: A long-form video: transcribed and mined for clips.
    SOURCE = "source"
    #: Material for editing (B-roll, intros…): only normalized and prepared, no
    #: transcription or clip finding.
    ASSET = "asset"
