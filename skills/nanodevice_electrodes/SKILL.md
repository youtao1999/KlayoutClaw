---
name: nanodevice_electrodes
description: Write the electrode layer (2/0, fine metal, small beam current) of a six-piece dual-gated graphene device after nanodevice_topgate and nanodevice_contacts. Paths from the arm heads (in active region ∩ contacts), the top-gate contacts and the exposed bottom graphite (two back-gate leads) out to tails on a ring around the stack, where nanodevice_pads puts the big pads (2/1); none touch each other, only the back-gate leads touch the bottom graphite.
---

# nanodevice_electrodes -- fine metal leads of a six-piece stack

Status: in development (2026-11-17). Arm leads, top-gate leads, the two back-gate leads and
checks 1-5 exist. The back-gate leads are written in the same run as the other electrodes,
with the same rules (user, 2026-11-17): the 7/0 mask already protects their landing area X.

Process (user, 2026-11-17): after the 7/0 etch (down to the bottom hBN) the graphene is left
only under the top gate, still in the top hBN; after the 4/0 etch (down to the top hBN) the
top graphite is gone in the contacts. Then 2/0 is written, etched all the way down to the bare
substrate, and gold is evaporated: the gold makes edge contact with every conductor under the
lead, the graphene active region at an arm lead's head. So no lead may overlap any conductor
but its own terminal, not even under hBN (the bottom graphite under the bottom hBN included).

Same design principle as `nanodevice_topgate`: every part is a set expression, every rule a
set relation. One skill per process step: this one is the fine metal write (2/0).

## Inputs and scope

Arguments can also come from `data/params.json` `args` (block `electrodes/<script>`); effective arguments
and choices go to `data/record.json`. See nanodevice_topgate, "Params and run record".

All in the device folder's `klayoutclaw/`:
- `result.gds` with the top gate (5/0-5/3, 11/4, flake copies) from `nanodevice_topgate`
  and the etch mask 7/0, contacts 4/0 and etch checker 4/1 from
  `nanodevice_contacts`. Do not change those layers here. No pads needed: the leads end at
  tails, and `nanodevice_pads` puts the pads on them afterwards.
- `data/prepared.gds` (the bottom graphite BG is read from here) and `data/params.json`
  (only the local frame and the flake layers are used; its old `layers.pads` and
  `layers.electrodes` entries are ignored: here 2/0 = electrodes, 2/1 = pads).

Writes only 2/0; `electrodes.py` clears 2/0 first, so rerunning is safe, but then rerun
`nanodevice_pads` too: its tentacles sit on the old tails. Not written here:
2/1 big pads, 3/1. Python: on Linux plain `python3` (`docs/device_skills_linux.md`); on the Mac the `instrMCPdev` conda env; run the procedure under `bash -c`
(zsh does not split `$A`).

## Set rules

Layers: T = top gate 5/0-5/3, A = active region 11/4, C = contacts 4/0,
top-gate contacts 5/2, BG = bottom graphite 13/0, leads 2/0.

- each electrode (lead) L runs from its head outward to its tail; tails are evenly spaced on
  a circle around the channel centre, one per lead, as small as the flakes allow: the
  flakes' farthest bounding-box corner + 30 um. User (2026-11-17): the electrodes are thin,
  dirt on them can break the contact, so they must not be long; the big pads' tentacles
  reach in to the tails.
- P = T ∪ BG: the top gate and the bottom graphite, the parts of the stack a lead may meet
  only at its head
- arm lead: head of L = L ∩ P, its starting part on the arm. Hard rule (user): head ⊆ A ∩ C
  (active region and contact: graphene there, top graphite etched away)
- top-gate lead (user): same rules as the arm leads; its head is on a top-gate contact
  island (5/2): L ∩ P ⊆ that island
- back-gate leads (user): the back gate has two leads, same rules as the other leads; their
  terminals are pieces of the exposed bottom graphite X = BG − (TG ∪ TBN ∪ G ∪ BBN), kept
  under PMMA by the 7/0 mask: L ∩ BG ⊆ X
- back-gate edge contact (user, 2026-11-18), opt-in with params `"back_gate": {"edge_contact": true,
  "gap": 0.5}` for a bottom graphite with no bare part (e.g. top graphite lying on it wherever the
  hBN does not cover it): X also holds (BG ∩ BBN) − (T grown by gap), bottom graphite still under the
  bottom hBN. The 7/0 etch clears everything above it down to the bottom hBN (it is not protected),
  and the 2/0 etch cuts through the bottom hBN, so the gold makes edge contact with the graphite.
  `tg_lib.bg_terminal` is the one definition of X used by electrodes.py, check.py and
  nanodevice_finalcheck
- hard rule (user): no electrode touches another electrode, and none but the back-gate leads
  touch the back gate: Lᵢ ∩ Lⱼ = ∅; L ∩ BG = ∅ for arm and top-gate leads; L ∩ BG ⊆ X for
  back-gate leads
- L is a path of width 1 um, or slightly smaller than the arm width (user); always below
  its terminal's width (check 4), so 0.8 um for 1 um arms
- Claude's: each L touches one terminal (arm, top-gate contact or piece of X); leads stay
  0.5 um apart; top-gate and back-gate leads are min(0.8, terminal width − 0.1) um wide
  (a piece of X: 2 × its erosion depth)
  (e.g. 0.5 um on 0.6 um islands)

## Glossary

Definitions given by the user, in the user's terms. Keep it up to date. Terms of earlier
steps are in the `nanodevice_topgate` and `nanodevice_contacts` glossaries.

| Term | Definition | Layer |
|---|---|---|
| electrode | fine metal, small beam current; a path from the top gate outward to its tail, where a big pad connects | 2/0 |
| tail (of an electrode) | the outer end of an electrode, where its big pad connects | last point of the path |
| head (of an electrode) | the starting point of the electrode, on the arm (or on the top-gate contact for a top-gate lead); for an arm it must lie within the active region ∩ contact layer | L ∩ P |
| top-gate lead | electrode from a top-gate contact island to a big pad; same rules as the arm leads | 2/0 |
| back-gate leads | the two electrodes from the exposed bottom graphite (back gate) to big pads; same rules as the other leads, written with them | 2/0 |
| back-gate edge contact | a back-gate lead landing on bottom graphite still under the bottom hBN, contacting the graphite edge through the hBN (params `back_gate.edge_contact`) | 2/0 |
| big pads | see `nanodevice_pads` | 2/1 |

## Procedure

```
cd <device>/klayoutclaw
P=<python>; S=<KlayoutClaw>/skills/nanodevice_electrodes/scripts; A="--flakes data/prepared.gds --params data/params.json --writes result.gds"
$P $S/electrodes.py $A           # arm, top-gate and back-gate leads on 2/0 (paths)
$P $S/check.py $A
$P <KlayoutClaw>/skills/nanodevice_topgate/scripts/check.py $A    # earlier layers unchanged: all pass
$P <KlayoutClaw>/skills/nanodevice_contacts/scripts/check.py $A
```

**Leads** (2/0), `electrodes.py`. One GDS path per arm, per top-gate contact and two for the
back gate.

Arm lead, local frame:
- head: starts `--inset` 0.05 um inside the contact's inner edge, on the arm centre line,
  and runs out over the arm tip (long enough: the topgate skill runs arms to the
  active-region edge), so L ∩ P lies in A ∩ C;
- stub: straight out along x' until `--clear` 1 um past the rest of the top gate on that
  side (the top-gate contacts reach furthest);
- then straight to its tail.
- Tails: n = number of leads, evenly spaced on a circle around the channel centre (first
  at angle 0, local frame) of radius `--tail-radius auto` = farthest corner of the flakes'
  bounding box + `--tail-margin` 30 um (or a number in um). Per side, the arms take the tails
  whose direction is nearest the side's direction, matched in y' order so leads do not
  cross.
- `--width` 0.8 um.

Top-gate lead: head at the centre of the island; stub along an axis, `--clear` past the
island, then straight to its tail.
Back-gate leads (`--bg-leads` 2): as the top-gate leads, one per piece of X, largest pieces
first; head at the deepest point of the piece (erode in 0.05 um steps until it vanishes).
A piece's width is 2 × the depth it erodes to before vanishing (any edge angle); only
pieces with width − 0.1 um at least `--min-width` 0.3 um count, thinner slivers are not
back-gate terminals. Back-gate lead width: min(0.8, piece width − 0.1) um.
Fewer usable pieces than leads: the script stops (two heads on one piece not implemented yet).
Every terminal lead (top-gate and back-gate) tries the four stub axes nearest the tail first
and takes the first whose lead meets the stack (T ∪ BG) only on its terminal.
Tails of the terminal leads: every assignment of the free tails is tried, and the shortest
one wins where every lead meets the stack only on its terminal and all leads stay `--spacing`
(0.5 um) apart. (A greedy nearest-tail choice can leave a later terminal only tails behind the
channel.) `--tail-slots` puts more tail positions on the circle than leads (default: one per
lead); use it when no assignment exists. The arms still take the slots nearest their sides.
More slots crowd the tails, and `nanodevice_pads` then moves the pads outward, so take the
smallest count that works.
Inset, clear, tail margin, 0.8 um and the 0.3 um minimum width are Claude's choices.

## Checks

1. head (P = T ∪ BG): arm lead L ∩ P ⊆ A ∩ C; top-gate lead L ∩ P ⊆ its own top-gate
   contact; back-gate lead L ∩ P ⊆ its piece of X; L ∩ P ≠ ∅.
2. each L touches exactly one terminal (arm, top-gate contact or piece of X). Pads are
   checked by `nanodevice_pads`.
3. leads 0.5 um apart (none touch).
4. `--min-width` 0.3 um <= lead width < its terminal's width (for a piece of X: 2 × its
   erosion depth).
5. L ∩ BG = ∅ for every lead but the back-gate leads, whose L ∩ BG ⊆ X; exactly
   `--bg-leads` (2) back-gate leads.

A worked example on a real device is kept with the device data, not in this repo. In the user's hand-drawn reference, 2/0 holds one lead per arm, per
top-gate contact and for the back gate, each running out to a big pad.
