"""Fingers: rewrite the top-gate etch mask 7/0 with the least exposed area.

P = T ∪ W ∪ X, what 7/0 must protect (top gate 5/0-5/3, etch checker 4/1, exposed bottom graphite
X = BG − (TG ∪ TBN ∪ G ∪ BBN)), as in nanodevice_contacts/mask.py.
- outline R' = bounding box of P grown by --margin (GDS frame): the big rectangle shrunk inward as
  far as it can while still holding all of P. R' − P is exposed, as before.
- fingers: outside R', the flakes' outline R (their bounding box grown by --frame) minus R' is cut
  by the lanes (each electrode on 2/0 grown by --clear) into one gap per pair of neighbouring
  electrodes. A gap with flake material in it gets a finger: the gap clipped to the bounding box
  of its flake material grown by --margin. It etches away every bit of flake between those two
  electrodes, so no debris can short them; a gap without flakes needs no finger.
- conductors: top graphite and graphene outside R', grown by --margin, are exposed too, also under
  the electrodes (user, 2026-11-17: etch the debris away rather than leave it in the lanes), so no
  conductive debris is left for an electrode to touch.
M = ((R' − P) ∪ fingers ∪ conductors) − P. Large exposed areas near fine features blur them (proximity dose), so the
exposed area is kept small.

Usage: python fingers.py --flakes prepared.gds --params params.json --writes result.gds
                         [--margin 2] [--frame 2] [--clear 0.25] [--leads 2/0] [--checker 4/1] [--layer 7/0]
Run after nanodevice_pads (the electrodes 2/0 must exist).
"""
import argparse
import os
import sys

import klayout.db as db

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "nanodevice_topgate", "scripts"))
from tg_lib import Design, graphene, layer, load_params, parse, read_layer, record, write_layer  # noqa: E402

FLAKES = ["top_top_hbn", "top_graphite", "top_hbn", "graphene", "bottom_hbn", "graphite"]

ap = argparse.ArgumentParser()
ap.add_argument("--flakes", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--writes", required=True)
ap.add_argument("--margin", type=float, default=2.0, help="um: R' around P, and fingers past their flake material")
ap.add_argument("--frame", type=float, default=2.0, help="um around the flakes' bounding box (R, as mask.py --margin)")
ap.add_argument("--clear", type=float, default=0.25, help="um kept between a finger and an electrode; below half the closest spacing between electrodes, or their lanes merge and keep debris that touches both")
ap.add_argument("--leads", default="2/0")
ap.add_argument("--checker", default="4/1")
ap.add_argument("--layer", default="7/0")
a = parse(ap, "fingers/fingers")

Pm = load_params(a.params)
D = Design(a.flakes, Pm)
fl = {k: read_layer(a.flakes, "%d/%d" % tuple(Pm["layers"][k])) for k in FLAKES}
dbu = fl["graphite"][1]
flakes = db.Region()
for r, _ in fl.values():
    flakes += r
flakes.merge()
T = db.Region()
for s in ["5/0", "5/1", "5/2", "5/3"]:
    T += read_layer(a.writes, s)[0]
if T.is_empty():
    sys.exit("no top gate on 5/0-5/3")
G = graphene(a.flakes, Pm)[0]
X = fl["graphite"][0] - fl["top_graphite"][0] - fl["top_hbn"][0] - G - fl["bottom_hbn"][0]
P = (T + read_layer(a.writes, a.checker)[0] + X).merged()

ly = db.Layout()
ly.read(a.writes)
leads = db.Region()
for s in ly.top_cell().shapes(ly.layer(*layer(a.leads))).each():
    leads.insert(s.polygon)
if leads.is_empty():
    sys.exit("no electrodes on %s: run nanodevice_electrodes first" % a.leads)

R = db.Region(flakes.bbox().enlarged(D.um(a.frame)))
Ri = db.Region(P.bbox().enlarged(D.um(a.margin)))
gaps = (R - Ri - leads.sized(D.um(a.clear))).merged()
fingers = db.Region()
for g in gaps.each():
    stuff = db.Region(g) & flakes
    if stuff.is_empty():
        continue                                 # no flake between these electrodes: nothing to etch
    fingers += db.Region(g) & db.Region(stuff.bbox().enlarged(D.um(a.margin)))
fingers.merge()
cond = ((fl["top_graphite"][0] + G) & (R - Ri)).sized(D.um(a.margin)) & R
M = ((Ri - P) + fingers + cond).merged() - P
assert (M & P).is_empty()
old = read_layer(a.writes, a.layer)[0]
write_layer(a.writes, a.layer, M, dbu)
um2 = lambda r: r.area() * dbu ** 2
b = Ri.bbox().to_dtype(dbu)
print("R' %s (%.1f x %.1f um), R' - P %.1f um2; %d gaps between electrodes, %d fingers %.1f um2 (corners %s)"
      % (b, b.width(), b.height(), um2(Ri - P), gaps.count(), fingers.count(), um2(fingers),
         sorted(p.num_points() for p in fingers.each())))
print("conductors outside R' (top graphite, graphene, grown by %.1f um): %.1f um2" % (a.margin, um2(cond)))
record(a.params, "fingers/fingers", exposed_um2=[round(um2(old), 2), round(um2(M), 2)])
print("7/0 exposed area %.1f -> %.1f um2 -> %s" % (um2(old), um2(M), a.layer))
