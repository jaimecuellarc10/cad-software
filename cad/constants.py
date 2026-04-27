from enum import Enum, auto

GRID_UNIT = 10    # 1 drawing unit = 10 scene pixels
SNAP_PX   = 14   # snap activation radius in viewport pixels
GRIP_PX   = 8    # grip square size in viewport pixels


class SnapMode(Enum):
    NONE         = auto()
    GRID         = auto()
    ENDPOINT     = auto()
    MIDPOINT     = auto()
    CENTER       = auto()
    INTERSECTION = auto()
