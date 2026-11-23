from pathlib import Path

from src.adapters.output.renderer.character_frames import bob_margin
from src.domain.models.render import CropMove, RenderPlan, ZoomCue


def build_command(
    plan: RenderPlan,
    source: Path,
    music: Path | None,
    ass: Path,
    fonts_dir: Path,
    output: Path,
    character: Path | None = None,
) -> list[str]:
    """ffmpeg arguments (after the global flags) rendering ``plan``.

    Each kept range is its own input with ``-ss`` before ``-i``: ffmpeg seeks to the
    nearest keyframe and decodes only from there, instead of a ``trim`` filter decoding
    the whole source up to the clip."""
    args: list[str] = []
    for span in plan.ranges:
        args += ["-ss", f"{span.start:.3f}", "-t", f"{span.duration:.3f}", "-i", str(source)]
    music_input = len(plan.ranges)
    if music is not None:
        args += ["-stream_loop", "-1", "-i", str(music)]
    character_input = music_input + (music is not None)
    if character is not None:
        args += ["-i", str(character)]

    pairs = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(len(plan.ranges)))
    pane_height = plan.height // len(plan.crops)
    panes = [
        f"crop={c.width}:{c.height}:{_position(plan.crop_moves, c.x, 'x')}:"
        f"{_position(plan.crop_moves, c.y, 'y')},scale={plan.width}:{pane_height}:flags=lanczos"
        f"{_zoom(plan.zooms, plan.width, pane_height)}"
        for c in plan.crops
    ]
    subtitles = f"subtitles=filename={ass}:fontsdir={fonts_dir}[video]"
    finish = f"setsar=1,{subtitles}"
    if character is not None and plan.character is not None:
        # The narrator goes over the picture and under the captions.
        box = plan.character
        y = box.y - bob_margin(box.height)
        finish = (
            f"setsar=1[picture];[picture][{character_input}:v:0]"
            f"overlay={box.x}:{y}:eof_action=pass:format=auto,{subtitles}"
        )
    filters = [f"{pairs}concat=n={len(plan.ranges)}:v=1:a=1[cut][voice]"]
    if plan.pip is not None:
        pip = plan.pip
        src = pip.source
        # Gameplay fills the frame; the facecam box goes on top, captions over both.
        filters += [
            "[cut]split=2[main][cam]",
            f"[main]{panes[0]}[game]",
            f"[cam]crop={src.width}:{src.height}:{src.x}:{src.y},"
            f"scale={pip.width}:{pip.height}:flags=lanczos,setsar=1[face]",
            f"[game][face]overlay={pip.x}:{pip.y},{finish}",
        ]
    elif len(panes) == 1:
        filters.append(f"[cut]{panes[0]},{finish}")
    else:
        filters += [
            "[cut]split=2[left][right]",
            f"[left]{panes[0]}[top]",
            f"[right]{panes[1]}[bottom]",
            f"[top][bottom]vstack=inputs=2,{finish}",
        ]
    audio = "[voice]"
    if music is not None and plan.music_volume is not None:
        filters.append(
            f"[{music_input}:a:0]atrim=duration={plan.duration:.3f},volume={plan.music_volume:.3f}[music]"
        )
        if plan.duck_music:
            filters += [
                "[voice]asplit=2[speech][key]",
                # The speech keys a compressor on the music: louder voice, quieter music.
                "[music][key]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[bed]",
                "[speech][bed]amix=inputs=2:duration=first:normalize=0[mix]",
            ]
        else:
            filters.append("[voice][music]amix=inputs=2:duration=first:normalize=0[mix]")
        audio = "[mix]"

    return args + [
        "-filter_complex", ";".join(filters),
        "-map", "[video]", "-map", audio,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart",
        str(output),
    ]  # fmt: skip


def _position(moves: list[CropMove], fixed: int, axis: str) -> str:
    """The crop's x or y: a constant, or (face tracking) a step function of output time
    written flat — first value plus each jump times ``gte(t, when)`` — that the crop
    filter evaluates per frame. Quoted so its commas don't split the filter chain."""
    if not moves:
        return str(fixed)
    values = [getattr(m, axis) for m in moves]
    expr = str(values[0])
    for move, previous, value in zip(moves[1:], values, values[1:], strict=False):
        if value != previous:
            delta = value - previous
            expr += f"{'+' if delta > 0 else '-'}{abs(delta)}*gte(t,{move.time:.3f})"
    return f"'{expr}'"


def _zoom(zooms: list[ZoomCue], width: int, height: int) -> str:
    """Zoom-ins on the already framed picture: scale it up per frame by ``Z(t)`` and
    crop the centre back to the frame size. ``Z`` is written flat — one term per zoom,
    a hard step for a punch-in, a linear ramp for a push — and evaluated every frame."""
    if not zooms:
        return ""
    terms = []
    for z in zooms:
        window = f"gte(t,{z.start:.3f})*lt(t,{z.end:.3f})"
        ease = f"*clip((t-{z.start:.3f})/{z.ramp:.3f},0,1)" if z.ramp > 0 else ""
        terms.append(f"{z.scale - 1:.4f}*{window}{ease}")
    factor = "(1+" + "+".join(terms) + ")"
    scaled_w = f"2*trunc({width}*{factor}/2)"
    scaled_h = f"2*trunc({height}*{factor}/2)"
    # crop's iw/ih (and its default centring) keep the size the graph was configured
    # with, so the centre offset is written out from t like the scale itself.
    return (
        f",scale=w='{scaled_w}':h='{scaled_h}':eval=frame:flags=bicubic"
        f",crop={width}:{height}:x='({scaled_w}-{width})/2':y='({scaled_h}-{height})/2'"
    )
