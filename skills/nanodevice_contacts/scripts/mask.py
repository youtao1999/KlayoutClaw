"""Contacts: top-gate etch mask M = R − (T ∪ W ∪ X).

R = bounding box of the union of all flakes, grown by --margin; T = top gate (5/0-5/3, from
nanodevice_topgate); W = etch checker (4/1, from checker.py, exposed later in the contact etch);
X = BG − (TG ∪ TBN ∪ G ∪ BBN): the bottom graphite with nothing but top-top hBN above it (where
the back-gate lead lands). The 7/0 etch would cut it while removing the top-top hBN and top
graphite; everything below the top hBN (top hBN, graphene pieces, bottom hBN) is taken out of X.
M is the written (exposed) area; T, W and X stay under PMMA. The etch goes all the way down to
the bottom hBN, so it defines the shape of the top gate and of the graphene.

Usage: python mask.py --flakes prepared.gds --params params.json --writes writes.gds
                      [--margin 2] [--checker 4/1] [--layer 7/0]
Run checker.py first (an empty 4/1 is fine: no checker on this stack).
"""
import argparse
import os
import sys

import klayout.db as db

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "nanodevice_topgate", "scripts"))
from tg_lib import graphene, load_params, parse, read_layer, write_layer  # noqa: E402

FLAKES = ["top_top_hbn", "top_graphite", "top_hbn", "graphene", "bottom_hbn", "graphite"]
TOP_GATE = ["5/0", "5/1", "5/2", "5/3"]

ap = argparse.ArgumentParser()
ap.add_argument("--flakes", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--writes", required=True)
ap.add_argument("--margin", type=float, default=2.0, help="um added around the flake bounding box")
ap.add_argument("--checker", default="4/1")
ap.add_argument("--layer", default="7/0")
a = parse(ap, "contacts/mask")

P = load_params(a.params)
fl = {k: read_layer(a.flakes, "%d/%d" % tuple(P["layers"][k])) for k in FLAKES}
dbu = fl["graphite"][1]
flakes = db.Region()
for r, _ in fl.values():
    flakes += r
T = db.Region()
for s in TOP_GATE:
    T += read_layer(a.writes, s)[0]
T.merge()
if T.is_empty():
    sys.exit("no top gate on 5/0-5/3: run nanodevice_topgate first")
W = read_layer(a.writes, a.checker)[0]
G = graphene(a.flakes, P)[0]                    # union of the graphene pieces
X = (fl["graphite"][0] - fl["top_graphite"][0] - fl["top_hbn"][0] - G - fl["bottom_hbn"][0]).merged()
R = db.Region(flakes.bbox().enlarged(int(round(a.margin / dbu))))
keep = (T + W + X).merged()
M = R - keep
assert (flakes - R).is_empty() and (M & keep).is_empty() and ((M + keep) ^ R).is_empty()
write_layer(a.writes, a.layer, M, dbu)
um2 = lambda r: r.area() * dbu ** 2
print("R %s (%.1f x %.1f um); kept under PMMA: T %.3f, W %.3f, X = BG - (TG ∪ TBN ∪ G ∪ BBN) %.3f um2; M = R - (T ∪ W ∪ X) %.2f um2 -> %s"
      % (R.bbox().to_dtype(dbu), R.bbox().width() * dbu, R.bbox().height() * dbu, um2(T), um2(W), um2(X), um2(M), a.layer))
