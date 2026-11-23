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


# ---------------------------------------------------------------- the British pair

NAVY, NAVY_DARK, NAVY_RIM = "#26324f", "#18203a", "#9aa7c7"


def thick(points: list[tuple[float, float]], colour: str, width: float, rim: str) -> str:
    """A limb drawn as cloth: a rim colour, then the cloth on top, so it shows on black."""
    return line(points, rim, width + 10) + line(points, colour, width)


def hands(*points: tuple[float, float]) -> str:
    return "".join(
        f'<circle cx="{x}" cy="{y}" r="22" fill="{SKIN}" stroke="{INK}" stroke-width="7"/>'
        for x, y in points
    )


def neck() -> str:
    return line([(500, 640), (500, 724)], INK, 54) + line([(500, 640), (500, 724)], SKIN, 40)


def gent_head() -> str:
    """A squared, defined jaw instead of the round head (same eye and mouth anchors)."""
    cx, cy, r = HEAD
    ears = "".join(
        f'<ellipse cx="{x}" cy="{cy + 10}" rx="30" ry="48" fill="{SKIN}" '
        f'stroke="{INK}" stroke-width="12"/>'
        for x in (cx - r + 8, cx + r - 8)
    )
    skull = (
        f"M {cx - r} {cy} A {r} {r} 0 0 1 {cx + r} {cy} "
        f"C {cx + r} 500 715 548 690 584 L 604 654 Q {cx} 678 396 654 L 310 584 "
        f"C 285 548 {cx - r} 500 {cx - r} {cy} Z"
    )
    contour = stroke(
        "M 646 600 L 604 640 M 354 600 L 396 640 M 492 646 q 8 7 16 0 "
        "M 338 500 q 14 34 44 48 M 662 500 q -14 34 -44 48",
        6,
        "#bdbdbd",
    )
    return ears + fill(skull, SKIN) + stroke(skull, 12) + contour


def gent_hair() -> str:
    """Blonde, short at the sides, parted on one side and swept over into a soft quiff."""
    blonde, shade, rim = "#e8c35a", "#b38b2e", "#7c5d17"
    mass = (
        "M 292 410 C 278 330 296 258 340 214 C 360 196 380 186 395 182 "
        "C 432 148 520 134 602 150 C 692 168 742 240 724 330 C 722 366 716 394 708 410 "
        "C 700 360 680 332 640 318 Q 520 296 420 312 C 370 320 330 352 310 410 Z"
    )
    sideburns = fill("M 290 404 L 298 474 L 316 474 L 314 404 Z", blonde) + fill(
        "M 710 404 L 702 474 L 684 474 L 686 404 Z", blonde
    )
    part = stroke("M 396 184 C 402 222 406 262 412 310", 6, shade)
    sweep = stroke(
        "M 420 200 C 500 168 600 172 682 222 M 430 240 C 512 214 612 220 692 272 "
        "M 442 282 C 522 262 600 268 662 302",
        5,
        shade,
    )
    return sideburns + fill(mass, blonde) + stroke(mass, 7, rim) + part + sweep


def suit() -> str:
    """Navy suit: jacket with lapels, white shirt, burgundy tie, pocket square."""
    legs = ([(500, 1060), (425, 1250), (397, 1404)], [(500, 1060), (575, 1250), (603, 1404)])
    trousers = "".join(thick(leg, NAVY, 46, NAVY_RIM) for leg in legs)
    shoes = "".join(
        f'<ellipse cx="{x}" cy="1424" rx="46" ry="19" fill="#0d0d0d" stroke="#8a8a8a" '
        'stroke-width="6"/>'
        for x in (372, 628)
    )
    jacket = (
        "M 404 712 L 596 712 C 616 800 604 950 618 1092 L 520 1104 L 500 1080 "
        "L 480 1104 L 382 1092 C 396 950 384 800 404 712 Z"
    )
    sleeves = thick([(414, 730), (382, 878), (362, 984)], NAVY, 46, NAVY_RIM) + thick(
        [(586, 730), (614, 872), (650, 966)], NAVY, 46, NAVY_RIM
    )
    cuffs = line([(350, 986), (376, 996)], "#ffffff", 12) + line(
        [(638, 970), (664, 958)], "#ffffff", 12
    )
    shirt = fill("M 450 712 L 550 712 L 500 862 Z", "#ffffff")
    collar = stroke("M 450 712 L 476 744 L 500 722 L 524 744 L 550 712", 6)
    tie = fill("M 487 726 L 513 726 L 508 752 L 492 752 Z", "#7a1f2b") + fill(
        "M 492 752 L 508 752 L 517 832 L 500 856 L 483 832 Z", "#8e2433"
    )
    lapels = fill("M 450 712 L 428 770 L 452 778 L 500 866 Z", NAVY_DARK) + fill(
        "M 550 712 L 572 770 L 548 778 L 500 866 Z", NAVY_DARK
    )
    lapel_lines = stroke(
        "M 450 712 L 428 770 L 452 778 L 500 866 L 548 778 L 572 770 L 550 712", 5, NAVY_RIM
    )
    buttons = "".join(
        f'<circle cx="500" cy="{y}" r="9" fill="#0f1426" stroke="{NAVY_RIM}" stroke-width="4"/>'
        for y in (912, 972)
    )
    pocket = stroke("M 536 812 L 584 812", 6, NAVY_RIM) + fill(
        "M 546 812 L 552 790 L 562 800 L 570 786 L 578 812 Z", "#ffffff"
    )
    return (
        trousers + shoes + neck() + fill(jacket, NAVY) + stroke(jacket, 7, NAVY_RIM) + sleeves
        + cuffs + shirt + lapels + lapel_lines + collar + tie + buttons + pocket
        + hands((362, 1006), (656, 988))
    )  # fmt: skip


ROSE, ROSE_DARK, ROSE_RIM, CREAM = "#a8325a", "#7d2342", "#f2b6c9", "#f6e6c8"


def gown() -> str:
    """A rose gown: fitted bodice with a scoop neck, puffed sleeves, ribbon sash, full
    skirt with folds and a cream hem, and a pearl necklace."""
    arms = [[(432, 744), (396, 880), (360, 1010)], [(568, 744), (604, 875), (655, 990)]]
    limbs = "".join(line(a, INK, BODY_OUTLINE) for a in arms) + "".join(
        line(a, SKIN, BODY_LINE) for a in arms
    )
    shoes = "".join(
        f'<ellipse cx="{x}" cy="1412" rx="30" ry="14" fill="#3a1420" stroke="{ROSE_RIM}" '
        'stroke-width="5"/>'
        for x in (452, 548)
    )
    skirt = (
        "M 438 892 L 562 892 C 610 1050 690 1250 722 1390 Q 500 1420 278 1390 "
        "C 310 1250 390 1050 438 892 Z"
    )
    folds = stroke(
        "M 470 916 C 450 1080 420 1250 398 1396 M 500 916 L 500 1404 "
        "M 530 916 C 550 1080 580 1250 602 1396 M 452 930 C 400 1100 350 1260 330 1392 "
        "M 548 930 C 600 1100 650 1260 670 1392",
        6,
        ROSE_DARK,
    )
    hem = stroke("M 282 1388 Q 500 1418 718 1388", 14, CREAM)
    bodice = "M 424 718 L 452 712 Q 500 784 548 712 L 576 718 L 562 892 L 438 892 Z"
    sleeves = "".join(
        f'<ellipse cx="{x}" cy="742" rx="44" ry="34" fill="{ROSE}" stroke="{ROSE_RIM}" '
        'stroke-width="6"/>'
        for x in (430, 570)
    )
    sash = fill("M 436 874 L 564 874 L 563 900 L 437 900 Z", CREAM) + fill(
        "M 548 886 L 586 868 L 584 906 Z M 548 886 L 572 930 L 556 934 Z", CREAM
    )
    pearls = "".join(
        f'<circle cx="{(1 - t) ** 2 * 458 + 2 * (1 - t) * t * 500 + t**2 * 542:.1f}" '
        f'cy="{(1 - t) ** 2 * 724 + 2 * (1 - t) * t * 772 + t**2 * 724:.1f}" r="6" '
        'fill="#ffffff" stroke="#b9b9b9" stroke-width="2"/>'
        for t in (i / 10 for i in range(11))
    )
    return (
        limbs + hands((360, 1010), (655, 990)) + shoes + fill(skirt, ROSE)
        + stroke(skirt, 7, ROSE_RIM) + folds + hem + neck() + fill(bodice, ROSE)
        + stroke(bodice, 7, ROSE_RIM) + sleeves + sash + pearls
    )  # fmt: skip


def lady_hair() -> tuple[str, str, str]:
    """(defs, behind-head hair, in-front hair): a brown updo with a bun, middle part
    swept back, and a curl in front of each ear."""
    brown, shade, rim = "#6b3e22", "#4a2814", "#a8714a"
    bun = (
        f'<circle cx="500" cy="196" r="84" fill="{brown}" stroke="{rim}" stroke-width="7"/>'
        + stroke("M 446 200 C 460 150 540 150 552 196 C 548 232 490 240 474 206", 6, shade)
    )
    top = (
        "M 275 430 C 270 262 380 200 500 200 C 620 200 730 262 725 430 "
        "C 715 370 690 330 650 306 C 600 290 540 296 500 318 "
        "C 460 296 400 290 350 306 C 310 330 285 370 275 430 Z"
    )
    swept = stroke(
        "M 500 318 C 460 268 400 250 330 290 M 500 318 C 540 268 600 250 670 290 "
        "M 500 318 C 480 260 440 228 380 232 M 500 318 C 520 260 560 228 620 232",
        5,
        shade,
    )
    curls = stroke(
        "M 292 420 C 266 470 304 500 280 548 C 270 568 284 584 296 578 "
        "M 708 420 C 734 470 696 500 720 548 C 730 568 716 584 704 578",
        10,
        brown,
    )
    front = f'<g clip-path="url(#head)">{fill(top, brown)}{swept}</g>' + stroke(top, 6, rim) + curls
    return HEAD_CLIP, bun, front


#: Skin colour per character (the rest are the default white).
SKINS = {"lady": "#fbeee6"}


def build(name: str) -> dict[str, str]:
    global SKIN  # every drawing helper reads it; set once per character
    SKIN = SKINS.get(name, "#ffffff")
    files: dict[str, str] = {}
    defs, under = "", ""
    figure = body() + head()
    lashes = False
    if name == "guy":
        defs, hair = guy_hair()
        over = hair + guy_beard()
    elif name == "girl":
        defs, under, over = girl_hair()
        lashes = True
    elif name == "gent":
        figure = suit() + gent_head()
        over = gent_hair()
    elif name == "lady":
        defs, under, over = lady_hair()
        figure = gown() + head()
        lashes = True
    else:
        raise ValueError(name)
    for expression in EXPRESSIONS:
        eye_lashes = "".join(lash(x, y) for x, y in EYES) if lashes and expression != "happy" else ""
        files[f"base/{expression}.svg"] = svg(
            under, figure, over, face(expression), eye_lashes, defs=defs
        )
    for shape in MOUTHS:
        files[f"mouth/{shape}.svg"] = svg(mouth(shape))
    files["blink.svg"] = svg(blink(lashes))
    files["preview.svg"] = svg(
        under, figure, over, face("neutral"),
        "".join(lash(x, y) for x, y in EYES) if lashes else "", mouth("X"), defs=defs,
    )  # fmt: skip
    return files


CHARACTERS = {
    "guy": {"label": "Guy", "voice": "am_michael"},
    "girl": {"label": "Girl", "voice": "af_heart"},
    "gent": {"label": "British gent", "voice": "bm_george"},
    "lady": {"label": "British lady", "voice": "bf_emma"},
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
