"""Fingers: checks on the rewritten 7/0. Exit 1 if any fails.

P = T ∪ W ∪ X (as fingers.py), R' = bounding box of P grown by --margin, leads = 2/0.
1. M ∩ P = ∅ and R' − P ⊆ M: P stays protected, everything else inside R' is etched.
2. fingers keep --clear from every electrode: M − R' − conductors (top graphite and graphene outside
   R', grown by --margin, which are etched also under the electrodes) stays --clear away.
3. no debris shorts: every piece of conductive flake left after the etch, (TG ∪ G ∪ BG) − M − P,
   touches at most one electrode and does not touch P (slivers under 4 dbu wide, rounding
   along P's edge, are ignored).

Usage: python check.py --flakes prepared.gds --params params.json --writes writes.gds [--frame 2]
"""
import argparse
import os
import sys

import klayout.db as db

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "nanodevice_topgate", "scripts"))
from tg_lib import Design, graphene, layer, load_params, read_layer  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--flakes", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--writes", required=True)
ap.add_argument("--margin", type=float, default=2.0)
ap.add_argument("--frame", type=float, default=2.0, help="um around the flakes' bounding box (R, as fingers.py --frame)")
ap.add_argument("--clear", type=float, default=0.25)
ap.add_argument("--leads", default="2/0")
ap.add_argument("--checker", default="4/1")
ap.add_argument("--layer", default="7/0")
a = ap.parse_args()

Pm = load_params(a.params)
D = Design(a.flakes, Pm)
F = lambda k: read_layer(a.flakes, "%d/%d" % tuple(Pm["layers"][k]))[0]
M, dbu = read_layer(a.writes, a.layer)
G = graphene(a.flakes, Pm)[0]
T = db.Region()
for s in ["5/0", "5/1", "5/2", "5/3"]:
    T += read_layer(a.writes, s)[0]
X = F("graphite") - F("top_graphite") - F("top_hbn") - G - F("bottom_hbn")
P = (T + read_layer(a.writes, a.checker)[0] + X).merged()
Ri = db.Region(P.bbox().enlarged(D.um(a.margin)))
ly = db.Layout()
ly.read(a.writes)
leads = [db.Region(s.polygon) for s in ly.top_cell().shapes(ly.layer(*layer(a.leads))).each()]
fails = []
if not (M & P).is_empty():
    fails.append("1 M overlaps P by %.3f um2" % ((M & P).area() * dbu ** 2))
if ((Ri - P) - M).area() * dbu ** 2 > 1e-3:            # 1e-3 um2: rounding slivers
    fails.append("1 %.3f um2 of R' - P not exposed" % (((Ri - P) - M).area() * dbu ** 2))
R = db.Region(sum((F(k) for k in ["top_top_hbn", "top_graphite", "top_hbn", "graphene", "bottom_hbn", "graphite"]), db.Region()).bbox().enlarged(D.um(a.frame)))
cond = ((F("top_graphite") + G) & (R - Ri)).sized(D.um(a.margin)) & R
fing = M - Ri - cond
for k, L in enumerate(leads):
    if not (fing & L.sized(D.um(a.clear) - 1)).sized(-2).is_empty():   # ignore slivers < 4 dbu wide
        fails.append("2 a finger within %.2f um of electrode %d" % (a.clear, k))
debris = ((F("top_graphite") + G + F("graphite")) - M - P).merged()
for p in debris.each():
    if db.Region(p).sized(-2).is_empty():                # rounding slivers (< 4 dbu wide) along P's edge
        continue
    r = db.Region(p)
    n = sum(not (r & L).is_empty() for L in leads)
    if n > 1 or not (r.sized(1) & P).is_empty():
        x1, y1, x2, y2 = D.local_bbox(p)
        fails.append("3 debris %.2f um2 at x' %.1f..%.1f, y' %.1f..%.1f touches %d electrodes%s"
                     % (p.area() * dbu ** 2, x1, x2, y1, y2, n, " and P" if not (r.sized(1) & P).is_empty() else ""))
for n, name in [(1, "P protected, R' - P exposed"), (2, "fingers %.2f um from electrodes" % a.clear),
                (3, "no conductive debris touches two electrodes or the device")]:
    f = [x for x in fails if x.startswith("%d " % n)]
    print("%s %d. %s" % ("FAIL" if f else "PASS", n, name))
    for x in f:
        print("     " + x[2:])
print("exposed %.1f um2; %d debris pieces left (ignoring slivers < 4 dbu wide)" % (M.area() * dbu ** 2, sum(not db.Region(p).sized(-2).is_empty() for p in debris.each())))
sys.exit(1 if fails else 0)
