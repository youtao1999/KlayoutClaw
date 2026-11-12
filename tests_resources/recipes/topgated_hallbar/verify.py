"""Step V: full design-rule / connectivity verification of the final GDS.

Usage: python verify.py --gds result.gds --params params.json --record design.json --out verify.json
Prints a PASS/FAIL table; writes the machine-readable result (copy into result.json "checks").
Exit 0 only if every hard check passes.
"""
import argparse
import json
import sys

import klayout.db as db

from recipe_lib import Design, load_params, min_gap

ap = argparse.ArgumentParser()
ap.add_argument("--gds", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--record", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()

P = load_params(a.params)
rec = json.load(open(a.record))
D = Design(a.gds, P)
dbu = D.dbu
A = lambda r: r.area() * dbu * dbu

g, gt = D.R("graphene"), D.R("graphite")
L1, L5, L2, L20, L22, L23, L25, L15 = (D.R(k) for k in ("top_gate", "top_gate_lead", "pads", "etch", "graphite_contact", "electrodes", "etch_protect", "etch_outline"))
TGm = (L1 + L5).merged()
metal = (TGm + L22 + L23).merged()
cx, cy = P["channel"]["x"], P["channel"]["y"]
chan = D.box(cx[0], cy[0], cx[1], cy[1])
tips = db.Region()
for arm in rec["arms"]:
    tips += D.box(*arm["tip_box"])
E = list(L23.each())
W = list(L2.each())
ohmic = db.Region([p for p in E if (db.Region(p) & L22).is_empty()])

rows = []
def chk(name, value, ok, hard=True):
    rows.append(dict(name=name, value=value, ok=bool(ok), hard=hard))

# device
chk("channel inside graphene AND graphite", round(A(chan - (g & gt)), 4), A(chan - (g & gt)) < 1e-3)
chk("channel margin to overlap edge >= 1.5 um", round(A(chan - (g & gt).sized(D.um(-1.5))), 4), A(chan - (g & gt).sized(D.um(-1.5))) < 0.01, hard=False)
chk("top gate on graphene (fraction)", round(A(L1 & g) / A(L1), 4), A(L1 & g) / A(L1) >= 0.99)
ovs = [r["overshoot"] for r in rec["arms"]]
chk("finger overshoot past graphite edge 0.5-1.0 um", [min(ovs), max(ovs)], min(ovs) >= 0.5 - 1e-3 and max(ovs) <= 1.0)
chk("contact tips on graphene-only (fraction)", round(A(tips & (g - gt)) / A(tips), 4), A(tips & (g - gt)) / A(tips) >= 0.99)
chk("contact tips part of electrodes (L23)", round(A(tips - L23), 4), A(tips - L23) < 0.02)
chk("tips to top-gate metal gap >= 0.5 um", min_gap(tips, TGm, dbu), (min_gap(tips, TGm, dbu) or 9) >= 0.55)
chk("graphite contact inside graphite (fraction)", round(A(L22 & gt) / A(L22), 4), A(L22 & gt) / A(L22) >= 0.99)
chk("graphite contact to top-gate metal gap >= 1 um", min_gap(L22, TGm, dbu), (min_gap(L22, TGm, dbu) or 9) >= 1.0)
# electrodes / routes
chk("electrodes = arms + graphite contact", len(E), len(E) == len(rec["arms"]) + 1)
chk("electrode-electrode min gap >= 0.6 um", min(min_gap(db.Region(x), db.Region(y), dbu) or 9 for i, x in enumerate(E) for y in E[i + 1:]),
    min(min_gap(db.Region(x), db.Region(y), dbu) or 9 for i, x in enumerate(E) for y in E[i + 1:]) >= 0.6)
chk("electrodes to top-gate metal gap >= 0.5 um", min_gap(L23, TGm, dbu), (min_gap(L23, TGm, dbu) or 9) >= 0.5)
chk("ohmic electrodes over graphite (um2)", round(A(ohmic & gt), 4), A(ohmic & gt) == 0)
chk("each electrode joins exactly one wide lead", [sum(1 for w in W if not (db.Region(p) & db.Region(w)).is_empty()) for p in E],
    all(sum(1 for w in W if not (db.Region(p) & db.Region(w)).is_empty()) == 1 for p in E))
tg_w = [w for w in W if not (db.Region(w) & L5).is_empty()]
chk("top gate: L1 touches L5, L5 joins one wide lead", len(tg_w), not (L1 & L5).is_empty() and len(tg_w) == 1)
chk("top-gate net to ohmic metal gap", min_gap(TGm, L23 + L22, dbu), (min_gap(TGm, L23 + L22, dbu) or 9) >= 0.5)
chk("wide leads/pads = nets, none touching", L2.count(), L2.count() == len(E) + 1)
chk("wide leads/pads over flakes (um2)", round(A(L2 & (D.R("top_hbn") + D.R("bottom_hbn") + g + gt)), 3), A(L2 & (D.R("top_hbn") + D.R("bottom_hbn") + g + gt)) == 0, hard=False)
pads_only = db.Region([w for w in W]).sized(D.um(-20)).sized(D.um(20))
chk("pads clear of template markers by 20 um", min_gap(pads_only, D.markers(), dbu, steps=(5, 10, 15, 20)), (min_gap(pads_only, D.markers(), dbu, steps=(5, 10, 15, 20)) is None))
# etch mask
chk("etch window does not cover protected shapes (um2)", round(A(L20 & L25), 4), A(L20 & L25) == 0)
chk("etch window does not cover L2 leads/pads (um2)", round(A(L20 & L2), 4), A(L20 & L2) == 0)
far = L20 - L15.sized(D.um(0.3))
chk("etch fingers do not overlap metal outside the stack (um2)", round(A(far & metal), 4), A(far & metal) == 0)
flakes = (D.R("top_hbn") + g + D.R("bottom_hbn") + gt).merged()
chk("every flake area is metal, protected or etched (um2 left)", round(A(flakes - metal - L25 - L20), 4), A(flakes - metal - L25 - L20) < 0.01)
# surviving graphene
surv = (g & (metal + L25)).merged()
comps = []
for c in surv.each():
    r = db.Region(c)
    comps.append(dict(area=round(A(r), 2), top_gate=not (r & TGm).is_empty(), electrodes=sum(1 for p in E if not (r & db.Region(p)).is_empty()), graphite_contact=not (r & L22).is_empty()))
comps.sort(key=lambda c: -c["area"])
dev = comps[0] if comps else {}
chk("device graphene joins top gate + all ohmic electrodes", dev, dev.get("top_gate") and dev.get("electrodes") == len(rec["arms"]))
side = ((g & (L23 + L25)) - TGm).merged()
multi = [round(A(db.Region(c)), 2) for c in side.each() if sum(1 for p in E if not (db.Region(c) & db.Region(p)).is_empty()) > 1]
chk("no graphene path between two electrodes outside the channel", multi, not multi)
chk("surviving graphene pieces", comps, True, hard=False)

ok = all(r["ok"] for r in rows if r["hard"])
for r in rows:
    print("%-4s %-62s %s" % ("PASS" if r["ok"] else ("FAIL" if r["hard"] else "WARN"), r["name"], json.dumps(r["value"])[:120]))
print("OVERALL:", "PASS" if ok else "FAIL")
json.dump(dict(ok=ok, checks=rows, frame=rec["frame"], arms=rec["arms"], pads=rec["pads"],
               etch=dict(area_um2=round(A(L20)), holes=[p.holes() for p in L20.each()])), open(a.out, "w"), indent=1)
sys.exit(0 if ok else 1)
