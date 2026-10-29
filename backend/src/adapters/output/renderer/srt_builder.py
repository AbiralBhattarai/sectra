from src.domain.models.render import RenderPlan


def build_srt(plan: RenderPlan) -> str:
    blocks = []
    for index, cue in enumerate(plan.subtitles, start=1):
        text = " ".join(w.text for w in cue.words)
        blocks.append(f"{index}\n{_srt_time(cue.start)} --> {_srt_time(cue.end)}\n{text}\n")
    return "\n".join(blocks)


def _srt_time(seconds: float) -> str:
    millis = round(max(0.0, seconds) * 1000)
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
