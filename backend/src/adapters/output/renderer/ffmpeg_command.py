from pathlib import Path

from src.domain.models.render import RenderPlan


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

    crop = plan.crop
    pairs = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(len(plan.ranges)))
    filters = [
        f"{pairs}concat=n={len(plan.ranges)}:v=1:a=1[cut][voice]",
        f"[cut]crop={crop.width}:{crop.height}:{crop.x}:{crop.y},"
        f"scale={plan.width}:{plan.height}:flags=lanczos,setsar=1,"
        f"subtitles=filename={ass}:fontsdir={fonts_dir}[video]",
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
