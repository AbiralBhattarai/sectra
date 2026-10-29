from pydantic import BaseModel


class MusicTrack(BaseModel):
    #: Stored file name, which an EDL's ``music.file`` refers to.
    file: str
    #: Name shown to the user.
    name: str
    artist: str | None = None
    #: Rough feel ("upbeat", "chill", …) for grouping the built-in library.
    mood: str | None = None
    #: Part of Sectra's built-in CC0 library rather than uploaded by the user.
    default: bool = False
