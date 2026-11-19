"""Deliverables of a finished six-piece design, in <device>/klayoutclaw/ (the folder above data/):
  writes.gds    only the EBL write layers (7/0 top-gate etch mask, 4/0 contacts, 4/1 etch checker if any,
                2/0 electrodes, 2/1 big pads), taken from result.gds: the file sent to the EBL. + writes.lyp
  result.lyp    layer names for result.gds, the design file the skills built (template, the flakes as they
                landed, every design layer). The stack plan (design.gds) is never written.
  <photo>.lyimg the full-stack photo placed by the marker alignment (data/gds_warp_px.npy), when present.
Exports only a design whose final check passed on the current result.gds and prepared.gds (data/record.json,
finalcheck/check, with their sha256); --force overrides.

Usage: python export.py --flakes data/prepared.gds --params data/params.json --writes result.gds
"""
import argparse
import json
import os
import sys

import klayout.db as db
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "nanodevice_topgate", "scripts"))
from tg_lib import parse, record, sha256  # noqa: E402

NAMES = {(7, 0): "top-gate etch mask (deep, to the bottom hBN)", (4, 0): "contacts (shallow, to the top hBN)",
         (4, 1): "etch checker", (2, 0): "electrodes (fine metal, small current)", (2, 1): "big pads (large current)",
         (5, 0): "channel", (5, 1): "arms", (5, 2): "top-gate contacts", (5, 3): "top-gate electrodes",
         (11, 4): "active region", (16, 0): "top-top hBN", (14, 0): "top graphite", (10, 0): "top hBN",
         (11, 0): "graphene", (11, 1): "graphene piece 1", (11, 2): "graphene piece 2", (11, 3): "graphene piece 3",
         (12, 0): "bottom hBN", (13, 0): "bottom graphite"}
COLORS = ["#ff8080", "#80ff80", "#40c040", "#ffd700", "#ff9900", "#0080ff", "#00a0ff", "#00c0ff", "#00e0ff",
          "#ff00ff", "#c0c0ff", "#808080", "#a0e0ff", "#ff60ff", "#ff4040", "#c03030", "#802020", "#60ff60", "#404040"]

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--flakes", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--writes", required=True, help="result.gds, the file the skills built")
ap.add_argument("--force", action="store_true", help="export although the final check did not pass")
a = parse(ap, "finalcheck/export")

data = os.path.dirname(os.path.abspath(a.params))
out = os.path.dirname(data)
rec_path = os.path.join(data, "record.json")
verdict = json.load(open(rec_path)).get("finalcheck/check", {}) if os.path.exists(rec_path) else {}
if not a.force:
    if not verdict.get("passed"):
        sys.exit("final check has not passed (record.json finalcheck/check): run nanodevice_finalcheck first, or --force")
    if verdict.get("sha256") != {"writes": sha256(a.writes), "flakes": sha256(a.flakes)}:
        sys.exit("%s or %s changed since the final check passed: rerun the final check, or --force"
                 % (os.path.basename(a.writes), os.path.basename(a.flakes)))

des = db.Layout()
des.read(a.writes)
dtop = des.top_cell()
dlay = {(des.get_info(i).layer, des.get_info(i).datatype): i for i in des.layer_indexes() if not dtop.shapes(i).is_empty()}
P = json.load(open(a.params))


def write(ly, path):
    opt = db.SaveLayoutOptions()
    opt.format = "GDS2"
    opt.gds2_max_vertex_count = 4000              # every GDS record < 32 kB (other readers / EBL software)
    ly.write(path + ".part", opt)
    os.replace(path + ".part", path)


def lyp(path, specs):
    xs = ['<?xml version="1.0" encoding="utf-8"?>', "<layer-properties>"]
    for k, (l, d) in enumerate(specs):
        c = COLORS[k % len(COLORS)]
        xs += [" <properties>", "  <frame-color>%s</frame-color>" % c, "  <fill-color>%s</fill-color>" % c,
               "  <dither-pattern>I9</dither-pattern>", "  <visible>true</visible>", "  <width>1</width>",
               "  <name>%d/%d %s</name>" % (l, d, NAMES.get((l, d), "")), "  <source>%d/%d@1</source>" % (l, d), " </properties>"]
    with open(path, "w") as f:
        f.write("\n".join(xs + ["</layer-properties>"]) + "\n")


if os.path.abspath(a.writes) == os.path.abspath(os.path.join(out, "writes.gds")):
    sys.exit("--writes is the design file the skills built (result.gds), not writes.gds")

# writes.gds: the EBL layers only
w = db.Layout()
w.dbu = des.dbu
wtop = w.create_cell("TOP")
ebl = [(7, 0), (4, 0), (4, 1), (2, 0), (2, 1)]
for k in ebl:
    if k in dlay:
        wtop.shapes(w.layer(*k)).insert(dtop.shapes(dlay[k]))
missing = [k for k in ebl if k not in dlay and k != (4, 1)]   # 4/1 (etch checker) is optional
if missing:
    sys.exit("design file lacks EBL layer(s) %s" % ", ".join("%d/%d" % k for k in missing))
write(w, os.path.join(out, "writes.gds"))
lyp(os.path.join(out, "writes.lyp"), [k for k in ebl if k in dlay])

lyp(os.path.join(out, "result.lyp"), sorted(dlay))

# photo overlay, placed by the marker alignment (pixel (col, row) centre -> KLayout image coordinates)
img_out = None
warp = os.path.join(data, "gds_warp_px.npy")
photo = P.get("prepare", {}).get("photo")
if photo and os.path.exists(warp):
    import klayout.lay as lay
    dev = os.path.dirname(out)
    M = np.load(warp)
    img = lay.Image(os.path.join(dev, photo))
    Wd, Hd = img.width(), img.height()
    A, t = M[:, :2], M[:, 2]
    Ai = A @ np.diag([1.0, -1.0])
    ti = A @ np.array([Wd / 2 - 0.5, Hd / 2 - 0.5]) + t
    img.matrix = db.Matrix3d(Ai[0, 0], Ai[0, 1], ti[0], Ai[1, 0], Ai[1, 1], ti[1], 0.0, 0.0, 1.0)
    img_out = os.path.join(out, os.path.splitext(os.path.basename(photo))[0] + ".lyimg")
    img.write(img_out)
    m = lay.Image.read(img_out).matrix
    for col, row in ((0, 0), (Wd - 1, Hd - 1)):
        p = m.trans(db.DPoint(col + 0.5 - Wd / 2, Hd / 2 - row - 0.5))
        q = M @ np.array([col, row, 1.0])
        assert abs(p.x - q[0]) < 1e-6 and abs(p.y - q[1]) < 1e-6, ("lyimg placement mismatch", p, q)

record(a.params, "finalcheck/export", writes_layers=["%d/%d" % k for k in ebl if k in dlay],
       image=img_out and os.path.basename(img_out))
print("writes.gds: %s (from %s); %s" % (", ".join("%d/%d" % k for k in ebl if k in dlay), os.path.basename(a.writes),
      ("photo overlay " + os.path.basename(img_out)) if img_out else "no photo overlay (no prepare.photo or alignment)"))
