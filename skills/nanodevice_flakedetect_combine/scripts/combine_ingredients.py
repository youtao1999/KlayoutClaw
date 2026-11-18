#!/usr/bin/env python
"""Combine per-ingredient detections (one image per flake) into full_stack traces.json.

For stacks imaged flake by flake (e.g. dual-gated devices: top-top hBN, top graphite, top hBN,
graphene, bottom hBN, bottom graphite), each material is detected in its own image and brought
into the full_stack frame with its own 2x3 warp (e.g. warp_top.npy from sweep.py + refine.py,
which handles arbitrary rotation). transform.py is hard-wired to bottom_part/top_part; this
script takes any number of materials, including the two extra ones:

  top_top_hBN   16/0   thin hBN used to pick up the top graphite
  top_graphite  14/0   top gate graphite
  (graphite 13/0 = bottom graphite; top_hBN 10/0, graphene 11/0, bottom_hBN 12/0 as usual)

Item syntax:  MATERIAL=MASK[:WARP[:inv]]
  MASK  binary mask PNG (non-zero = flake) or contour .npy, in the SOURCE image frame
  WARP  2x3 .npy mapping source px -> full_stack px; omit if MASK is already in full_stack px;
        add ':inv' if the matrix maps full_stack -> source (e.g. warp_sift_bottom.npy)

Usage:
    python combine_ingredients.py --image full_stack_raw.png --pixel-size 0.06162 \
        --item top_graphite=detect/top_graphite_mask.png:align/top_graphite/warp_top.npy \
        --item graphene=detect/graphene_mask.png:align/graphene/warp_top.npy \
        --item bottom_hBN=detect/bottom_hbn_mask.png \
        --output-dir combine/
Outputs: traces.json, <material>_full.png, overlay_raw.png
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "nanodevice_flakedetect", "scripts"))
from core import LAYER_MAP, flood_fill_holes, smooth_material  # noqa: E402

EXTRA_LAYERS = {"top_top_hBN": "16/0", "top_graphite": "14/0"}
LAYERS = {**LAYER_MAP, **EXTRA_LAYERS}
STACK = ["top_top_hBN", "top_graphite", "top_hBN", "graphene", "bottom_hBN", "graphite"]
SMOOTH_AS = {"top_top_hBN": "top_hBN", "top_graphite": "graphite"}
COLORS = {"top_top_hBN": (255, 255, 0), "top_graphite": (255, 0, 255), "top_hBN": (0, 255, 255),
          "graphene": (0, 0, 255), "bottom_hBN": (0, 255, 0), "graphite": (255, 0, 0)}


def parse_item(s):
    mat, _, rest = s.partition("=")
    if mat not in LAYERS:
        raise SystemExit("unknown material %r (known: %s)" % (mat, ", ".join(STACK)))
    parts = rest.split(":")
    if not parts[0]:
        raise SystemExit("item %r has no mask" % s)
    warp = parts[1] if len(parts) > 1 and parts[1] else None
    inv = len(parts) > 2 and parts[2] == "inv"
    return mat, parts[0], warp, inv


def load_mask(path, src_shape):
    if path.endswith(".npy"):
        cnt = np.load(path).reshape(-1, 1, 2).astype(np.int32)
        if src_shape is None:
            raise SystemExit("contour %s needs --source-size or a PNG mask" % path)
        m = np.zeros(src_shape, np.uint8)
        cv2.drawContours(m, [cnt], -1, 255, -1)
        return m
    m = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if m is None:
        raise SystemExit("cannot read mask %s" % path)
    return np.where(m > 0, 255, 0).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True, help="full_stack reference image")
    ap.add_argument("--pixel-size", type=float, required=True)
    ap.add_argument("--item", action="append", required=True)
    ap.add_argument("--source-size", help="WxH of source images for .npy contours")
    ap.add_argument("--min-area-px", type=int, default=500)
    ap.add_argument("--output-dir", required=True)
    a = ap.parse_args()
    os.makedirs(a.output_dir, exist_ok=True)

    img = cv2.imread(a.image)
    if img is None:
        raise SystemExit("cannot read %s" % a.image)
    h, w = img.shape[:2]
    src_shape = tuple(int(v) for v in a.source_size.split("x"))[::-1] if a.source_size else None

    masks, notes = {}, {}
    for s in a.item:
        mat, mpath, wpath, inv = parse_item(s)
        m = load_mask(mpath, src_shape or (h, w))
        if wpath:
            M = np.load(wpath).astype(np.float64)[:2]
            if inv:
                M = cv2.invertAffineTransform(M)
            m = cv2.warpAffine(m, M, (w, h), flags=cv2.INTER_NEAREST)
        if not m.any():
            raise SystemExit("%s mask is empty after warping (%s) - wrong warp or crop?" % (mat, wpath))
        m = flood_fill_holes(m)
        masks[mat] = np.maximum(masks.get(mat, 0), m).astype(np.uint8)
        notes[mat] = "%s via %s%s" % (mpath, wpath or "identity (already full_stack px)", " (inverted)" if inv else "")

    materials, gid = {}, 0
    overlay = img.copy()
    for mat in STACK:
        if mat not in masks:
            continue
        cv2.imwrite(os.path.join(a.output_dir, "%s_full.png" % mat), masks[mat])
        cnts, _ = cv2.findContours(masks[mat], cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        entries = []
        for c in cnts:
            if cv2.contourArea(c) < a.min_area_px:
                continue
            c = smooth_material(c, SMOOTH_AS.get(mat, mat))
            if len(c) < 3:
                continue
            gid += 1
            pts = c.reshape(-1, 2).tolist()
            entries.append(dict(id=gid, contour_px=pts,
                                contour_um=[[round(x * a.pixel_size, 3), round(y * a.pixel_size, 3)] for x, y in pts],
                                area_um2=round(cv2.contourArea(c) * a.pixel_size ** 2, 3), num_points=len(pts)))
            cv2.polylines(overlay, [c], True, COLORS[mat], 3)
        if not entries:
            raise SystemExit("%s has no contour >= %d px" % (mat, a.min_area_px))
        materials[mat] = entries

    present = [m for m in STACK if m in materials]
    traces = dict(image=os.path.abspath(a.image), pixel_size_um=a.pixel_size, image_size_px=[w, h],
                  image_size_um=[round(w * a.pixel_size, 3), round(h * a.pixel_size, 3)],
                  stack=present, layer_map={m: LAYERS[m] for m in present}, materials=materials, notes=notes)
    json.dump(traces, open(os.path.join(a.output_dir, "traces.json"), "w"), indent=1)
    cv2.imwrite(os.path.join(a.output_dir, "overlay_raw.png"), overlay)
    print(json.dumps({m: dict(n=len(materials[m]), area_um2=[e["area_um2"] for e in materials[m]]) for m in present}, indent=1))


if __name__ == "__main__":
    main()
