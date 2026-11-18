"""Big pads: checks on 2/1 (pads = axis-aligned boxes, tentacles = the other shapes). Exit 1 if any fails.

1. every pad is a box with both sides >= --min-width; every tentacle is a trapezoid (4 corners,
   two parallel sides).
2. every lead (2/0) has exactly one tentacle, which holds the lead's tail and touches exactly one
   pad; every pad has exactly one tentacle; pads and tentacles touch no other lead.
3. pads --gap apart; tentacles --gap from other tentacles and other pads.
4. pads and tentacles stay --clear away from the flakes' bounding box.

Usage: python check.py --flakes prepared.gds --params params.json --writes writes.gds
"""
import argparse
import os
import sys

import klayout.db as db

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "nanodevice_topgate", "scripts"))
from tg_lib import Design, layer, load_params, read_layer  # noqa: E402

FLAKES = ["top_top_hbn", "top_graphite", "top_hbn", "graphene", "bottom_hbn", "graphite"]

ap = argparse.ArgumentParser()
ap.add_argument("--flakes", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--writes", required=True)
ap.add_argument("--min-width", type=float, default=60.0)
ap.add_argument("--gap", type=float, default=20.0)
ap.add_argument("--clear", type=float, default=20.0)
ap.add_argument("--leads", default="2/0")
ap.add_argument("--layer", default="2/1")
a = ap.parse_args()

P = load_params(a.params)
D = Design(a.flakes, P)
flakes = db.Region()
for k in FLAKES:
    flakes += read_layer(a.flakes, "%d/%d" % tuple(P["layers"][k]))[0]
ly = db.Layout()
ly.read(a.writes)
dbu = ly.dbu
keep_out = db.Region(flakes.bbox()).sized(D.um(a.clear))
paths = [s.dpath for s in ly.top_cell().shapes(ly.layer(*layer(a.leads))).each() if s.is_path()]
leads = [db.Region(p.to_itype(dbu).polygon()) for p in paths]
tails = [list(p.each_point())[-1].to_itype(dbu) for p in paths]
shapes = [s.polygon for s in ly.top_cell().shapes(ly.layer(*layer(a.layer))).each()]
pads = [p for p in shapes if p.is_box()]
tents = [p for p in shapes if not p.is_box()]
R = db.Region
fails = []


def trapezoid(p):
    pts = list(p.each_point_hull())
    if len(pts) != 4:
        return False
    e = [pts[(i + 1) % 4] - pts[i] for i in range(4)]
    par = lambda u, v: u.x * v.y - u.y * v.x == 0
    return par(e[0], e[2]) or par(e[1], e[3])


for i, p in enumerate(pads):
    b = p.bbox()
    if min(b.width(), b.height()) * dbu < a.min_width - 1e-9:
        fails.append("1 pad %d: %.1f x %.1f um" % (i, b.width() * dbu, b.height() * dbu))
    nt = sum(not (R(p) & R(t)).is_empty() for t in tents)
    if nt != 1:
        fails.append("2 pad %d has %d tentacles" % (i, nt))
    for j in range(i):
        if not (R(p).sized(D.um(a.gap)) & R(pads[j])).is_empty():
            fails.append("3 pads %d and %d closer than %.0f um" % (j, i, a.gap))
for i, t in enumerate(tents):
    if not trapezoid(t):
        fails.append("1 tentacle %d is not a trapezoid (%d corners)" % (i, t.num_points_hull()))
    for j, u in enumerate(tents):
        if j != i and not (R(t).sized(D.um(a.gap)) & R(u)).is_empty():
            fails.append("3 tentacles %d and %d closer than %.0f um" % (i, j, a.gap))
for k, (L, tl) in enumerate(zip(leads, tails)):
    mine = [i for i, t in enumerate(tents) if t.inside(tl)]
    if len(mine) != 1:
        fails.append("2 lead %d: tail in %d tentacles" % (k, len(mine)))
        continue
    t = tents[mine[0]]
    own = [p for p in pads if not (R(p) & R(t)).is_empty()]
    if len(own) != 1:
        fails.append("2 lead %d: its tentacle touches %d pads" % (k, len(own)))
        continue
    mine_r = R(own[0]) + R(t)
    for j, M in enumerate(leads):
        if j != k and not (mine_r & M).is_empty():
            fails.append("2 lead %d: its pad or tentacle touches lead %d" % (k, j))
    for i, p in enumerate(pads):
        if p is not own[0] and not (R(t).sized(D.um(a.gap)) & R(p)).is_empty():
            fails.append("3 lead %d: its tentacle within %.0f um of pad %d" % (k, a.gap, i))
for s in shapes:
    if not (R(s) & keep_out).is_empty():
        fails.append("4 a pad or tentacle within %.0f um of the flakes" % a.clear)
        break
if not (len(pads) == len(tents) == len(leads)):
    fails.append("2 %d pads, %d tentacles, %d leads" % (len(pads), len(tents), len(leads)))
for n, name in [(1, "pads are boxes with sides >= %.0f um, tentacles are trapezoids" % a.min_width),
                (2, "one tentacle per lead holds its tail and joins one pad"),
                (3, "pads and tentacles %.0f um apart" % a.gap), (4, "pads and tentacles %.0f um clear of the flakes" % a.clear)]:
    f = [x for x in fails if x.startswith("%d " % n)]
    print("%s %d. %s" % ("FAIL" if f else "PASS", n, name))
    for x in f:
        print("     " + x[2:])
print("%d pads, %d tentacles, %d leads" % (len(pads), len(tents), len(leads)))
sys.exit(1 if fails else 0)
