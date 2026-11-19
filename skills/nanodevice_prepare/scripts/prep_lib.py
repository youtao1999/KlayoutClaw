"""Shared helpers for nanodevice_prepare: the params "prepare" block, the full-stack photo, flake masks and
the rigid edge fit. Coordinates: photo px (x right, y down) unless stated."""
import argparse
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]                                  # KlayoutClaw checkout
sys.path.insert(0, str(ROOT / "skills" / "nanodevice_stack" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "nanodevice_topgate" / "scripts"))
from place_stack import edge_dist, outline_pts, refine, sweep  # noqa: E402
from stack_io import catalog_mask  # noqa: E402
from tg_lib import record  # noqa: E402,F401

TRACE_NAMES = ("top_top_hBN", "top_graphite", "top_hBN", "bottom_hBN", "graphite")   # make_prepared.py material keys


def args(doc):
    ap = argparse.ArgumentParser(description=doc)
    ap.add_argument("--params", required=True, help="<device>/klayoutclaw/data/params.json")
    ap.add_argument("--device", help="device folder (default: two levels above params.json's folder)")
    return ap.parse_args()


class Prep:
    """The "prepare" block of params.json, with paths resolved against the device folder."""

    def __init__(self, a):
        self.params = Path(a.params).resolve()
        self.P = json.loads(self.params.read_text())
        self.c = self.P["prepare"]
        self.dev = Path(a.device).resolve() if a.device else self.params.parents[2]
        self.data = self.params.parent                   # run records next to params.json
        self.out = self.data / "prepare"
        self.work = self.data.parent / "work" / "prepare"  # review renders (scratch)
        self.out.mkdir(exist_ok=True)
        self.work.mkdir(parents=True, exist_ok=True)

    def path(self, rel):
        return self.dev / rel

    def photo(self):
        im = cv2.imread(str(self.path(self.c["photo"])))
        if im is None:
            sys.exit("cannot read the full-stack photo %s" % self.path(self.c["photo"]))
        return im

    def save(self, name, obj):
        tmp = self.out / (name + ".json.part")
        tmp.write_text(json.dumps(obj, indent=1))
        os.replace(tmp, self.out / (name + ".json"))

    def load(self, name):
        p = self.out / (name + ".json")
        if not p.exists():
            sys.exit("%s missing: run the earlier nanodevice_prepare step first" % p)
        return json.loads(p.read_text())


def source_mask(prep, spec, shape_hw):
    """Binary mask (0/255) of a flake in its own picture's px: a catalog GDS layer ({"gds", "layer"}),
    the opaque part of a picture ({"image"}, largest piece), or None for {"polygon_px"} (already in photo px)."""
    if "gds" in spec:
        return catalog_mask(str(prep.path(spec["gds"])), tuple(spec.get("layer", [20, 0])), tuple(spec.get("image_hw", shape_hw)))
    if "image" in spec:
        im = cv2.imread(str(prep.path(spec["image"])), cv2.IMREAD_UNCHANGED)
        if im is None or im.ndim < 3 or im.shape[2] < 4:
            sys.exit("%s: needs a picture with transparent background (alpha)" % spec["image"])
        m = (im[..., 3] > 128).astype(np.uint8)
        n, lab, st, _ = cv2.connectedComponentsWithStats(m)
        return ((lab == 1 + np.argmax(st[1:, 4])) * 255).astype(np.uint8)
    return None


def warp(mask, M, shape_hw):
    return cv2.warpAffine(mask, np.asarray(M, float), (shape_hw[1], shape_hw[0]), flags=cv2.INTER_NEAREST)


def fit(dt, mask, region, scale=1.0, rot_range=None):
    """Rigid fit of mask's outline to the photo edges over all rotations (or rot_range). Returns the best
    fit and the best fit at least 90 deg away from it (the 180 deg alternative a near-symmetric flake has)."""
    pts = outline_pts(mask, step=3)
    lo, hi = rot_range or (0.0, 360.0)
    cands = []
    for q in np.arange(lo, hi, 45.0):                    # best fit per 45 deg window, then refined
        T0, r0, sc = sweep(dt, pts, np.arange(q, min(q + 45.0, hi), 1.0), scale, region=region)
        T, x, c = refine(dt, pts, T0, 3.0, 60)
        cands.append(dict(M=T.tolist(), rot_deg=float(np.degrees(np.arctan2(T[1][0], T[0][0]))), cost_px=float(c)))
    cands.sort(key=lambda z: z["cost_px"])
    best = cands[0]
    far = [z for z in cands[1:] if abs(((z["rot_deg"] - best["rot_deg"]) + 180) % 360 - 180) >= 90]
    return best, (far[0] if far else None)


def contours(mask, eps=1.5, min_area=400):
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    return [cv2.approxPolyDP(c, eps, True).reshape(-1, 2).astype(float).tolist() for c in cs if cv2.contourArea(c) > min_area]
