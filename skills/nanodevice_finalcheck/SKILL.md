---
name: nanodevice_finalcheck
description: Final electrical check of a finished six-piece dual-gated graphene device design (after nanodevice_topgate, _contacts, _electrodes, _pads, _fingers). Pure set arithmetic on the pieces left after both etches, each device joined with its electrodes: top gate, graphene and back gate must not be shorted together, and no two electrodes may be shorted.
---

# nanodevice_finalcheck -- shorts by set arithmetic

Status: in development (2026-11-17). One script, checks 1-4. Writes nothing.

User (2026-11-17): check that none of the electrodes are shorted together and that the back
gate, top gate and graphene are not shorted together, written as set arithmetic.

## Rules (user's formulation, 2026-11-17)

Process (user, 2026-11-17): 7/0 is the deep etch, down to the bottom hBN; it leaves the
bottom graphite alone, which sits underneath the bottom hBN. 4/0 ∪ 4/1 is the shallow etch,
down to the top hBN. The 2/0 etch goes all the way down to the bare substrate, so an
electrode contacts every conductor it overlaps.

Primed sets, each piece after both etches:
- TG' = (TG − 7/0) − (4/0 ∪ 4/1)
- TTBN' = (TTBN − 7/0) − (4/0 ∪ 4/1)
- TBN' = TBN − 7/0
- Gr' = Gr − 7/0   (Gr = ∪ graphene pieces)
- BBN' = BBN,  BG' = BG

Star sets, each device with its electrodes (an electrode = its 2/0 path with its 2/1
tentacle and pad; its role from its head: arm -> graphene, top-gate contact 5/2 -> top
gate, exposed bottom graphite -> back gate):
- TG* = TG' ∪ top-gate leads
- BG* = BG' ∪ back-gate leads
- Gr* = Gr' ∪ arm electrodes

Checks, with L_TG, L_BG, L_Gr the top-gate, back-gate and arm electrodes. hBN insulates only
between two flakes, never between metal and a flake (the 2/0 etch cuts through it), so the
dielectric is subtracted from the flake-flake overlap only:
1. ((TG' ∩ Gr') − TBN') ∪ (L_TG ∩ Gr*) ∪ (TG* ∩ L_Gr) = ∅
2. ((TG' ∩ BG') − (BBN' ∪ TBN')) ∪ (L_TG ∩ BG*) ∪ (TG* ∩ L_BG) = ∅
3. ((BG' ∩ Gr') − BBN') ∪ (L_BG ∩ Gr*) ∪ (BG* ∩ L_Gr) = ∅
(First written as (TG* ∩ Gr*) − TBN' etc.; that hid an arm electrode lying on the top gate,
because the top hBN lies under the top graphite, not between it and the metal.)
4. (Claude's, for "no electrodes shorted together") any two electrodes are disjoint, and no
   conductor piece outside the devices (a piece of TG', Gr' or BG' not on the channel) touches
   two of them.

## Procedure

```
cd <device>/klayoutclaw
P=<python>; A="--flakes data/prepared.gds --params data/params.json --writes writes.gds"
$P <KlayoutClaw>/skills/nanodevice_finalcheck/scripts/check.py $A
```
Python: the `instrMCPdev` conda env; run under `bash -c` (zsh does not split `$A`).

## Negative tests

Run on broken copies of a finished design, all caught: no 7/0 etch (checks 1-3); a metal box
across two pads (checks 1-4); fingers with lanes wider than half the electrode spacing (check 4,
leads shorted through top-graphite debris); an arm lead extended onto its arm (checks 1 and 3).
A worked example on a real device is kept with the device data, not in this repo.
