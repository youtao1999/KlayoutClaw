"""Contacts: checks. Exit 1 if any fails.

1. (T ∩ C) ∩ ∂C ⊆ A: where the contact boundary lies on the top gate, it lies in the active
   region. T = top gate 5/0-5/3, C = contacts, A = active region 11/4. Sets are closed: T and A
   are grown by 1 dbu so boundary-on-boundary counts as inside.
2. T − C is one piece: the contacts do not cut the top gate into disjoint pieces.
3. C stays away from the top-gate body (T minus the arm tips arms − BG): C ∩ body grown by
   --gap = ∅.
4. Room for every electrode head: per arm, T ∩ C ∩ A (graphene left, top graphite etched
   away) reaches at least --min-head along x'.

Usage: python check.py --flakes prepared.gds --params params.json --writes writes.gds [--contacts 4/0]
"""
import argparse
import os
import sys

import klayout.db as db

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "nanodevice_topgate", "scripts"))
from tg_lib import Design, body, load_params, read_layer  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--flakes", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--writes", required=True)
ap.add_argument("--contacts", default="4/0")
ap.add_argument("--min-head", type=float, default=0.4, help="um, shortest head room along x'")
ap.add_argument("--gap", type=float, default=0.15, help="um kept between C and the top-gate body")
a = ap.parse_args()

D = Design(a.flakes, load_params(a.params))
C, dbu = read_layer(a.writes, a.contacts)
A = read_layer(a.writes, "11/4")[0]
T = db.Region()
for s in ["5/0", "5/1", "5/2", "5/3"]:
    T += read_layer(a.writes, s)[0]
if C.is_empty() or A.is_empty() or T.is_empty():
    sys.exit("need contacts %s, active region 11/4 and top gate 5/0-5/3 in writes" % a.contacts)

on_T = C.edges().inside_part(T.merged().sized(1))
bad = on_T.outside_part(A.sized(1))
ok = bad.is_empty()
print("%s 1. (T ∩ C) ∩ ∂C ⊆ A: boundary on top gate %.2f um, outside active region %.2f um"
      % ("PASS" if ok else "FAIL", on_T.length() * dbu, bad.length() * dbu))
for e in bad.each():
    p1, p2 = (D.Ti * p for p in (e.p1.to_dtype(dbu), e.p2.to_dtype(dbu)))
    print("     x',y' (%.2f, %.2f) - (%.2f, %.2f)" % (p1.x, p1.y, p2.x, p2.y))

rest = (T - C).merged()
ok2 = rest.count() == 1
print("%s 2. T − C is one piece: %d pieces" % ("PASS" if ok2 else "FAIL", rest.count()))
if not ok2:
    for p in sorted(rest.each(), key=lambda p: -p.area()):
        print("     piece %.3f um2 at x',y' (%.2f, %.2f, %.2f, %.2f)" % ((p.area() * dbu ** 2,) + tuple(D.local_bbox(p))))

hit = C & body(a.writes, D.R("graphite")).sized(D.um(a.gap))
ok3 = hit.is_empty()
print("%s 3. C stays %.2f um away from the top-gate body: overlap %.4f um2" % ("PASS" if ok3 else "FAIL", a.gap, hit.area() * dbu ** 2))
for p in hit.each():
    print("     at x',y' (%.2f, %.2f, %.2f, %.2f)" % tuple(D.local_bbox(p)))

room = (T.merged() & C & A).merged()
arms, ch = read_layer(a.writes, "5/1")[0], read_layer(a.writes, "5/0")[0]
lens = []
cx1, _, cx2, _ = D.local_bbox(next(ch.each()))
for p in (arms - ch).each():
    x1, y1, x2, y2 = D.local_bbox(p)
    west = x2 < (cx1 + cx2) / 2
    band = room & (D.box(-1e3, y1, cx1, y2) if west else D.box(cx2, y1, 1e3, y2))
    lens.append(("W" if west else "E", y1, max((D.local_bbox(q)[2] - D.local_bbox(q)[0] for q in band.each()), default=0.0)))
ok4 = min(t[2] for t in lens) >= a.min_head - 1e-9
print("%s 4. head room >= %.2f um per arm: %s" % ("PASS" if ok4 else "FAIL", a.min_head,
      ", ".join("%s y' %.2f: %.2f" % t for t in sorted(lens))))
sys.exit(0 if ok and ok2 and ok3 and ok4 else 1)
