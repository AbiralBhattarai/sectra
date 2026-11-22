"""Draws Sectra's narrator characters as layered SVGs (stdlib only).

    python scripts/make_characters.py            # writes assets/characters/{guy,girl}/

Every layer shares one 1000x1500 canvas, so they stack in place:
  base/<expression>.svg  the whole figure with eyes and brows, no mouth
  mouth/<A-H,X>.svg      Rhubarb Lip Sync mouth shapes, at the mouth anchor
  blink.svg              closed eyelids (covers the open eyes)
  preview.svg            neutral face with the resting mouth, for the UI

The figures are white stick people outlined in near-black, so they read on a black
screen and on bright gameplay alike. Tweak the constants below and re-run.
"""

import json
from pathlib import Path

W, H = 1000, 1500
HEAD = (500, 430, 225)  # cx, cy, r
EYES = ((418, 418), (582, 418))
MOUTH = (500, 548)
SKIN = "#ffffff"
INK = "#151515"
BODY_OUTLINE = 36
BODY_LINE = 22
MOUTH_INSIDE = "#6e1a26"
TONGUE = "#d65a6e"
TEETH = "#ffffff"

EXPRESSIONS = ("neutral", "happy", "sad", "angry", "shocked", "smug")


# ---------------------------------------------------------------- helpers


def svg(*parts: str, defs: str = "") -> str:
    body = "\n  ".join(p for p in parts if p)
    defs_block = f"<defs>{defs}</defs>\n  " if defs else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}">\n  {defs_block}{body}\n</svg>\n'
    )


def line(points: list[tuple[float, float]], colour: str, width: float) -> str:
    d = "M " + " L ".join(f"{x} {y}" for x, y in points)
    return (
        f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="{width}" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
    )


def stroke(d: str, width: float = 12, colour: str = INK, fill: str = "none") -> str:
    return (
        f'<path d="{d}" fill="{fill}" stroke="{colour}" stroke-width="{width}" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
    )


def fill(d: str, colour: str, extra: str = "") -> str:
    return f'<path d="{d}" fill="{colour}"{extra}/>'


def mirror(x: float) -> float:
    return 2 * HEAD[0] - x


# ---------------------------------------------------------------- body & head

LIMBS = [
    [(500, 650), (500, 1060)],  # neck + torso
    [(500, 760), (405, 880), (360, 1010)],  # left arm
    [(500, 760), (600, 875), (655, 990)],  # right arm, a little open (talking pose)
    [(500, 1060), (425, 1250), (395, 1420)],  # left leg
    [(500, 1060), (575, 1250), (605, 1420)],  # right leg
    [(395, 1420), (345, 1428)],  # feet
    [(605, 1420), (655, 1428)],
]


def body() -> str:
    outline = "".join(line(limb, INK, BODY_OUTLINE) for limb in LIMBS)
    white = "".join(line(limb, SKIN, BODY_LINE) for limb in LIMBS)
    hands = "".join(
        f'<circle cx="{x}" cy="{y}" r="22" fill="{SKIN}" stroke="{INK}" stroke-width="7"/>'
        for x, y in ((360, 1010), (655, 990))
    )
    return outline + white + hands


def head() -> str:
    cx, cy, r = HEAD
    ears = "".join(
        f'<ellipse cx="{x}" cy="{cy + 10}" rx="30" ry="48" fill="{SKIN}" '
        f'stroke="{INK}" stroke-width="12"/>'
        for x in (cx - r + 6, cx + r - 6)
    )
    return ears + (
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{SKIN}" stroke="{INK}" stroke-width="12"/>'
    )


HEAD_CLIP = (
    f'<clipPath id="head"><circle cx="{HEAD[0]}" cy="{HEAD[1]}" r="{HEAD[2] - 4}"/></clipPath>'
)


# ---------------------------------------------------------------- faces


def brows(left: str, right: str, width: float = 13) -> str:
    return stroke(left, width) + stroke(right, width)


def oval_eyes(rx: float = 17, ry: float = 25, dy: float = 0) -> str:
    return "".join(
        f'<ellipse cx="{x}" cy="{y + dy}" rx="{rx}" ry="{ry}" fill="{INK}"/>'
        f'<circle cx="{x + 6}" cy="{y + dy - 9}" r="5" fill="{SKIN}"/>'
        for x, y in EYES
    )


def face(expression: str) -> str:
    (lx, ly), (rx, ry) = EYES
    if expression == "neutral":
        return oval_eyes() + brows(
            f"M {lx - 32} {ly - 62} Q {lx} {ly - 72} {lx + 30} {ly - 64}",
            f"M {rx - 30} {ry - 64} Q {rx} {ry - 72} {rx + 32} {ry - 62}",
        )
    if expression == "happy":
        arcs = "".join(stroke(f"M {x - 28} {y + 8} Q {x} {y - 30} {x + 28} {y + 8}", 13) for x, y in EYES)
        cheeks = "".join(
            f'<ellipse cx="{x}" cy="{y + 62}" rx="30" ry="15" fill="#ff8fa3" opacity="0.45"/>'
            for x in (lx - 28, rx + 28)
            for y in (ly,)
        )
        return arcs + cheeks + brows(
            f"M {lx - 32} {ly - 72} Q {lx} {ly - 88} {lx + 30} {ly - 76}",
            f"M {rx - 30} {ry - 76} Q {rx} {ry - 88} {rx + 32} {ry - 72}",
        )
    if expression == "sad":
        return oval_eyes(15, 21, 6) + brows(
            f"M {lx - 32} {ly - 50} L {lx + 30} {ly - 74}",
            f"M {rx - 30} {ry - 74} L {rx + 32} {ry - 50}",
        )
    if expression == "angry":
        return oval_eyes(17, 17, 6) + brows(
            f"M {lx - 34} {ly - 76} L {lx + 32} {ly - 46}",
            f"M {rx - 32} {ry - 46} L {rx + 34} {ry - 76}",
            17,
        )
    if expression == "shocked":
        eyes = "".join(
            f'<circle cx="{x}" cy="{y}" r="34" fill="{SKIN}" stroke="{INK}" stroke-width="10"/>'
            f'<circle cx="{x}" cy="{y}" r="13" fill="{INK}"/>'
            for x, y in EYES
        )
        return eyes + brows(
            f"M {lx - 34} {ly - 82} Q {lx} {ly - 104} {lx + 32} {ly - 86}",
            f"M {rx - 32} {ry - 86} Q {rx} {ry - 104} {rx + 34} {ry - 82}",
        )
    if expression == "smug":
        lids = "".join(
            f'<ellipse cx="{x}" cy="{y}" rx="17" ry="25" fill="{INK}"/>'
            f'<rect x="{x - 24}" y="{y - 30}" width="48" height="27" fill="{SKIN}"/>'
            + stroke(f"M {x - 26} {y - 3} L {x + 26} {y - 3}", 11)
            for x, y in EYES
        )
        return lids + brows(
            f"M {lx - 32} {ly - 58} Q {lx} {ly - 62} {lx + 30} {ly - 56}",
            f"M {rx - 30} {ry - 78} Q {rx} {ry - 96} {rx + 32} {ry - 84}",
        )
    raise ValueError(expression)


def blink(lashes: bool) -> str:
    parts = []
    for x, y in EYES:
        parts.append(f'<ellipse cx="{x}" cy="{y}" rx="40" ry="40" fill="{SKIN}"/>')
        parts.append(stroke(f"M {x - 26} {y + 2} Q {x} {y + 14} {x + 26} {y + 2}", 11))
    if lashes:
        parts += [lash(x, y + 6, closed=True) for x, y in EYES]
    return "".join(parts)


def lash(x: float, y: float, closed: bool = False) -> str:
    """Two little lashes at the outer corner of an eye."""
    side = -1 if x < HEAD[0] else 1
    ox = x + side * 20
    oy = y - (0 if closed else 14)
    return stroke(
        f"M {ox} {oy} l {side * 18} -12 M {ox - side * 6} {oy - 8} l {side * 12} -16", 7
    )


# ---------------------------------------------------------------- mouths (Rhubarb shapes)


def mouth(shape: str) -> str:
    x, y = MOUTH
    if shape == "A":  # M, B, P: lips pressed
        return stroke(f"M {x - 52} {y} Q {x} {y + 8} {x + 52} {y}", 13)
    if shape == "X":  # idle / rest: relaxed, a hint of a smile
        return stroke(f"M {x - 46} {y - 2} Q {x} {y + 16} {x + 46} {y - 2}", 12)
    if shape == "B":  # most consonants: slightly open, teeth together
        return (
            fill(f"M {x - 56} {y - 14} Q {x} {y - 22} {x + 56} {y - 14} Q {x + 60} {y + 14} {x} {y + 22} Q {x - 60} {y + 14} {x - 56} {y - 14} Z", MOUTH_INSIDE)
            + fill(f"M {x - 50} {y - 12} Q {x} {y - 19} {x + 50} {y - 12} L {x + 52} {y + 2} Q {x} {y + 8} {x - 52} {y + 2} Z", TEETH)
            + stroke(f"M {x - 56} {y - 14} Q {x} {y - 22} {x + 56} {y - 14} Q {x + 60} {y + 14} {x} {y + 22} Q {x - 60} {y + 14} {x - 56} {y - 14} Z", 11)
        )
    if shape == "C":  # EH, AE: open
        return _open(56, 36, teeth=True)
    if shape == "D":  # AA: wide open
        return _open(66, 60, teeth=True, tongue=True)
    if shape == "E":  # AO, ER: rounded
        return _open(40, 46, tongue=True)
    if shape == "F":  # UW, OW, W: puckered
        return _open(24, 28) + stroke(f"M {x - 8} {y - 34} q 8 -6 16 0 M {x - 8} {y + 34} q 8 6 16 0", 7)
    if shape == "G":  # F, V: top teeth on the lower lip
        return (
            fill(f"M {x - 54} {y - 10} Q {x} {y - 24} {x + 54} {y - 10} Q {x} {y + 14} {x - 54} {y - 10} Z", MOUTH_INSIDE)
            + fill(f"M {x - 44} {y - 12} Q {x} {y - 22} {x + 44} {y - 12} L {x + 40} {y + 2} Q {x} {y + 8} {x - 40} {y + 2} Z", TEETH)
            + stroke(f"M {x - 54} {y - 10} Q {x} {y - 24} {x + 54} {y - 10} Q {x} {y + 14} {x - 54} {y - 10} Z", 11)
            + stroke(f"M {x - 48} {y + 8} Q {x} {y + 22} {x + 48} {y + 8}", 11)
        )
    if shape == "H":  # L: open, tongue raised behind the teeth
        rx, ry = 52, 44
        return (
            f'<ellipse cx="{x}" cy="{y + 8}" rx="{rx}" ry="{ry}" fill="{MOUTH_INSIDE}"/>'
            + fill(f"M {x - 30} {y + 30} Q {x} {y - 40} {x + 30} {y + 30} Z", TONGUE)
            + f'<ellipse cx="{x}" cy="{y + 8}" rx="{rx}" ry="{ry}" fill="none" stroke="{INK}" stroke-width="11"/>'
        )
    raise ValueError(shape)


def _open(rx: float, ry: float, teeth: bool = False, tongue: bool = False) -> str:
    x, y = MOUTH
    cy = y + ry * 0.35
    parts = [f'<ellipse cx="{x}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{MOUTH_INSIDE}"/>']
    clip = f'<clipPath id="m"><ellipse cx="{x}" cy="{cy}" rx="{rx}" ry="{ry}"/></clipPath>'
    inner = []
    if teeth:
        inner.append(f'<rect x="{x - rx}" y="{cy - ry}" width="{2 * rx}" height="{ry * 0.42}" fill="{TEETH}"/>')
    if tongue:
        inner.append(f'<ellipse cx="{x}" cy="{cy + ry * 0.85}" rx="{rx * 0.7}" ry="{ry * 0.5}" fill="{TONGUE}"/>')
    if inner:
        parts.append(f'<defs>{clip}</defs><g clip-path="url(#m)">{"".join(inner)}</g>')
    parts.append(
        f'<ellipse cx="{x}" cy="{cy}" rx="{rx}" ry="{ry}" fill="none" stroke="{INK}" stroke-width="11"/>'
    )
    return "".join(parts)


MOUTHS = ("A", "B", "C", "D", "E", "F", "G", "H", "X")


# ---------------------------------------------------------------- the two characters


def guy_hair() -> tuple[str, str]:
    """Skin fade: a short textured crop on top, fading to skin over the ears, with a
    crisp line-up. A light rim keeps the dark hair visible on a black screen."""
    cx, cy, r = HEAD
    hair, rim = "#1b1b1b", "#7a7a7a"
    defs = (
        HEAD_CLIP
        + '<linearGradient id="fade" gradientUnits="userSpaceOnUse" x1="0" y1="330" x2="0" y2="540">'
        f'<stop offset="0" stop-color="{hair}" stop-opacity="1"/>'
        f'<stop offset="0.3" stop-color="{hair}" stop-opacity="0.85"/>'
        f'<stop offset="1" stop-color="{hair}" stop-opacity="0"/></linearGradient>'
    )
    # The faded sides: everything above the hairline inside the head, fading downwards.
    sides = fill(
        f"M {cx - r} {cy - r} H {cx + r} V 580 H 706 "
        f"C 696 420 662 340 612 318 Q {cx} 298 388 318 C 338 340 304 420 294 580 H {cx - r} Z",
        "url(#fade)",
        ' clip-path="url(#head)"',
    )
    # The crop on top: a little fuller than the skull, with a soft textured edge.
    crown = (
        f"M 292 338 C 280 250 330 186 {cx} 178 C 670 186 720 250 708 338 "
        f"C 690 326 650 318 612 318 Q {cx} 298 388 318 C 350 318 310 326 292 338 Z"
    )
    top = fill(crown, hair) + stroke(
        f"M 292 338 C 280 250 330 186 {cx} 178 C 670 186 720 250 708 338", 7, rim
    )
    texture = stroke(
        "M 380 230 q 22 -14 44 -4 M 470 210 q 24 -12 48 -2 M 560 226 q 22 -12 44 -2 "
        "M 420 270 q 22 -12 44 -2 M 520 262 q 22 -12 44 -2",
        6,
        "#3c3c3c",
    )
    line_up = stroke("M 388 318 Q 500 298 612 318", 4, "#000000")
    return defs, sides + top + texture + line_up


def guy_beard() -> str:
    """Short boxed beard along the jaw and chin, with a moustache; the mouth area stays
    clear so every mouth shape reads. A light rim along the jaw shows it on black."""
    cx, cy, r = HEAD
    beard_colour = "#242424"
    beard = fill(
        f"M {cx - r + 10} 470 C 292 600 380 668 {cx} 670 C 620 668 708 600 {cx + r - 10} 470 "
        f"L 690 470 C 680 540 640 586 590 600 "
        f"C 570 578 540 566 {cx} 566 C 460 566 430 578 410 600 "
        f"C 360 586 320 540 310 470 Z",
        beard_colour,
        ' clip-path="url(#head)"',
    )
    jaw_rim = stroke(
        f"M {cx - r + 4} 478 C 296 610 384 662 {cx} 662 C 616 662 704 610 {cx + r - 4} 478",
        6,
        "#7a7a7a",
    )
    stubble = "".join(
        f'<circle cx="{x}" cy="{y}" r="3" fill="#4a4a4a"/>'
        for x, y in (
            (350, 560), (380, 600), (420, 630), (470, 645), (530, 645), (580, 630),
            (620, 600), (650, 560), (330, 520), (670, 520), (450, 610), (550, 610),
        )
    )  # fmt: skip
    moustache = fill(
        f"M 430 516 C 452 492 484 490 {cx} 500 C 516 490 548 492 570 516 "
        f"C 548 508 522 510 {cx} 518 C 478 510 452 508 430 516 Z",
        beard_colour,
    )
    return beard + stubble + jaw_rim + moustache


def girl_hair() -> tuple[str, str, str]:
    """(defs, behind-head hair, in-front hair): brown, shoulder length, side-swept bangs."""
    brown, shade = "#7b4a2a", "#5c341b"
    behind = fill(
        "M 262 420 C 250 170 750 170 738 420 C 744 560 770 690 790 790 "
        "C 735 822 672 818 632 792 C 640 700 640 640 630 600 L 370 600 "
        "C 360 640 360 700 368 792 C 328 818 265 822 210 790 C 230 690 256 560 262 420 Z",
        brown,
    ) + stroke("M 300 560 C 290 650 300 720 300 780 M 700 560 C 710 650 700 720 700 780", 7, shade)
    bangs = fill(
        "M 270 470 C 250 280 360 196 500 196 C 650 196 760 290 728 470 "
        "C 712 390 680 336 640 312 C 600 350 520 368 420 352 C 470 336 500 316 520 296 "
        "C 450 330 380 340 330 330 C 300 370 284 420 270 470 Z",
        brown,
        ' clip-path="url(#head)"',
    )
    locks = fill(
        "M 276 360 C 250 470 252 580 292 668 L 330 640 C 300 560 300 460 318 380 Z", brown
    ) + fill(
        "M 724 360 C 750 470 748 580 708 668 L 670 640 C 700 560 700 460 682 380 Z", brown
    )
    strands = stroke(
        "M 520 296 C 470 330 400 344 340 330 M 640 312 C 600 340 540 356 470 352", 6, shade
    )
    # Outline the hair on the face so it reads against white skin.
    rim = stroke(
        "M 270 470 C 284 420 300 370 330 330 C 380 340 450 330 520 296 C 500 316 470 336 "
        "420 352 C 520 368 600 350 640 312 C 680 336 712 390 728 470",
        6,
        shade,
    )
    return HEAD_CLIP, behind, bangs + locks + strands + rim


def build(name: str) -> dict[str, str]:
    files: dict[str, str] = {}
    if name == "guy":
        defs, hair = guy_hair()
        under, over = "", hair + guy_beard()
        lashes = False
    else:
        defs, under, over = girl_hair()
        lashes = True
    for expression in EXPRESSIONS:
        eye_lashes = "".join(lash(x, y) for x, y in EYES) if lashes and expression != "happy" else ""
        files[f"base/{expression}.svg"] = svg(
            under, body(), head(), over, face(expression), eye_lashes, defs=defs
        )
    for shape in MOUTHS:
        files[f"mouth/{shape}.svg"] = svg(mouth(shape))
    files["blink.svg"] = svg(blink(lashes))
    files["preview.svg"] = svg(
        under, body(), head(), over, face("neutral"),
        "".join(lash(x, y) for x, y in EYES) if lashes else "", mouth("X"), defs=defs,
    )  # fmt: skip
    return files


CHARACTERS = {
    "guy": {"label": "Guy", "voice": "am_michael"},
    "girl": {"label": "Girl", "voice": "af_heart"},
}


def main() -> None:
    root = Path(__file__).resolve().parent.parent / "assets" / "characters"
    for name, meta in CHARACTERS.items():
        for relative, content in build(name).items():
            path = root / name / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        manifest = {"name": meta["label"], "size": [W, H], "voice": meta["voice"]}
        (root / name / "character.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        print(f"wrote {root / name}")


if __name__ == "__main__":
    main()
