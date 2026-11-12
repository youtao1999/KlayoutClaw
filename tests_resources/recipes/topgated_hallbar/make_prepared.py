"""Step P4: assemble prepared.gds = template (flake-layer collisions remapped) + flakes + defects,
all in chip coordinates of the chosen field.

Flakes are mapped straight from contour_px with gds_warp_px.npy (image px -> GDS um), so the
result does not depend on which pixel size was used for contour_um.

  template L11 -> L111, L12 -> L112 (only if the template uses the flake layers; see --remap)
  flakes: top_hBN L10, graphene L11, bottom_hBN L12, graphite L13 (bottom graphite),
          top_graphite L14, top_top_hBN L16 (dual-gated stacks; see combine_ingredients.py)
  defects (review/defects.json: blobs px_box, lines px_poly+width_px) -> L50

Usage: python make_prepared.py --template Template.gds --traces combine/traces.json \
         --warp-px gdsalign/gds_warp_px.npy [--defects review/defects.json] --out prepared.gds \
         [--traces-gds-out gdsalign/traces_gds.json]
"""
import argparse
import json

import klayout.db as db
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--template", required=True)
ap.add_argument("--traces", required=True)
ap.add_argument("--warp-px", required=True)
ap.add_argument("--defects")
ap.add_argument("--out", required=True)
ap.add_argument("--traces-gds-out")
ap.add_argument("--remap", default="11:111,12:112,10:110,13:113")
a = ap.parse_args()

LAYERS = {"top_hBN": 10, "graphene": 11, "bottom_hBN": 12, "graphite": 13, "top_graphite": 14, "top_top_hBN": 16}
M = np.load(a.warp_px)
px2g = lambda pts: (np.asarray(pts, float) @ M[:, :2].T + M[:, 2])

ly = db.Layout(); ly.read(a.template)
tops = ly.top_cells(); assert len(tops) == 1
top = tops[0]; d = ly.dbu
# flatten the template so remapping catches every shape
top.flatten(True)
remap = dict(tuple(map(int, s.split(":"))) for s in a.remap.split(",") if s)
moved = {}
for src, dst in remap.items():
    li = ly.find_layer(src, 0)
    if li is None or top.shapes(li).is_empty():
        continue
    lj = ly.layer(dst, 0)
    top.shapes(lj).insert(top.shapes(li)); top.shapes(li).clear()
    moved["%d/0" % src] = "%d/0" % dst

t = json.load(open(a.traces))
areas = {}
for mat, entries in t["materials"].items():
    lm = t.get("layer_map", {}).get(mat)
    li = ly.layer(*(int(v) for v in lm.split("/"))) if lm else ly.layer(LAYERS[mat], 0)
    for e in entries:
        g = px2g(e["contour_px"])
        e["contour_gds"] = g.tolist()
        top.shapes(li).insert(db.DPolygon([db.DPoint(x, y) for x, y in g]).to_itype(d))
    areas[mat] = round(db.Region(top.shapes(li)).merged().area() * d * d, 1)

n_def = 0
if a.defects:
    dj = json.load(open(a.defects)); ld = ly.layer(50, 0)
    for bl in dj.get("blobs", []):
        x0, y0, x1, y1 = bl["px_box"]
        g = px2g([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
        top.shapes(ld).insert(db.DPolygon([db.DPoint(x, y) for x, y in g]).to_itype(d)); n_def += 1
    for ln in dj.get("lines", []):
        g = px2g(ln["px_poly"]); w = ln["width_px"] * float(np.hypot(*M[:, 0]))
        top.shapes(ld).insert(db.DPath([db.DPoint(x, y) for x, y in g], w).to_itype(d).polygon()); n_def += 1

ly.write(a.out)
if a.traces_gds_out:
    t["frame"] = "GDS um (chosen field), contour_gds from contour_px via gds_warp_px.npy"
    json.dump(t, open(a.traces_gds_out, "w"), indent=1)
print(json.dumps(dict(out=a.out, remapped=moved, flake_areas_um2=areas, defects=n_def)))
