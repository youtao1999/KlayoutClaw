"""Shared helpers for the top-gate scripts: the recipe's Design (local strip frame) and layer I/O."""
import os
import sys

import klayout.db as db

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "tests_resources", "recipes", "topgated_hallbar"))
from recipe_lib import Design, load_params  # noqa: E402,F401


def layer(spec):
    l, d = (int(v) for v in spec.split("/"))
    return l, d


def read_layer(path, spec):
    ly = db.Layout()
    ly.read(path)
    # insert() copies the shapes; Region(iterator) would keep a lazy reference to ly, which is
    # freed on return (an already-merged region, e.g. one box, then reads back empty)
    r = db.Region()
    r.insert(ly.top_cell().begin_shapes_rec(ly.layer(*layer(spec))))
    return r.merged(), ly.dbu


def graphene(path, params):
    """Graphene = union of all graphene pieces (glossary). Active region = their intersection."""
    pieces = [read_layer(path, "%d/%d" % tuple(p))[0] for p in params["layers"]["graphene_pieces"]]
    union, active = db.Region(), None
    for r in pieces:
        union += r
        active = r if active is None else (active & r)
    return union.merged(), active


def erode(region, dbu, step=0.05):
    """Erode region in step-um steps until it vanishes: (last non-empty region, depth in um).
    2 x depth is the region's real width, whatever the angle of its edges."""
    d, n = int(round(step / dbu)), 0
    while True:
        e = region.sized(-d)
        if e.is_empty():
            return region, n * step
        region, n = e, n + 1


CLEARANCE, ESCAPE = 0.3, 50.0      # um: distance kept from the arm corridors; corridor length


def arm_keepout(D, ch, arms, clearance=CLEARANCE, escape=ESCAPE):
    """Arm corridors: each arm outside the channel, extended outward along x' by escape (room for
    the arm's own electrode), grown by clearance, minus the channel. Top-gate contacts and
    electrodes stay out of this set."""
    cx1, _, cx2, _ = D.local_bbox(next(ch.each()))
    k = db.Region()
    for p in (arms - ch).each():
        x1, y1, x2, y2 = D.local_bbox(p)
        k += D.box(x1 - escape, y1, x2, y2) if x2 < (cx1 + cx2) / 2 else D.box(x1, y1, x2 + escape, y2)
    return k.merged().sized(D.um(clearance)) - ch


def body(writes, bg):
    """Top-gate body = top gate minus the arm tips (arms − BG): channel ∪ (arms ∩ BG) ∪ top-gate
    contacts ∪ top-gate electrodes. Built from the parts, not as T − tips, so no 1-dbu slivers."""
    arms = read_layer(writes, "5/1")[0]
    return (read_layer(writes, "5/0")[0] + (arms & bg) + read_layer(writes, "5/2")[0] + read_layer(writes, "5/3")[0]).merged()


def write_layer(path, spec, region, dbu):
    """Replace one layer of path with region; every other layer is kept. Written as .part, then renamed."""
    ly = db.Layout()
    if os.path.exists(path):
        ly.read(path)
    else:                                   # first write: new writes.gds with one top cell
        ly.dbu = dbu
        ly.create_cell("TOP")
    assert abs(ly.dbu - dbu) < 1e-12, "dbu differs between flakes and writes GDS"
    s = ly.top_cell().shapes(ly.layer(*layer(spec)))
    s.clear()
    s.insert(region)
    opt = db.SaveLayoutOptions()
    opt.format = "GDS2"
    ly.write(path + ".part", opt)
    os.replace(path + ".part", path)
