from collections.abc import Mapping
from pathlib import Path

from src.domain.models.edl import Color
from src.domain.models.render import CropMove, PlannedBroll, PlannedSegment, RenderPlan
from src.domain.services.color_grading import matrix, transfer

#: Every segment is resampled to this rate: xfade needs identical inputs.
OUTPUT_FPS = 30
_AUDIO_FORMAT = "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"


def build_command(
    plan: RenderPlan,
    inputs: Mapping[str, Path],
    music: Path | None,
    ass: Path,
    fonts_dir: Path,
    output: Path,
) -> list[str]:
    """ffmpeg arguments (after the global flags) rendering ``plan``; ``inputs`` maps each
    segment's/B-roll item's ``input`` key to its file.

    Each video segment is its own input with ``-ss`` before ``-i``: ffmpeg seeks to the
    nearest keyframe and decodes only from there. Each segment is normalised (size, fps,
    pixel and sample format, exact length) so neighbours can be joined with ``xfade`` /
    ``acrossfade`` (transition) or ``concat`` (hard cut)."""
    args: list[str] = []
    filters: list[str] = []
    for i, segment in enumerate(plan.segments):
        args += _segment_input(segment, inputs[segment.input])
        filters += _segment_video(plan, segment, i)
        filters.append(_segment_audio(segment, i))
    count = len(plan.segments)

    video, audio = "[v0]", "[a0]"
    for i in range(1, count):
        segment = plan.segments[i]
        if segment.transition:
            d = segment.transition.duration
            filters += [
                f"{video}[v{i}]xfade=transition={segment.transition.type.value}:"
                f"duration={d:.3f}:offset={segment.offset:.3f}[jv{i}]",
                f"{audio}[a{i}]acrossfade=d={d:.3f}:c1=tri:c2=tri[ja{i}]",
            ]
        else:
            # concat drops the frame rate (ffmpeg 7 reports 1/0), which a later xfade rejects.
            filters += [
                f"{video}{audio}[v{i}][a{i}]concat=n=2:v=1:a=1[cv{i}][ja{i}]",
                f"[cv{i}]fps={OUTPUT_FPS}[jv{i}]",
            ]
        video, audio = f"[jv{i}]", f"[ja{i}]"

    for k, item in enumerate(plan.broll):
        index = count + k
        args += _broll_input(item, inputs[item.input])
        filters.append(_broll_video(item, index, k))
        filters.append(
            f"{video}[b{k}]overlay=x={item.x}:y={item.y}:eof_action=pass:"
            f"enable='between(t,{item.start:.3f},{item.start + item.duration:.3f})'[ov{k}]"
        )
        video = f"[ov{k}]"
        if item.has_audio:
            filters += [
                _broll_audio(item, index, k),
                f"{audio}[ba{k}]amix=inputs=2:duration=first:normalize=0[am{k}]",
            ]
            audio = f"[am{k}]"

    finish = ["setsar=1"]
    audio_finish = []
    if plan.fade_in > 0:
        finish.append(f"fade=t=in:st=0:d={plan.fade_in:.3f}")
        audio_finish.append(f"afade=t=in:st=0:d={plan.fade_in:.3f}")
    if plan.fade_out > 0:
        start = plan.duration - plan.fade_out
        finish.append(f"fade=t=out:st={start:.3f}:d={plan.fade_out:.3f}")
        audio_finish.append(f"afade=t=out:st={start:.3f}:d={plan.fade_out:.3f}")
    finish += [f"subtitles=filename={ass}:fontsdir={fonts_dir}", "format=yuv420p"]
    filters.append(f"{video}{','.join(finish)}[video]")
    filters.append(f"{audio}{','.join(audio_finish) or 'anull'}[voice]")

    audio = "[voice]"
    if music is not None and plan.music_volume is not None:
        music_input = count + len(plan.broll)
        args += ["-stream_loop", "-1", "-i", str(music)]
        filters.append(
            f"[{music_input}:a:0]atrim=duration={plan.duration:.3f},volume={plan.music_volume:.3f},"
            f"{_AUDIO_FORMAT}[music]"
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
        "-r", str(OUTPUT_FPS),
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-t", f"{plan.duration:.3f}",
        str(output),
    ]  # fmt: skip


def _segment_input(segment: PlannedSegment, path: Path) -> list[str]:
    if segment.kind == "image":
        return [
            "-loop",
            "1",
            "-framerate",
            str(OUTPUT_FPS),
            "-t",
            f"{segment.length:.3f}",
            "-i",
            str(path),
        ]
    if segment.kind == "freeze":
        return ["-ss", f"{segment.source_start:.3f}", "-t", "1", "-i", str(path)]
    return [
        "-ss",
        f"{segment.source_start:.3f}",
        "-t",
        f"{segment.source_duration:.3f}",
        "-i",
        str(path),
    ]


def _segment_video(plan: RenderPlan, segment: PlannedSegment, i: int) -> list[str]:
    """Filters turning input ``i`` into ``[v{i}]``: exactly ``length`` seconds of
    WxH yuv420p at OUTPUT_FPS."""
    length = f"{segment.length:.3f}"
    if segment.kind == "freeze":
        head = f"[{i}:v:0]trim=end_frame=1,setpts=PTS-STARTPTS,fps={OUTPUT_FPS},tpad=stop_mode=clone:stop_duration={length}"
    elif segment.kind == "image":
        head = f"[{i}:v:0]setpts=PTS-STARTPTS,fps={OUTPUT_FPS}"
    else:
        head = f"[{i}:v:0]setpts=(PTS-STARTPTS)/{segment.speed:g},fps={OUTPUT_FPS}"
    tail = ",".join(
        [*_color(segment.color), "tpad=stop_mode=clone:stop_duration=0.5", f"trim=duration={length}",
         # setpts unsets the frame rate (ffmpeg 7), and xfade needs a constant one.
         "setpts=PTS-STARTPTS", "format=yuv420p", "setsar=1", f"fps={OUTPUT_FPS}"]
    )  # fmt: skip

    if len(segment.crops) == 2:
        pane_height = plan.height // 2
        top, bottom = (
            f"crop={c.width}:{c.height}:{c.x}:{c.y},scale={plan.width}:{pane_height}:flags=lanczos"
            for c in segment.crops
        )
        return [
            f"{head},split=2[l{i}][r{i}]",
            f"[l{i}]{top}[t{i}]",
            f"[r{i}]{bottom}[u{i}]",
            f"[t{i}][u{i}]vstack=inputs=2,{tail}[v{i}]",
        ]
    if segment.crop_to is not None:
        return [f"{head},{_ken_burns(plan, segment)},{tail}[v{i}]"]
    c = segment.crops[0]
    x = _position(segment.crop_moves, c.x, "x")
    y = _position(segment.crop_moves, c.y, "y")
    pane = f"crop={c.width}:{c.height}:{x}:{y},scale={plan.width}:{plan.height}:flags=lanczos"
    return [f"{head},{pane},{tail}[v{i}]"]


def _segment_audio(segment: PlannedSegment, i: int) -> str:
    length = f"{segment.length:.3f}"
    if not segment.has_audio:
        return f"anullsrc=channel_layout=stereo:sample_rate=48000,atrim=duration={length},{_AUDIO_FORMAT}[a{i}]"
    chain = ["asetpts=PTS-STARTPTS", *_atempo(segment.speed)]
    if segment.volume != 1:
        chain.append(f"volume={segment.volume:.3f}")
    if segment.audio_fade_in > 0:
        chain.append(f"afade=t=in:st=0:d={segment.audio_fade_in:.3f}")
    if segment.audio_fade_out > 0:
        start = segment.length - segment.audio_fade_out
        chain.append(f"afade=t=out:st={start:.3f}:d={segment.audio_fade_out:.3f}")
    chain += [_AUDIO_FORMAT, "apad", f"atrim=duration={length}", "asetpts=PTS-STARTPTS"]
    return f"[{i}:a:0]{','.join(chain)}[a{i}]"


def _atempo(speed: float) -> list[str]:
    """atempo takes 0.5–2 per instance; chain them for anything outside."""
    stages: list[str] = []
    while speed > 2:
        stages.append("atempo=2")
        speed /= 2
    while speed < 0.5:
        stages.append("atempo=0.5")
        speed /= 0.5
    if abs(speed - 1) > 1e-6:
        stages.append(f"atempo={speed:g}")
    return stages


def _color(color: Color | None) -> list[str]:
    """The grade as lutrgb (brightness, contrast) + colorchannelmixer (saturate, sepia,
    hue): the same maths as the preview's CSS filter."""
    if color is None:
        return []
    filters = []
    slope, intercept = transfer(color)
    if abs(slope - 1) > 1e-6 or abs(intercept) > 1e-6:
        lut = f"'clip(val*{slope:.4f}+{intercept * 255:.2f},0,255)'"
        filters.append(f"lutrgb=r={lut}:g={lut}:b={lut}")
    m = matrix(color)
    if any(abs(m[r][c] - (r == c)) > 1e-4 for r in range(3) for c in range(3)):
        names = ("r", "g", "b")
        mix = ":".join(f"{names[r]}{names[c]}={m[r][c]:.4f}" for r in range(3) for c in range(3))
        filters.append(f"colorchannelmixer={mix}")
    return filters


def _ken_burns(plan: RenderPlan, segment: PlannedSegment) -> str:
    """Animated framing from ``crops[0]`` to ``crop_to``. crop can't change size per
    frame, so zoompan zooms a source-aspect window that holds the target (it cannot
    change aspect either) and a moving crop cuts the output's aspect out of it."""
    a, b = segment.crops[0], segment.crop_to
    sw, sh = segment.source_width, segment.source_height
    frames = max(segment.length * OUTPUT_FPS, 1)
    p = f"min(1,on/{frames:.1f})"  # progress, zoompan's frame counter
    pt = f"min(1,t/{segment.length:.3f})"  # progress, crop's timestamp

    def lerp(u: float, v: float, prog: str) -> str:
        return f"({u}+{v - u}*{prog})"

    if plan.width / plan.height <= sw / sh:
        # Output is narrower than the source: the window's height is the target's.
        zoom = f"{sh}/{lerp(a.height, b.height, p)}"
        zp_w = f"({lerp(a.height, b.height, p)}*{sw / sh:.6f})"
        centre = f"({lerp(a.x, b.x, p)}+{lerp(a.width, b.width, p)}/2)"
        zx = f"max(0,min({sw}-{zp_w},{centre}-{zp_w}/2))"
        zy = lerp(a.y, b.y, p)
        out_w, out_h = _even(plan.height * sw / sh), plan.height
        zp_w_t = f"({lerp(a.height, b.height, pt)}*{sw / sh:.6f})"
        centre_t = f"({lerp(a.x, b.x, pt)}+{lerp(a.width, b.width, pt)}/2)"
        zx_t = f"max(0,min({sw}-{zp_w_t},{centre_t}-{zp_w_t}/2))"
        cx = f"({lerp(a.x, b.x, pt)}-{zx_t})*{plan.height}/{lerp(a.height, b.height, pt)}"
        cy = "0"
    else:
        zoom = f"{sw}/{lerp(a.width, b.width, p)}"
        zp_h = f"({lerp(a.width, b.width, p)}*{sh / sw:.6f})"
        centre = f"({lerp(a.y, b.y, p)}+{lerp(a.height, b.height, p)}/2)"
        zx = lerp(a.x, b.x, p)
        zy = f"max(0,min({sh}-{zp_h},{centre}-{zp_h}/2))"
        out_w, out_h = plan.width, _even(plan.width * sh / sw)
        zp_h_t = f"({lerp(a.width, b.width, pt)}*{sh / sw:.6f})"
        centre_t = f"({lerp(a.y, b.y, pt)}+{lerp(a.height, b.height, pt)}/2)"
        zy_t = f"max(0,min({sh}-{zp_h_t},{centre_t}-{zp_h_t}/2))"
        cx = "0"
        cy = f"({lerp(a.y, b.y, pt)}-{zy_t})*{plan.width}/{lerp(a.width, b.width, pt)}"
    return (
        f"zoompan=z='{zoom}':x='{zx}':y='{zy}':d=1:s={out_w}x{out_h}:fps={OUTPUT_FPS},"
        f"crop={plan.width}:{plan.height}:'{cx}':'{cy}'"
    )


def _broll_input(item: PlannedBroll, path: Path) -> list[str]:
    if item.kind == "image":
        return [
            "-loop",
            "1",
            "-framerate",
            str(OUTPUT_FPS),
            "-t",
            f"{item.duration:.3f}",
            "-i",
            str(path),
        ]
    return ["-ss", f"{item.media_start:.3f}", "-t", f"{item.duration:.3f}", "-i", str(path)]


def _broll_video(item: PlannedBroll, index: int, k: int) -> str:
    c = item.crop
    chain = [
        "setpts=PTS-STARTPTS",
        f"fps={OUTPUT_FPS}",
        f"crop={c.width}:{c.height}:{c.x}:{c.y}",
        f"scale={item.width}:{item.height}:flags=lanczos",
        "setsar=1",
        "format=yuva420p",
    ]
    if item.fade > 0:
        chain += [
            f"fade=t=in:st=0:d={item.fade:.3f}:alpha=1",
            f"fade=t=out:st={item.duration - item.fade:.3f}:d={item.fade:.3f}:alpha=1",
        ]
    chain.append(f"setpts=PTS+{item.start:.3f}/TB")
    return f"[{index}:v:0]{','.join(chain)}[b{k}]"


def _broll_audio(item: PlannedBroll, index: int, k: int) -> str:
    chain = ["asetpts=PTS-STARTPTS", f"volume={item.volume:.3f}"]
    if item.fade > 0:
        chain += [
            f"afade=t=in:st=0:d={item.fade:.3f}",
            f"afade=t=out:st={item.duration - item.fade:.3f}:d={item.fade:.3f}",
        ]
    chain += [_AUDIO_FORMAT, f"adelay={round(item.start * 1000)}:all=1"]
    return f"[{index}:a:0]{','.join(chain)}[ba{k}]"


def _position(moves: list[CropMove], fixed: int, axis: str) -> str:
    """The crop's x or y: a constant, or (face tracking) a step function of the
    segment's time written flat — first value plus each jump times ``gte(t, when)`` —
    that the crop filter evaluates per frame. Quoted so its commas don't split the
    filter chain."""
    if not moves:
        return str(fixed)
    values = [getattr(m, axis) for m in moves]
    expr = str(values[0])
    for move, previous, value in zip(moves[1:], values, values[1:], strict=False):
        if value != previous:
            delta = value - previous
            expr += f"{'+' if delta > 0 else '-'}{abs(delta)}*gte(t,{move.time:.3f})"
    return f"'{expr}'"


def _even(value: float) -> int:
    return max(2, int(round(value / 2)) * 2)
