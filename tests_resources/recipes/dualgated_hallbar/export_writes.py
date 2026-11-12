"""Step W: one GDS layer per EBL write, for review and for the writer.

Input : result.gds (all design layers) + params. Output: writes.gds with layer k/0 = everything exposed
in EBL write k (solid = exposed), each merged, top cell only; plus writes.lyp (KLayout layer names).
Nothing else: no flakes, no template, no scratch layers.

Optional photo overlay (--image + --warp-px): the microscope image saved as a KLayout image file (.lyimg:
pixels + placement) using the fine-marker alignment, so the template markers in the photo sit on the GDS
markers. Load it in KLayout over writes.gds / result.gds (File > Add Image..., choose the .lyimg).

Writes come from params "ebl_writes" (list of {"name", "layers": [design layer keys]}); default is the
dual-gated process:
  1 step1_topgate_etch : L31            (CHF3 top-top hBN, O2 top graphite)
  2 step2_metal        : L22+L23+L24+L2 (CHF3 top hBN, evaporate)
  3 step3_final_etch   : L20            (fingers / graphene shaping)

Usage: python export_writes.py --in result.gds --params params.json --out writes.gds \
           [--image full_stack_raw.png --warp-px gds_warp_px.npy [--image-out overlay.lyimg]]
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
ap.add_argument("--image", help="microscope image to save as a KLayout .lyimg overlay")
ap.add_argument("--warp-px", help="2x3 affine: image px (col, row) -> GDS um (from fine_marker_align.py)")
ap.add_argument("--image-out", help="overlay path (default: <out dir>/<image name>.lyimg)")
a = ap.parse_args()


def write_lyimg(img_path, warp_path, out_path):
    """Save img_path as a KLayout image file (.lyimg) placed by the marker alignment warp.

    warp: GDS um = M @ [col, row, 1] with pixel centres at integer (col, row) (fine_marker_align.py).
    KLayout image coordinates: origin at the image centre, y up, pixel (col, row) centre at
    (col + 0.5 - W/2, H/2 - row - 0.5)  (checked by rendering a one-pixel probe)."""
    import klayout.lay as lay
    M = np.load(warp_path)
    img = lay.Image(img_path)
    W, H = img.width(), img.height()
    A, t = M[:, :2], M[:, 2]
    Ai = A @ np.diag([1.0, -1.0])                      # image y up -> row down
    ti = A @ np.array([W / 2 - 0.5, H / 2 - 0.5]) + t
    img.matrix = db.Matrix3d(Ai[0, 0], Ai[0, 1], ti[0], Ai[1, 0], Ai[1, 1], ti[1], 0.0, 0.0, 1.0)
    img.write(out_path)
    chk = lay.Image.read(out_path)                     # round trip: pixel (0, 0) and (W-1, H-1) land where the warp says
    m = chk.matrix
    for col, row in ((0, 0), (W - 1, H - 1)):
        p = m.trans(db.DPoint(col + 0.5 - W / 2, H / 2 - row - 0.5))
        q = M @ np.array([col, row, 1.0])
        assert abs(p.x - q[0]) < 1e-6 and abs(p.y - q[1]) < 1e-6, ("lyimg placement mismatch", p, q)
    return dict(lyimg=out_path, image=os.path.basename(img_path), size_px=[W, H],
                um_per_px=round(float(np.sqrt(abs(np.linalg.det(A)))), 5),
                corners_gds_um=[[round(float(v), 2) for v in M @ np.array([c, r, 1.0])] for c, r in ((0, 0), (W - 1, H - 1))])


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
opt = db.SaveLayoutOptions()
opt.gds2_max_vertex_count = 4000          # keep every GDS record < 32 kB (other readers / EBL software)
out.write(a.out, opt)

lyp = ["<?xml version=\"1.0\" encoding=\"utf-8\"?>", "<layer-properties>"]
for k, w in enumerate(writes, 1):
    c = COLORS[(k - 1) % len(COLORS)]
    lyp += [" <properties>", "  <frame-color>%s</frame-color>" % c, "  <fill-color>%s</fill-color>" % c,
            "  <dither-pattern>I9</dither-pattern>", "  <visible>true</visible>", "  <width>1</width>",
            "  <name>%d %s</name>" % (k, w["name"]), "  <source>%d/0@1</source>" % k, " </properties>"]
lyp.append("</layer-properties>")
open(os.path.splitext(a.out)[0] + ".lyp", "w").write("\n".join(lyp) + "\n")
res = dict(out=a.out, writes=report)
if a.image:
    if not a.warp_px:
        sys.exit("--image needs --warp-px")
    res["overlay"] = write_lyimg(a.image, a.warp_px, a.image_out or os.path.join(
        os.path.dirname(os.path.abspath(a.out)), os.path.splitext(os.path.basename(a.image))[0] + ".lyimg"))
    rep = os.path.join(os.path.dirname(os.path.abspath(a.warp_px)), "gds_alignment_report.json")
    if os.path.exists(rep):
        q = json.load(open(rep)).get("quality", {})
        res["overlay"]["marker_alignment"] = {k: q[k] for k in q if not isinstance(q[k], (list, dict))}
print(json.dumps(res, indent=1))
