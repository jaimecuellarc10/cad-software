from enum import Enum, auto

GRID_UNIT = 10    # 1 drawing unit = 10 scene pixels
SNAP_PX   = 14   # snap activation radius in viewport pixels
GRIP_PX   = 8    # grip square size in viewport pixels


class DrawingUnit(Enum):
    MM   = ("mm",   1.0,    4)
    CM   = ("cm",   10.0,   5)
    M    = ("m",    1000.0, 6)
    INCH = ("in",   25.4,   1)
    FOOT = ("ft",   304.8,  2)

    def __init__(self, label: str, mm_per_unit: float, insunits: int):
        self.label = label
        self.mm_per_unit = mm_per_unit
        self.insunits = insunits

# DXF $INSUNITS code → DrawingUnit (for import)
INSUNITS_TO_UNIT: dict[int, "DrawingUnit"] = {u.insunits: u for u in DrawingUnit}


class SnapMode(Enum):
    NONE         = auto()
    GRID         = auto()
    ENDPOINT     = auto()
    MIDPOINT     = auto()
    CENTER       = auto()
    INTERSECTION = auto()
