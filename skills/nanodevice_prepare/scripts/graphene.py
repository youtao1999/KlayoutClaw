"""Step 3: place the graphene pieces, which no photo shows, from the stack plan (design.gds of
stack_design's blueprint). The plan's last step cell is mapped onto the photo by fitting its outline of
the flake that picked the graphene up (default the top hBN) to that flake's fit from fit.py (rigid,
all rotations, IoU). Only that flake places the graphene: other flakes may have been stacked
differently from the plan. Their plan-vs-fit overlap is reported for information; a low value means the
stack deviated from the plan there (see the device's deviation note) or that fit is wrong.

Usage: python graphene.py --params <device>/klayoutclaw/data/params.json
prepare.graphene: {"design": "design.gds", "cell": "<optional; default the last S<n>_ step cell>",
  "picked_by": "top_hBN", "picked_by_layer": [40, 0], "pieces_layer": [2, 0], "compare": {"bottom_hBN": [50, 0]}}
The pieces are clipped to the flake that picked them up; the plan's pixel size is PLAN_UM_PER_PX.
Writes data/prepare/graphene.json (pieces and active region in photo px) and work/prepare/graphene.png.
"""
import re
import sys

import cv2
import klayout.db as db
import numpy as np
from scipy.optimize import minimize

from prep_lib import Prep, args, record, source_mask, warp

PLAN_UM_PER_PX = 0.06173                       # catalog / stack-plan pixel size

a = args(__doc__)
p = Prep(a)
g = p.c["graphene"]
im = p.photo()
H, W = im.shape[:2]
ly = db.Layout()
ly.read(str(p.path(g["design"])))
steps = [c for c in ly.each_cell() if re.match(r"S\d+_", c.name)]
cell = next((c for c in ly.each_cell() if c.name == g["cell"]), None) if g.get("cell") else \
    max(steps, key=lambda c: int(c.name[1:].split("_")[0]), default=None)
if cell is None:
    sys.exit("design.gds has no step cell %s" % (g.get("cell") or "S<n>_..."))


def polys(spec, merge=True):
    r = db.Region(cell.begin_shapes_rec(ly.layer(*spec)))
    return [np.array([[q.x * ly.dbu, q.y * ly.dbu] for q in poly.each_point_hull()]) for poly in (r.merged() if merge else r).each()]


def T_of(x):            # plan um (y up) -> photo px (y down): rotation x[0] deg, translation x[1:3]
    t, s = np.radians(x[0]), 1.0 / PLAN_UM_PER_PX
    return np.c_[s * np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]]) @ np.diag([1, -1]), x[1:3]]


def raster(ps, T):
    m = np.zeros((H, W), np.uint8)
    for q in ps:
        cv2.fillPoly(m, [np.round(q @ T[:, :2].T + T[:, 2]).astype(np.int32)], 1)
    return m


iou = lambda u, v: (u & v).sum() / max((u | v).sum(), 1)


def fitted(role):
    f = p.load(role)
    if "polygon_px" in f:
        m = np.zeros((H, W), np.uint8)
        cv2.fillPoly(m, [np.round(np.array(f["polygon_px"])).astype(np.int32)], 1)
        return m
    return (warp(source_mask(p, p.c["flakes"][role], (H, W)), f["best"]["M"], (H, W)) > 0).astype(np.uint8)


def frame(plan, target):
    c_t = np.argwhere(target)[:, ::-1].mean(0)
    c_s = np.vstack(plan).mean(0)
    start = lambda th: [th, *(c_t - T_of([th, 0, 0])[:, :2] @ c_s)]
    th0 = max(range(0, 360, 2), key=lambda th: iou(raster(plan, T_of(start(th))), target))
    x0 = start(th0)
    r = minimize(lambda x: -iou(raster(plan, T_of(x)), target), x0, method="Nelder-Mead",
                 options=dict(initial_simplex=[x0, np.add(x0, [2, 0, 0]), np.add(x0, [0, 20, 0]), np.add(x0, [0, 0, 20])],
                              xatol=0.01, fatol=1e-5, maxiter=2000))
    return T_of(r.x), float(r.x[0] % 360), float(-r.fun)


anchor = g.get("picked_by", "top_hBN")
amask = fitted(anchor)
T, theta, a_iou = frame(polys(tuple(g.get("picked_by_layer", [40, 0]))), amask)
px = lambda ps: [(q @ T[:, :2].T + T[:, 2]).tolist() for q in ps]
pieces = px(polys(tuple(g.get("pieces_layer", [2, 0])), merge=False))   # insertion order = piece 1, 2, ...
clipped = []                                           # graphene stays inside the flake that picked it up
for q in pieces:
    m = np.zeros((H, W), np.uint8)
    cv2.fillPoly(m, [np.round(np.array(q)).astype(np.int32)], 1)
    cs, _ = cv2.findContours((m & amask) * 255, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    clipped.append(cv2.approxPolyDP(max(cs, key=cv2.contourArea), 1.0, True).reshape(-1, 2).astype(float).tolist())
pieces = clipped
act = np.ones((H, W), np.uint8)
for q in pieces:
    m = np.zeros((H, W), np.uint8)
    cv2.fillPoly(m, [np.round(np.array(q)).astype(np.int32)], 1)
    act &= m
um_px = abs(np.linalg.det(np.load(p.data / "gds_warp_px.npy")[:, :2])) if (p.data / "gds_warp_px.npy").exists() else PLAN_UM_PER_PX ** 2
compare = {}
for role, spec in g.get("compare", {}).items():
    if role in p.c["flakes"]:
        compare[role] = round(iou(raster(polys(tuple(spec)), T), fitted(role)), 3)
print("plan cell %s mapped by %s: rotation %.1f deg, IoU %.3f" % (cell.name, anchor, theta, a_iou))
print("graphene pieces %d, active region %.1f um2" % (len(pieces), act.sum() * um_px))
for role, v in compare.items():
    print("plan %s vs its fit: IoU %.3f%s" % (role, v, "" if v >= 0.8 else
          "  <- the stack deviated from the plan here (deviation note?) or that fit is wrong; the graphene does not use it"))
p.save("graphene", dict(cell=cell.name, picked_by=anchor, T_plan_um_to_px=T.tolist(), rotation_deg=theta,
                        picked_by_iou=a_iou, pieces_px=pieces, compare_iou=compare))
ov = im.copy()
for q in pieces:
    cv2.polylines(ov, [np.round(np.array(q)).astype(np.int32)], True, (0, 0, 255), 3)
cs, _ = cv2.findContours(act * 255, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
cv2.drawContours(ov, cs, -1, (255, 255, 255), 3)
x0, y0, x1, y1 = p.c.get("region_px", (0, 0, W, H))
cv2.imwrite(str(p.work / "graphene.png"), ov[y0:y1, x0:x1])
record(p.params, "prepare/graphene", cell=cell.name, picked_by=anchor, rotation_deg=round(theta, 3),
       picked_by_iou=round(a_iou, 4), pieces=len(pieces), active_um2=round(float(act.sum() * um_px), 2), compare_iou=compare)
if a_iou < 0.9:
    print("WARNING: the plan's %s matches its fit with IoU %.3f only: check fit_%s.png" % (anchor, a_iou, anchor))
