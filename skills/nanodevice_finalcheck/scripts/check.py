"""Final check: shorts by set arithmetic on the finished design (user's formulation, 2026-11-17).

Primed sets, the pieces after both etches (7/0 deep, to the bottom hBN, which shields the bottom
graphite beneath it; then 4/0 ∪ 4/1 shallow, to the top hBN):
  TG'   = (TG − 7/0) − (4/0 ∪ 4/1)        TTBN' = (TTBN − 7/0) − (4/0 ∪ 4/1)
  TBN'  = TBN − 7/0                        Gr'   = Gr − 7/0   (Gr = union of the graphene pieces)
  BBN'  = BBN                              BG'   = BG
Star sets, each device with its electrodes (an electrode = its 2/0 path with its 2/1 pad and
tentacle; its role from its head: arm -> graphene, top-gate contact 5/2 -> top gate, exposed bottom
graphite -> back gate):
  TG* = TG' ∪ top-gate leads     BG* = BG' ∪ back-gate leads     Gr* = Gr' ∪ arm electrodes
The 2/0 etch goes all the way down to the bare substrate, so an electrode contacts every conductor
it overlaps: hBN insulates only between two flakes, never between metal and a flake. With L_TG,
L_BG, L_Gr the top-gate, back-gate and arm electrodes:
1. ((TG' ∩ Gr') − TBN') ∪ (L_TG ∩ Gr*) ∪ (TG* ∩ L_Gr) = ∅
2. ((TG' ∩ BG') − (BBN' ∪ TBN')) ∪ (L_TG ∩ BG*) ∪ (TG* ∩ L_BG) = ∅
3. ((BG' ∩ Gr') − BBN') ∪ (L_BG ∩ Gr*) ∪ (BG* ∩ L_Gr) = ∅
4. no electrodes shorted together: any two electrodes are disjoint, and no conductor piece
   outside the devices (a piece of TG', Gr' or BG' not on the channel: debris) touches two of them.

Usage: python check.py --flakes prepared.gds --params params.json --writes result.gds
"""
import argparse
import os
import sys

import klayout.db as db

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "nanodevice_topgate", "scripts"))
from tg_lib import bg_terminal, graphene, layer, load_params, parse, read_layer, record  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--flakes", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--writes", required=True)
a = parse(ap, "finalcheck/check", check=True)

Pm = load_params(a.params)
F = lambda k: read_layer(a.flakes, "%d/%d" % tuple(Pm["layers"][k]))[0]
Wr = lambda s: read_layer(a.writes, s)[0]
E7, E4, ch, arms, I = Wr("7/0"), (Wr("4/0") + Wr("4/1")).merged(), Wr("5/0"), Wr("5/1"), Wr("5/2")
TG, TBN, BBN, BG = F("top_graphite"), F("top_hbn"), F("bottom_hbn"), F("graphite")
Gr = graphene(a.flakes, Pm)[0]
dbu = 0.001

TGp = ((TG - E7) - E4).merged()
TBNp = TBN - E7
Grp = (Gr - E7).merged()
BBNp, BGp = BBN, BG.merged()

ly = db.Layout()
ly.read(a.writes)
dbu = ly.dbu
paths = [db.Region(s.polygon) for s in ly.top_cell().shapes(ly.layer(*layer("2/0"))).each()]
big = Wr("2/1")
X = bg_terminal(a.flakes, Pm, a.writes)
electrodes = []                                  # (role, region: path + its pad and tentacle)
for L in paths:
    role = [n for n, t in [("graphene", arms - ch), ("top gate", I), ("back gate", X)] if not (L & t).is_empty()]
    pad = db.Region([p for p in big.each() if not (db.Region(p) & L).is_empty()])
    pad = big.interacting(pad)                   # tentacle -> its pad
    electrodes.append((role[0] if len(role) == 1 else "?", (L + pad).merged()))
by = lambda r: sum((e for n, e in electrodes if n == r), db.Region()).merged()

Ltg, Lbg, Lgr = by("top gate"), by("back gate"), by("graphene")
TGs, BGs, Grs = (TGp + Ltg).merged(), (BGp + Lbg).merged(), (Grp + Lgr).merged()
um2 = lambda r: r.area() * dbu ** 2
checks = [("1", "top gate - graphene: ((TG' ∩ Gr') − TBN') ∪ (L_TG ∩ Gr*) ∪ (TG* ∩ L_Gr) = ∅",
           ((TGp & Grp) - TBNp) + (Ltg & Grs) + (TGs & Lgr)),
          ("2", "top gate - back gate: ((TG' ∩ BG') − (BBN' ∪ TBN')) ∪ (L_TG ∩ BG*) ∪ (TG* ∩ L_BG) = ∅",
           ((TGp & BGp) - (BBNp + TBNp)) + (Ltg & BGs) + (TGs & Lbg)),
          ("3", "back gate - graphene: ((BG' ∩ Gr') − BBN') ∪ (L_BG ∩ Gr*) ∪ (BG* ∩ L_Gr) = ∅",
           ((BGp & Grp) - BBNp) + (Lbg & Grs) + (BGs & Lgr))]
fails = []
for n, name, r in checks:
    print("%s %s. %s%s" % ("PASS" if r.is_empty() else "FAIL", n, name, "" if r.is_empty() else ": %.4f um2" % um2(r)))
    fails += [] if r.is_empty() else [n]

bad = [k for k, (n, _) in enumerate(electrodes) if n == "?"]
pairs = set()
debris = [p for reg in (TGp, Grp, BGp) for p in reg.each() if (db.Region(p) & ch).is_empty()]
for i in range(len(electrodes)):
    for j in range(i):
        if not (electrodes[i][1] & electrodes[j][1]).is_empty():
            pairs.add((j, i))
for p in debris:
    on = [k for k, (_, e) in enumerate(electrodes) if not (db.Region(p) & e).is_empty()]
    pairs.update((on[x], on[y]) for x in range(len(on)) for y in range(x + 1, len(on)))
ok4 = not pairs and not bad
print("%s 4. no electrodes shorted together%s" % ("PASS" if ok4 else "FAIL",
      "" if ok4 else ": " + ", ".join("%d-%d" % p for p in sorted(pairs)) + (" no role: %s" % bad if bad else "")))
print("electrodes: %s; debris pieces %d" % (", ".join("%d %s" % (sum(n == r for n, _ in electrodes), r)
      for r in ("graphene", "top gate", "back gate")), len(debris)))
record(a.params, "finalcheck/check", passed=not fails and ok4, failed=fails + ([] if ok4 else ["4"]),
       electrodes={r: sum(n == r for n, _ in electrodes) for r in ("graphene", "top gate", "back gate")})
sys.exit(1 if fails or not ok4 else 0)
