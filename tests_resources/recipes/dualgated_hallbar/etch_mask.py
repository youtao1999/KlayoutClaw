"""Step E (dual-gated): final etch mask L20 (process step 3), stack05 convention.

L15 outline = all flakes (L16, L14, L10-L13) grown, notches closed, simplified (clean edges).
L25 protect = top gate (L1) + finger-end -> contact bridges + every contact (from build_device.py).
L20 etch    = (L15 - L25) + fingers.  Solid = exposed PMMA = etched; holes = resist stays.
  The graphene that survives is the top-gate Hall bar + the 2 um bridges + under the contacts,
  i.e. a Hall bar with longer arms. Fingers: one straight finger_width band per gap between
  neighbouring electrode nets, out to finger_reach beyond the outline, kept metal_clearance off
  L22/L23/L24 and pad_clearance off L2, so debris between electrodes is etched away.

Usage: python etch_mask.py --in post.gds --params params.json --out result.gds
"""
import argparse
import json
import math
import os
import sys

import klayout.db as db

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "topgated_hallbar"))
from recipe_lib import Design, convex_hull, load_params  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--in", dest="inp", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()

P = load_params(a.params)
D = Design(a.inp, P)
dbu, um = D.dbu, D.um
E = P["etch"]

flakes = db.Region()
for k in ("top_top_hbn", "top_graphite", "top_hbn", "graphene", "bottom_hbn", "graphite"):
    flakes += D.R(k)
flakes = flakes.merged()
g_out, close_r, tol = E["outline_grow"], E.get("outline_close", 4.0), E.get("outline_simplify", 1.0)
for _ in range(6):
    outline = flakes.sized(um(g_out + close_r)).sized(um(-close_r)).merged().smoothed(um(tol)).merged()
    if (flakes.sized(um(E.get("outline_min_margin", 1.5))) - outline).is_empty():
        break
    tol *= 0.6
else:
    sys.exit("could not simplify the outline while keeping the flake margin")

prot = D.R("etch_protect")
L1, L22, L23, L24, L2 = D.R("top_gate"), D.R("graphite_contact"), D.R("electrodes"), D.R("tg_contact"), D.R("pads")
metal = (L22 + L23 + L24).merged()

# ---- nets: each fine electrode (+ its gate contact / top gate) + its wide lead/pad
nets = []
for p in L23.each():
    s = db.Region(p)
    if not (s & L24).is_empty():
        s = (s + L24 + L1).merged()
    if not (s & L22).is_empty():
        s = (s + L22).merged()
    for w in L2.each():
        if not (db.Region(w) & s).is_empty():
            s += db.Region(w)
    nets.append(s.merged())

# ---- grow nets until they meet (Voronoi-like zones) inside the pad hull
H = convex_hull(L2).sized(um(10))
zones = [(n & H).merged() for n in nets]
for s in [0.3] * 10 + [1.0] * 27 + [3.0] * 20 + [6.0] * 40:
    claimed = db.Region()
    for z in zones:
        claimed += z
    free = (H - claimed.merged()).merged()
    if free.is_empty():
        break
    new = []
    for z in zones:
        gz = (z.sized(um(s)) & free).merged()
        free = (free - gz).merged()
        new.append((z + gz).merged())
    zones = new
reach = outline.sized(um(E["finger_reach"]))
ring = (reach - outline).merged()
keep_out = (metal.sized(um(E["metal_clearance"])) + L2.sized(um(E["pad_clearance"]))).merged()

cx, cy = D.frame["center_um"]
fingers, pairs = db.Region(), []
for i in range(len(zones)):
    for j in range(i + 1, len(zones)):
        bij = (zones[i].sized(um(0.05)) & zones[j].sized(um(0.05)) & ring).merged()
        if bij.area() * dbu * dbu < 0.5:
            continue
        pts = [(q.x * dbu, q.y * dbu) for p in bij.each() for q in p.each_point_hull()]
        mx = sum(p[0] for p in pts) / len(pts); my = sum(p[1] for p in pts) / len(pts)
        sxx = sum((p[0] - mx) ** 2 for p in pts); syy = sum((p[1] - my) ** 2 for p in pts)
        sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
        ang = 0.5 * math.atan2(2 * sxy, sxx - syy); ux, uy = math.cos(ang), math.sin(ang)
        if (mx - cx) * ux + (my - cy) * uy < 0:
            ux, uy = -ux, -uy
        s = [(p[0] - mx) * ux + (p[1] - my) * uy for p in pts]
        s0, s1 = min(s) - 2.0, max(s)
        hw = E["finger_width"] / 2
        a0 = (mx + s0 * ux, my + s0 * uy); a1 = (mx + s1 * ux, my + s1 * uy)
        rect = db.DPolygon([db.DPoint(a0[0] - uy * hw, a0[1] + ux * hw), db.DPoint(a1[0] - uy * hw, a1[1] + ux * hw),
                            db.DPoint(a1[0] + uy * hw, a1[1] - ux * hw), db.DPoint(a0[0] + uy * hw, a0[1] - ux * hw)])
        fingers.insert(rect.to_itype(dbu))
        pairs.append((i, j))
fingers = ((fingers.merged() & reach) - keep_out).merged()
fingers = fingers.sized(um(-0.15)).sized(um(0.15)).merged()
fingers = (fingers - keep_out).merged()
fingers = db.Region([p for p in fingers.each() if p.area() * dbu * dbu >= 1.0]).merged()
etch = (((outline - prot) + fingers).merged() - prot).merged()
pockets = (etch.hulls() - etch).merged()
fill = db.Region([p for p in pockets.each() if (db.Region(p) & prot).is_empty()])
etch = ((etch + (fill - keep_out)).merged() - prot - L1).merged()     # exact: no slivers on the top gate

D.put("etch_outline", outline)
D.put("etch", etch)

# ---- checks
Dm = (reach.sized(um(-0.5)) - L2.sized(um(E["pad_clearance"] + 0.5))).merged()
bad = []
for c in (Dm - etch).merged().each():
    cr = db.Region(c)
    if not (cr & prot).is_empty():
        continue
    hit = [i for i, n in enumerate(nets) if not (cr & n).is_empty()]
    if len(hit) > 1:
        bad.append(hit)
far = etch - outline.sized(um(0.3))
res = dict(
    etch_area_um2=round(etch.area() * dbu * dbu), etch_polygons=etch.count(),
    etch_holes=[p.holes() for p in etch.each()], finger_pieces=fingers.count(), finger_pairs=len(pairs),
    outline_points=[p.num_points() for p in outline.each()],
    etch_over_protect_um2=round((etch & prot).area() * dbu * dbu, 4),
    etch_over_top_gate_um2=round((etch & L1).area() * dbu * dbu, 4),
    etch_over_pads_um2=round((etch & L2).area() * dbu * dbu, 4),
    fingers_over_metal_um2=round((far & metal).area() * dbu * dbu, 4),
    unseparated_nets_within_reach=bad,
)
ok = (res["etch_over_protect_um2"] == 0 and res["etch_over_top_gate_um2"] == 0 and res["etch_over_pads_um2"] == 0
      and res["fingers_over_metal_um2"] == 0 and not bad)
D.write(a.out)
print(json.dumps(res, indent=1))
sys.exit(0 if ok else 2)
