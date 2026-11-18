"""Shared helpers for stack.json (klayoutclaw.stack/0.1)."""
import json
import os

import cv2
import numpy as np


def load_stack(path):
    s = json.load(open(path))
    if s.get("format") != "klayoutclaw.stack/0.1":
        raise SystemExit("%s: unsupported format %r" % (path, s.get("format")))
    s["_dir"] = os.path.dirname(os.path.abspath(path))
    return s


def catalog_mask(gds_path, layer, shape_hw):
    """Rasterise a flake_catalog GDS layer into an image-px mask.

    Catalog GDS = whole image in um, origin bottom-left, y up; layer 0/0 is the image frame.
    """
    import klayout.db as db
    ly = db.Layout(); ly.read(gds_path)
    top = ly.top_cells()[0]
    H, W = shape_hw
    frame = db.Region(top.begin_shapes_rec(ly.layer(0, 0))).bbox()
    w_um = frame.width() * ly.dbu if not frame.empty() else None
    h_um = frame.height() * ly.dbu if not frame.empty() else None
    if not w_um:
        raise SystemExit("%s has no 0/0 image frame" % gds_path)
    ps = w_um / W
    m = np.zeros((H, W), np.uint8)
    for p in db.Region(top.begin_shapes_rec(ly.layer(*layer))).merged().each():
        hull = np.array([[q.x * ly.dbu / ps, (h_um - q.y * ly.dbu) / ps] for q in p.each_point_hull()])
        cv2.fillPoly(m, [np.round(hull).astype(np.int32)], 255)
        for hi in range(p.holes()):
            hole = np.array([[q.x * ly.dbu / ps, (h_um - q.y * ly.dbu) / ps] for q in p.each_point_hole(hi)])
            cv2.fillPoly(m, [np.round(hole).astype(np.int32)], 0)
    return m


def apply(M, pts):
    M = np.asarray(M, float)
    return np.asarray(pts, float) @ M[:, :2].T + M[:, 2]


def compose(A, B):
    """A o B for 2x3 affines (apply B first)."""
    A3 = np.vstack([np.asarray(A, float), [0, 0, 1]])
    B3 = np.vstack([np.asarray(B, float), [0, 0, 1]])
    return (A3 @ B3)[:2]


def similarity(rot_deg, scale, tx, ty, cx=0.0, cy=0.0):
    """Rotate+scale about (cx, cy) then translate by (tx, ty); y-down image convention."""
    t = np.radians(rot_deg)
    c, s = np.cos(t) * scale, np.sin(t) * scale
    return np.array([[c, -s, cx - c * cx + s * cy + tx], [s, c, cy - s * cx - c * cy + ty]])
