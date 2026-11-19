"""Top gate, part 1: the channel. A rectangle along the bottom-graphite strip, narrower than
the bottom graphite by channel.bg_inset on each side, written to the channel layer of result.gds.

Usage: python channel.py --flakes prepared.gds --params params.json --writes result.gds [--layer 5/0]

--flakes : GDS with the bottom graphite (params layers.graphite), same frame as result.gds
--params : device params; uses gate_end and channel {y: [y1, y2] or "auto", bg_inset, min_width,
           arm_reach (auto: 0.7)}; "auto" takes the longest stretch where the active region reaches
           arm_reach past both bottom-graphite edges and both hBN cover the graphite
           (local strip frame: x' across the bottom graphite, y' along it)
The channel layer in result.gds is replaced; every other layer is left as it is.
"""
import argparse
import sys

from tg_lib import Design, graphene, load_params, parse, record, write_layer

ap = argparse.ArgumentParser()
ap.add_argument("--flakes", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--writes", required=True)
ap.add_argument("--layer", default="5/0")
a = parse(ap, "topgate/channel")

P = load_params(a.params)
D = Design(a.flakes, P)
CH = P["channel"]
if CH["y"] == "auto":
    # the longest stretch along the bottom graphite where the active region reaches arm_reach past both
    # graphite edges (room for arms and their contacts) and both hBN cover the graphite
    A = graphene(a.flakes, P)[1]
    TBN, BBN, reach = D.R("top_hbn"), D.R("bottom_hbn"), CH.get("arm_reach", 0.7)
    inside = lambda R, xa, xb, y: (D.box(xa, y - 0.01, xb, y + 0.01) - R).is_empty()
    gx1, gy1, gx2, gy2 = D.local_bbox(next(D.R("graphite").each()))
    good = []
    for k in range(int(gy1 * 10) + 1, int(gy2 * 10)):
        y = k / 10
        xl, xr = D.graphite_edge(y, "L"), D.graphite_edge(y, "R")
        if inside(A, xl - reach, xr + reach, y) and inside(TBN, xl, xr, y) and inside(BBN, xl, xr, y):
            good.append(y)
    runs = []
    for y in good:
        if runs and y - runs[-1][-1] < 0.15:
            runs[-1].append(y)
        else:
            runs.append([y])
    if not runs:
        sys.exit("no stretch of the bottom graphite where the active region reaches %.2f um past both edges" % reach)
    y1, y2 = max(((r[0], r[-1]) for r in runs), key=lambda r: r[1] - r[0])
else:
    y1, y2 = CH["y"]
ys = [y1 + (y2 - y1) * k / 20 for k in range(21)]
x1 = max(D.graphite_edge(y, "L") for y in ys) + CH["bg_inset"]
x2 = min(D.graphite_edge(y, "R") for y in ys) - CH["bg_inset"]
if x2 - x1 < CH.get("min_width", 1.0):
    sys.exit("bottom graphite too narrow: channel would be %.3f um wide" % (x2 - x1))
ch = D.box(x1, y1, x2, y2)
assert (ch - D.R("graphite")).is_empty(), "channel leaves the bottom graphite"

write_layer(a.writes, a.layer, ch, D.dbu)
record(a.params, "topgate/channel", x=[round(x1, 4), round(x2, 4)], y=[y1, y2], width=round(x2 - x1, 4))
print("channel %s local x' [%.3f, %.3f] y' [%.3f, %.3f]  width %.3f um  length %.3f um  area %.3f um2"
      % (a.layer, x1, x2, y1, y2, x2 - x1, y2 - y1, ch.area() * D.dbu ** 2))
print("frame", D.frame)
