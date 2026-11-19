"""Step 2: place every visible flake in the full-stack photo: a rigid fit (scale 1 by default: same camera)
of its outline to the photo's edges over ALL rotations. Never limit the rotation by the plan: stacks
deviate from it (a flake can be dropped turned 180 deg). The best fit at least 90 deg away is reported
too; when its cost is within --ambiguous of the best, the script stops with exit code 3 and the operator
decides (pin the rotation with "rot_range" in that flake's entry).

Usage: python fit.py --params <device>/klayoutclaw/data/params.json [--ambiguous 0.15]
prepare.flakes: {role: {"gds": "ingredients/BN001a.gds", "layer": [20, 0]} | {"image": "<alpha png>"} |
                 {"polygon_px": [[x, y], ...]}, optional "scale", "rot_range": [lo, hi]}
prepare.region_px: [x0, y0, x1, y1], where the stack lies in the photo (default: whole photo).
Writes data/prepare/<role>.json (M: flake px -> photo px) and work/prepare/fit_<role>.png.
"""
import argparse
import sys

import cv2
import numpy as np

from prep_lib import Prep, edge_dist, fit, record, source_mask, warp

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--params", required=True)
ap.add_argument("--device")
ap.add_argument("--ambiguous", type=float, default=0.15, help="warn when the alternative's cost is within this fraction of the best")
a = ap.parse_args()
p = Prep(a)
im = p.photo()
H, W = im.shape[:2]
region = tuple(p.c.get("region_px", (0, 0, W, H)))
dt, _ = edge_dist(im, 25.0)
summary, warn = {}, []
for role, spec in p.c["flakes"].items():
    if "polygon_px" in spec:                           # traced in the photo already
        p.save(role, dict(role=role, polygon_px=spec["polygon_px"], source="polygon_px"))
        summary[role] = "traced in the photo"
        print("%-13s traced in the photo (%d points)" % (role, len(spec["polygon_px"])))
        continue
    mask = source_mask(p, spec, (H, W))
    best, alt = fit(dt, mask, region, spec.get("scale", 1.0), spec.get("rot_range"))
    p.save(role, dict(role=role, source={k: v for k, v in spec.items()}, best=best, alternative=alt))
    amb = alt is not None and alt["cost_px"] <= best["cost_px"] * (1 + a.ambiguous)
    line = "%-13s rot %7.2f deg, edge cost %.2f px" % (role, best["rot_deg"], best["cost_px"])
    if alt:
        line += "; next best %.1f deg away: rot %7.2f, cost %.2f px" % (
            abs(((alt["rot_deg"] - best["rot_deg"]) + 180) % 360 - 180), alt["rot_deg"], alt["cost_px"])
    print(line + ("  <- AMBIGUOUS" if amb else ""))
    if amb:
        warn.append(role)
    summary[role] = dict(rot_deg=round(best["rot_deg"], 3), cost_px=round(best["cost_px"], 3),
                         alternative=None if not alt else [round(alt["rot_deg"], 3), round(alt["cost_px"], 3)], ambiguous=amb)
    ov = im.copy()
    for M, col in ([(alt["M"], (255, 0, 255))] if alt else []) + [(best["M"], (0, 255, 0))]:
        cs, _ = cv2.findContours(warp(mask, M, (H, W)), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(ov, cs, -1, col, 3)
    x0, y0, x1, y1 = region
    cv2.imwrite(str(p.work / ("fit_%s.png" % role)), ov[y0:y1, x0:x1])
record(p.params, "prepare/fit", flakes=summary)
print("review: %s/fit_<role>.png (best fit green, alternative magenta)" % p.work)
if warn:
    print("ambiguous rotation for %s: compare the two fits, ask the operator, then pin \"rot_range\"" % ", ".join(warn))
    sys.exit(3)
