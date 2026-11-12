"""Step D1: build the top-gated Hall bar geometry from params (before routing).

Input : GDS with template (+ remapped L111/L112) and committed flakes L10-L13 in chip coords.
Output: same GDS plus
  L1  top gate  (channel strip + one finger per arm, finger ends = graphite edge + overshoot)
  L5  top-gate lead (path from inside the channel, along the strip axis away from gate_end)
  L21 ohmic contact tips (TEMPORARY: routing pins/obstacles; merged into L23 by post_route.py)
  L22 graphite (bottom-gate) contact
  L25 etch-protect scratch (finger-end -> tip bridges + graphite-contact patch)
  L2  bonding pads (ring; pads that crowd template markers are pushed out)
  L100 routing pins (tips + graphite contact + top-gate-lead pin)
and a JSON design record (--record) with the local frame and every tip box.

Usage: python build_device.py --in prepared.gds --params params.json --out device.gds --record design.json
"""
import argparse
import json
import math
import sys

import klayout.db as db

from recipe_lib import Design, load_params, min_gap

ap = argparse.ArgumentParser()
ap.add_argument("--in", dest="inp", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--record", required=True)
a = ap.parse_args()

P = load_params(a.params)
D = Design(a.inp, P)
dbu = D.dbu
for k in ("top_gate", "top_gate_lead", "tips_tmp", "graphite_contact", "etch_protect", "pads", "pins_tmp", "electrodes", "etch", "etch_outline"):
    D.clear(k)

g, gt = D.R("graphene"), D.R("graphite")
g_only = (g - gt).merged()
cx1, cx2 = P["channel"]["x"]
cy1, cy2 = P["channel"]["y"]
F, B, TP = P["finger"], P["bridge"], P["tips"]

# ---- arms: probes on both sides + current leads
arms = []
hw = P["probes"]["arm_width"] / 2
for y in P["probes"]["y"]:
    arms.append(dict(name="L%+.1f" % y, side="L", y=[y - hw, y + hw]))
    arms.append(dict(name="R%+.1f" % y, side="R", y=[y - hw, y + hw]))
for c in P["current_leads"]:
    arms.append(dict(name=c["name"], side=c["side"], y=list(c["y"])))

tg = D.box(cx1, cy1, cx2, cy2)
tips, bridges = db.Region(), db.Region()
report = []
for arm in arms:
    s, (y1, y2) = arm["side"], arm["y"]
    tip_in, tip_out = (TP["L"][1], TP["L"][0]) if s == "L" else (TP["R"][0], TP["R"][1])
    sgn = -1 if s == "L" else 1                       # outward direction in x'
    edge = min(D.graphite_edge(y1, s), D.graphite_edge(y2, s)) if s == "L" else max(D.graphite_edge(y1, s), D.graphite_edge(y2, s))
    fe = edge + sgn * F["overshoot"]                  # finger end: past the graphite edge
    if sgn * (tip_in - fe) < F["min_gap"]:            # keep >= min_gap to the tip
        fe = tip_in - sgn * F["min_gap"]
    bumped = False
    if sgn * (tip_in - fe) < F["bump_below_gap"]:     # still tight -> move tip outward
        tip_in += sgn * F["bump"]; tip_out += sgn * F["bump"]; bumped = True
    ov = F["channel_overlap"]
    if s == "L":
        tg += D.box(fe, y1, cx1 + ov, y2)
    else:
        tg += D.box(cx2 - ov, y1, fe, y2)
    th = TP["extra_half_height"]
    tbox = [min(tip_in, tip_out), y1 - th, max(tip_in, tip_out), y2 + th]
    tips += D.box(*tbox)
    ew = B["extra_half_width"]
    bx = sorted([tip_in - sgn * (-B["overlap"]), fe - sgn * B["overlap"]])  # overlap into tip and onto finger
    bridges += D.box(bx[0], y1 - ew, bx[1], y2 + ew)
    arm.update(graphite_edge=round(edge, 3), finger_end=round(fe, 3), overshoot=round(sgn * (fe - edge), 3),
               gap=round(sgn * (tip_in - fe), 3), tip_box=[round(v, 3) for v in tbox], tip_bumped=bumped)
    report.append(arm)

tg = tg.merged()
gcb = P["graphite_contact"]["box"]
gc = D.box(*gcb)
gc_protect = D.box(gcb[0] - P["graphite_contact"]["protect_grow"], gcb[1] - P["graphite_contact"]["protect_grow"],
                   gcb[2] + P["graphite_contact"]["protect_grow"], gcb[3] + P["graphite_contact"]["protect_grow"])
protect = (bridges + gc_protect).merged().sized(D.um(B["grow"])).merged()

tl = P["tg_lead"]
lead = D.path([(tl["x"], tl["y"][0]), (tl["x"], tl["y"][1])], tl["width"])
hp = tl["pin"] / 2
tg_pin = D.box(tl["x"] - hp, tl["y"][1] - hp, tl["x"] + hp, tl["y"][1] + hp)

# ---- pads ring
pp = P["pads"]
cx, cy = D.frame["center_um"]
mk = D.markers()
pads = db.Region()
pad_info = []
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

D.put("top_gate", tg)
D.put("top_gate_lead", lead)
D.put("tips_tmp", tips.merged())
D.put("graphite_contact", gc)
D.put("etch_protect", protect)
D.put("pads", pads)
D.put("pins_tmp", (tips + gc + tg_pin).merged())

# ---- self-checks
chan = D.box(cx1, cy1, cx2, cy2)
checks = {
    "channel_inside_graphene_and_graphite": (chan - (g & gt)).is_empty(),
    "channel_margin_to_graphite_edge_ge_1.5": (chan - (g & gt).sized(D.um(-1.5))).area() * dbu * dbu < 0.01,
    "tips_on_graphene_only_frac": round((tips & g_only).area() / tips.area(), 4),
    "top_gate_on_graphene_frac": round((tg & g).area() / tg.area(), 4),
    "finger_overshoot_range": [min(r["overshoot"] for r in report), max(r["overshoot"] for r in report)],
    "finger_to_tip_gap_min": min(r["gap"] for r in report),
    "graphite_contact_in_graphite_frac": round((gc & gt).area() / gc.area(), 4),
    "graphite_contact_to_top_gate_gap": min_gap(gc, tg + lead, dbu),
    "bridges_separate": protect.count() == len(arms) + 1,
    "tg_lead_to_tips_gap": min_gap(lead, tips, dbu),
    "tips_min_gap": min(min_gap(db.Region(x), db.Region(y), dbu) or 9 for i, x in enumerate(tips.each()) for y in list(tips.each())[i + 1:]),
}
ok = (checks["channel_inside_graphene_and_graphite"] and checks["tips_on_graphene_only_frac"] >= 0.99
      and checks["finger_overshoot_range"][0] >= 0.5 and checks["finger_to_tip_gap_min"] >= 0.5
      and checks["graphite_contact_in_graphite_frac"] >= 0.99 and (checks["graphite_contact_to_top_gate_gap"] or 9) >= 1.0
      and checks["bridges_separate"])

D.write(a.out)
rec = dict(sample=P["sample"], frame=D.frame, arms=report, pads=pad_info, checks=checks, ok=ok)
json.dump(rec, open(a.record, "w"), indent=1)
print(json.dumps(dict(frame=D.frame, checks=checks, ok=ok), indent=1))
for r in report:
    print("%-6s edge %7.3f  finger_end %7.3f  overshoot %.2f  gap %.2f  tip %s%s" % (
        r["name"], r["graphite_edge"], r["finger_end"], r["overshoot"], r["gap"], r["tip_box"], "  (tip bumped)" if r["tip_bumped"] else ""))
sys.exit(0 if ok else 2)
