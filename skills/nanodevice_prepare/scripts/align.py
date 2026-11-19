"""Step 1: align the full-stack photo to the chip template's fine markers (fine_marker_align.py), gate the
result, and render every marker site with the template squares on it (work/prepare/markers.png).

Usage: python align.py --params <device>/klayoutclaw/data/params.json
Uses prepare.photo, .template, .field_center_um, .rotation_hint_deg (0 or 180), .um_per_px (nominal),
.marker_layer ([19, 0]), .marker_pitch_um (50). Writes data/gds_warp_px.npy (photo px -> GDS um),
data/gds_warp.npy, data/gds_alignment_report.json.
"""
import json
import shutil
import subprocess
import sys

import cv2
import gdstk
import numpy as np

from prep_lib import ROOT, Prep, args, record

a = args(__doc__)
p = Prep(a)
c = p.c
ps = c["um_per_px"]
tmp = p.work / "align"
cmd = [sys.executable, str(ROOT / "tests_resources" / "recipes" / "topgated_hallbar" / "fine_marker_align.py"),
       "--image", str(p.path(c["photo"])), "--template", str(p.path(c["template"])), "--ps", str(ps),
       "--field", *map(str, c["field_center_um"]), "--rot-hint", str(c.get("rotation_hint_deg", 0)),
       "--layer", *map(str, c.get("marker_layer", [19, 0])), "--pitch", str(c.get("marker_pitch_um", 50)),
       "--out", str(tmp)]
r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode:
    sys.exit("fine_marker_align.py failed:\n" + r.stderr[-2000:])
rep = json.loads((tmp / "gds_alignment_report.json").read_text())
q, lat = rep["quality"], rep["lattice_offset_check"]
bad = [m for m, ok in [("fewer than 4 inlier marker sites", q["inliers"] >= 4),
                       ("mean residual >= 0.3 um", q["mean_residual_um"] < 0.3),
                       ("pixel size more than 2 % from nominal", abs(rep["pixel_size_measured_um"] / ps - 1) <= 0.02)] if not ok]
print("alignment: %d/%d sites, mean residual %.3f um, pixel %.5f um (nominal %.5f), rotation %.3f deg, "
      "site pattern match %.2f (runner-up %.2f)" % (q["inliers"], q["n_sites_in_fov"], q["mean_residual_um"],
      rep["pixel_size_measured_um"], ps, rep["transform"]["rotation_deg"], lat["mean_response"], lat["runner_up"]["mean_response"]))
for f in ("gds_warp_px.npy", "gds_warp.npy", "gds_alignment_report.json"):
    shutil.copy2(tmp / f, p.data / f)

# review render: every marker site in view, template squares drawn on the photo
M = np.load(p.data / "gds_warp_px.npy")
Mi = np.linalg.inv(np.vstack([M, [0, 0, 1]]))[:2]
im = p.photo()
lay = tuple(c.get("marker_layer", [19, 0]))
for poly in gdstk.read_gds(str(p.path(c["template"]))).top_level()[0].get_polygons():
    if (poly.layer, poly.datatype) == lay:
        px = np.c_[poly.points, np.ones(len(poly.points))] @ Mi.T
        cv2.polylines(im, [np.round(px).astype(np.int32)], True, (0, 255, 0), 1)
h = 70
tiles = [cv2.resize(im[int(y) - h:int(y) + h, int(x) - h:int(x) + h], (2 * h * 2, 2 * h * 2), interpolation=cv2.INTER_NEAREST)
         for x, y in (s["img_px"] for s in rep["sites"]) if h <= x < im.shape[1] - h and h <= y < im.shape[0] - h]
if tiles:
    n = int(np.ceil(np.sqrt(len(tiles))))
    tiles += [np.zeros_like(tiles[0])] * (n * n - len(tiles))
    cv2.imwrite(str(p.work / "markers.png"), np.vstack([np.hstack(tiles[k * n:(k + 1) * n]) for k in range(n)]))
record(p.params, "prepare/align", inliers=q["inliers"], sites=q["n_sites_in_fov"], mean_residual_um=q["mean_residual_um"],
       um_per_px=rep["pixel_size_measured_um"], rotation_deg=rep["transform"]["rotation_deg"],
       site_pattern_match=[lat["mean_response"], lat["runner_up"]["mean_response"]], passed=not bad)
if bad:
    sys.exit("alignment failed: " + "; ".join(bad) + " (check work/prepare/markers.png, the field and rotation_hint_deg)")
print("review: %s (template squares in green on every marker site)" % (p.work / "markers.png"))
