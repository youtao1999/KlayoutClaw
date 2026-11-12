"""Step D1 (dual-gated): graphite top gate + graphite bottom gate Hall bar, before routing.

Process this geometry is drawn for (see the device folder's instruction.md):
  1  one mask: CHF3 removes top-top hBN, O2 removes top graphite outside the top gate
     -> L31 (write, exposed = etched) = window - L1 top gate - L26 bottom-graphite protect
  2  one write: graphene edge contacts + top-gate contact + bottom-gate contact + leads + pads,
     CHF3 through the top hBN, evaporate          -> L23 fine (incl. tips), L24, L22, L2 wide
  3  final etch: fingers between electrodes; resist on the top gate, contacts and bridges
     -> L20 (etch_mask.py), protect scratch L25

Input : prepared.gds with template + flakes L16 top-top hBN, L14 top graphite, L10 top hBN,
        L11 graphene, L12 bottom hBN, L13 bottom graphite (local frame from L13).
Output: + L1 top gate (graphite that stays: channel + 1 um arms + tab + contact pad)
          L24 top-gate metal contact      L22 bottom-gate metal contact
          L26 bottom-graphite protect (where it is not under hBN)   L31 step-1 etch window
          L21 graphene contact tips (TEMPORARY, merged into L23 by post_route.py)
          L25 step-3 protect scratch      L2 bonding pads      L100 routing pins
        and design.json (--record).

Usage: python build_device.py --in prepared.gds --params params.json --out device.gds --record design.json
"""
import argparse
import json
import math
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
ap.add_argument("--out", required=True)
ap.add_argument("--record", required=True)
a = ap.parse_args()

P = load_params(a.params)
D = Design(a.inp, P)
dbu, um = D.dbu, D.um
for k in ("top_gate", "tg_contact", "graphite_contact", "bg_protect", "tg_etch", "tips_tmp",
          "etch_protect", "pads", "pins_tmp", "electrodes", "etch", "etch_outline"):
    D.clear(k)

g, bg, tgr = D.R("graphene"), D.R("graphite"), D.R("top_graphite")
hbn = (D.R("top_hbn") + D.R("bottom_hbn")).merged()
ttbn = D.R("top_top_hbn")
g_only = (g - bg).merged()
cy1, cy2 = P["channel"]["y"]
CH = P["channel"]
if "x" in CH:
    cx1, cx2 = CH["x"]
else:                                   # narrower than the bottom graphite by bg_inset on each side
    ysamp = [cy1 + (cy2 - cy1) * k / 20 for k in range(21)]
    cx1 = max(D.graphite_edge(y, "L") for y in ysamp) + CH["bg_inset"]
    cx2 = min(D.graphite_edge(y, "R") for y in ysamp) - CH["bg_inset"]
    if cx2 - cx1 < CH.get("min_width", 1.0):
        sys.exit("bottom graphite too narrow: channel would be %.2f um wide" % (cx2 - cx1))
# graphene pieces (e.g. twisted trilayer): the channel must lie where all pieces overlap
g_all = None
for ld in P["layers"].get("graphene_pieces", []):
    r = D.Rl(*ld)
    g_all = r if g_all is None else (g_all & r)
A, F = P["arms"], P["finger"]
W, GAPC = A["width"], A["contact_gap"]
TW, TL = A.get("tip_width", W), A["tip_length"]
BL = A["bridge_length"]

# ---- arm positions: pack opposite pairs at pitch = tip width + contact gap
if "y" in A:
    ys = list(A["y"])
else:
    y_lo, y_hi = A["y_range"]
    pitch = TW + GAPC
    n = int(math.floor((y_hi - y_lo - TW) / pitch + 1e-9)) + 1
    y0 = (y_lo + y_hi) / 2 - (n - 1) * pitch / 2
    ys = [round(y0 + i * pitch, 4) for i in range(n)]
ys = [y for y in ys if not any(e[0] - W / 2 < y < e[1] + W / 2 for e in A.get("exclude", []))]
arms = []
for y in ys:
    for s in A.get("sides", ["L", "R"]):
        arms.append(dict(name="%s%+.2f" % (s, y), side=s, y=[y - W / 2, y + W / 2]))
for c in P.get("current_leads", []):
    arms.append(dict(name=c["name"], side=c["side"], y=list(c["y"])))

tg = D.box(cx1, cy1, cx2, cy2)
tips, bridges, arm_core = db.Region(), db.Region(), db.Region()
report = []
for arm in arms:
    s, (y1, y2) = arm["side"], arm["y"]
    sgn = -1 if s == "L" else 1
    e1, e2 = D.graphite_edge(y1, s), D.graphite_edge(y2, s)
    edge = min(e1, e2) if s == "L" else max(e1, e2)       # worst (outermost) bottom-graphite edge
    fe = edge + sgn * F["overshoot"]                     # top-gate arm end, past the bottom-graphite edge
    tip_in = fe + sgn * BL
    tip_out = tip_in + sgn * TL
    ov = F["channel_overlap"]
    tg += D.box(fe, y1, cx1 + ov, y2) if s == "L" else D.box(cx2 - ov, y1, fe, y2)
    yc, th = (y1 + y2) / 2, max(TW, y2 - y1) / 2
    tbox = [min(tip_in, tip_out), yc - th, max(tip_in, tip_out), yc + th]
    tips += D.box(*tbox)
    B = P["bridge"]
    bx = sorted([tip_in + sgn * B["overlap"], fe - sgn * B["overlap"]])
    bridges += D.box(bx[0], y1 - B["extra_half_width"], bx[1], y2 + B["extra_half_width"]).sized(um(0.01))
    xa, xb = sorted([cx1 if s == "L" else cx2, tip_in])
    arm_core += D.box(xa, y1, xb, y2)                    # graphene needed: channel edge -> contact
    arm.update(bg_edge=round(edge, 3), tg_arm_end=round(fe, 3), overshoot=round(sgn * (fe - edge), 3),
               bridge=round(sgn * (tip_in - fe), 3), tip_box=[round(v, 3) for v in tbox])
    report.append(arm)

# ---- top-gate contact: metal pad (L24) on a top-graphite pad joined to the channel by tab(s)
TC = P["tg_contact"]
tgc = D.box(*TC["box"])
tg += tgc.sized(um(TC["margin"]))
for t in TC.get("tab", []):
    tg += D.box(*t)
tg = tg.merged()

# ---- bottom-gate contact (L22) on bottom graphite, outside the channel
GC = P["graphite_contact"]
gc = D.box(*GC["box"])

# ---- step 1: bottom-graphite protect + etch window
S1 = P["step1"]
bg_exposed = (bg - hbn).merged()
keep = bg_exposed
if "bg_protect_regions" in S1:          # protect only these exposed parts (others are etched in step 1)
    sel = db.Region()
    for b in S1["bg_protect_regions"]:
        sel += D.box(*b)
    keep = (bg_exposed & sel).merged()
bg_protect = (keep.sized(um(S1["bg_protect_grow"])) + gc.sized(um(S1["bg_protect_grow"]))).merged()
window = (tgr + ttbn).merged().sized(um(S1["window_grow"])).merged()
tg_etch = (window - tg - bg_protect).merged()

# ---- step 3 protect: top gate, bridges, every contact (all grown slightly)
S3 = P["protect"]
protect = (tg.sized(um(S3["top_gate_grow"])) + bridges + tips.sized(um(S3["contact_grow"]))
           + gc.sized(um(S3["contact_grow"])) + tgc.sized(um(S3["contact_grow"]))).merged()

# ---- pads ring (same rules as the top-gated recipe)
pp = P["pads"]
cx, cy = D.frame["center_um"]
mk = D.markers()
pads, pad_info = db.Region(), []
for k in range(pp["n"]):
    ang = math.radians(pp["start_deg"] + (-1 if pp["clockwise"] else 1) * 360.0 / pp["n"] * k)
    for rr in (pp["radius"], pp["bump_radius"]):
        x, y = cx + rr * math.cos(ang), cy + rr * math.sin(ang)
        b = db.DBox(x - pp["size"] / 2, y - pp["size"] / 2, x + pp["size"] / 2, y + pp["size"] / 2)
        if (db.Region(b.enlarged(pp["marker_clearance"], pp["marker_clearance"]).to_itype(dbu)) & mk).is_empty():
            break
    else:
        sys.exit("pad %d collides with markers even at bump_radius" % k)
    pads.insert(b.to_itype(dbu))
    pad_info.append(dict(index=k, center=[round(x, 1), round(y, 1)], radius=rr))
n_nets = len(arms) + 2
if pp["n"] < n_nets:
    sys.exit("pads.n = %d < %d nets (%d graphene contacts + top gate + bottom gate)" % (pp["n"], n_nets, len(arms)))

D.put("top_gate", tg)
D.put("tg_contact", tgc)
D.put("graphite_contact", gc)
D.put("bg_protect", bg_protect)
D.put("tg_etch", tg_etch)
D.put("tips_tmp", tips.merged())
D.put("etch_protect", protect)
D.put("pads", pads)
D.put("pins_tmp", (tips + gc + tgc).merged())

# ---- self-checks
nz = lambda d: 99.0 if d is None else d     # None = farther than the 10 um search range
Ar = lambda r: r.area() * dbu * dbu
frac = lambda r, inside: round(Ar(r & inside) / Ar(r), 4) if Ar(r) else 0.0
chan = D.box(cx1, cy1, cx2, cy2)
tip_list = list(tips.merged().each())
checks = {
    "n_graphene_contacts": len(arms),
    "channel_x_local": [round(cx1, 3), round(cx2, 3)], "channel_width": round(cx2 - cx1, 3),
    "channel_inside_graphene_bg_topgraphite": Ar(chan - (g & bg & tgr)) < 1e-3,
    "channel_inside_all_graphene_pieces": (Ar(chan - g_all) < 1e-3) if g_all is not None else None,
    "channel_margin_to_bg_edge": dist(chan, D.box(-60, cy1, 60, cy2) - bg, dbu),
    "arms_and_bridges_on_all_pieces_frac": frac(arm_core, g_all) if g_all is not None else None,
    "tips_on_all_pieces_frac": frac(tips, g_all) if g_all is not None else None,
    "top_gate_in_top_graphite_frac": frac(tg, tgr),
    "top_gate_in_top_hbn_frac": frac(tg, D.R("top_hbn")),
    "arms_and_bridges_on_graphene_frac": frac(arm_core, g),
    "tips_on_graphene_only_frac": frac(tips, g_only),
    "tip_overshoot_range": [min(r["overshoot"] for r in report), max(r["overshoot"] for r in report)],
    "tips_to_top_gate_gap": dist(tips, tg, dbu),
    "tips_min_gap": space(tips, dbu),
    "n_tip_polygons": len(tip_list),
    "tg_contact_in_top_graphite_frac": frac(tgc, tgr),
    "tg_contact_margin_in_top_gate": Ar(tgc.sized(um(TC["margin"] - 0.05)) - tg) < 1e-3,
    "tg_contact_over_graphene_um2": round(Ar(tgc & g), 3),
    "graphite_contact_in_bg_frac": frac(gc, bg),
    "graphite_contact_on_exposed_bg_frac": frac(gc, bg_exposed),
    "graphite_contact_to_graphene_gap": dist(gc, g, dbu),
    "graphite_contact_to_top_gate_gap": dist(gc, tg, dbu),
    "step1_top_graphite_left_unexposed_um2": round(Ar(tgr - tg - bg_protect - tg_etch), 4),
    "step1_window_over_exposed_bg_um2": round(Ar(tg_etch & bg_exposed), 4),   # etched on purpose if not in bg_protect_regions
    "step1_window_over_protected_bg_um2": round(Ar(tg_etch & keep), 4),
    "step1_top_graphite_kept_in_bg_protect_um2": round(Ar((tgr & bg_protect) - tg), 4),
    # gate short: top graphite left after step 1 (L1 + what L26 protects) lying on exposed bottom graphite
    "top_graphite_on_exposed_bg_after_step1_um2": round(Ar(((tg + (tgr & bg_protect)) & bg_exposed)), 4),
    "top_gate_over_exposed_bg_um2": round(Ar(tg & bg_exposed), 4),
}
ok = (checks["channel_inside_graphene_bg_topgraphite"] and checks["channel_inside_all_graphene_pieces"] is not False
      and checks["top_gate_in_top_graphite_frac"] >= 0.99
      and checks["arms_and_bridges_on_graphene_frac"] >= 0.99
      and checks["tips_on_graphene_only_frac"] >= A.get("min_tip_graphene_frac", 0.99)
      and checks["n_tip_polygons"] == len(arms)
      and checks["tip_overshoot_range"][0] >= 0.5 - 1e-3
      and nz(checks["tips_to_top_gate_gap"]) >= BL - 0.01
      and nz(checks["tips_min_gap"]) >= GAPC - 0.01
      and checks["tg_contact_in_top_graphite_frac"] >= 0.99 and checks["tg_contact_margin_in_top_gate"]
      and checks["graphite_contact_in_bg_frac"] >= 0.99
      and nz(checks["graphite_contact_to_graphene_gap"]) >= 1.0
      and nz(checks["graphite_contact_to_top_gate_gap"]) >= 1.0
      and checks["step1_top_graphite_left_unexposed_um2"] < 0.01
      and checks["top_graphite_on_exposed_bg_after_step1_um2"] < 0.01
      and checks["step1_window_over_protected_bg_um2"] == 0)

D.write(a.out)
rec = dict(sample=P["sample"], frame=D.frame, channel=[round(v, 4) for v in (cx1, cy1, cx2, cy2)], arms=report, pads=pad_info, checks=checks, ok=ok)
json.dump(rec, open(a.record, "w"), indent=1)
print(json.dumps(dict(frame=D.frame, checks=checks, ok=ok), indent=1))
for r in report:
    print("%-8s bg_edge %7.3f  tg_arm_end %7.3f  overshoot %.2f  bridge %.2f  tip %s" % (
        r["name"], r["bg_edge"], r["tg_arm_end"], r["overshoot"], r["bridge"], r["tip_box"]))
sys.exit(0 if ok else 2)
