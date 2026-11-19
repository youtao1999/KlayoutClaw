"""Top gate, final checks (run after flakes.py, channel.py, arms.py, contacts.py, electrodes.py). Exit 1 if any fails.

1 arms      subset of the active region (intersection of all graphene pieces)
2 channel   subset of the bottom (back-gate) graphite
3 contacts  subset of top hBN minus graphene (union of all graphene pieces)
4 connected channel, arms, contacts and electrodes form one polygon: the top gate is not cut into pieces
5 top gate  (channel + arms + contacts + electrodes) strict subset of the top graphite
6 electrodes subset of top hBN (top hBN separates them from the graphene)
7 electrodes each one touches the channel (comes out of the channel, not an arm)
8 corridors  contacts and electrodes stay out of the arm corridors (tg_lib.arm_keepout)

Usage: python check.py --flakes prepared.gds --params params.json --writes result.gds
                       [--channel 5/0] [--arms 5/1] [--contacts 5/2] [--electrodes 5/3]
                       [--clearance 0.3] [--escape 50]
"""
import argparse
import sys

import klayout.db as db

from tg_lib import CLEARANCE, ESCAPE, Design, arm_keepout, graphene, load_params, parse, read_layer

ap = argparse.ArgumentParser()
ap.add_argument("--flakes", required=True, help="GDS with the bottom graphite, for the local frame")
ap.add_argument("--params", required=True)
ap.add_argument("--writes", required=True)
ap.add_argument("--channel", default="5/0")
ap.add_argument("--arms", default="5/1")
ap.add_argument("--contacts", default="5/2")
ap.add_argument("--electrodes", default="5/3")
ap.add_argument("--clearance", type=float, default=CLEARANCE)
ap.add_argument("--escape", type=float, default=ESCAPE)
a = parse(ap, "topgate/check", check=True)

P = load_params(a.params)
lm = P["layers"]
R = lambda s: read_layer(a.writes, s if isinstance(s, str) else "%d/%d" % tuple(s))[0]
_, dbu = read_layer(a.writes, a.channel)
um2 = lambda r: r.area() * dbu ** 2
ch, arms, cts = R(a.channel), R(a.arms), R(a.contacts)
g_union, active = graphene(a.writes, P)
tgr = R(lm["top_graphite"])
el = R(a.electrodes)
tg = (ch + arms + cts + el).merged()
corr = arm_keepout(Design(a.flakes, P), ch, arms, a.clearance, a.escape)
loose = sum(1 for p in el.each() if (ch & db.Region(p)).is_empty())

for name, r in (("channel", ch), ("arms", arms), ("top-gate contacts", cts), ("top-gate electrodes", el)):
    if r.is_empty():
        sys.exit("FAIL %s is empty" % name)

def outside(r, region, what):
    """failure message if r is not a subset of region, else None"""
    x = um2(r - region)
    return "%.4f um2 outside %s" % (x, what) if x > 0 else None


res = [   # (check, failure message or None)
    ("1 arms in active region", outside(arms, active, "the active region")),
    ("2 channel in bottom graphite", outside(ch, R(lm["graphite"]), "the bottom graphite")),
    ("3 contacts in top hBN - graphene", outside(cts, R(lm["top_hbn"]) - g_union, "top hBN - graphene")),
    ("4 top gate connected", "top gate is %d pieces, not 1" % tg.count() if tg.count() != 1 else None),
    ("5 top gate strict subset of top graphite", outside(tg, tgr, "the top graphite")
     or ("top gate equals the top graphite" if (tgr - tg).is_empty() else None)),
    ("6 electrodes in top hBN", outside(el, R(lm["top_hbn"]), "top hBN")),
    ("7 every electrode touches the channel", "%d electrode(s) do not touch the channel" % loose if loose else None),
    ("8 contacts and electrodes out of the arm corridors",
     "%.4f um2 inside the corridors" % um2((cts + el) & corr) if um2((cts + el) & corr) > 0 else None),
]
for name, msg in res:
    print("%s  %s%s" % ("FAIL" if msg else "PASS", name, "  (%s)" % msg if msg else ""))
ok = not any(msg for _, msg in res)
print("top gate area %.3f um2, top graphite %.3f um2" % (um2(tg), um2(tgr)))
sys.exit(0 if ok else 1)
