"""Big pads (2/1): one rectangle per electrode tail, spread around the stack, each with a
trapezoidal tentacle out to its tail.

Each lead on 2/0 ends at a tail t (nanodevice_electrodes); u = unit(t − channel centre).
- pad: axis-aligned rectangle (GDS frame), --size square, its inner edge centred at m = centre + u·r
  and running outward along the axis nearest u.
- tentacle: trapezoid with both parallel sides across that axis: --base wide on the pad's inner
  edge (--overlap inside the pad), --tip wide at the tail end; its centre line runs from the base
  centre through the tail and on --into past it (along the axis), so the tail lies inside it and
  the fine lead overlaps it.
r: the smallest from tail radius + --reach upward in --step steps for which pads keep --gap from
each other, tentacles keep --gap from each other and from other pads, and nothing touches another
lead or comes within --clear of the flakes.

Usage: python pads.py --flakes prepared.gds --params params.json --writes writes.gds
                      [--size 120] [--base 40] [--tip 4] [--into 5] [--overlap 2] [--reach 20]
                      [--step 5] [--gap 20] [--clear 20] [--leads 2/0] [--layer 2/1]
"""
import argparse
import math
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
ap.add_argument("--size", type=float, default=120.0, help="um, pad side")
ap.add_argument("--base", type=float, default=40.0, help="um, tentacle width at the pad")
ap.add_argument("--tip", type=float, default=4.0, help="um, tentacle width at the tail")
ap.add_argument("--into", type=float, default=5.0, help="um, tentacle tip past the tail (overlap with the fine lead)")
ap.add_argument("--overlap", type=float, default=2.0, help="um, tentacle base inside the pad")
ap.add_argument("--reach", type=float, default=20.0, help="um, shortest tentacle")
ap.add_argument("--step", type=float, default=5.0)
ap.add_argument("--gap", type=float, default=20.0, help="um between pads, and between tentacles")
ap.add_argument("--clear", type=float, default=20.0, help="um, pads and tentacles stay this far from the flakes' bounding box")
ap.add_argument("--leads", default="2/0")
ap.add_argument("--layer", default="2/1")
a = ap.parse_args()

P = load_params(a.params)
D = Design(a.flakes, P)
ch, dbu = read_layer(a.writes, "5/0")
cx1, cy1, cx2, cy2 = D.local_bbox(next(ch.each()))
cc = D.T * db.DPoint((cx1 + cx2) / 2, (cy1 + cy2) / 2)          # channel centre, GDS um
flakes = db.Region()
for k in FLAKES:
    flakes += read_layer(a.flakes, "%d/%d" % tuple(P["layers"][k]))[0]
keep_out = db.Region(flakes.bbox()).sized(D.um(a.clear))

ly = db.Layout()
ly.read(a.writes)
paths = [s.dpath for s in ly.top_cell().shapes(ly.layer(*layer(a.leads))).each() if s.is_path()]
if not paths:
    sys.exit("no lead paths on %s: run nanodevice_electrodes first" % a.leads)
leads = [db.Region(p.to_itype(dbu).polygon()) for p in paths]
tails = [list(p.each_point())[-1] for p in paths]
rt = max(t.distance(cc) for t in tails)


def parts(t, r):
    """Pad (DBox) and tentacle (DPolygon) for tail t with the pad's inner edge at radius r."""
    u = (t - cc) * (1.0 / t.distance(cc))
    m = cc + u * r
    h = a.size / 2
    if abs(u.x) >= abs(u.y):                                     # runs along x
        sx = 1 if u.x > 0 else -1
        pad = db.DBox(m.x, m.y - h, m.x + sx * a.size, m.y + h)
        bx = m.x + sx * a.overlap
        k = a.into / abs(bx - t.x)                               # tip on the line base -> tail, --into past the tail
        tx, ty = t.x + (t.x - bx) * k, t.y + (t.y - m.y) * k
        pts = [(bx, m.y - a.base / 2), (bx, m.y + a.base / 2), (tx, ty + a.tip / 2), (tx, ty - a.tip / 2)]
    else:                                                        # runs along y
        sy = 1 if u.y > 0 else -1
        pad = db.DBox(m.x - h, m.y, m.x + h, m.y + sy * a.size)
        by = m.y + sy * a.overlap
        k = a.into / abs(by - t.y)
        tx, ty = t.x + (t.x - m.x) * k, t.y + (t.y - by) * k
        pts = [(m.x - a.base / 2, by), (m.x + a.base / 2, by), (tx + a.tip / 2, ty), (tx - a.tip / 2, ty)]
    return pad, db.DPolygon([db.DPoint(x, y) for x, y in pts])


def ok(ps):
    R = lambda s: db.Region(s.to_itype(dbu))
    pads, tents = [R(p) for p, _ in ps], [R(t) for _, t in ps]
    g = D.um(a.gap)
    for i in range(len(ps)):
        mine = pads[i] + tents[i]
        if not (mine & keep_out).is_empty():
            return False
        for j in range(len(ps)):
            if j == i:
                continue
            if not (mine & leads[j]).is_empty():
                return False
            if j < i and not (pads[i].sized(g) & pads[j]).is_empty():
                return False
            if not (tents[i].sized(g) & (tents[j] + pads[j])).is_empty():
                return False
    return True


r = rt + a.reach
while r < rt + 2000 and not ok([parts(t, r) for t in tails]):
    r += a.step
if r >= rt + 2000:
    sys.exit("no pad radius fits: lower --size/--base/--gap")
ps = [parts(t, r) for t in tails]
sh = ly.top_cell().shapes(ly.layer(*layer(a.layer)))
sh.clear()
for pad, tent in ps:
    sh.insert(pad.to_itype(dbu))
    sh.insert(tent.to_itype(dbu))
opt = db.SaveLayoutOptions()
opt.format = "GDS2"
ly.write(a.writes + ".part", opt)
os.replace(a.writes + ".part", a.writes)
for t, (pad, tent) in zip(tails, ps):
    along_x = abs((t - cc).x) >= abs((t - cc).y)
    print("tail (%.1f, %.1f): pad (%.1f, %.1f; %.1f, %.1f), tentacle %.1f um along %s"
          % (t.x, t.y, pad.left, pad.bottom, pad.right, pad.top,
             tent.bbox().width() if along_x else tent.bbox().height(), "x" if along_x else "y"))
print("%d pads %.0f x %.0f um, inner edges at %.0f um from the channel centre (tails at %.0f um), tentacles %.0f -> %.0f um wide -> %s"
      % (len(ps), a.size, a.size, r, rt, a.base, a.tip, a.layer))
