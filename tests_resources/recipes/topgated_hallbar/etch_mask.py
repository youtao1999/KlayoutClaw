"""Step E: etch mask (L20) in the stack05 convention.

L15 outline  = all flakes (L10-L13) grown by outline_grow.
L25 protect  = finger-end -> tip bridges + graphite-contact patch (from build_device.py).
L20 etch     = (L15 - L25)  +  fingers.
  Solid = exposed PMMA = etched; holes = resist stays. Inside the outline the window may cover
  electrode/top-gate metal (the metal itself masks the etch), exactly as stack05's L2 does.
  Fingers: ~finger_width wide bands on the centre line of every gap between neighbouring
  electrode nets (nets = fine electrode + its wide lead/pad; top gate + lead; graphite contact),
  from the outline out to finger_reach beyond it, clipped metal_clearance off all step-1/2 metal
  and pad_clearance off the (later) L2 leads/pads. They must NOT overlap any electrode.
Checks: no overlap with protect/L2/metal (outside the outline), and inside the finger reach
no unexposed region touches two different nets.

Usage: python etch_mask.py --in post.gds --params params.json --out result.gds
"""
import argparse
import json
import sys

import klayout.db as db

from recipe_lib import Design, convex_hull, load_params

ap = argparse.ArgumentParser()
ap.add_argument("--in", dest="inp", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()

P = load_params(a.params)
D = Design(a.inp, P)
dbu, um = D.dbu, D.um
E = P["etch"]

flakes = (D.R("top_hbn") + D.R("graphene") + D.R("bottom_hbn") + D.R("graphite")).merged()
# clean outline (stack05 style: few long straight edges): grow, close small notches, simplify,
# and make sure every flake stays >= outline_min_margin inside
g_out, close_r, tol = E["outline_grow"], E.get("outline_close", 4.0), E.get("outline_simplify", 1.0)
for _ in range(6):
    outline = flakes.sized(um(g_out + close_r)).sized(um(-close_r)).merged().smoothed(um(tol)).merged()
    if (flakes.sized(um(E.get("outline_min_margin", 1.5))) - outline).is_empty():
        break
    tol *= 0.6
else:
    sys.exit("could not simplify the outline while keeping the flake margin")
prot = D.R("etch_protect")
L1, L5, L22, L23, L2 = D.R("top_gate"), D.R("top_gate_lead"), D.R("graphite_contact"), D.R("electrodes"), D.R("pads")
metal = (L1 + L5 + L22 + L23).merged()

# ---- nets
seeds = [db.Region(p) for p in L23.each()] + [(L1 + L5).merged()]
seeds = [(s + L22).merged() if not (s & L22).is_empty() else s for s in seeds]
nets = []
for s in seeds:
    n = s.dup()
    for w in L2.each():
        if not (db.Region(w) & s).is_empty():
            n += db.Region(w)
    nets.append(n.merged())

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

# one straight rectangle per pair of neighbouring nets: fit a line to their zone boundary inside
# the ring (outline .. outline+reach), W wide, from 2 um inside the outline to the far end
import math
cx, cy = D.frame["center_um"]
fingers = db.Region()
pairs = []
for i in range(len(zones)):
    for j in range(i + 1, len(zones)):
        bij = (zones[i].sized(um(0.05)) & zones[j].sized(um(0.05)) & ring).merged()
        if bij.area() * dbu * dbu < 0.5:
            continue
        pts = [(q.x * dbu, q.y * dbu) for p in bij.each() for q in p.each_point_hull()]
        mx = sum(p[0] for p in pts) / len(pts); my = sum(p[1] for p in pts) / len(pts)
        sxx = sum((p[0] - mx) ** 2 for p in pts); syy = sum((p[1] - my) ** 2 for p in pts); sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
        ang = 0.5 * math.atan2(2 * sxy, sxx - syy); ux, uy = math.cos(ang), math.sin(ang)
        if (mx - cx) * ux + (my - cy) * uy < 0:
            ux, uy = -ux, -uy                                           # point outward
        s = [(p[0] - mx) * ux + (p[1] - my) * uy for p in pts]
        s0, s1 = min(s) - 2.0, max(s)
        hw = E["finger_width"] / 2
        a0 = (mx + s0 * ux, my + s0 * uy); a1 = (mx + s1 * ux, my + s1 * uy)
        rect = db.DPolygon([db.DPoint(a0[0] - uy * hw, a0[1] + ux * hw), db.DPoint(a1[0] - uy * hw, a1[1] + ux * hw),
                            db.DPoint(a1[0] + uy * hw, a1[1] - ux * hw), db.DPoint(a0[0] + uy * hw, a0[1] - ux * hw)])
        fingers.insert(rect.to_itype(dbu))
        pairs.append((i, j))
fingers = ((fingers.merged() & reach) - keep_out).merged()
fingers = fingers.sized(um(-0.15)).sized(um(0.15)).merged()        # drop slivers < 0.3 um
fingers = (fingers - keep_out).merged()
fingers = db.Region([p for p in fingers.each() if p.area() * dbu * dbu >= 1.0]).merged()   # drop crumbs
etch = (((outline - prot) + fingers).merged() - prot).merged()
# fill enclosed unexposed pockets that hold no metal and are not protected holes (cosmetic)
pockets = (etch.hulls() - etch).merged()
fill = db.Region([p for p in pockets.each() if (db.Region(p) & prot).is_empty()])
fill = (fill - keep_out).merged()                   # fill up to the same clearance the fingers keep
etch = (etch + fill).merged()

D.put("etch_outline", outline)
D.put("etch", etch)

# ---- checks
Dm = (reach.sized(um(-0.5)) - L2.sized(um(E["pad_clearance"] + 0.5))).merged()
bad = []
for c in (Dm - etch).merged().each():
    cr = db.Region(c)
    if not (cr & prot).is_empty():
        continue                                   # intentional bridge / graphite-contact holes
    hit = [i for i, n in enumerate(nets) if not (cr & n).is_empty()]
    if len(hit) > 1:
        bad.append(hit)
far = etch - outline.sized(um(0.3))
res = dict(
    etch_area_um2=round(etch.area() * dbu * dbu), etch_polygons=etch.count(),
    etch_holes=[p.holes() for p in etch.each()], finger_pieces=fingers.count(), finger_pairs=len(pairs),
    outline_points=[p.num_points() for p in outline.each()], etch_points=[p.num_points() for p in etch.each()],
    etch_over_protect_um2=round((etch & prot).area() * dbu * dbu, 4),
    etch_over_pads_um2=round((etch & L2).area() * dbu * dbu, 4),
    fingers_over_metal_um2=round((far & metal).area() * dbu * dbu, 4),
    unseparated_nets_within_reach=bad,
)
ok = res["etch_over_protect_um2"] == 0 and res["etch_over_pads_um2"] == 0 and res["fingers_over_metal_um2"] == 0 and not bad
D.write(a.out)
print(json.dumps(res, indent=1))
sys.exit(0 if ok else 2)
