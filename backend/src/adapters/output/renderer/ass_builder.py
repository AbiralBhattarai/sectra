"""Captions and overlays as an ASS script for libass. Sizes and positions mirror the
browser preview (frontend/src/styles.css), where text is sized in cqmin: 1/100 of the
frame's shorter side."""

from src.domain.enums.caption_style_enum import CaptionStyle
from src.domain.enums.overlay_style_enum import OverlayStyle
from src.domain.models.render import RenderPlan

#: libass sizes text by the font's Windows ascent + descent, not its em square; for
#: Montserrat that is (1109 + 453) / 1000 em. Measured: a 400-size "H" renders 179 px
#: tall with a 0.7 em cap height.
ASS_SIZE_PER_EM = 1.562
EXTRA_BOLD = "Montserrat ExtraBold"
SEMI_BOLD = "Montserrat SemiBold"
WHITE = "&H00FFFFFF"  # style colours are &HAABBGGRR
#: Inline colour overrides are written \c&HBBGGRR&.
HIGHLIGHT_OVERRIDE = "&H4DE1FF&"  # #ffe14d
WHITE_OVERRIDE = "&HFFFFFF&"

_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, \
Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, \
Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{styles}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def build_ass(plan: RenderPlan) -> str:
    width, height = plan.width, plan.height
    cqmin = min(width, height) / 100
    margin = round(width * 0.07)  # captions wrap at 86% of the width, like the preview

    def style(
        name,
        font,
        em_cqmin,
        border_style,
        outline,
        shadow,
        back,
        outline_colour="&H00000000",
        alignment=5,
    ):
        size = round(em_cqmin * cqmin * ASS_SIZE_PER_EM, 1)
        return (
            f"Style: {name},{font},{size},{WHITE},{WHITE},{outline_colour},{back},0,0,0,0,"
            f"100,100,0,0,{border_style},{round(outline, 1)},{round(shadow, 1)},{alignment},"
            f"{margin},{margin},0,1"
        )

    styles = [
        # 0.9cqmin stroke painted under the fill shows 0.45cqmin of outline.
        style("bold", EXTRA_BOLD, 7, 1, 0.45 * cqmin, 0, "&H00000000", alignment=8),
        style("clean", SEMI_BOLD, 4.6, 1, 0, 0.3 * cqmin, "&H26000000", alignment=2),
        style("boxed", SEMI_BOLD, 4.6, 3, 1.0 * cqmin, 0, "&H59000000", "&H59000000", alignment=2),
        style("title", EXTRA_BOLD, 5.5, 3, 1.2 * cqmin, 0, "&H4D000000", "&H4D000000"),
        style("label", SEMI_BOLD, 4, 1, 0, 0.3 * cqmin, "&H26000000"),
    ]
    lines = [_HEADER.format(width=width, height=height, styles="\n".join(styles))]

    centre = width // 2
    if plan.caption_style is CaptionStyle.BOLD_HIGHLIGHT:
        position = f"{{\\an8\\pos({centre},{round(height * 0.62)})}}"
        for cue in plan.captions:
            words = [_escape(w.text).upper() for w in cue.words]
            # One event per spoken word, with that word highlighted.
            for i, word in enumerate(cue.words):
                start = cue.start if i == 0 else word.start
                end = cue.words[i + 1].start if i + 1 < len(cue.words) else cue.end
                if end <= start:
                    continue
                text = " ".join(
                    f"{{\\c{HIGHLIGHT_OVERRIDE}}}{w}{{\\c{WHITE_OVERRIDE}}}" if j == i else w
                    for j, w in enumerate(words)
                )
                lines.append(_dialogue(0, start, end, "bold", position + text))
    elif plan.caption_style is not CaptionStyle.NONE:
        position = f"{{\\an2\\pos({centre},{round(height * 0.91)})}}"
        for cue in plan.captions:
            text = " ".join(_escape(w.text) for w in cue.words)
            lines.append(
                _dialogue(0, cue.start, cue.end, plan.caption_style.value, position + text)
            )

    for overlay in plan.overlays:
        name = "title" if overlay.style is OverlayStyle.TITLE else "label"
        position = f"{{\\an5\\pos({round(overlay.x * width)},{round(overlay.y * height)})}}"
        lines.append(
            _dialogue(1, overlay.start, overlay.end, name, position + _escape(overlay.text))
        )
    return "\n".join(lines) + "\n"


def _dialogue(layer: int, start: float, end: float, style: str, text: str) -> str:
    return f"Dialogue: {layer},{_ass_time(start)},{_ass_time(end)},{style},,0,0,0,,{text}"


def _ass_time(seconds: float) -> str:
    centis = round(max(0.0, seconds) * 100)
    hours, rest = divmod(centis, 360_000)
    minutes, rest = divmod(rest, 6_000)
    secs, centis = divmod(rest, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _escape(text: str) -> str:
    """Braces start override blocks and backslashes start escapes in ASS."""
    return text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", "\\N").strip()
