"""Step 4: write data/traces.json (every flake as contours in photo px) and data/prepared.gds (template +
flakes in chip coordinates, through the marker alignment) with make_prepared.py. Renders all layers on
the photo to work/prepare/all.png for review.

Usage: python prepared.py --params <device>/klayoutclaw/data/params.json
Layers (make_prepared.py): top_top_hBN 16/0, top_graphite 14/0, top_hBN 10/0, graphene 11/0 (union of the
pieces 11/1, 11/2, ...), bottom_hBN 12/0, graphite (bottom graphite) 13/0. Template layers (datatype 0)
that collide with a flake or design layer (2, 4, 5, 7, 10-14, 16) move to 100 + n, e.g. 4/0 -> 104/0, so
nanodevice_topgate can start result.gds as a copy of prepared.gds.
"""
import json
import subprocess
import sys

import cv2
import numpy as np

from prep_lib import ROOT, TRACE_NAMES, Prep, args, contours, record, source_mask, warp

# template layers that would collide with a flake layer or a design layer of the six-piece chain move to 100 + n
REMAP = ",".join("%d:%d" % (n, 100 + n) for n in (2, 4, 5, 7, 10, 11, 12, 13, 14, 16))

a = args(__doc__)
p = Prep(a)
im = p.photo()
H, W = im.shape[:2]
mats, layer_map, areas = {}, {}, {}
for role in p.c["flakes"]:
    if role not in TRACE_NAMES:
        sys.exit("unknown flake role %s (one of %s)" % (role, ", ".join(TRACE_NAMES)))
    f = p.load(role)
    if "polygon_px" in f:
        mats[role] = [{"contour_px": f["polygon_px"]}]
    else:
        m = warp(source_mask(p, p.c["flakes"][role], (H, W)), f["best"]["M"], (H, W))
        mats[role] = [{"contour_px": c} for c in contours(m)]
g = p.load("graphene")
union = np.zeros((H, W), np.uint8)
for k, q in enumerate(g["pieces_px"], 1):
    mats["graphene_%d" % k] = [{"contour_px": q}]
    layer_map["graphene_%d" % k] = "11/%d" % k
    cv2.fillPoly(union, [np.round(np.array(q)).astype(np.int32)], 255)
mats["graphene"] = [{"contour_px": c} for c in contours(union, eps=1.0)]
(p.data / "traces.json").write_text(json.dumps({"frame": "full-stack photo px", "materials": mats, "layer_map": layer_map}))

r = subprocess.run([sys.executable, str(ROOT / "tests_resources" / "recipes" / "topgated_hallbar" / "make_prepared.py"),
                    "--template", str(p.path(p.c["template"])), "--traces", str(p.data / "traces.json"),
                    "--warp-px", str(p.data / "gds_warp_px.npy"), "--out", str(p.data / "prepared.gds"),
                    "--remap", REMAP],
                   capture_output=True, text=True)
if r.returncode:
    sys.exit("make_prepared.py failed:\n" + r.stderr[-2000:])
res = json.loads(r.stdout.strip().splitlines()[-1])
print("prepared.gds: %s" % ", ".join("%s %.1f um2" % kv for kv in res["flake_areas_um2"].items()))

COL = {"top_top_hBN": (255, 255, 0), "top_graphite": (255, 0, 255), "top_hBN": (0, 255, 255), "bottom_hBN": (0, 200, 0),
       "graphite": (0, 128, 255)}
ov = im.copy()
for role, entries in mats.items():
    for e in entries:
        cv2.polylines(ov, [np.round(np.array(e["contour_px"])).astype(np.int32)], True,
                      COL.get(role, (0, 0, 255)) if role != "graphene" else (255, 255, 255), 3)
x0, y0, x1, y1 = p.c.get("region_px", (0, 0, W, H))
cv2.imwrite(str(p.work / "all.png"), ov[y0:y1, x0:x1])
record(p.params, "prepare/prepared", flake_areas_um2=res["flake_areas_um2"], template_layers_moved=res["remapped"])
print("review: %s (all layers on the photo; graphene union in white)" % (p.work / "all.png"))
