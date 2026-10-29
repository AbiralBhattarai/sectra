from enum import StrEnum


class VideoFile(StrEnum):
    """Files kept per source video once it has been processed."""

    SOURCE = "source.mp4"  # normalized: short side ≤ 1080, H.264/AAC; the editor plays it
    AUDIO = "audio.wav"  # 16 kHz mono PCM, input for VAD and STT
    PEAKS = "peaks.json"  # waveform for the timeline
    THUMBNAIL = "thumbnail.jpg"
    SPEECH = "speech.json"  # VAD speech segments, in seconds
    TRANSCRIPT = "transcript.json"  # word-timed transcript on the source timeline
