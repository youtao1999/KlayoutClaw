---
name: nanodevice_pads
description: Write the big pads (2/1, large beam current) of a six-piece dual-gated graphene device after nanodevice_electrodes. One big axis-aligned rectangle per electrode, spread around the stack, with a trapezoidal tentacle reaching in to the electrode's tail.
---

# nanodevice_pads -- big pads of a six-piece stack

Status: in development (2026-11-17). Pads, tentacles and checks 1-4 exist.

User (2026-11-17): not many requirements on the big pads. They must be big, good polygons,
rectangular, spread around the stack, and connect to the tails of the electrodes through
trapezoidal tentacles coming out of each pad. Stick to simple shapes. The fine electrodes
are thin (about 1 um), so dirt on them can break the contact: keep them short and let the
tentacles bridge the distance (the electrode skill puts the tails as close as the flakes
allow).

Same design principle as `nanodevice_topgate`: every part is a set expression, every rule a
set relation.

## Inputs and scope

All in the device folder's `klayoutclaw/`:
- `writes.gds` with the electrodes 2/0 from `nanodevice_electrodes` (GDS paths; the last
  point of each is its tail) and the channel 5/0 (its centre is the pads' centre).
- `data/prepared.gds` (flakes) and `data/params.json` (local frame and flake layers only;
  its old `layers.pads` [2,0], `layers.electrodes` and `pads`/`routing` blocks are ignored:
  here 2/0 = electrodes, 2/1 = big pads).

Writes only 2/1 (pads and tentacles as separate shapes); rerunning is safe. Python: the
`instrMCPdev` conda env; run the procedure under `bash -c` (zsh does not split `$A`).

## Set rules

Pads Bₖ and tentacles Kₖ (2/1), leads Lₖ (2/0) with tails tₖ, F = bounding box of the flakes:
- Bₖ is an axis-aligned rectangle (GDS frame), both sides ≥ 60 um (big)
- Kₖ is a trapezoid; tₖ ∈ Kₖ; Kₖ ∩ Bₖ ≠ ∅; Kₖ ∩ Bⱼ = ∅ (j ≠ k)
- (Bₖ ∪ Kₖ) ∩ Lⱼ = ∅ for j ≠ k (each pad connects to exactly its own lead)
- Bₖ, Bⱼ 20 um apart; Kₖ 20 um from Kⱼ and Bⱼ (j ≠ k)
- (Bₖ ∪ Kₖ) ∩ (F grown by 20 um) = ∅ (spread around the stack, clear of it)
Numbers are Claude's choices.

## Glossary

Definitions given by the user, in the user's terms. Keep it up to date. Earlier terms are in
the `nanodevice_topgate`, `nanodevice_contacts` and `nanodevice_electrodes` glossaries.

| Term | Definition | Layer |
|---|---|---|
| big pads | big, rectangular, simple pads spread around the stack, large beam current; each connects to the tail of an electrode through a tentacle | 2/1 |
| tentacle | trapezoid coming out of a big pad, wide at the pad, narrow at the electrode's tail, making contact with the electrode | 2/1 |
| tail (of an electrode) | the outer end of an electrode, where its tentacle connects | last point of each 2/0 path |

## Procedure

```
cd <device>/klayoutclaw
P=<python>; S=<KlayoutClaw>/skills/nanodevice_pads/scripts; A="--flakes data/prepared.gds --params data/params.json --writes writes.gds"
$P $S/pads.py $A
$P $S/check.py $A
for s in topgate contacts electrodes; do $P <KlayoutClaw>/skills/nanodevice_$s/scripts/check.py $A; done   # earlier layers unchanged
```
Rerun after every `nanodevice_electrodes` run (the tails move).

**Pads and tentacles** (2/1), `pads.py`. For each tail t, with u = unit(t − channel centre):
- pad: `--size` 120 um square, its inner edge centred at m = centre + u·r, running outward
  along the axis nearest u;
- tentacle: trapezoid with both parallel sides across that axis, `--base` 40 um wide on
  the pad's inner edge (2 um inside the pad), `--tip` 4 um wide at the tail end; its centre
  line runs from the base centre through the tail and `--into` 5 um past it, so the fine
  lead overlaps the tentacle by about 5 um.
- r: the smallest from (tail radius + `--reach` 20 um) upward in 5 um steps for which all
  set rules hold.

## Checks

1. pads are boxes with sides ≥ 60 um; tentacles are trapezoids.
2. one tentacle per lead holds its tail and joins exactly one pad; each pad has one
   tentacle; pads and tentacles touch no other lead.
3. pads 20 um apart; tentacles 20 um from other tentacles and pads.
4. pads and tentacles 20 um clear of the flakes' bounding box.

A worked example on a real device is kept with the device data, not in this repo. The user's hand-drawn reference pads are larger hand-drawn polygons, not
rectangles.
