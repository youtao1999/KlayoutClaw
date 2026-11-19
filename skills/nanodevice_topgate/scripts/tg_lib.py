"""Shared helpers for the top-gate scripts: the recipe's Design (local strip frame) and layer I/O."""
import argparse
import json
import os
import sys

import klayout.db as db

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "tests_resources", "recipes", "topgated_hallbar"))
from recipe_lib import Design, load_params  # noqa: E402,F401


NO_RECORD = "KLAYOUTCLAW_NO_RECORD"   # set for trial runs (place.py) so they leave no record


def parse(ap, step, check=False):
    """Parse the command line with defaults from params.json "args" -> step (e.g. "topgate/place"); the
    command line still wins. Keys are argument names (n, tail_slots, ...); "_"-keys are notes.
    Writers record their effective arguments under step in record.json next to params.json.
    check=True (a check script reading its writer's block): keys it does not take are skipped, no record."""
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--params")
    pre = pre.parse_known_args()[0]
    if not pre.params:
        ap.parse_args()                       # reports the missing --params
    with open(pre.params) as f:
        blk = json.load(f).get("args", {}).get(step, {})
    blk = {k.replace("-", "_"): v for k, v in blk.items() if not k.startswith("_")}
    dests = {x.dest: x for x in ap._actions}
    bad = sorted(set(blk) - set(dests))
    if bad and not check:
        sys.exit("params.json args.%s: unknown argument(s) %s" % (step, ", ".join(bad)))
    for k in blk:
        if k in dests:
            dests[k].required = False         # supplied by params.json
    ap.set_defaults(**{k: v for k, v in blk.items() if k in dests})
    a = ap.parse_args()
    if not check:
        record(a.params, step, args={k: v for k, v in vars(a).items() if k not in ("flakes", "params", "writes")})
    return a


def record(params_path, step, **fields):
    """Merge fields into record.json (next to params.json) under step: the device's run record."""
    if os.environ.get(NO_RECORD):
        return
    path = os.path.join(os.path.dirname(os.path.abspath(params_path)), "record.json")
    r = {}
    if os.path.exists(path):
        with open(path) as f:
            r = json.load(f)
    r.setdefault(step, {}).update(fields)
    with open(path + ".part", "w") as f:
        json.dump(r, f, indent=1)
    os.replace(path + ".part", path)


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


def bg_terminal(flakes, params, writes):
    """Back-gate terminal: the exposed bottom graphite X = BG − (TG ∪ TBN ∪ G ∪ BBN), kept under
    PMMA by the 7/0 mask. With params back_gate.edge_contact (user, 2026-11-18: for a bottom graphite
    with no bare part) it also holds (BG ∩ BBN) − (top gate grown by back_gate.gap): bottom graphite
    under the bottom hBN, cleared by the 7/0 etch and edge-contacted through the bottom hBN by the
    2/0 etch, which goes down to the substrate."""
    lm = params["layers"]
    F = lambda k: read_layer(flakes, "%d/%d" % tuple(lm[k]))[0]
    bg, bbn = F("graphite"), F("bottom_hbn")
    x = bg - F("top_graphite") - F("top_hbn") - graphene(flakes, params)[0] - bbn
    bgp = params.get("back_gate", {})
    if bgp.get("edge_contact"):
        t, dbu = read_layer(writes, "5/0")
        for s in ("5/1", "5/2", "5/3"):
            t += read_layer(writes, s)[0]
        x += (bg & bbn) - t.merged().sized(int(round(bgp.get("gap", 0.5) / dbu)))
    return x.merged()


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
    else:                                   # first write: new design file with one top cell
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
