"""Top gate, part 3: the top-gate contacts. Each contact is a --size square (local strip frame)
that lies completely inside top hBN minus graphene (union of the graphene pieces), and on the top
graphite, since the top gate is etched from it, and outside the arm corridors (tg_lib.arm_keepout),
so each arm keeps room for its own electrode. One contact per allowed area, largest areas
first, up to --n; inside an area the square sits as close to the top gate (channel + arms) as
it can.

Usage: python contacts.py --flakes prepared.gds --params params.json --writes writes.gds
                          [--n 2] [--size 1.0] [--margin 0] [--clearance 0.3] [--escape 50]
                          [--channel 5/0] [--arms 5/1] [--layer 5/2]

--margin: keep the square this far inside the allowed area, um.
Reads the flakes and the top gate from writes.gds (run flakes.py, channel.py, arms.py first)
and replaces --layer.
"""
import argparse
import math
import sys

import klayout.db as db

from tg_lib import CLEARANCE, ESCAPE, Design, arm_keepout, load_params, read_layer, write_layer
from tg_lib import graphene as graphene_union

ap = argparse.ArgumentParser()
ap.add_argument("--flakes", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--writes", required=True)
ap.add_argument("--n", type=int, default=2)
ap.add_argument("--size", type=float, default=1.0, help="contact side, um")
ap.add_argument("--margin", type=float, default=0.0)
ap.add_argument("--clearance", type=float, default=CLEARANCE)
ap.add_argument("--escape", type=float, default=ESCAPE)
ap.add_argument("--channel", default="5/0")
ap.add_argument("--arms", default="5/1")
ap.add_argument("--layer", default="5/2")
a = ap.parse_args()

P = load_params(a.params)
D = Design(a.flakes, P)
lm = P["layers"]
spec = lambda ld: "%d/%d" % tuple(ld)
R = lambda s: read_layer(a.writes, s)[0]
graphene = graphene_union(a.writes, P)[0]
ch, arms = R(a.channel), R(a.arms)
if ch.is_empty() or arms.is_empty():
    sys.exit("run channel.py and arms.py first")
gate = (ch + arms).merged()
if gate.count() != 1:
    sys.exit("channel + arms is not one polygon")
allowed = (((R(spec(lm["top_hbn"])) - graphene) & R(spec(lm["top_graphite"])))
           - arm_keepout(D, ch, arms, a.clearance, a.escape)).merged()
allowed = allowed.sized(-D.um(a.margin) - 5)     # +5 dbu: edges shared with rotated sets round across
gx1, gy1, gx2, gy2 = D.local_bbox(next(gate.each()))

def gate_dist(x, y):
    """distance from (x, y) to the top gate's local bounding box"""
    return math.hypot(max(gx1 - x, 0, x - gx2), max(gy1 - y, 0, y - gy2))

zones = sorted(allowed.each(), key=lambda p: -p.area())
contacts, rows, step, h = db.Region(), [], 0.05, a.size / 2
for z in zones:
    if len(rows) == a.n:
        break
    zr = db.Region(z)
    if zr.area() * D.dbu ** 2 < a.size ** 2:
        continue
    zx1, zy1, zx2, zy2 = D.local_bbox(z)
    best = None
    for i in range(int((zx2 - zx1 - a.size) / step) + 1):
        x = zx1 + h + i * step
        for j in range(int((zy2 - zy1 - a.size) / step) + 1):
            y = zy1 + h + j * step
            d = gate_dist(x, y)
            if best and d >= best[0]:
                continue
            if (D.box(x - h, y - h, x + h, y + h) - zr).is_empty():
                best = (d, x, y)
    if best:
        d, x, y = best
        contacts += D.box(x - h, y - h, x + h, y + h)
        rows.append((x, y, d))
if len(rows) < a.n:
    sys.exit("only %d of %d contacts fit in top hBN - graphene on the top graphite, outside the arm corridors" % (len(rows), a.n))
assert (contacts - allowed).is_empty() and (contacts & graphene).is_empty()

write_layer(a.writes, a.layer, contacts, D.dbu)
for x, y, d in rows:
    print("contact centre x' %.3f y' %.3f  size %.2f um  %.3f um from the top gate bbox" % (x, y, a.size, d))
print("%d contacts on %s" % (len(rows), a.layer))
