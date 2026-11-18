"""Step R2: split auto_route output into process layers (+ automatic tip-escape fix).

Input : GDS saved right after auto_route (two_level) wrote inner paths (0.5 um), boundary
        patches and outer paths (4 um) to L23; L21 tips, L22 graphite contact, L100 pins, L2 pads present.
Output:
  L23 = fine ohmic electrodes incl. contact tips (L21 merged in) + graphite-contact electrode
  L5  = top-gate lead extended by its fine route (+ pin square)
  L2  = wide leads + patches merged with their pad (one polygon per net, written in the last step)
  L21, L100 removed.
Fixes applied automatically:
  * a fine route that grazes / crosses a FOREIGN contact tip is cut back around its own tip and
    re-connected with a short outward jog (a fix first done by hand on an earlier device);
  * electrodes are trimmed to keep tg_clearance from top-gate metal (only where it does not sever).
Exit 2 if anything still needs a manual fix (listed in the JSON printout).

Usage: python post_route.py --in routed.gds --params params.json --record design.json --out post.gds
"""
import argparse
import json
import sys

import klayout.db as db

from recipe_lib import Design, load_params, min_gap

ap = argparse.ArgumentParser()
ap.add_argument("--in", dest="inp", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--record", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()

P = load_params(a.params)
D = Design(a.inp, P)
dbu, um = D.dbu, D.um
PR = P["post_route"]
GAP = PR["min_electrode_gap"]
W_IN = P["routing"]["inner_width"]

shapes = [db.Region(s.polygon) for s in D.top.shapes(D.li("electrodes")).each()]
assert shapes, "no routes on L23 - run auto_route first"
inner = [r.sized(um(-0.3)).is_empty() for r in shapes]        # 0.5 um paths vanish, 4-5 um shapes survive
pins = [db.Region(p) for p in D.R("pins_tmp").each()]
pads = [db.Region(p) for p in D.R("pads").each()]
L1, L5, gt = D.R("top_gate"), D.R("top_gate_lead"), D.R("graphite")

# ---- group route shapes into nets (touching)
parent = list(range(len(shapes)))
def find(i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]; i = parent[i]
    return i
for i in range(len(shapes)):
    for j in range(i + 1, len(shapes)):
        if not (shapes[i].sized(1) & shapes[j]).is_empty():
            parent[find(i)] = find(j)
groups = {}
for i in range(len(shapes)):
    groups.setdefault(find(i), []).append(i)

nets = []
for idx in groups.values():
    inn, wid = db.Region(), db.Region()
    for i in idx:
        (inn if inner[i] else wid).insert(shapes[i])
    inn, wid = inn.merged(), wid.merged()
    pin_ov = [(k, (inn & p).area()) for k, p in enumerate(pins) if not (inn.sized(um(0.05)) & p).is_empty()]
    pad_hits = [k for k, p in enumerate(pads) if not (wid & p).is_empty()]
    if not pin_ov or len(pad_hits) != 1:
        sys.exit("route group touches pins %s pads %s - routing open or pad short; re-route" % (pin_ov, pad_hits))
    own = max(pin_ov, key=lambda t: t[1])[0]           # a route starts inside its own pin
    nets.append(dict(pin=own, pad=pad_hits[0], inn=inn, wid=wid, foreign=[k for k, _ in pin_ov if k != own],
                     top_gate=not (pins[own] & L5.sized(um(0.1))).is_empty()))
assert sorted(n["pin"] for n in nets) == list(range(len(pins))), "each pin must own exactly one route"

def other_metal(me):
    """Other nets' fine routes + pins (top-gate metal handled separately)."""
    r = db.Region()
    for n in nets:
        if n is not me:
            r += n["inn"] + pins[n["pin"]]
    return r.merged()

TG_ALL = (L1 + L5).merged()
GC = D.R("graphite_contact")

def ok_route(n, cand):
    if (min_gap(cand, other_metal(n), dbu) or 9) < GAP:
        return False
    if not n["top_gate"] and (min_gap(cand - pins[n["pin"]], TG_ALL, dbu) or 9) < PR["tg_clearance"]:
        return False
    ohmic = (pins[n["pin"]] & GC).is_empty() and not n["top_gate"]
    return not (ohmic and not ((cand - pins[n["pin"]]) & gt).is_empty())

# ---- automatic tip-escape fix
fixes = []
for n in nets:
    if not n["foreign"] and (min_gap(n["inn"], other_metal(n), dbu) or 9) >= GAP:
        continue
    pin = pins[n["pin"]]
    pb = pin.bbox(); pc = pb.center()
    cxl, cyl = D.to_local(pc.x * dbu, pc.y * dbu)
    sgn = -1 if cxl < 0 else 1
    wanted = None
    for rcut in (3.0, 4.0, 5.0):
        rest = (n["inn"] - pin.sized(um(rcut))).merged()
        piece = [p for p in rest.each() if not (db.Region(p).sized(um(0.05)) & n["wid"]).is_empty()]
        if not piece:
            continue
        piece = db.Region(piece[0])
        # nearest vertex of the remaining route to the pin
        best = None
        for p in piece.each():
            for q in p.each_point_hull():
                dd = (q.x - pc.x) ** 2 + (q.y - pc.y) ** 2
                if best is None or dd < best[0]:
                    best = (dd, q)
        tx, ty = D.to_local(best[1].x * dbu, best[1].y * dbu)
        half = (D.local_bbox(list(pin.each())[0])[2] - D.local_bbox(list(pin.each())[0])[0]) / 2
        for jog in (0.8, 1.2, 1.6, 2.0, 2.5, 3.0):
            x0 = cxl + sgn * (half - 0.1)
            cand_path = D.path([(x0, cyl), (cxl + sgn * (half + jog), cyl), (tx, ty)], W_IN)
            cand = (piece + cand_path).merged()
            if cand.count() == 1 and ok_route(n, cand):
                wanted = (cand, rcut, jog)
                break
        if wanted:
            break
    if wanted:
        n["inn"] = wanted[0]
        fixes.append(dict(pin=n["pin"], local_tip=[round(cxl, 2), round(cyl, 2)], how="auto re-drawn first segment (cut %.1f um, jog %.1f um)" % wanted[1:]))
    else:
        fixes.append(dict(pin=n["pin"], local_tip=[round(cxl, 2), round(cyl, 2)], how="MANUAL: no clean escape found - redraw the first segment by hand"))

# ---- assemble layers
fine23, fine5, wide = db.Region(), L5.dup(), db.Region()
for n in nets:
    if n["top_gate"]:
        fine5 += n["inn"] + pins[n["pin"]]
    else:
        fine23 += n["inn"]
    wide += (n["wid"] + pads[n["pad"]]).merged()
tips = D.R("tips_tmp")
elec = (fine23 + tips).merged()
TGm = (L1 + fine5).merged()
trim = (elec - TGm.sized(um(PR["tg_clearance"]))).merged()
if trim.count() == elec.count():
    trimmed_area = round((elec - trim).area() * dbu * dbu, 4); elec = trim
else:
    trimmed_area = "skipped (would sever a net)"

D.put("electrodes", elec)
D.put("top_gate_lead", fine5.merged())
D.put("pads", wide.merged())
for k in ("tips_tmp", "pins_tmp"):
    D.clear(k); D.ly.delete_layer(D.li(k))

# ---- checks
E = list(elec.each())
close = []
for i, x in enumerate(E):
    for j in range(i + 1, len(E)):
        gap = min_gap(db.Region(x), db.Region(E[j]), dbu)
        if gap is not None and gap < GAP:
            h = um(gap / 2)
            c = (db.Region(x).sized(h) & db.Region(E[j]).sized(h)).bbox().center()
            close.append(dict(a=i, b=j, gap_lt=gap, at_local=[round(v, 2) for v in D.to_local(c.x * dbu, c.y * dbu)]))
gc = D.R("graphite_contact")
ohmic = db.Region([p for p in E if (db.Region(p) & gc).is_empty()])
W = list(wide.merged().each())
res = dict(
    nets=len(nets), electrodes=len(E), top_gate_nets=sum(n["top_gate"] for n in nets), tg_trim_um2=trimmed_area,
    electrode_to_top_gate_gap=min_gap(elec, TGm, dbu),
    ohmic_over_graphite_um2=round((ohmic & gt).area() * dbu * dbu, 4),
    each_electrode_one_wide=[sum(1 for w in W if not (db.Region(p) & db.Region(w)).is_empty()) for p in E],
    close_electrode_pairs=close, tip_escape_fixes=fixes,
)
ok = (not any(f["how"].startswith("MANUAL") for f in fixes) and len(E) == len(nets) - 1 and res["top_gate_nets"] == 1
      and not close and res["ohmic_over_graphite_um2"] == 0 and all(k == 1 for k in res["each_electrode_one_wide"])
      and (res["electrode_to_top_gate_gap"] or 9) >= PR["tg_clearance"] - 0.01)
D.write(a.out)
print(json.dumps(res, indent=1))
print("OK" if ok else "NEEDS MANUAL FIX (see above)")
sys.exit(0 if ok else 2)
