---
name: nanodevice_fingers
description: Shrink the top-gate etch mask 7/0 of a six-piece dual-gated graphene device after nanodevice_pads. The big rectangle is shrunk to the smallest rectangle that still holds the protected region, plus trapezoidal fingers between neighbouring electrodes that etch away any flake debris that could short them.
---

# nanodevice_fingers -- smallest top-gate etch mask

Status: in development (2026-11-17). Fingers and checks 1-3 exist.

User (2026-11-17): writing a big area needs a lot of beam current, and its proximity dose
blurs the PMMA at the neighbouring fine features. So shrink the rectangular outline of 7/0
inward as far as possible while still containing all the protected region, then add
trapezoidal fingers in between the electrodes: they keep the exposed area small but still
etch away any debris between neighbouring electrodes that might short them.

Same design principle as `nanodevice_topgate`: every part is a set expression, every rule a
set relation. Runs after `nanodevice_pads`; it rewrites 7/0 from `nanodevice_contacts`.

## Inputs and scope

All in the device folder's `klayoutclaw/`:
- `writes.gds` with the top gate 5/0-5/3, the etch checker 4/1 (`nanodevice_contacts`), the
  electrodes 2/0 (`nanodevice_electrodes`) and 7/0.
- `data/prepared.gds` (flakes) and `data/params.json` (local frame and flake layers only).

Rewrites only 7/0; rerunning is safe. Rerun it after `nanodevice_contacts/mask.py` (which
writes the full mask again) or after `nanodevice_electrodes` (the lanes move). Python: the
`instrMCPdev` conda env; run under `bash -c` (zsh does not split `$A`).

## Set rules

- protected region P = T ∪ W ∪ X (top gate, etch checker, exposed bottom graphite
  X = BG − (TG ∪ TBN ∪ G ∪ BBN)), as in `nanodevice_contacts`
- shrunk outline R' = bounding box of P grown by 2 um (GDS frame): the smallest rectangle
  that still holds P, with an etched moat around it
- R = the flakes' bounding box grown by 2 um (the old big rectangle); lanes = electrodes
  (2/0) grown by `--clear`
- gaps = R − R' − lanes: one piece per pair of neighbouring electrodes
- finger = gap ∩ (bounding box of the flake material in that gap, grown by 2 um); a gap
  with no flake material gets no finger
- conductors = top graphite and graphene outside R', grown by 2 um (∩ R): exposed too, also
  under the electrodes (user, 2026-11-17: etch the debris away rather than leave it in the
  lanes; the final check counts any top graphite under an arm electrode as a short)
- mask M (7/0) = ((R' − P) ∪ fingers ∪ conductors) − P
- no debris shorts: every piece of conductive flake left after the etch, (TG ∪ G ∪ BG) − M
  − P, touches at most one electrode and does not touch P
- `--clear` 0.25 um, below half the closest electrode spacing (1.2 um between the arm
  leads' stubs). With 1 um the lanes of two arm leads merged and the top graphite left under
  them touched both: a short.
Numbers are Claude's choices.

## Glossary

Definitions given by the user, in the user's terms. Keep it up to date. Earlier terms are in
the other nanodevice_* glossaries.

| Term | Definition | Layer |
|---|---|---|
| fingers | trapezoidal exposed regions in between neighbouring electrodes, out from the shrunk outline; they etch away debris that might short the electrodes while keeping the exposed area small | part of 7/0 |
| shrunk outline R' | the rectangular outline of 7/0 shrunk inward as far as possible while still containing all the protected region | part of 7/0 |
| protected region P | what the 7/0 etch must not touch: top gate, etch checker, exposed bottom graphite | not written |

## Procedure

```
cd <device>/klayoutclaw
P=<python>; S=<KlayoutClaw>/skills/nanodevice_fingers/scripts; A="--flakes data/prepared.gds --params data/params.json --writes writes.gds"
$P $S/fingers.py $A
$P $S/check.py $A
for s in topgate contacts electrodes pads; do $P <KlayoutClaw>/skills/nanodevice_$s/scripts/check.py $A; done   # all still pass
```

## Checks

1. M ∩ P = ∅ and R' − P ⊆ M.
2. fingers (M − R' − conductors) keep `--clear` from every electrode (slivers under 4 dbu
   wide ignored).
3. no conductive debris piece touches two electrodes or P (slivers under 4 dbu wide,
   rounding along P's edge, are ignored).

check.py takes the same `--margin`, `--frame` and `--clear` as fingers.py; pass the same values.

A worked example on a real device is kept with the device data, not in this repo.
