"""Step R2 (dual-gated): split routes into process layers + automatic tip-escape fix.

Input : routed.gds (two-level auto_route output on L23: 0.5 um inner paths, patches, 4 um outer
        paths) with L21 tips, L22 bottom-gate contact, L24 top-gate contact, L100 pins, L2 pads.
Output:
  L23 = all fine electrodes (graphene contacts incl. tips, top-gate net, bottom-gate net)
  L2  = wide leads + patches merged with their pad (one polygon per net)
  L21, L100 removed.  (Everything in L22/L23/L24/L2 is written in the same process step 2.)
Rules (step 2 etches the top hBN under every metal shape with CHF3, so metal touching graphene
or graphite makes contact there):
  * graphene-contact nets: no metal over bottom graphite, >= tg_clearance from the top gate (L1);
  * top-gate net: outside L1 its metal keeps >= g_clearance from graphene;
  * bottom-gate net: metal keeps >= g_clearance from graphene and tg_clearance from L1;
  * electrode-electrode gap >= min_electrode_gap.
A fine route that violates these near its own tip is re-drawn with a short outward jog.
Exit 2 if anything still needs a manual fix.

Usage: python post_route.py --in routed.gds --params params.json --record design.json --out post.gds
"""
import argparse
import json
import os
import sys

import klayout.db as db

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "topgated_hallbar"))
from recipe_lib import Design, load_params  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dg_lib import dist, space  # noqa: E402

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
GAP, TGC, GC_ = PR["min_electrode_gap"], PR["tg_clearance"], PR["g_clearance"]
W_IN = P["routing"]["inner_width"]
nz = lambda d: 99.0 if d is None else d     # None = farther than the 10 um search range

shapes = [db.Region(s.polygon) for s in D.top.shapes(D.li("electrodes")).each()]
assert shapes, "no routes on L23 - run the router first"
inner = [r.sized(um(-0.3)).is_empty() for r in shapes]        # 0.5 um paths vanish, 4-5 um shapes survive
pins = [db.Region(p) for p in D.R("pins_tmp").each()]
pads = [db.Region(p) for p in D.R("pads").each()]
L1, L22, L24 = D.R("top_gate"), D.R("graphite_contact"), D.R("tg_contact")
g, bg = D.R("graphene"), D.R("graphite")

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
    own = max(pin_ov, key=lambda t: t[1])[0]
    kind = "tg" if not (pins[own] & L24).is_empty() else ("bg" if not (pins[own] & L22).is_empty() else "ohmic")
    nets.append(dict(pin=own, pad=pad_hits[0], inn=inn, wid=wid, kind=kind, foreign=[k for k, _ in pin_ov if k != own]))
assert sorted(n["pin"] for n in nets) == list(range(len(pins))), "each pin must own exactly one route"


def other_metal(me):
    r = db.Region()
    for n in nets:
        if n is not me:
            r += n["inn"] + pins[n["pin"]]
    return r.merged()


def violations(n, cand):
    """Rule violations of a candidate fine route (+ its pin) for net n."""
    v = []
    if nz(dist(cand, other_metal(n), dbu)) < GAP:
        v.append("electrode gap")
    off_pin = (cand - pins[n["pin"]]).merged()
    if n["kind"] != "tg" and nz(dist(off_pin, L1, dbu)) < TGC:
        v.append("too close to top gate")
    if n["kind"] == "ohmic" and not (off_pin & bg).is_empty():
        v.append("over bottom graphite")
    if n["kind"] == "tg" and nz(dist(cand - L1, g, dbu)) < GC_:
        v.append("top-gate metal near graphene")
    if n["kind"] == "bg" and nz(dist(cand, g, dbu)) < GC_:
        v.append("bottom-gate metal near graphene")
    return v


# ---- automatic tip-escape fix (graphene contacts only)
fixes = []
for n in nets:
    if n["kind"] != "ohmic" or (not n["foreign"] and not violations(n, n["inn"])):
        continue
    pin = pins[n["pin"]]
    pc = pin.bbox().center()
    cxl, cyl = D.to_local(pc.x * dbu, pc.y * dbu)
    sgn = -1 if cxl < 0 else 1
    wanted = None
    for rcut in (3.0, 4.0, 5.0):
        rest = (n["inn"] - pin.sized(um(rcut))).merged()
        piece = [p for p in rest.each() if not (db.Region(p).sized(um(0.05)) & n["wid"]).is_empty()]
        if not piece:
            continue
        piece = db.Region(piece[0])
        best = min(((q.x - pc.x) ** 2 + (q.y - pc.y) ** 2, q) for p in piece.each() for q in p.each_point_hull())[1]
        tx, ty = D.to_local(best.x * dbu, best.y * dbu)
        lb = D.local_bbox(list(pin.each())[0])
        half = (lb[2] - lb[0]) / 2
        for jog in (0.8, 1.2, 1.6, 2.0, 2.5, 3.0):
            cand = (piece + D.path([(cxl + sgn * (half - 0.1), cyl), (cxl + sgn * (half + jog), cyl), (tx, ty)], W_IN)).merged()
            if cand.count() == 1 and not violations(n, cand):
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
fine, wide = db.Region(), db.Region()
for n in nets:
    fine += n["inn"]
    wide += (n["wid"] + pads[n["pad"]]).merged()
elec = (fine + D.R("tips_tmp")).merged()
D.put("electrodes", elec)
D.put("pads", wide.merged())
for k in ("tips_tmp", "pins_tmp"):
    D.clear(k); D.ly.delete_layer(D.li(k))

# ---- checks on the final layers
E = list(elec.each())
close = []
for i, x in enumerate(E):
    for j in range(i + 1, len(E)):
        gap = dist(db.Region(x), db.Region(E[j]), dbu)
        if gap is not None and gap < GAP:
            h = um(gap / 2) + 1
            c = (db.Region(x).sized(h) & db.Region(E[j]).sized(h)).bbox().center()
            close.append(dict(a=i, b=j, gap_lt=gap, at_local=[round(v, 2) for v in D.to_local(c.x * dbu, c.y * dbu)]))
kind_of = []
for p in E:
    r = db.Region(p)
    kind_of.append("tg" if not (r & L24).is_empty() else ("bg" if not (r & L22).is_empty() else "ohmic"))
ohm = db.Region([p for p, k in zip(E, kind_of) if k == "ohmic"])
tgn = db.Region([p for p, k in zip(E, kind_of) if k == "tg"]) + L24
bgn = db.Region([p for p, k in zip(E, kind_of) if k == "bg"]) + L22
W = list(wide.merged().each())
res = dict(
    nets=len(nets), electrodes=len(E), kinds={k: kind_of.count(k) for k in ("ohmic", "tg", "bg")},
    ohmic_over_bottom_graphite_um2=round((ohm & bg).area() * dbu * dbu, 4),
    ohmic_to_top_gate_gap=dist(ohm, L1, dbu),
    bg_net_to_top_gate_gap=dist(bgn, L1, dbu),
    tg_net_outside_L1_to_graphene_gap=dist(tgn - L1, g, dbu),
    bg_net_to_graphene_gap=dist(bgn, g, dbu),
    each_electrode_one_wide=[sum(1 for w in W if not (db.Region(p) & db.Region(w)).is_empty()) for p in E],
    close_electrode_pairs=close, tip_escape_fixes=fixes,
)
ok = (not any(f["how"].startswith("MANUAL") for f in fixes) and len(E) == len(nets)
      and res["kinds"]["tg"] == 1 and res["kinds"]["bg"] == 1 and not close
      and res["ohmic_over_bottom_graphite_um2"] == 0
      and nz(res["ohmic_to_top_gate_gap"]) >= TGC - 0.01 and nz(res["bg_net_to_top_gate_gap"]) >= TGC - 0.01
      and nz(res["tg_net_outside_L1_to_graphene_gap"]) >= GC_ - 0.01 and nz(res["bg_net_to_graphene_gap"]) >= GC_ - 0.01
      and all(k == 1 for k in res["each_electrode_one_wide"]))
D.write(a.out)
print(json.dumps(res, indent=1))
print("OK" if ok else "NEEDS MANUAL FIX (see above)")
sys.exit(0 if ok else 2)
