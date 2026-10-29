from pathlib import Path

from src.adapters.output.renderer.ass_builder import ASS_SIZE_PER_EM, build_ass
from src.adapters.output.renderer.ffmpeg_command import build_command
from src.adapters.output.renderer.srt_builder import build_srt
from src.domain.enums.caption_style_enum import CaptionStyle
from src.domain.enums.overlay_style_enum import OverlayStyle
from src.domain.models.edl import Captions, Edl, Music, Overlay
from src.domain.models.speech import TimeSpan
from src.domain.models.transcript import Word
from src.domain.services.render_planning import plan_render


def plan(style=CaptionStyle.BOLD_HIGHLIGHT, music=None, overlays=()):
    edl = Edl(
        ranges=[TimeSpan(start=10, end=12), TimeSpan(start=20, end=23)],
        captions=Captions(
            words=[
                Word(text="hello", start=10.2, end=10.6),
                Word(text="{world}", start=10.7, end=11.0),
            ],
            style=style,
        ),
        overlays=list(overlays),
        music=music,
    )
    return plan_render(edl, 1920, 1080)


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


def test_command_seeks_each_range_and_ducks_music():
    music = Music(file="abc-beat.mp3", volume=0.2, duck=True)
    args = build_command(
        plan(music=music),
        Path("/v/source.mp4"),
        Path("/m/beat.mp3"),
        Path("/v/x.ass"),
        Path("/fonts"),
        Path("/v/out.mp4"),
    )
    joined = " ".join(args)
    assert "-ss 10.000 -t 2.000 -i /v/source.mp4 -ss 20.000 -t 3.000 -i /v/source.mp4" in joined
    assert "-stream_loop -1 -i /m/beat.mp3" in joined
    graph = args[args.index("-filter_complex") + 1]
    assert "[0:v:0][0:a:0][1:v:0][1:a:0]concat=n=2:v=1:a=1[cut][voice]" in graph
    assert "crop=608:1080:656:0,scale=1080:1920" in graph
    assert "subtitles=filename=/v/x.ass:fontsdir=/fonts" in graph
    assert "[2:a:0]atrim=duration=5.000,volume=0.200[music]" in graph
    assert "sidechaincompress" in graph
    assert args[args.index("-map") + 3] == "[mix]"


def test_command_without_music_maps_the_voice():
    args = build_command(plan(), Path("s"), None, Path("a"), Path("f"), Path("o"))
    assert "-stream_loop" not in args
    assert args[args.index("-map") + 3] == "[voice]"
