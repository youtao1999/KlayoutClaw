"""Top gate, part 4: top-gate electrodes. One top-graphite electrode per top-gate contact, joining
it to the channel. Set rules:
  E subset of TG ∩ TBN   (top graphite, with top hBN separating it from the graphene)
  E ∩ arm corridors = ∅   (tg_lib.arm_keepout: each arm outside the channel extended outward
  by --escape and grown by --clearance; keeps the arms free for their own electrodes)
  E touches the channel (it comes out of the channel, not out of an arm)
Each electrode is the shortest Manhattan route (local strip frame, few turns) of --width from
the contact to a point that puts its end fully inside the channel; both ends sit fully inside.

Usage: python electrodes.py --flakes prepared.gds --params params.json --writes writes.gds
                            [--width 0.5] [--clearance 0.3] [--escape 50] [--step 0.05] [--turn 1.0]
                            [--channel 5/0] [--arms 5/1] [--contacts 5/2] [--layer 5/3]
"""
import argparse
import heapq
import sys

import klayout.db as db

from tg_lib import CLEARANCE, ESCAPE, Design, arm_keepout, load_params, parse, read_layer, write_layer

ap = argparse.ArgumentParser()
ap.add_argument("--flakes", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--writes", required=True)
ap.add_argument("--width", type=float, default=0.5, help="electrode width, um")
ap.add_argument("--clearance", type=float, default=CLEARANCE, help="distance kept from the arm corridors, um")
ap.add_argument("--escape", type=float, default=ESCAPE, help="arm corridor length outward from the arm, um")
ap.add_argument("--step", type=float, default=0.05, help="routing grid, um")
ap.add_argument("--turn", type=float, default=1.0, help="cost of one turn, um of extra length")
ap.add_argument("--channel", default="5/0")
ap.add_argument("--arms", default="5/1")
ap.add_argument("--contacts", default="5/2")
ap.add_argument("--layer", default="5/3")
a = parse(ap, "topgate/electrodes")

P = load_params(a.params)
D = Design(a.flakes, P)
lm = P["layers"]
R = lambda s: read_layer(a.writes, s if isinstance(s, str) else "%d/%d" % tuple(s))[0]
ch, arms, cts = R(a.channel), R(a.arms), R(a.contacts)
if ch.is_empty() or arms.is_empty() or cts.is_empty():
    sys.exit("run channel.py, arms.py and contacts.py first")
keepout = arm_keepout(D, ch, arms, a.clearance, a.escape)
allowed = ((R(lm["top_graphite"]) & R(lm["top_hbn"])) - keepout).merged()

# route in the local frame, on a grid of centre-line points whose width-square lies in the set
toL = D.Ti.to_itrans(D.dbu)                      # layout dbu -> local dbu
h, s = D.um(a.width / 2), D.um(a.step)
free = allowed.transformed(toL).sized(-h - s)    # centre-line may go here (1-step margin: corners cut between nodes)
goal = ch.transformed(toL).sized(-h)
bb = allowed.transformed(toL).bbox()
nx, ny = bb.width() // s + 1, bb.height() // s + 1
org = db.Point(bb.left, bb.bottom)


def grid(region):
    px = region.rasterize(org, db.Vector(s, s), db.Vector(1, 1), nx, ny)   # 1x1 dbu probe per node
    return {(i, j) for j, row in enumerate(px) for i, v in enumerate(row) if v > 0}


FREE, GOAL = grid(free), grid(goal)
local = lambda i, j: ((org.x + i * s) * D.dbu, (org.y + j * s) * D.dbu)
DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1)]
turn = a.turn / a.step


def route(starts):
    """Dijkstra over (node, direction) from every start node; cost = steps + turn penalty.
    Returns the node path."""
    heap = [(0.0, n, -1) for n in starts]
    best, prev = {(n, -1): 0.0 for n in starts}, {}
    while heap:
        c, n, d = heapq.heappop(heap)
        if n in GOAL:
            path = [n]
            while (n, d) in prev:
                n, d = prev[(n, d)]
                path.append(n)
            return path[::-1]
        if c > best.get((n, d), 1e18):
            continue
        for k, (di, dj) in enumerate(DIRS):
            m = (n[0] + di, n[1] + dj)
            if m not in FREE:
                continue
            nc = c + 1 + (turn if d not in (-1, k) else 0)
            if nc < best.get((m, k), 1e18):
                best[(m, k)] = nc
                prev[(m, k)] = (n, d)
                heapq.heappush(heap, (nc, m, k))
    return None


bars = db.Region()
for c in cts.each():
    x1, y1, x2, y2 = D.local_bbox(c)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    starts = grid(db.Region(c).transformed(toL).sized(-h)) & FREE    # width-square fully on the contact
    path = route(starts)
    if not path:
        sys.exit("no route from contact (%.3f, %.3f) to the channel inside TG ∩ TBN clear of the arm corridors" % (cx, cy))
    corners = [path[0]] + [path[k] for k in range(1, len(path) - 1)
                           if (path[k][0] - path[k - 1][0], path[k][1] - path[k - 1][1])
                           != (path[k + 1][0] - path[k][0], path[k + 1][1] - path[k][1])] + [path[-1]]
    pts = [local(*q) for q in corners]
    e = db.Region()
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        w = a.width / 2
        e += D.box(min(ax, bx) - w, min(ay, by) - w, max(ax, bx) + w, max(ay, by) + w)
    e.merge()
    bars += e
    print("electrode from contact (%.3f, %.3f): %s  length %.3f um" % (
        cx, cy, " -> ".join("(%.2f, %.2f)" % p for p in pts), (len(path) - 1) * a.step))

bars.merge()
off = (bars - allowed).area() * D.dbu ** 2
assert off < 1e-3, "electrodes leave TG ∩ TBN − keep-out by %.4f um2" % off
write_layer(a.writes, a.layer, bars, D.dbu)
print("%d electrodes on %s; top gate is %d polygon(s)" % (cts.count(), a.layer, (ch + arms + cts + bars).merged().count()))
