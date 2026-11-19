"""Etch checker W (optional, 4/1): an exposed rectangle for watching the contact etch (4/x, down to the
top hBN). It holds a part where optically only the top-top hBN and the top graphite are seen on
bare substrate, plus some bare substrate. When the stack part matches the bare substrate colour,
the top-top hBN and the top graphite are etched away where exposed. The 7/0 mask protects W
(mask.py leaves it under PMMA), so W is first etched in the contact etch.

S = (TTBN ∩ TG) − (TBN ∪ G ∪ BBN ∪ BG), eroded by --margin: only top-top hBN on top graphite.
Q = R − ((TBN ∪ G ∪ BBN ∪ BG) grown by --margin): where W may lie; R = flake bounding box grown
by --frame (as in mask.py).
W (local frame) = the largest square in S as seed, grown one grid step at a time inside Q, each
side up to --size: each step takes the direction whose new row/column holds the most S (then
the most bare substrate), so W covers the stack part first; it stops when no step adds more
S and bare substrate is at least --bare of W. The seed is cut to --size. W must hold bare substrate.
Many stacks have no such region, or no such W: then no checker is drawn (4/1 cleared), exit 0.

Usage: python checker.py --flakes prepared.gds --params params.json --writes writes.gds
                         [--margin 0.5] [--min-seed 1] [--size 10] [--bare 0.25] [--step 0.1] [--frame 2] [--layer 4/1]
Run before mask.py.
"""
import argparse
import os
import sys

import klayout.db as db

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "nanodevice_topgate", "scripts"))
from tg_lib import Design, graphene, load_params, parse, read_layer, write_layer  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--flakes", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--writes", required=True)
ap.add_argument("--margin", type=float, default=0.5, help="um kept from top hBN, graphene, bottom hBN, bottom graphite")
ap.add_argument("--min-seed", type=float, default=1.0, help="um, smallest top-top hBN + top graphite square worth a checker")
ap.add_argument("--size", type=float, default=10.0, help="um, largest side of the checker")
ap.add_argument("--bare", type=float, default=0.25, help="stop growing once bare substrate is this fraction of W")
ap.add_argument("--step", type=float, default=0.1, help="search grid, um")
ap.add_argument("--frame", type=float, default=2.0, help="um around the flake bounding box (R, as mask.py --margin)")
ap.add_argument("--layer", default="4/1")
a = parse(ap, "contacts/checker")

P = load_params(a.params)
D = Design(a.flakes, P)
lm = P["layers"]
R = lambda k: read_layer(a.flakes, "%d/%d" % tuple(lm[k]))[0]
G = graphene(a.flakes, P)[0]
TTBN, TG = R("top_top_hbn"), R("top_graphite")
below = (R("top_hbn") + G + R("bottom_hbn") + R("graphite")).merged()
flakes = (TTBN + TG + below).merged()
M = db.Region(flakes.bbox().enlarged(D.um(a.frame)))             # R
S = ((TTBN & TG) - below).merged()

toL = D.Ti.to_itrans(D.dbu)                      # layout dbu -> local dbu
s, m = D.um(a.step), D.um(a.margin)
Q = (M - below.sized(m)).transformed(toL)
bb = Q.bbox()
nx, ny = bb.width() // s + 1, bb.height() // s + 1
org = db.Point(bb.left, bb.bottom)


def grid(region):
    px = region.rasterize(org, db.Vector(s, s), db.Vector(1, 1), nx, ny)   # 1x1 dbu probe per node
    return [[v > 0 for v in row] for row in px]


def maxsquare(ok):
    """Largest all-True node square (i0, j0, i1, j1): dp[j][i] = side of the square ending at (i, j)."""
    best, prev = (0, None), [0] * nx
    for j in range(ny):
        cur = [0] * nx
        for i in range(nx):
            if ok[j][i]:
                cur[i] = 1 + min(prev[i], cur[i - 1], prev[i - 1]) if i and j else 1
                if cur[i] > best[0]:
                    best = (cur[i], (i - cur[i] + 1, j - cur[i] + 1, i, j))
        prev = cur
    return best[1]


x = lambda i: (org.x + i * s) * D.dbu
y = lambda j: (org.y + j * s) * D.dbu


def none(why):
    write_layer(a.writes, a.layer, db.Region(), D.dbu)
    print("no etch checker: " + why)
    sys.exit(0)


seed = maxsquare(grid(S.transformed(toL).sized(-m)))
if seed is None or x(seed[2]) - x(seed[0]) < a.min_seed - 1e-9:
    none("no top-top hBN + top graphite on bare substrate of at least %.1f um square" % a.min_seed)

inQ, inS, cap = grid(Q), grid(S.transformed(toL)), int(round(a.size / a.step))
inB = grid(db.Region(bb) - flakes.transformed(toL))             # bare substrate
i0, j0, i1, j1 = seed
i1, j1 = min(i1, i0 + cap), min(j1, j0 + cap)                    # seed side at most --size
seed = (i0, j0, i1, j1)
count = lambda g, cells: sum(g[j][i] for i, j in cells)
while True:
    n = (i1 - i0 + 1) * (j1 - j0 + 1)
    enough = count(inB, [(i, j) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)]) >= a.bare * n
    opts = []                                    # (new box, its new nodes)
    if i1 - i0 < cap:
        if i0 > 0:
            opts.append(((i0 - 1, j0, i1, j1), [(i0 - 1, j) for j in range(j0, j1 + 1)]))
        if i1 < nx - 1:
            opts.append(((i0, j0, i1 + 1, j1), [(i1 + 1, j) for j in range(j0, j1 + 1)]))
    if j1 - j0 < cap:
        if j0 > 0:
            opts.append(((i0, j0 - 1, i1, j1), [(i, j0 - 1) for i in range(i0, i1 + 1)]))
        if j1 < ny - 1:
            opts.append(((i0, j0, i1, j1 + 1), [(i, j1 + 1) for i in range(i0, i1 + 1)]))
    opts = [(box, c) for box, c in opts if all(inQ[j][i] for i, j in c)]
    best = max(opts, key=lambda o: (count(inS, o[1]), count(inB, o[1])), default=None)
    if best is None or (enough and count(inS, best[1]) == 0):
        break
    i0, j0, i1, j1 = best[0]

W = D.box(x(i0), y(j0), x(i1), y(j1))
assert (W - M).is_empty() and (W & below).is_empty(), "checker leaves R or touches the stack below"
um2 = lambda r: r.area() * D.dbu ** 2
bare, stack = um2(W - flakes), um2(W & S)
if bare <= 0:
    none("no %.1f um checker around the top-top hBN + top graphite holds bare substrate" % a.size)
write_layer(a.writes, a.layer, W, D.dbu)
print("etch checker: x' %.2f..%.2f, y' %.2f..%.2f (%.2f x %.2f um, seed %.2f um square), %.2f um2: "
      "top-top hBN + top graphite %.2f, bare substrate %.2f, other %.2f -> %s"
      % (x(i0), x(i1), y(j0), y(j1), x(i1) - x(i0), y(j1) - y(j0), x(seed[2]) - x(seed[0]),
         um2(W), stack, bare, um2(W) - stack - bare, a.layer))
