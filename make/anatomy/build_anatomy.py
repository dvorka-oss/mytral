# MyTraL: my training log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
"""Generate ``mytral/anatomy.py`` from vendored react-native-body-highlighter data.

The muscle path geometry is adapted from react-native-body-highlighter
(https://github.com/HichamELBSI/react-native-body-highlighter), MIT licensed,
Copyright (c) 2022 ELABBASSI Hicham. See ``licenses/react-native-body-highlighter.txt``.

Usage
-----
    python3 make/anatomy/build_anatomy.py

This re-generates ``mytral/anatomy.py``. It is a build-time tool and is NOT
imported at runtime.
"""

from __future__ import annotations

import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
UPSTREAM = HERE / "upstream"
OUT = HERE.parent.parent / "mytral" / "anatomy.py"

# the 60 canonical data-part-id strings the injury system depends on
# (= settings._ALL_BODY_PART_IDS plus the 3 picker-only ids)
EXPECTED_PART_IDS = {
    # front singletons
    "front-head", "front-neck", "front-chest", "front-abs",
    # front obliques (picker-only on the legacy macro, kept here)
    "front-obliques-l", "front-obliques-r",
    # back singletons
    "back-head", "back-neck", "back-upper", "back-lower",
    # back lats
    "back-lats-l", "back-lats-r",
}
for _face in ("front", "back"):
    for _base in (
        "shoulder", "arm", "elbow", "forearm", "wrist", "hand",
        "hip", "thigh", "knee", "calf", "ankle", "foot",
    ):
        EXPECTED_PART_IDS.add(f"{_face}-{_base}-l")
        EXPECTED_PART_IDS.add(f"{_face}-{_base}-r")

# upstream slug -> (muscle_key | None, part_base, sided)
#   sided=True  -> emit "<face>-<base>-l" / "-r" from the left/right arrays
#   sided=False -> merge both arrays into one "<face>-<base>" region
FRONT_MAP = {
    "head": (None, "head", False),
    "hair": (None, "head", False),
    "neck": ("neck", "neck", False),
    "trapezius": ("traps", "neck", False),
    "deltoids": ("shoulders", "shoulder", True),
    "chest": ("pecs", "chest", False),
    "abs": ("abs", "abs", False),
    "obliques": ("obliques", "obliques", True),
    "biceps": ("biceps", "arm", True),
    "triceps": ("triceps", "arm", True),
    "forearm": ("forearms", "forearm", True),
    "hands": (None, "hand", True),
    "adductors": ("hip_flexors", "hip", True),
    "quadriceps": ("quads", "thigh", True),
    "tibialis": ("calves", "calf", True),
    "calves": ("calves", "calf", True),
    "knees": (None, "knee", True),
    "ankles": (None, "ankle", True),
    "feet": (None, "foot", True),
}
BACK_MAP = {
    "head": (None, "head", False),
    "hair": (None, "head", False),
    "neck": ("neck", "neck", False),
    "trapezius": ("traps", "upper", False),
    "upper-back": ("lats", "lats", True),
    "lower-back": ("lower_back", "lower", False),
    "deltoids": ("shoulders", "shoulder", True),
    "triceps": ("triceps", "arm", True),
    "forearm": ("forearms", "forearm", True),
    "hands": (None, "hand", True),
    "gluteal": ("glutes", "hip", True),
    "hamstring": ("hamstrings", "thigh", True),
    "adductors": ("hip_flexors", "thigh", True),
    "calves": ("calves", "calf", True),
    "ankles": (None, "ankle", True),
    "feet": (None, "foot", True),
}

# human labels for tooltips (by part base)
BASE_LABEL = {
    "head": "Head", "neck": "Neck", "shoulder": "Shoulder", "chest": "Chest",
    "abs": "Abs", "obliques": "Oblique", "arm": "Upper arm", "elbow": "Elbow",
    "forearm": "Forearm", "wrist": "Wrist", "hand": "Hand", "upper": "Upper back",
    "lats": "Lat", "lower": "Lower back", "hip": "Hip", "thigh": "Thigh",
    "knee": "Knee", "calf": "Calf", "ankle": "Ankle", "foot": "Foot",
}
SIDE_LABEL = {"l": "left", "r": "right"}

# synthesized joints absent upstream: (face, joint, region_a, region_b) - the
# marker is placed midway between region_a and region_b on each side
SYNTH_JOINTS = [
    ("front", "elbow", "arm", "forearm"),
    ("front", "wrist", "forearm", "hand"),
    ("back", "elbow", "arm", "forearm"),
    ("back", "wrist", "forearm", "hand"),
    ("back", "knee", "thigh", "calf"),
]


def _parse(ts_path: pathlib.Path) -> dict[str, dict[str, list[str]]]:
    """Parse a bodyFront/bodyBack .ts file into {slug: {"left":[...], "right":[...]}}."""
    text = ts_path.read_text()
    blocks = re.split(r'slug:\s*"([^"]+)"', text)
    result: dict[str, dict[str, list[str]]] = {}
    for i in range(1, len(blocks), 2):
        slug = blocks[i]
        body = blocks[i + 1]
        sides: dict[str, list[str]] = {}
        for side in ("left", "right"):
            m = re.search(side + r"\s*:\s*\[(.*?)\]", body, re.DOTALL)
            if m:
                sides[side] = re.findall(r'"(M[^"]*)"', m.group(1))
        if not sides:  # no left/right keys: take any path strings
            sides["left"] = re.findall(r'"(M[^"]*)"', body)
        result[slug] = sides
    return result


_NUM = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
# parameter count per absolute command; arcs (A) handled specially for flags
_PARAMS = {"M": 2, "L": 2, "T": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "A": 7}


class _Scanner:
    """Cursor over an SVG path string with arc-flag-aware number reading."""

    def __init__(self, d: str):
        self.d = d
        self.i = 0

    def _skip(self) -> None:
        while self.i < len(self.d) and self.d[self.i] in " ,\t\r\n":
            self.i += 1

    def read_num(self) -> float:
        self._skip()
        m = _NUM.match(self.d, self.i)
        self.i = m.end()
        return float(m.group())

    def read_flag(self) -> float:
        # arc flags are a single '0' or '1', possibly glued to the next number
        self._skip()
        ch = self.d[self.i]
        self.i += 1
        return float(ch)

    def read_command(self) -> str | None:
        self._skip()
        if self.i >= len(self.d):
            return None
        ch = self.d[self.i]
        if ch.isalpha():
            self.i += 1
            return ch
        return ""  # implicit repeat of previous command


def _bbox(paths: list[str]) -> tuple[float, float, float, float]:
    """Absolute bounding box (minx, miny, maxx, maxy) of SVG path strings.

    Handles relative/absolute M L H V C S Q T A Z, including arc flags glued
    to the following number (e.g. ``a1 1 0 012.9 1.1``). Only command endpoints
    are tracked (control points / arc bulge ignored) - ample for joint placement.
    """
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    for d in paths:
        sc = _Scanner(d)
        cx = cy = sx = sy = 0.0
        cmd = ""
        while True:
            c = sc.read_command()
            if c is None:
                break
            if c:
                cmd = c
            if cmd in "Zz":
                cx, cy = sx, sy
                continue
            rel = cmd.islower()
            up = cmd.upper()
            if up == "A":
                sc.read_num(); sc.read_num(); sc.read_num()  # rx ry rotation
                sc.read_flag(); sc.read_flag()               # large-arc, sweep
                x, y = sc.read_num(), sc.read_num()
                cx, cy = (cx + x, cy + y) if rel else (x, y)
            elif up == "H":
                x = sc.read_num()
                cx = cx + x if rel else x
            elif up == "V":
                y = sc.read_num()
                cy = cy + y if rel else y
            else:
                vals = [sc.read_num() for _ in range(_PARAMS[up])]
                ex, ey = vals[-2], vals[-1]
                cx, cy = (cx + ex, cy + ey) if rel else (ex, ey)
                if up == "M":
                    sx, sy = cx, cy
                    cmd = "l" if rel else "L"  # implicit lineto after moveto
            minx, miny = min(minx, cx), min(miny, cy)
            maxx, maxy = max(maxx, cx), max(maxy, cy)
    return minx, miny, maxx, maxy


def _center(bb: tuple[float, float, float, float]) -> tuple[float, float]:
    return (bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0


def _ellipse_path(cx: float, cy: float, rx: float, ry: float) -> str:
    """An SVG path approximating an ellipse (two arcs) for a joint marker."""
    return (
        f"M{cx - rx:.1f} {cy:.1f}"
        f"a{rx:.1f} {ry:.1f} 0 1 0 {2 * rx:.1f} 0"
        f"a{rx:.1f} {ry:.1f} 0 1 0 {-2 * rx:.1f} 0Z"
    )


def _build_regions(data, mapping, face):
    """Return (regions, bboxes_by_base) for one face.

    regions: list of dicts {part_id, muscle_key, label, paths}
    bboxes_by_base: {(base, side): bbox} for synthesized-joint placement
    """
    regions = []
    bboxes: dict[tuple[str, str], tuple] = {}
    # anatomical sides: on the FRONT view the subject faces us, so the subject's
    # left limb is on the viewer's right - the upstream "left" array (drawn on
    # the viewer's left) is the subject's right ("-r"). On the BACK view the
    # subject faces away, so upstream "left" is the subject's left ("-l").
    if face == "front":
        side_suffix = (("left", "r"), ("right", "l"))
    else:
        side_suffix = (("left", "l"), ("right", "r"))
    for slug, sides in data.items():
        if slug not in mapping:
            continue
        muscle_key, base, sided = mapping[slug]
        if sided:
            for side_key, suffix in side_suffix:
                paths = sides.get(side_key, [])
                if not paths:
                    continue
                part_id = f"{face}-{base}-{suffix}"
                label = f"{BASE_LABEL.get(base, base.title())} ({SIDE_LABEL[suffix]})"
                regions.append(
                    {"part_id": part_id, "muscle_key": muscle_key,
                     "label": label, "paths": paths}
                )
                bboxes.setdefault((base, suffix), _bbox(paths))
        else:
            paths = sides.get("left", []) + sides.get("right", [])
            if not paths:
                continue
            part_id = f"{face}-{base}"
            regions.append(
                {"part_id": part_id, "muscle_key": muscle_key,
                 "label": BASE_LABEL.get(base, base.title()), "paths": paths}
            )
    return regions, bboxes


def _synthesize(face, bboxes):
    """Build joint-marker regions placed between two neighbouring regions."""
    out = []
    for f, joint, a, b in SYNTH_JOINTS:
        if f != face:
            continue
        for suffix in ("l", "r"):
            ba = bboxes.get((a, suffix))
            bb = bboxes.get((b, suffix))
            if not ba or not bb:
                continue
            # joint sits between the two regions
            ax, ay = _center(ba)
            bx, by = _center(bb)
            cx = (ax + bx) / 2.0
            cy = (ay + by) / 2.0
            rx = max(10.0, min(ba[2] - ba[0], bb[2] - bb[0]) * 0.32)
            out.append(
                {"part_id": f"{face}-{joint}-{suffix}", "muscle_key": None,
                 "label": f"{BASE_LABEL[joint]} ({SIDE_LABEL[suffix]})",
                 "paths": [_ellipse_path(cx, cy, rx, rx * 0.9)]}
            )
    return out


def _outline(face: str) -> str:
    text = (UPSTREAM / "wrapper.tsx").read_text()
    ds = re.findall(r'd="(M[^"]+)"', text)
    cands = []
    for d in ds:
        nums = _NUM.findall(d)
        if len(nums) < 200:
            continue
        first_x = float(nums[0])
        cands.append((first_x, d))
    front = [d for x, d in cands if x < 724]
    back = [d for x, d in cands if x >= 724]
    pick = front if face == "front" else back
    return max(pick, key=len) if pick else ""


def _emit_region(r) -> str:
    mk = f'"{r["muscle_key"]}"' if r["muscle_key"] else "None"
    paths = ", ".join(f'"{p}"' for p in r["paths"])
    return (
        f'    AnatomyRegion("{r["part_id"]}", {mk}, '
        f'"{r["label"]}", ({paths},)),\n'
    )


def main() -> None:
    front_data = _parse(UPSTREAM / "bodyFront.ts")
    back_data = _parse(UPSTREAM / "bodyBack.ts")

    front_regions, front_bb = _build_regions(front_data, FRONT_MAP, "front")
    back_regions, back_bb = _build_regions(back_data, BACK_MAP, "back")
    front_regions += _synthesize("front", front_bb)
    back_regions += _synthesize("back", back_bb)

    emitted = {r["part_id"] for r in front_regions + back_regions}
    missing = EXPECTED_PART_IDS - emitted
    extra = emitted - EXPECTED_PART_IDS
    assert not missing, f"missing part-ids: {sorted(missing)}"
    assert not extra, f"unexpected part-ids: {sorted(extra)}"

    header = '''# MyTraL: my training log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
"""Anatomical mannequin geometry (front + back) for the body diagram.

GENERATED by ``make/anatomy/build_anatomy.py`` - do not edit by hand.

The muscle path geometry is adapted from react-native-body-highlighter
(https://github.com/HichamELBSI/react-native-body-highlighter), MIT licensed,
Copyright (c) 2022 ELABBASSI Hicham. See ``licenses/react-native-body-highlighter.txt``.

Each :class:`AnatomyRegion` carries the canonical ``data-part-id`` (one of the 60
body-part ids the injury/sickness system uses) and, for muscle regions, the
``data-muscle-key`` (one of the 16 keys in :mod:`mytral.muscle_groups`). The
mannequin macro renders these region by region, applying mode-specific CSS classes.
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class AnatomyRegion:
    """One paintable body region: its part id, muscle key, label and SVG paths."""

    part_id: str
    muscle_key: str | None
    label: str
    paths: tuple[str, ...]


FRONT_VIEWBOX = "0 0 724 1448"
BACK_VIEWBOX = "724 0 724 1448"
'''

    with OUT.open("w") as f:
        f.write(header)
        f.write(f'\nFRONT_OUTLINE = "{_outline("front")}"\n')
        f.write(f'\nBACK_OUTLINE = "{_outline("back")}"\n')
        f.write("\nFRONT_REGIONS: tuple[AnatomyRegion, ...] = (\n")
        for r in front_regions:
            f.write(_emit_region(r))
        f.write(")\n")
        f.write("\nBACK_REGIONS: tuple[AnatomyRegion, ...] = (\n")
        for r in back_regions:
            f.write(_emit_region(r))
        f.write(")\n")

    print(f"OK: {len(front_regions)} front + {len(back_regions)} back regions")
    print(f"OK: {len(emitted)} distinct part-ids (expected {len(EXPECTED_PART_IDS)})")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
