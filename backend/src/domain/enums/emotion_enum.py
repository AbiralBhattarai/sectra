from enum import StrEnum


class Emotion(StrEnum):
    """A narrator character's facial expression; each has a ``base/<value>`` layer."""

    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    SHOCKED = "shocked"
    SMUG = "smug"
