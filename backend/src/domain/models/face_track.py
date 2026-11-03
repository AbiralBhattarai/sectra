from pydantic import BaseModel

#: Tracks are sampled at the rate the active-speaker model was trained on.
FRAME_RATE = 25


class FaceTrack(BaseModel):
    """One face followed across consecutive frames of the tracked span."""

    id: int
    #: Index of the track's first frame on the span's frame grid.
    first_frame: int
    #: Per frame: face centre as fractions of the source frame.
    centres: list[tuple[float, float]]
    #: Per frame: active-speaker logit, > 0 = speaking.
    scores: list[float]
