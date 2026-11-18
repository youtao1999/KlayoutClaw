"""Electrodes: checks on each lead L (one path on 2/0). Exit 1 if any fails.

P = T ∪ BG: top gate 5/0-5/3 and bottom graphite 13/0. I = top-gate contacts 5/2.
X = exposed bottom graphite BG − (TG ∪ TBN ∪ G ∪ BBN), the back-gate terminal.
1. head: arm lead L ∩ P ⊆ A ∩ C (the active region inside a contact, top graphite etched away);
   top-gate lead L ∩ P ⊆ its own top-gate contact; back-gate lead L ∩ P ⊆ its piece of X.
   L ∩ P ≠ ∅.
2. L touches exactly one terminal (an arm, a top-gate contact or a piece of X). (Pads: checked by
   nanodevice_pads.)
3. leads are --spacing apart from each other (none touch).
4. --min-width (0.3) <= lead width < its terminal's width (arm width, top-gate contact size, or
   for a piece of X 2 x its erosion depth, tg_lib.erode).
5. back gate: L ∩ BG = ∅ for every lead but the back-gate leads, whose L ∩ BG ⊆ X; exactly
   --bg-leads (2) back-gate leads.
Sets are closed: A ∩ C, the island and the piece of X are grown by 1 dbu.

Usage: python check.py --flakes prepared.gds --params params.json --writes writes.gds [--spacing 0.5] [--min-width 0.3]
"""
import argparse
import os
import sys

import klayout.db as db

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "nanodevice_topgate", "scripts"))
from tg_lib import Design, erode, graphene, layer, load_params, read_layer  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--flakes", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--writes", required=True)
ap.add_argument("--spacing", type=float, default=0.5)
ap.add_argument("--bg-leads", type=int, default=2)
ap.add_argument("--min-width", type=float, default=0.3)
ap.add_argument("--layer", default="2/0")
a = ap.parse_args()

D = Design(a.flakes, load_params(a.params))
R = lambda s: read_layer(a.writes, s)[0]
ch, arms, C, A, I = R("5/0"), R("5/1"), R("4/0"), R("11/4"), R("5/2")
BG = D.R("graphite")
lm = load_params(a.params)["layers"]
F = lambda k: read_layer(a.flakes, "%d/%d" % tuple(lm[k]))[0]
X = (BG - F("top_graphite") - F("top_hbn") - graphene(a.flakes, load_params(a.params))[0] - F("bottom_hbn")).merged()
P = (ch + arms + I + R("5/3") + BG).merged()
ly = db.Layout()
ly.read(a.writes)
dbu = ly.dbu
paths = [s for s in ly.top_cell().shapes(ly.layer(*layer(a.layer))).each() if s.is_path()]
if not paths:
    sys.exit("no lead paths on %s" % a.layer)
leads = [db.Region(s.polygon) for s in paths]
AC = (A & C).sized(1)
side = lambda p: min(D.local_bbox(p)[2] - D.local_bbox(p)[0], D.local_bbox(p)[3] - D.local_bbox(p)[1])
terms = [(db.Region(p), D.local_bbox(p)[3] - D.local_bbox(p)[1], AC) for p in (arms - ch).each()]   # arms run along x'
terms += [(db.Region(p), side(p), db.Region(p).sized(1)) for p in I.each()]           # (terminal, width, allowed head)
nX = len(terms)
width = lambda p: 2 * erode(db.Region((D.Ti * p.to_dtype(dbu)).to_itype(dbu)), dbu)[1]   # local frame, as electrodes.py
terms += [(db.Region(p), width(p), db.Region(p).sized(1)) for p in X.each()]
fails = []
nbg = 0
for k, L in enumerate(leads):
    head = L & P
    mine = [(w, ok) for r, w, ok in terms if not (L & r).is_empty()]
    is_bg = any(not (L & r).is_empty() for r, _, _ in terms[nX:])
    nbg += is_bg
    bad = head - mine[0][1] if mine else head
    if head.is_empty() or not bad.is_empty():
        fails.append("1 lead %d: on the stack %.3f um2, outside its allowed head %.3f um2" % (k, head.area() * dbu ** 2, bad.area() * dbu ** 2))
    if len(mine) != 1:
        fails.append("2 lead %d: touches %d terminals" % (k, len(mine)))
    for m in range(k):
        if not (L.sized(D.um(a.spacing)) & leads[m]).is_empty():
            fails.append("3 leads %d and %d closer than %.2f um" % (m, k, a.spacing))
    if mine and paths[k].path_dwidth >= mine[0][0] - 1e-9:
        fails.append("4 lead %d: width %.2f not below its terminal width %.2f" % (k, paths[k].path_dwidth, mine[0][0]))
    if paths[k].path_dwidth < a.min_width - 1e-9:
        fails.append("4 lead %d: width %.2f below the minimum %.2f" % (k, paths[k].path_dwidth, a.min_width))
    if not is_bg and not (L & BG).is_empty():
        fails.append("5 lead %d: touches the bottom graphite, %.3f um2" % (k, (L & BG).area() * dbu ** 2))
    if is_bg and not ((L & BG) - X.sized(1)).is_empty():
        fails.append("5 lead %d: back-gate lead on bottom graphite outside X" % k)
if nbg != a.bg_leads:
    fails.append("5 %d back-gate leads" % nbg)
for n, name in [(1, "head in A ∩ C (arm), on its top-gate contact, or on exposed bottom graphite (back gate)"), (2, "one terminal"),
                (3, "leads %.2f um apart" % a.spacing), (4, "width at least %.2f and below terminal width" % a.min_width), (5, "only the back-gate leads touch the bottom graphite, inside X")]:
    f = [x for x in fails if x.startswith("%d " % n)]
    print("%s %d. %s" % ("FAIL" if f else "PASS", n, name))
    for x in f:
        print("     " + x[2:])
print("%d leads" % len(leads))
sys.exit(1 if fails else 0)
