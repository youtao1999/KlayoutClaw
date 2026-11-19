"""Electrodes (2/0): one path per arm, per top-gate contact and per back-gate lead, from its head
out to its tail. No lead touches another; only the back-gate leads touch the bottom graphite,
and only inside the exposed bottom graphite X.

Tails: one per lead, evenly spaced on a circle of radius --tail-radius around the channel centre
(local frame, first at angle 0). Default: as small as possible, the farthest corner of the flakes'
bounding box plus --tail-margin, so the fine leads are short (user, 2026-11-17: thin leads are
fragile, dirt can break them; keep them short). The big pads (nanodevice_pads, 2/1) reach the
tails with trapezoidal tentacles.

Arm lead, in the local frame:
- head: starts --inset inside the contact C's inner edge, on the arm's centre line, and runs out
  over the arm tip, so the part of the lead on graphene lies in A ∩ C
  (the top graphite there is etched away);
- stub: straight out along x' until --clear past everything else of the top gate on that side;
- then straight to its tail.
Tails: per side, the n tails whose direction from the channel centre is closest to the side's
direction (west 180 deg, east 0 deg), matched to the arms in y' order so the leads do not cross.
Width: --width, slightly narrower than the arms, so the head stays inside the arm.

Top-gate lead: same rules. Head at the centre of a top-gate contact island (5/2); tail: the free
tail whose direction from the channel centre is nearest the island's; stub from the head along the
axis (x' or y') nearest the tail direction, --clear past the island, then straight to the tail.
Width: min(--width, island size - 0.1).

Back-gate leads (--bg-leads, 2): same rules as the top-gate lead (head at the deepest point of the
terminal); terminals: the largest pieces of the exposed bottom graphite X = BG − (TG ∪ TBN ∪ G ∪
BBN) (kept under PMMA by the 7/0 mask), one lead per piece. A piece's width is 2 x the depth it
erodes to before vanishing (tg_lib.erode); only pieces with width − 0.1 >= --min-width count,
thinner slivers are not terminals. Width: min(--width, piece width - 0.1).

Usage: python electrodes.py --flakes prepared.gds --params params.json --writes writes.gds
                            [--width 0.8] [--inset 0.05] [--clear 1] [--tail-radius auto|<um>] [--tail-margin 30] [--bg-leads 2] [--min-width 0.3] [--layer 2/0]
"""
import argparse
import itertools
import math
import os
import sys

import klayout.db as db

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "nanodevice_topgate", "scripts"))
from tg_lib import Design, bg_terminal, erode, graphene, layer, load_params, parse, read_layer, record  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--flakes", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--writes", required=True)
ap.add_argument("--width", type=float, default=0.8, help="um, lead width (slightly below the arm width)")
ap.add_argument("--inset", type=float, default=0.05, help="um, head start inside the contact's inner edge")
ap.add_argument("--clear", type=float, default=1.0, help="um, stub runs this far past the top gate on its side")
ap.add_argument("--tail-slots", type=int, default=0, help="tail positions on the circle (default 0: one per lead); more give the top-gate and back-gate leads a choice")
ap.add_argument("--spacing", type=float, default=0.5, help="um kept between leads when choosing the terminal leads' tails (as check.py)")
ap.add_argument("--tail-radius", default="auto", help="um, circle of the lead tails around the channel centre, or auto")
ap.add_argument("--tail-margin", type=float, default=30.0, help="um past the flakes' farthest bounding-box corner (auto radius)")
ap.add_argument("--bg-leads", type=int, default=2, help="back-gate leads (user: the back gate has two)")
ap.add_argument("--min-width", type=float, default=0.3, help="um, narrowest writable lead; thinner pieces of X are not terminals")
ap.add_argument("--layer", default="2/0")
a = parse(ap, "electrodes/electrodes")

D = Design(a.flakes, load_params(a.params))
ch, dbu = read_layer(a.writes, "5/0")
arms, C = read_layer(a.writes, "5/1")[0], read_layer(a.writes, "4/0")[0]
T = db.Region()
for s in ["5/0", "5/1", "5/2", "5/3"]:
    T += read_layer(a.writes, s)[0]
if ch.count() != 1 or arms.is_empty() or C.is_empty():
    sys.exit("need channel 5/0, arms 5/1 (nanodevice_topgate) and contacts 4/0 (nanodevice_contacts)")
loc = lambda r: [D.Ti * p.to_dtype(dbu) for p in r.each()]      # local-frame DPolygons, um
cx1, _, cx2, _ = D.local_bbox(next(ch.each()))
mid = (cx1 + cx2) / 2
side_of = lambda b: (b.right < mid)                              # True = west
Tl, Cl = loc(T.merged()), loc(C)
cc = db.DPoint((cx1 + cx2) / 2, sum(D.local_bbox(p)[1] + D.local_bbox(p)[3] for p in ch.each()) / 2)
I = read_layer(a.writes, "5/2")[0]
n = (arms - ch).count() + I.count() + a.bg_leads
if a.tail_radius == "auto":
    fl = db.Region()
    for k in ["top_top_hbn", "top_graphite", "top_hbn", "graphene", "bottom_hbn", "graphite"]:
        fl += read_layer(a.flakes, "%d/%d" % tuple(load_params(a.params)["layers"][k]))[0]
    b = fl.bbox().to_dtype(dbu)
    rad = max((D.Ti * p).distance(cc) for p in (b.p1, b.p2, db.DPoint(b.left, b.top), db.DPoint(b.right, b.bottom))) + a.tail_margin
else:
    rad = float(a.tail_radius)
print("tails on a %.1f um circle around the channel centre" % rad)
slots = max(n, a.tail_slots)
free_tails = [cc + db.DVector(math.cos(2 * math.pi * k / slots), math.sin(2 * math.pi * k / slots)) * rad for k in range(slots)]
ang = lambda p: math.atan2(p.y - cc.y, p.x - cc.x)


leads = []
for west in (True, False):
    side = sorted((p.bbox() for p in loc(arms - ch) if side_of(p.bbox()) == west), key=lambda b: b.center().y)
    if not side:
        continue
    cts = [p.bbox() for p in Cl if side_of(p.bbox()) == west]
    assert len(cts) == 1, "expected one contact rectangle per side"
    cb = cts[0]
    x0 = cb.right - a.inset if west else cb.left + a.inset           # head start, inside C
    far = min(p.bbox().left for p in Tl) if west else max(p.bbox().right for p in Tl)
    xs = far - a.clear if west else far + a.clear                    # stub end, past the top gate
    want = math.pi if west else 0.0
    gap = lambda p: abs(math.remainder(ang(p) - want, 2 * math.pi))
    mine = sorted(free_tails, key=gap)[:len(side)]
    for p in mine:
        free_tails.remove(p)
    mine.sort(key=lambda p: p.y)                                     # arms and tails in the same y' order
    for b, end in zip(side, mine):
        yc = b.center().y
        s = db.DPoint(xs, yc)
        leads.append(db.DPath([db.DPoint(x0, yc), s, end], a.width))
        print("%s arm y' %.2f: head x' %.2f, stub to x' %.2f, tail (%.1f, %.1f), length %.1f um"
              % ("west" if west else "east", yc, x0, xs, end.x, end.y, abs(xs - x0) + s.distance(end)))

stack = (T + D.R("graphite")).merged()                           # a lead may meet these only on its terminal


def deepest(poly):
    """A point deep inside a DPolygon and its width: erode in 0.05 um steps until it vanishes;
    centre of the last piece, 2 x the erosion depth."""
    r, depth = erode(db.Region(poly.to_itype(dbu)), dbu)
    p = max(r.each(), key=lambda q: q.area())
    c = p.bbox().center()
    return (c if p.inside(c) else next(p.each_point_hull())).to_dtype(dbu), 2 * depth


def route(poly, end, bg):
    """Lead from deep inside a terminal (DPolygon, local frame) to the tail end: stub along an axis,
    --clear past the terminal's bounding box, then straight to the tail. Axes are tried nearest the
    tail first; the first whose lead meets the stack (T ∪ BG) only on the terminal is returned as
    (path, stub end), or None if every axis crosses the stack."""
    b = poly.bbox()
    c, width = deepest(poly)
    d = end - c
    w = min(a.width, (width if bg else min(b.width(), b.height())) - 0.1)
    ok = db.Region((D.T * poly).to_itype(dbu)).sized(1)
    stubs = [db.DPoint(b.left - a.clear, c.y), db.DPoint(b.right + a.clear, c.y),
             db.DPoint(c.x, b.bottom - a.clear), db.DPoint(c.x, b.top + a.clear)]
    stubs.sort(key=lambda s: -(s - c).sprod(d) / (s - c).length())   # axis nearest the tail first
    for s in stubs:
        dp = db.DPath([c, s, end], w)
        if ((reg(dp) & stack) - ok).is_empty():
            return dp, s
    return None


reg = lambda dp: db.Region((D.T * dp).to_itype(dbu).polygon())
plen = lambda dp: sum(p.distance(q) for p, q in zip(list(dp.each_point())[:-1], list(dp.each_point())[1:]))

# terminal leads: the top-gate contacts, then the back gate (from the exposed bottom graphite X =
# BG − (TG ∪ TBN ∪ G ∪ BBN), its largest pieces)
terms = [(isl, "top-gate contact", False) for isl in loc(I)]
X = bg_terminal(a.flakes, load_params(a.params), a.writes)   # + edge terminals under BBN if back_gate.edge_contact
pieces = sorted((p for p in loc(X) if deepest(p)[1] - 0.1 >= a.min_width - 1e-9), key=lambda p: -p.area())
if len(pieces) < a.bg_leads:
    # shortcut: one lead per piece of X; two heads on one piece are not implemented yet
    sys.exit("need %d pieces of exposed bottom graphite at least %.2f um wide for %d back-gate leads, found %d"
             % (a.bg_leads, a.min_width + 0.1, a.bg_leads, len(pieces)))
terms += [(p, "back gate %d" % (k + 1), True) for k, p in enumerate(pieces[:a.bg_leads])]

# tails for the terminal leads: every assignment of the free tails is tried (a greedy nearest-tail
# choice can leave a later terminal only tails behind the channel); the shortest one where every lead
# meets the stack only on its terminal and all leads stay --spacing apart wins
gap = D.um(a.spacing)
arm_regs = [reg(dp) for dp in leads]
cand = {}                                            # (terminal, tail) -> (path, stub end, region), routes clear of the arm leads
for i, (p, _, bg) in enumerate(terms):
    for j, end in enumerate(free_tails):
        got = route(p, end, bg)
        if got and all((reg(got[0]).sized(gap) & o).is_empty() for o in arm_regs):
            cand[i, j] = got + (reg(got[0]),)
clash = lambda u, v: not (cand[u][2].sized(gap) & cand[v][2]).is_empty()
best = None
for perm in itertools.permutations(range(len(free_tails)), len(terms)):
    keys = list(enumerate(perm))
    if any(k not in cand for k in keys) or any(clash(keys[x], keys[y]) for x in range(len(keys)) for y in range(x)):
        continue
    total = sum(plen(cand[k][0]) for k in keys)
    if best is None or total < best[0]:
        best = (total, [cand[k][:2] for k in keys])
if best is None:
    sys.exit("no assignment of tails lets every top-gate and back-gate lead avoid the stack and the other leads")
for (_, name, _), (dp, s) in zip(terms, best[1]):
    pts = list(dp.each_point())
    leads.append(dp)
    print("%s (%.2f, %.2f): stub to (%.2f, %.2f), tail (%.1f, %.1f), width %.2f, length %.1f um"
          % (name, pts[0].x, pts[0].y, s.x, s.y, pts[-1].x, pts[-1].y, dp.width, plen(dp)))

ly = db.Layout()
ly.read(a.writes)
sh = ly.top_cell().shapes(ly.layer(*layer(a.layer)))
sh.clear()
for dp in leads:
    sh.insert((D.T * dp).to_itype(dbu))
opt = db.SaveLayoutOptions()
opt.format = "GDS2"
ly.write(a.writes + ".part", opt)
os.replace(a.writes + ".part", a.writes)
record(a.params, "electrodes/electrodes", tail_radius=round(rad, 3), tail_slots=slots,
       leads=[{"path": [[round(p.x, 3), round(p.y, 3)] for p in dp.each_point()], "width": dp.width} for dp in leads])
print("%d leads -> %s" % (len(leads), a.layer))
