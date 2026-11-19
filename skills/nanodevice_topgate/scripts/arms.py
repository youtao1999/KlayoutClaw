"""Top gate, part 2: the arms. n arms per side, each `width` wide with `gap` between neighbours,
centred along the channel, then moved by --shift along y' (+ = towards gate_end); opposite
arms sit at the same y'. Each arm runs from inside the
channel (by --overlap) out past the bottom-graphite edge by --overshoot. Default --overshoot max:
each arm runs out as far as it stays --edge-margin inside the active region (11/4), so the arm tip
leaves room for the electrode head (user, 2026-11-17: longer arms for head room).

Usage: python arms.py --flakes prepared.gds --params params.json --writes writes.gds
                      --n 3 --width 1 --gap 1 [--shift 0] [--overshoot max|<um>] [--edge-margin 0.1] [--overlap 0.5] [--sides L R]
                      [--channel 5/0] [--layer 5/1]

Reads the channel from writes.gds (--channel, written by channel.py) and replaces --layer.
"""
import argparse
import sys

from tg_lib import Design, load_params, parse, read_layer, write_layer

ap = argparse.ArgumentParser()
ap.add_argument("--flakes", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--writes", required=True)
ap.add_argument("--n", type=int, required=True, help="arms per side")
ap.add_argument("--width", type=float, required=True, help="arm width, um")
ap.add_argument("--gap", type=float, required=True, help="gap between neighbouring arms, um")
ap.add_argument("--shift", type=float, default=0.0, help="move the arm group along the channel, um")
ap.add_argument("--overshoot", default="max", help="arm end past the bottom-graphite edge, um, or max (to the active-region edge)")
ap.add_argument("--edge-margin", type=float, default=0.1, help="um kept inside the active region by --overshoot max")
ap.add_argument("--overlap", type=float, default=0.5, help="arm start inside the channel, um")
ap.add_argument("--sides", nargs="+", default=["L", "R"], choices=["L", "R"])
ap.add_argument("--channel", default="5/0")
ap.add_argument("--layer", default="5/1")
a = parse(ap, "topgate/arms")

D = Design(a.flakes, load_params(a.params))
ch, dbu = read_layer(a.writes, a.channel)
if ch.count() != 1:
    sys.exit("expected one channel polygon on %s, found %d" % (a.channel, ch.count()))
cx1, cy1, cx2, cy2 = D.local_bbox(next(ch.each()))

span = a.n * a.width + (a.n - 1) * a.gap
if span > cy2 - cy1:
    sys.exit("%d arms need %.3f um, channel is %.3f um long" % (a.n, span, cy2 - cy1))
y0 = (cy1 + cy2 - span) / 2 + a.shift
if y0 < cy1 - 1e-9 or y0 + span > cy2 + 1e-9:
    sys.exit("shift %.3f moves the arms off the channel (allowed +-%.3f um)" % (a.shift, (cy2 - cy1 - span) / 2))
inA = read_layer(a.writes, "11/4")[0].sized(-D.um(a.edge_margin)) if a.overshoot == "max" else None
if inA is not None and inA.is_empty():
    sys.exit("--overshoot max needs the active region 11/4: run flakes.py first")


def reach(s, edge, y1, y2):
    """Overshoot past edge: the given number, or the longest that keeps the arm tip inside A."""
    if inA is None:
        return float(a.overshoot)
    box = (lambda o: D.box(edge - o, y1, edge, y2)) if s == "L" else (lambda o: D.box(edge, y1, edge + o, y2))
    lo, hi = 0.0, 20.0
    for _ in range(30):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if (box(m) - inA).is_empty() else (lo, m)
    return lo


arms = D.box(0, 0, 0, 0) - D.box(0, 0, 0, 0)        # empty Region in layout dbu
rows = []
for i in range(a.n):
    y1 = y0 + i * (a.width + a.gap)
    y2 = y1 + a.width
    for s in a.sides:
        e = [D.graphite_edge(y, s) for y in (y1, (y1 + y2) / 2, y2)]
        if s == "L":
            edge = min(e)                             # outermost bottom-graphite edge over the arm
            x1, x2 = edge - reach(s, edge, y1, y2), cx1 + a.overlap
        else:
            edge = max(e)
            x1, x2 = cx2 - a.overlap, edge + reach(s, edge, y1, y2)
        arms += D.box(x1, y1, x2, y2)
        rows.append((s, y1, y2, x1, x2, edge))
arms.merge()
assert arms.count() == a.n * len(a.sides), "arms touch each other"
assert not (arms - D.R("graphite")).is_empty(), "arms do not leave the bottom graphite"

write_layer(a.writes, a.layer, arms, dbu)
print("channel local x' [%.3f, %.3f] y' [%.3f, %.3f]" % (cx1, cx2, cy1, cy2))
for s, y1, y2, x1, x2, edge in rows:
    print("arm %s y' [%.3f, %.3f]  x' [%.3f, %.3f]  bottom-graphite edge %.3f, overshoot %.3f"
          % (s, y1, y2, x1, x2, edge, (edge - x1) if s == "L" else (x2 - edge)))
print("%d arms on %s, area %.3f um2" % (len(rows), a.layer, arms.area() * dbu ** 2))
