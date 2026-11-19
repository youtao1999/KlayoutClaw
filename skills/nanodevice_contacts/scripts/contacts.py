"""Contacts (4/0): rectangular exposed regions, etched only down to the top hBN: the top-top hBN
and top graphite there are removed, the graphene stays under the top hBN. The electrodes (a later
skill) contact the graphene inside them.

One rectangle per side, in the local frame:
- x': inner edge --gap + 0.05 um past the bottom-graphite edge (as close to the graphite as
  rule 3 allows, to leave the most head room on the arm tip), so C ∩ BG = ∅ and C covers the
  outer end of every arm on that side; outer edge --length further out (auto: 0.1 um past the
  farthest arm tip on that side, at least 3 um).
- y': the side's arm span grown by the corridor clearance, so C stays inside the arm corridors,
  then pulled in until C stays --gap away from the top-gate body (rule 3).
Rule 3: C covers only the arm tips (arms − BG) of the top gate and keeps --gap from the rest,
the body = channel ∪ (arms ∩ BG) ∪ top-gate contacts ∪ top-gate electrodes.

Usage: python contacts.py --flakes prepared.gds --params params.json --writes writes.gds [--length auto] [--layer 4/0]
"""
import argparse
import os
import sys

import klayout.db as db

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "nanodevice_topgate", "scripts"))
from tg_lib import CLEARANCE, Design, body, load_params, parse, read_layer, record, write_layer  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--flakes", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--writes", required=True)
ap.add_argument("--length", default="auto", help="um along x' from the inner edge outward; auto: 0.1 um past the farthest arm tip on that side, at least 3")
ap.add_argument("--clearance", type=float, default=CLEARANCE)
ap.add_argument("--gap", type=float, default=0.15, help="um kept between C and the top-gate body")
ap.add_argument("--layer", default="4/0")
a = parse(ap, "contacts/contacts")

D = Design(a.flakes, load_params(a.params))
ch, dbu = read_layer(a.writes, "5/0")
arms = read_layer(a.writes, "5/1")[0]
BG = D.R("graphite")
near = body(a.writes, BG).sized(D.um(a.gap))       # C must not meet this set
if ch.count() != 1 or arms.is_empty():
    sys.exit("run nanodevice_topgate first: need the channel 5/0 and arms 5/1")
cx1, _, cx2, _ = D.local_bbox(next(ch.each()))
mid = (cx1 + cx2) / 2

C = db.Region()
rec = {}
for west in (True, False):
    side = [D.local_bbox(p) for p in (arms - ch).each() if (D.local_bbox(p)[2] < mid) == west]
    if not side:
        continue
    y1, y2 = min(b[1] for b in side) - a.clearance, max(b[3] for b in side) + a.clearance
    ya, yb = y1 + a.clearance, y2 - a.clearance          # arm span
    bg = D.local_bbox(next((BG & D.box(-1e3, y1, 1e3, y2)).merged().each()))
    if west:
        end, edge = max(b[0] for b in side), bg[0]        # innermost arm end, outermost graphite edge
        assert end < edge, "west arms do not pass the bottom graphite"
        xb = edge - a.gap - 0.05
        xa = xb - (max(3.0, xb - min(b[0] for b in side) + 0.1) if a.length == "auto" else float(a.length))
    else:
        end, edge = min(b[2] for b in side), bg[2]
        assert end > edge, "east arms do not pass the bottom graphite"
        xa = edge + a.gap + 0.05
        xb = xa + (max(3.0, max(b[2] for b in side) - xa + 0.1) if a.length == "auto" else float(a.length))
    for p in (near & D.box(xa, y1, xb, ya)).each():   # pull the edges in, clear of the body
        y1 = max(y1, D.local_bbox(p)[3])
    for p in (near & D.box(xa, yb, xb, y2)).each():
        y2 = min(y2, D.local_bbox(p)[1])
    assert y1 < ya and y2 > yb, "no room for the contact between the arms and the top-gate body"
    C += D.box(xa, y1, xb, y2)
    rec["west" if west else "east"] = {"x": [round(xa, 4), round(xb, 4)], "y": [round(y1, 4), round(y2, 4)], "length": round(xb - xa, 4)}
    print("%s contact: x' %.2f..%.2f (graphite edge %.2f, arm end %.2f), y' %.2f..%.2f (arms %.2f..%.2f)"
          % ("west" if west else "east", xa, xb, edge, end, y1, y2, ya, yb))
C.merge()
assert (C & BG).is_empty(), "contact touches the bottom graphite"
assert (C & near).is_empty(), "contact within --gap of the top-gate body"
write_layer(a.writes, a.layer, C, dbu)
record(a.params, "contacts/contacts", rectangles=rec)
