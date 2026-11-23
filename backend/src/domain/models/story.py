from typing import Literal

from pydantic import BaseModel, Field

#: Kokoro v1.0 English voices offered in the UI: id → label. The prefix picks the
#: accent (``a`` American, ``b`` British) and the voice (``f`` female, ``m`` male).
VOICES: dict[str, str] = {
    "af_heart": "Heart (US, female)",
    "af_bella": "Bella (US, female)",
    "af_nicole": "Nicole (US, female, soft)",
    "af_sarah": "Sarah (US, female)",
    "am_michael": "Michael (US, male)",
    "am_fenrir": "Fenrir (US, male, deep)",
    "am_puck": "Puck (US, male, upbeat)",
    "bf_emma": "Emma (UK, female)",
    "bm_george": "George (UK, male)",
    "bm_fable": "Fable (UK, male)",
}
DEFAULT_VOICE = "af_heart"

#: Narrator characters bundled in ``assets/characters/``: name → (label, default voice).
CHARACTERS: dict[str, tuple[str, str]] = {
    "guy": ("Sam Stick", "am_michael"),
    "girl": ("Jane Stick", "af_heart"),
    "gent": ("George Stick", "bm_george"),
    "lady": ("Anna Stick", "bf_emma"),
}

BackgroundMode = Literal["black", "gameplay"]

#: Longest story accepted, in characters (~25 minutes of narration).
STORY_TEXT_MAX = 20_000


class StorySpec(BaseModel):
    """What the user asked for, plus what NARRATE resolved (``narration``, ``caption``)."""

    #: The pasted story.
    text: str = Field(min_length=1, max_length=STORY_TEXT_MAX)
    #: The user's title; "" = derive one (the LLM when polishing, else the first sentence).
    title: str = ""
    #: Rewrite the text for narration with the LLM first.
    polish: bool = False
    voice: str = DEFAULT_VOICE
    speed: float = Field(default=1.0, ge=0.7, le=1.5)
    background_mode: BackgroundMode = "black"
    #: A specific library clip, "<category>/<file>"; None = random.
    background: str | None = None
    #: Random clip from this category when ``background`` is None; None = any.
    category: str | None = None
    #: The talking narrator drawn on screen; None = no character.
    character: str | None = "guy"
    #: Filled by NARRATE: the text actually spoken and the social caption.
    narration: str = ""
    caption: str = ""
