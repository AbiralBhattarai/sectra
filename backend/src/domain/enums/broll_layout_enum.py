from enum import StrEnum


class BrollLayout(StrEnum):
    FULL = "full"  # covers the whole frame
    PIP = "pip"  # picture-in-picture box at (x, y), ``size`` wide
