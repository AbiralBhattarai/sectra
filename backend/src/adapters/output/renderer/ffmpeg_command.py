from pathlib import Path

from src.domain.models.render import CropMove, RenderPlan


def build_command(
    plan: RenderPlan, source: Path, music: Path | None, ass: Path, fonts_dir: Path, output: Path
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

    pairs = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(len(plan.ranges)))
    pane_height = plan.height // len(plan.crops)
    panes = [
        f"crop={c.width}:{c.height}:{_position(plan.crop_moves, c.x, 'x')}:"
        f"{_position(plan.crop_moves, c.y, 'y')},scale={plan.width}:{pane_height}:flags=lanczos"
        for c in plan.crops
    ]
    finish = f"setsar=1,subtitles=filename={ass}:fontsdir={fonts_dir}[video]"
    filters = [f"{pairs}concat=n={len(plan.ranges)}:v=1:a=1[cut][voice]"]
    if len(panes) == 1:
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
        "-c:a", "aac", "-b:a", "192k",
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
