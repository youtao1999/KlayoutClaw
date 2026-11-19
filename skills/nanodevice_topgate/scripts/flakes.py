"""Top gate, part 0: flakes and the active region. Copies every flake layer named in params
(top-top hBN, top graphite, top hBN, graphene, bottom hBN, bottom graphite, graphene pieces)
from the flakes GDS into writes.gds, and writes the active region, where all graphene pieces
overlap, to --layer.

Usage: python flakes.py --flakes prepared.gds --params params.json --writes writes.gds [--layer 11/4]
"""
import argparse
import sys

from tg_lib import load_params, parse, read_layer, write_layer

FLAKES = ["top_top_hbn", "top_graphite", "top_hbn", "graphene", "bottom_hbn", "graphite"]

ap = argparse.ArgumentParser()
ap.add_argument("--flakes", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--writes", required=True)
ap.add_argument("--layer", default="11/4")
a = parse(ap, "topgate/flakes")

lm = load_params(a.params)["layers"]
pieces = lm.get("graphene_pieces", [])
if not pieces:
    sys.exit("params has no layers.graphene_pieces")
active = None
for name, (l, d) in [(k, lm[k]) for k in FLAKES] + [("graphene piece", p) for p in pieces]:
    spec = "%d/%d" % (l, d)
    r, dbu = read_layer(a.flakes, spec)
    if r.is_empty():
        sys.exit("%s %s is empty in %s" % (name, spec, a.flakes))
    write_layer(a.writes, spec, r, dbu)
    print("%-15s %s  area %.3f um2" % (name, spec, r.area() * dbu ** 2))
    if name == "graphene piece":
        active = r if active is None else (active & r)
if active.is_empty():
    sys.exit("graphene pieces do not overlap: no active region")
write_layer(a.writes, a.layer, active, dbu)
print("active region   %s  %d polygon(s)  area %.3f um2" % (a.layer, active.count(), active.area() * dbu ** 2))
