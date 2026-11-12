from pathlib import Path

from src.adapters.output.renderer.ass_builder import ASS_SIZE_PER_EM, build_ass
from src.adapters.output.renderer.ffmpeg_command import build_command
from src.adapters.output.renderer.srt_builder import build_srt
from src.domain.enums.caption_style_enum import CaptionStyle
from src.domain.enums.overlay_style_enum import OverlayStyle
from src.domain.models.edl import (
    Color,
    Crop,
    FreezeSegment,
    ImageSegment,
    Music,
    Overlay,
    Transition,
)
from src.domain.models.render import CropMove, MediaSource
from src.domain.models.transcript import Word
from src.domain.services.render_planning import plan_render
from tests.unit.edl_builders import edl, seg, sources


def plan(style=CaptionStyle.BOLD_HIGHLIGHT, music=None, overlays=(), split_screen=False, **fields):
    clip = edl(
        (10, 12),
        (20, 23),
        captions=[
            Word(text="hello", start=10.2, end=10.6),
            Word(text="{world}", start=10.7, end=11.0),
        ],
        overlays=list(overlays),
        music=music,
        split_screen=split_screen,
        **fields,
    )
    clip.captions.style = style
    return plan_render(clip, sources())


INPUTS = {"main": Path("/v/source.mp4")}


def graph_of(args: list[str]) -> str:
    return args[args.index("-filter_complex") + 1]


def dialogues(ass: str) -> list[str]:
    return [line for line in ass.splitlines() if line.startswith("Dialogue:")]


def test_bold_highlight_emits_one_event_per_word_with_it_highlighted():
    ass = build_ass(plan())
    events = dialogues(ass)
    assert len(events) == 2
    assert events[0].startswith("Dialogue: 0,0:00:00.20,0:00:00.70,bold,")
    assert events[0].endswith("{\\c&H4DE1FF&}HELLO{\\c&HFFFFFF&} (WORLD)")
    # Braces in the text are escaped; the second word is the highlighted one.
    assert events[1].endswith("HELLO {\\c&H4DE1FF&}(WORLD){\\c&HFFFFFF&}")
    assert "PlayResX: 1080\nPlayResY: 1920" in ass


def test_caption_size_follows_cqmin_and_libass_metrics():
    ass = build_ass(plan())
    bold = next(line for line in ass.splitlines() if line.startswith("Style: bold,"))
    size = float(bold.split(",")[2])
    assert size == round(7 * 1080 / 100 * ASS_SIZE_PER_EM, 1)


def test_clean_captions_are_one_event_per_page_and_overlays_are_positioned():
    overlays = [Overlay(text="Hook", start=0, end=2, x=0.25, y=0.1, style=OverlayStyle.LABEL)]
    events = dialogues(build_ass(plan(CaptionStyle.CLEAN, overlays=overlays)))
    assert events[0].endswith("{\\an2\\pos(540,1747)}hello (world)")
    assert events[1] == "Dialogue: 1,0:00:00.00,0:00:02.00,label,,0,0,0,,{\\an5\\pos(270,192)}Hook"


def test_no_captions_style_renders_only_overlays():
    assert dialogues(build_ass(plan(CaptionStyle.NONE))) == []


def test_srt_uses_output_time():
    assert build_srt(plan()) == "1\n00:00:00,200 --> 00:00:01,300\nhello {world}\n"


def test_command_seeks_each_segment_joins_them_and_ducks_music():
    music = Music(file="abc-beat.mp3", volume=0.2, duck=True)
    args = build_command(
        plan(music=music),
        INPUTS,
        Path("/m/beat.mp3"),
        Path("/v/x.ass"),
        Path("/fonts"),
        Path("/v/out.mp4"),
    )
    joined = " ".join(args)
    assert "-ss 10.000 -t 2.000 -i /v/source.mp4 -ss 20.000 -t 3.000 -i /v/source.mp4" in joined
    assert "-stream_loop -1 -i /m/beat.mp3" in joined
    graph = graph_of(args)
    assert (
        "[0:v:0]setpts=(PTS-STARTPTS)/1,fps=30,crop=608:1080:656:0,scale=1080:1920:flags=lanczos,"
        in graph
    )
    assert "trim=duration=2.000,setpts=PTS-STARTPTS,format=yuv420p,setsar=1,fps=30[v0]" in graph
    assert "[0:a:0]asetpts=PTS-STARTPTS,aformat=" in graph
    assert "[v0][a0][v1][a1]concat=n=2:v=1:a=1[cv1][ja1];[cv1]fps=30[jv1]" in graph
    assert (
        "[jv1]setsar=1,subtitles=filename=/v/x.ass:fontsdir=/fonts,format=yuv420p[video]" in graph
    )
    assert "[2:a:0]atrim=duration=5.000,volume=0.200," in graph
    assert "sidechaincompress" in graph
    assert args[args.index("-map") + 3] == "[mix]"
    assert args[args.index("-t", args.index("-filter_complex")) + 1] == "5.000"


def test_command_without_music_maps_the_voice():
    args = build_command(plan(), INPUTS, None, Path("a"), Path("f"), Path("o"))
    assert "-stream_loop" not in args
    assert args[args.index("-map") + 3] == "[voice]"


def test_transitions_crossfade_picture_and_sound_at_the_planned_offset():
    clip = edl((10, 12), seg(20, 23, speed=2, transition=Transition(type="wipeleft", duration=0.5)))
    graph = graph_of(
        build_command(plan_render(clip, sources()), INPUTS, None, Path("a"), Path("f"), Path("o"))
    )
    assert "[v0][v1]xfade=transition=wipeleft:duration=0.500:offset=1.500[jv1]" in graph
    assert "[a0][a1]acrossfade=d=0.500:c1=tri:c2=tri[ja1]" in graph
    assert "setpts=(PTS-STARTPTS)/2," in graph and "atempo=2" in graph


def test_stills_speed_volume_grade_and_fades():
    clip = edl(
        seg(
            10,
            12,
            speed=0.25,
            volume=1.5,
            audio_fade_in=0.2,
            color=Color(brightness=1.2, saturation=0),
        ),
        FreezeSegment(at=11, duration=1),
        ImageSegment(image="a.png", duration=2),
        fade_in=0.5,
        fade_out=1,
    )
    image = {"image:a.png": MediaSource(width=400, height=400, has_audio=False)}
    args = build_command(
        plan_render(clip, sources(**image)),
        {**INPUTS, "image:a.png": Path("/i/a.png")},
        None,
        Path("a"),
        Path("f"),
        Path("o"),
    )
    joined, graph = " ".join(args), graph_of(args)
    assert "-ss 11.000 -t 1 -i /v/source.mp4" in joined
    assert "-loop 1 -framerate 30 -t 2.000 -i /i/a.png" in joined
    assert "atempo=0.5,atempo=0.5,volume=1.500,afade=t=in:st=0:d=0.200" in graph
    assert "lutrgb=r='clip(val*1.2000+0.00,0,255)'" in graph
    assert "colorchannelmixer=rr=0.2130:rg=0.7150:rb=0.0720" in graph
    assert (
        "[1:v:0]trim=end_frame=1,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration=1.000"
        in graph
    )
    assert "anullsrc=channel_layout=stereo:sample_rate=48000,atrim=duration=1.000" in graph
    assert "fade=t=in:st=0:d=0.500,fade=t=out:st=10.000:d=1.000" in graph
    assert "afade=t=in:st=0:d=0.500,afade=t=out:st=10.000:d=1.000[voice]" in graph


def test_split_screen_crops_both_halves_and_stacks_them():
    graph = graph_of(
        build_command(plan(split_screen=True), INPUTS, None, Path("a"), Path("f"), Path("o"))
    )
    assert (
        "fps=30,split=2[l0][r0];"
        "[l0]crop=960:854:0:113,scale=1080:960:flags=lanczos[t0];"
        "[r0]crop=960:854:960:113,scale=1080:960:flags=lanczos[u0];"
        "[t0][u0]vstack=inputs=2,tpad"
    ) in graph


def test_tracked_crop_is_a_step_function_of_segment_time():
    planned = plan()
    planned.segments[0].crop_moves = [
        CropMove(time=0, x=80, y=0),
        CropMove(time=0.5, x=1232, y=0),
        CropMove(time=1.5, x=80, y=0),
    ]
    args = build_command(planned, INPUTS, None, Path("a"), Path("f"), Path("o"))
    assert "crop=608:1080:'80+1152*gte(t,0.500)-1152*gte(t,1.500)':'0'," in graph_of(args)
    assert args.count("-i") == 2  # still one input per segment


def test_ken_burns_zooms_then_crops_a_moving_window():
    clip = edl(seg(0, 4, crop=Crop(), crop_to=Crop(scale=2)))
    graph = graph_of(
        build_command(plan_render(clip, sources()), INPUTS, None, Path("a"), Path("f"), Path("o"))
    )
    assert "zoompan=z='1080/(1080+-540*min(1,on/120.0))'" in graph
    assert ":d=1:s=3414x1920:fps=30,crop=1080:1920:" in graph


def test_broll_is_overlaid_during_its_span_and_mixed_when_audible():
    other = "00000000-0000-0000-0000-0000000000b0"
    clip = edl(
        (0, 10), broll=[{"media": other, "start": 2, "duration": 3, "volume": 0.5, "fade": 0.5}]
    )
    planned = plan_render(
        clip, sources(**{other: MediaSource(width=1920, height=1080, has_audio=True)})
    )
    args = build_command(
        planned, {**INPUTS, other: Path("/b.mp4")}, None, Path("a"), Path("f"), Path("o")
    )
    graph = graph_of(args)
    assert "-ss 0.000 -t 3.000 -i /b.mp4" in " ".join(args)
    assert "fade=t=out:st=2.500:d=0.500:alpha=1,setpts=PTS+2.000/TB[b0]" in graph
    assert "[v0][b0]overlay=x=0:y=0:eof_action=pass:enable='between(t,2.000,5.000)'[ov0]" in graph
    assert "adelay=2000:all=1[ba0]" in graph and "[a0][ba0]amix" in graph
