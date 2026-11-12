"""Step V (dual-gated): design-rule / connectivity verification of the final GDS.

Usage: python verify.py --gds result.gds --params params.json --record design.json --out verify.json
Prints a PASS/FAIL/WARN table and writes verify.json. Exit 0 only if every hard check passes.
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
ap.add_argument("--gds", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--record", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()

P = load_params(a.params)
rec = json.load(open(a.record))
D = Design(a.gds, P)
dbu, um = D.dbu, D.um
A = lambda r: r.area() * dbu * dbu
frac = lambda r, inside: round(A(r & inside) / A(r), 4) if A(r) else 0.0
gap = lambda x, y: dist(x, y, dbu)
nz = lambda d: 99.0 if d is None else d     # None = farther than the 10 um search range

g, bg, tgr = D.R("graphene"), D.R("graphite"), D.R("top_graphite")
thbn, bhbn, ttbn = D.R("top_hbn"), D.R("bottom_hbn"), D.R("top_top_hbn")
L1, L2, L20, L22, L23, L24, L25, L26, L31, L15 = (D.R(k) for k in (
    "top_gate", "pads", "etch", "graphite_contact", "electrodes", "tg_contact", "etch_protect", "bg_protect", "tg_etch", "etch_outline"))
AR = P["arms"]
chan = D.box(*rec["channel"])                                   # local frame, from build_device.py
g_all = None
for ld in P["layers"].get("graphene_pieces", []):
    g_all = D.Rl(*ld) if g_all is None else (g_all & D.Rl(*ld))
tips = db.Region()
for arm in rec["arms"]:
    tips += D.box(*arm["tip_box"])
tips = tips.merged()
E = list(L23.each())
kind = ["tg" if not (db.Region(p) & L24).is_empty() else ("bg" if not (db.Region(p) & L22).is_empty() else "ohmic") for p in E]
ohm = db.Region([p for p, k in zip(E, kind) if k == "ohmic"])
tgn = (db.Region([p for p, k in zip(E, kind) if k == "tg"]) + L24).merged()
bgn = (db.Region([p for p, k in zip(E, kind) if k == "bg"]) + L22).merged()
metal = (L22 + L23 + L24).merged()
W = list(L2.each())
n_arms = len(rec["arms"])

rows = []
def chk(name, value, ok, hard=True):
    rows.append(dict(name=name, value=value, ok=bool(ok), hard=hard))

# ---- device geometry
chk("channel inside graphene AND bottom graphite AND top gate", round(A(chan - (g & bg & L1)), 4), A(chan - (g & bg & L1)) < 1e-3)
inset = P["channel"].get("bg_inset", 1.5)
cmar = dist(chan, D.box(-60, rec["channel"][1], 60, rec["channel"][3]) - bg, dbu)
chk("channel inset from bottom-graphite edges >= %.2f um" % (inset - 0.05), cmar, nz(cmar) >= inset - 0.06)
if g_all is not None:
    chk("channel inside all graphene pieces (trilayer)", round(A(chan - g_all), 4), A(chan - g_all) < 1e-3)
    chk("contact tips on all graphene pieces (fraction)", frac(tips, g_all), frac(tips, g_all) >= 0.99, hard=False)
chk("top gate inside top graphite (fraction)", frac(L1, tgr), frac(L1, tgr) >= 0.99)
chk("top gate inside top hBN (fraction)", frac(L1, thbn), frac(L1, thbn) >= 0.99, hard=False)
ovs = [r["overshoot"] for r in rec["arms"]]
chk("top-gate arms past bottom-graphite edge 0.5-1.0 um", [min(ovs), max(ovs)], min(ovs) >= 0.5 - 1e-3 and max(ovs) <= 1.0 + 1e-3)
chk("graphene contacts (count)", n_arms, n_arms >= 2)
chk("contact tips on graphene-only (fraction) >= %.2f" % AR.get("min_tip_graphene_frac", 0.99), frac(tips, g - bg), frac(tips, g - bg) >= AR.get("min_tip_graphene_frac", 0.99))
chk("contact tips part of electrodes (L23)", round(A(tips - L23), 4), A(tips - L23) < 0.02)
tl = list(tips.each())
tmin = space(tips, dbu)
chk("contact-contact gap >= %.1f um" % AR["contact_gap"], tmin, nz(tmin) >= AR["contact_gap"] - 0.01)
chk("contact tips to top gate >= %.1f um (bridge)" % AR["bridge_length"], gap(tips, L1), nz(gap(tips, L1)) >= AR["bridge_length"] - 0.01)
chk("top-gate contact inside top graphite (fraction)", frac(L24, tgr), frac(L24, tgr) >= 0.99)
chk("top-gate contact inside top gate L1 (fraction)", frac(L24, L1), frac(L24, L1) >= 0.99)
chk("bottom-gate contact inside bottom graphite (fraction)", frac(L22, bg), frac(L22, bg) >= 0.99)
chk("bottom-gate contact to graphene >= 1 um", gap(L22, g), nz(gap(L22, g)) >= 1.0)
chk("bottom-gate contact to top gate >= 1 um", gap(L22, L1), nz(gap(L22, L1)) >= 1.0)

# ---- step 1 (top-top hBN + top graphite etch)
chk("step1 window does not cover top gate / bg protect (um2)", round(A(L31 & (L1 + L26)), 4), A(L31 & (L1 + L26)) == 0)
chk("step1 removes all top graphite outside top gate (um2 left)", round(A(tgr - L1 - L26 - L31), 4), A(tgr - L1 - L26 - L31) < 0.01)
chk("step1 removes all top-top hBN outside top gate (um2 left)", round(A(ttbn - L1 - L26 - L31), 4), A(ttbn - L1 - L26 - L31) < 0.01, hard=False)
bg_exp = (bg - thbn - bhbn).merged()
S1 = P.get("step1", {})
want = bg_exp
if "bg_protect_regions" in S1:          # only these exposed parts are protected; the rest is etched on purpose
    sel = db.Region()
    for b in S1["bg_protect_regions"]:
        sel += D.box(*b)
    want = (bg_exp & sel).merged()
chk("step1 protects the chosen exposed bottom graphite (um2 unprotected)", round(A(want - L26), 4), A(want - L26) < 0.01)
short = ((L1 + (tgr & L26)) & bg_exp).merged()
chk("no top graphite left on exposed bottom graphite after step 1 (gate short, um2)", round(A(short), 4), A(short) < 0.01)
bg_after = (bg - (L31 & bg_exp)).merged()
conn = [p for p in bg_after.each() if not (db.Region(p) & L22).is_empty()]
ok_conn = bool(conn) and not (db.Region(conn[0]) & chan).is_empty()
chk("bottom-gate contact still joins the bottom graphite under the channel after step 1", ok_conn, ok_conn)
chk("top graphite kept outside top gate (inside bg protect, um2)", round(A((tgr & L26) - L1), 4), A((tgr & L26) - L1) < 0.01, hard=False)

# ---- step 2 (electrodes + pads, CHF3 under all metal)
chk("electrodes = contacts + top gate + bottom gate", dict(ohmic=kind.count("ohmic"), tg=kind.count("tg"), bg=kind.count("bg")),
    kind.count("ohmic") == n_arms and kind.count("tg") == 1 and kind.count("bg") == 1)
emin = space(L23, dbu)
chk("electrode-electrode min gap >= %.1f um" % P["post_route"]["min_electrode_gap"], emin, nz(emin) >= P["post_route"]["min_electrode_gap"] - 0.01)
chk("graphene-contact metal over bottom graphite (um2)", round(A(ohm & bg), 4), A(ohm & bg) == 0)
chk("graphene-contact metal to top gate >= %.1f um" % P["post_route"]["tg_clearance"], gap(ohm, L1), nz(gap(ohm, L1)) >= P["post_route"]["tg_clearance"] - 0.01)
chk("top-gate metal outside L1 to graphene >= %.1f um" % P["post_route"]["g_clearance"], gap(tgn - L1, g), nz(gap(tgn - L1, g)) >= P["post_route"]["g_clearance"] - 0.01)
chk("bottom-gate metal to graphene >= %.1f um" % P["post_route"]["g_clearance"], gap(bgn, g), nz(gap(bgn, g)) >= P["post_route"]["g_clearance"] - 0.01)
chk("bottom-gate metal to top gate", gap(bgn, L1), nz(gap(bgn, L1)) >= P["post_route"]["tg_clearance"] - 0.01)
chk("each electrode joins exactly one wide lead", [sum(1 for w in W if not (db.Region(p) & db.Region(w)).is_empty()) for p in E],
    all(sum(1 for w in W if not (db.Region(p) & db.Region(w)).is_empty()) == 1 for p in E))
chk("wide leads/pads = nets, none touching", L2.count(), L2.count() == len(E))
chk("wide leads/pads over flakes (um2)", round(A(L2 & (thbn + bhbn + g + bg + tgr)), 3), A(L2 & (thbn + bhbn + g + bg + tgr)) == 0, hard=False)
pads_only = L2.sized(um(-20)).sized(um(20))
chk("pads clear of template markers by 20 um", dist(pads_only, D.markers(), dbu, 20.0), dist(pads_only, D.markers(), dbu, 20.0) is None)

# ---- step 3 (final etch)
chk("final etch does not cover protected shapes (um2)", round(A(L20 & L25), 4), A(L20 & L25) == 0)
chk("final etch does not cover the top gate (um2)", round(A(L20 & L1), 4), A(L20 & L1) == 0)
chk("final etch does not cover L2 leads/pads (um2)", round(A(L20 & L2), 4), A(L20 & L2) == 0)
far = L20 - L15.sized(um(0.3))
chk("etch fingers do not overlap metal outside the stack (um2)", round(A(far & metal), 4), A(far & metal) == 0)
flakes = (ttbn + tgr + thbn + g + bhbn + bg).merged()
chk("every flake area is metal, protected or etched (um2 left)", round(A(flakes - metal - L25 - L20), 4), A(flakes - metal - L25 - L20) < 0.01)

# ---- surviving graphene: Hall bar with long arms
surv = (g & (metal + L25)).merged()
comps = []
for c in surv.each():
    r = db.Region(c)
    comps.append(dict(area=round(A(r), 2), top_gate=not (r & L1).is_empty(),
                      contacts=sum(1 for p, k in zip(E, kind) if k == "ohmic" and not (r & db.Region(p)).is_empty()),
                      tg_metal=not (r & (tgn - L1)).is_empty(), bg_metal=not (r & bgn).is_empty()))
comps.sort(key=lambda c: -c["area"])
dev = comps[0] if comps else {}
chk("device graphene joins top gate + all graphene contacts", dev, dev.get("top_gate") and dev.get("contacts") == n_arms)
chk("no surviving graphene touches gate metal", [c for c in comps if c["tg_metal"] or c["bg_metal"]], not any(c["tg_metal"] or c["bg_metal"] for c in comps))
side = ((g & (L23 + L25)) - L1).merged()
multi = [round(A(db.Region(c)), 2) for c in side.each()
         if sum(1 for p, k in zip(E, kind) if k == "ohmic" and not (db.Region(c) & db.Region(p)).is_empty()) > 1]
chk("no graphene path between two contacts outside the top gate", multi, not multi)
chk("surviving graphene pieces", comps, True, hard=False)

ok = all(r["ok"] for r in rows if r["hard"])
for r in rows:
    print("%-4s %-66s %s" % ("PASS" if r["ok"] else ("FAIL" if r["hard"] else "WARN"), r["name"], json.dumps(r["value"])[:110]))
print("OVERALL:", "PASS" if ok else "FAIL")
json.dump(dict(ok=ok, checks=rows, frame=rec["frame"], arms=rec["arms"], pads=rec["pads"],
               etch=dict(area_um2=round(A(L20)), holes=[p.holes() for p in L20.each()])), open(a.out, "w"), indent=1)
sys.exit(0 if ok else 1)
