"""Synthetic end-to-end test of the dual-gated chain (no images, no KLayout GUI).

Builds rectangular flakes (top-top hBN, top graphite, top hBN, graphene, bottom hBN, bottom
graphite) on the chip template given by --template, then runs make_prepared -> build_device -> route_offline ->
post_route -> etch_mask -> verify -> export_writes with params_synthetic.json. Exit 0 if every step passes.

Usage: python selftest.py --template <chip template GDS> [--out <dir>] [--params <json>]   (instrMCPdev python)
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
TG_RECIPE = os.path.join(HERE, "..", "topgated_hallbar")
ap = argparse.ArgumentParser()
ap.add_argument("--template", required=True, help="chip template GDS (kept out of git)")
ap.add_argument("--out", default=None, help="output dir (default: a new temp dir)")
ap.add_argument("--params", default=os.path.join(HERE, "params_synthetic.json"))
a = ap.parse_args()
a.out = a.out or tempfile.mkdtemp(prefix="dualgate_selftest_")
os.makedirs(a.out, exist_ok=True)
print("output:", a.out)
O = lambda f: os.path.join(a.out, f)

# flakes as GDS-um rectangles relative to (2500, 2550); "pixels" = um so the px->GDS warp is a shift
rects = {
    "top_top_hBN": [-15, -13, 15, 28], "top_graphite": [-12, -11, 12, 26], "top_hBN": [-28, -16, 28, 35],
    "graphene": [-10, -13, 10, 15], "bottom_hBN": [-25, -17, 25, 32], "graphite": [-3.4, -20, 3.4, 22],
}
mats = {}
for i, (m, (x1, y1, x2, y2)) in enumerate(rects.items()):
    pts = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
    mats[m] = [dict(id=i + 1, contour_px=pts, contour_um=pts, area_um2=(x2 - x1) * (y2 - y1), num_points=4)]
json.dump(dict(materials=mats), open(O("traces.json"), "w"))
np.save(O("gds_warp_px.npy"), np.array([[1.0, 0, 2500.0], [0, 1.0, 2550.0]]))

PY = sys.executable
P = a.params
steps = [
    ("make_prepared", [os.path.join(TG_RECIPE, "make_prepared.py"), "--template", a.template,
                       "--traces", O("traces.json"), "--warp-px", O("gds_warp_px.npy"), "--out", O("prepared.gds")]),
    ("build_device", [os.path.join(HERE, "build_device.py"), "--in", O("prepared.gds"), "--params", P, "--out", O("device.gds"), "--record", O("design.json")]),
    ("route_offline", [os.path.join(HERE, "route_offline.py"), "--in", O("device.gds"), "--params", P, "--out", O("routed.gds")]),
    ("post_route", [os.path.join(HERE, "post_route.py"), "--in", O("routed.gds"), "--params", P, "--record", O("design.json"), "--out", O("post.gds")]),
    ("etch_mask", [os.path.join(HERE, "etch_mask.py"), "--in", O("post.gds"), "--params", P, "--out", O("result.gds")]),
    ("verify", [os.path.join(HERE, "verify.py"), "--gds", O("result.gds"), "--params", P, "--record", O("design.json"), "--out", O("verify.json")]),
    ("export_writes", [os.path.join(HERE, "export_writes.py"), "--in", O("result.gds"), "--params", P, "--out", O("writes.gds")]),
]
for name, cmd in steps:
    r = subprocess.run([PY] + cmd, capture_output=True, text=True)
    print("=== %s (exit %d)" % (name, r.returncode))
    print(r.stdout[-6000:] + r.stderr[-3000:])
    if r.returncode != 0:
        sys.exit("selftest FAILED at %s" % name)
print("selftest PASSED")
