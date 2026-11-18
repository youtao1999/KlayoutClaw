"""Top gate, part 1: the channel. A rectangle along the bottom-graphite strip, narrower than
the bottom graphite by channel.bg_inset on each side, written to the channel layer of writes.gds.

Usage: python channel.py --flakes prepared.gds --params params.json --writes writes.gds [--layer 5/0]

--flakes : GDS with the bottom graphite (params layers.graphite), same frame as writes.gds
--params : device params; uses gate_end and channel {y: [y1, y2], bg_inset, min_width}
           (local strip frame: x' across the bottom graphite, y' along it)
The channel layer in writes.gds is replaced; every other layer is left as it is.
"""
import argparse
import sys

from tg_lib import Design, load_params, write_layer

ap = argparse.ArgumentParser()
ap.add_argument("--flakes", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--writes", required=True)
ap.add_argument("--layer", default="5/0")
a = ap.parse_args()

P = load_params(a.params)
D = Design(a.flakes, P)
CH = P["channel"]
y1, y2 = CH["y"]
ys = [y1 + (y2 - y1) * k / 20 for k in range(21)]
x1 = max(D.graphite_edge(y, "L") for y in ys) + CH["bg_inset"]
x2 = min(D.graphite_edge(y, "R") for y in ys) - CH["bg_inset"]
if x2 - x1 < CH.get("min_width", 1.0):
    sys.exit("bottom graphite too narrow: channel would be %.3f um wide" % (x2 - x1))
ch = D.box(x1, y1, x2, y2)
assert (ch - D.R("graphite")).is_empty(), "channel leaves the bottom graphite"

write_layer(a.writes, a.layer, ch, D.dbu)
print("channel %s local x' [%.3f, %.3f] y' [%.3f, %.3f]  width %.3f um  length %.3f um  area %.3f um2"
      % (a.layer, x1, x2, y1, y2, x2 - x1, y2 - y1, ch.area() * D.dbu ** 2))
print("frame", D.frame)
