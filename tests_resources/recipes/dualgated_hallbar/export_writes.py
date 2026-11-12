"""Step W: one GDS layer per EBL write, for review and for the writer.

Input : result.gds (all design layers) + params. Output: writes.gds with layer k/0 = everything exposed
in EBL write k (solid = exposed), each merged, top cell only; plus writes.lyp (KLayout layer names).
Nothing else: no flakes, no template, no scratch layers.

Optional photo overlay (--image + --warp-px): GDS cannot hold a bitmap, so the aligned microscope image is
embedded as polygons: resampled to --photo-px um, colour-quantised to --photo-colors colours, one datatype
per colour on --photo-layer (default 100/0..). writes.lyp groups them as "50x photo", drawn under the
writes. NOT for exposure: send only layers 1..N (the writes) to the EBL.

Writes come from params "ebl_writes" (list of {"name", "layers": [design layer keys]}); default is the
dual-gated process:
  1 step1_topgate_etch : L31            (CHF3 top-top hBN, O2 top graphite)
  2 step2_metal        : L22+L23+L24+L2 (CHF3 top hBN, evaporate)
  3 step3_final_etch   : L20            (fingers / graphene shaping)

Usage: python export_writes.py --in result.gds --params params.json --out writes.gds \
           [--image full_stack_raw.png --warp-px gds_warp_px.npy --photo-px 0.25 --photo-colors 16]
"""
import argparse
import json
import os
import sys

import klayout.db as db
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "topgated_hallbar"))
from recipe_lib import Design, load_params  # noqa: E402

DEFAULT = [
    {"name": "step1_topgate_etch", "layers": ["tg_etch"]},
    {"name": "step2_metal", "layers": ["graphite_contact", "electrodes", "tg_contact", "pads"]},
    {"name": "step3_final_etch", "layers": ["etch"]},
]
COLORS = ["#ff8000", "#e0b000", "#ff3030", "#30a0ff", "#30c060"]

ap = argparse.ArgumentParser()
ap.add_argument("--in", dest="inp", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--image", help="microscope image to embed as a photo overlay")
ap.add_argument("--warp-px", help="2x3 affine: image px (col, row) -> GDS um (from fine_marker_align.py)")
ap.add_argument("--photo-px", type=float, default=0.25, help="photo resolution in um")
ap.add_argument("--photo-colors", type=int, default=16)
ap.add_argument("--photo-layer", type=int, default=100)
a = ap.parse_args()


def photo_regions(img_path, warp_path, px_um, ncol, dbu):
    """Aligned image -> [(rgb, Region)] one per quantised colour, darkest first."""
    import cv2
    img = cv2.imread(img_path)
    if img is None:
        sys.exit("cannot read image %s" % img_path)
    M = np.load(warp_path)
    s = float(np.sqrt(abs(np.linalg.det(M[:, :2]))))           # um per image px
    f = max(1, int(round(px_um / s)))
    H, Wd = img.shape[:2]
    small = cv2.resize(img, (Wd // f, H // f), interpolation=cv2.INTER_AREA)
    h, w = small.shape[:2]
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _, lab, cen = cv2.kmeans(small.reshape(-1, 3).astype(np.float32), ncol, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    lab = lab.reshape(h, w)
    order = np.argsort(cen @ np.array([0.114, 0.587, 0.299]))       # BGR luminance, dark -> bright
    # image px -> GDS: similarity, mirrored when det < 0 (ordinary y-down image -> y-up GDS)
    mir = np.linalg.det(M[:, :2]) < 0
    rot = np.degrees(np.arctan2(M[0, 1], M[0, 0])) if mir else np.degrees(np.arctan2(M[1, 0], M[0, 0]))
    T = db.ICplxTrans(s / 2 / dbu, rot, bool(mir), db.Vector(M[0, 2] / dbu, M[1, 2] / dbu))   # input unit: half px
    out = []
    for k in order:
        boxes = []
        m = (lab == k)
        for i in range(h):
            row = np.concatenate(([0], m[i].astype(np.int8), [0]))
            d = np.diff(row)
            for j0, j1 in zip(np.where(d == 1)[0].tolist(), np.where(d == -1)[0].tolist()):
                # small px (i, j) covers image px [j*f, (j+1)*f) x [i*f, (i+1)*f); pixel centres sit at integers
                boxes.append(db.Box(2 * j0 * f - 1, 2 * i * f - 1, 2 * j1 * f - 1, 2 * (i + 1) * f - 1))
        if boxes:
            r = db.Region(boxes).merged().transformed(T).merged()
            b, g, rr = (int(round(v)) for v in cen[k])
            out.append(((rr, g, b), r))
    return out, f * s

P = load_params(a.params)
D = Design(a.inp, P)
writes = P.get("ebl_writes", DEFAULT)

out = db.Layout()
out.dbu = D.dbu
top = out.create_cell(D.top.name)
report = []
for k, w in enumerate(writes, 1):
    r = db.Region()
    for key in w["layers"]:
        r += D.R(key)
    r = r.merged()
    if r.is_empty():
        sys.exit("write %d (%s) is empty - is %s the finished design?" % (k, w["name"], a.inp))
    top.shapes(out.layer(db.LayerInfo(k, 0, w["name"]))).insert(r)
    report.append(dict(layer="%d/0" % k, name=w["name"], from_layers=w["layers"],
                       polygons=r.count(), area_um2=round(r.area() * D.dbu * D.dbu, 1)))
photo = []
if a.image:
    if not a.warp_px:
        sys.exit("--image needs --warp-px")
    photo, eff = photo_regions(a.image, a.warp_px, a.photo_px, a.photo_colors, D.dbu)
    for d, (rgb, r) in enumerate(photo):
        top.shapes(out.layer(db.LayerInfo(a.photo_layer, d, "photo_%02d" % d))).insert(r)
    report.append(dict(layer="%d/0..%d" % (a.photo_layer, len(photo) - 1), name="50x photo (reference only, do not expose)",
                       image=os.path.basename(a.image), pixel_um=round(eff, 4), colours=len(photo),
                       polygons=sum(r.count() for _, r in photo)))
opt = db.SaveLayoutOptions()
opt.gds2_max_vertex_count = 4000          # keep every GDS record < 32 kB (other readers / EBL software)
out.write(a.out, opt)

lyp = ["<?xml version=\"1.0\" encoding=\"utf-8\"?>", "<layer-properties>"]
if photo:                                 # first in the list = painted first = underneath the writes
    lyp += [" <properties>", "  <name>50x photo (reference only)</name>", "  <expanded>false</expanded>"]
    for d, (rgb, _) in enumerate(photo):
        c = "#%02x%02x%02x" % rgb
        lyp += ["  <group-members>", "   <frame-color>%s</frame-color>" % c, "   <fill-color>%s</fill-color>" % c,
                "   <dither-pattern>I0</dither-pattern>", "   <visible>true</visible>", "   <width>0</width>",
                "   <name>photo_%02d</name>" % d, "   <source>%d/%d@1</source>" % (a.photo_layer, d), "  </group-members>"]
    lyp.append(" </properties>")
for k, w in enumerate(writes, 1):
    c = COLORS[(k - 1) % len(COLORS)]
    lyp += [" <properties>", "  <frame-color>%s</frame-color>" % c, "  <fill-color>%s</fill-color>" % c,
            "  <dither-pattern>I9</dither-pattern>", "  <visible>true</visible>", "  <width>1</width>",
            "  <name>%d %s</name>" % (k, w["name"]), "  <source>%d/0@1</source>" % k, " </properties>"]
lyp.append("</layer-properties>")
open(os.path.splitext(a.out)[0] + ".lyp", "w").write("\n".join(lyp) + "\n")
print(json.dumps(dict(out=a.out, writes=report), indent=1))
