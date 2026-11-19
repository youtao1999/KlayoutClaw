---
name: nanodevice_contacts
description: Write the two etch masks that follow nanodevice_topgate on a six-piece dual-gated graphene device. The top-gate etch mask 7/0 (big rectangle minus the top gate, the etch checker and the exposed bottom graphite; etched down to the bottom hBN), then the contact rectangles 4/0 with the etch checker 4/1 (etched down to the top hBN, removing the top graphite at the arm tips). Together they shape the top gate and the graphene, and open the arm tips for the electrodes.
---

# nanodevice_contacts -- contacts of a six-piece stack

Status: complete for the rules given so far (2026-11-17): etch checker, etch mask, contact
rectangles and checks 1-4.

Two etch steps (user, corrected 2026-11-17), no combined mask. Shaded (written) regions are
exposed and etched; unshaded regions stay under PMMA, which protects whatever is beneath.
1. through 7/0, all the way down to the bottom hBN. T, the etch checker W and X (exposed
   bottom graphite, below) stay under PMMA, so the graphene is left only under them, still encapsulated in the top
   hBN.
2. through 4/x (contacts 4/0, etch checker 4/1), only down to the top hBN: removes the
   top-top hBN and the top graphite in C (the arm tips; the top hBN still covers the
   graphene there) and in W.
Then the electrode skill writes 2/0, etches and evaporates gold, making contact with the
graphene active region inside A ∩ C.

The head room for the electrodes comes from the arms themselves: `nanodevice_topgate` runs
each arm out to the active-region edge (user, 2026-11-17), and this skill takes set
differences only.

Same design principle as `nanodevice_topgate`: every part is a set expression, every rule
a set relation.

`nanodevice_fingers` (run after the pads) later shrinks 7/0 to the smallest mask: rerun it
whenever `mask.py` is rerun.

## Inputs and scope

Arguments can also come from `data/params.json` `args` (block `contacts/<script>`); effective arguments
and choices go to `data/record.json`. See nanodevice_topgate, "Params and run record".

All in the device folder's `klayoutclaw/`:
- `writes.gds` with the top gate already written by `nanodevice_topgate`: channel 5/0,
  arms 5/1, top-gate contacts 5/2, top-gate electrodes 5/3, active region 11/4 and the
  flake copies. Do not rerun or change the top gate here.
- `data/prepared.gds` (the flakes) and `data/params.json` (only the `layers` map and the
  local frame are used).
- Nothing from the user: every number below has a default.

Writes only 4/1 (etch checker), 7/0 (top-gate etch mask) and 4/0 (contacts); each script
replaces only its own layer. Not written here, later steps: 2/0 electrode (fine metal),
2/1 big pads, 3/1. Python: the `instrMCPdev` conda env; on macOS run the procedure under
`bash -c` (zsh does not split `$A`).

## Set rules

- R = bounding box of the union of all flakes, grown by `--margin` (2 um)
- X = BG − (TG ∪ TBN ∪ G ∪ BBN): the bottom graphite with at most top-top hBN above it,
  where the back-gate lead will land (user, 2026-11-17). The 7/0 etch removes the top-top
  hBN and top graphite, so X must be protected from it; everything below the top hBN (top
  hBN, all graphene pieces, bottom hBN) is taken out of X, so X keeps no graphene.
- top-gate etch mask M = R − (T ∪ W ∪ X). Written (exposed); T, W and X stay under PMMA.
  Etch goes down to the bottom hBN. With params `back_gate.edge_contact` the back-gate edge
  terminals under the bottom hBN (`nanodevice_electrodes`) are not protected: the etch clears what
  lies above them.
- contacts C (4/0): rectangles. Etch goes down to the top hBN only: removes the top-top hBN
  and the top graphite in C, so the electrodes can reach the graphene there.
- hard rule 1 (user, 2026-11-17): (T ∩ C) ∩ ∂C ⊆ A. Where the contact boundary lies on the
  top gate, it lies in the active region A. Channel and arms lie in A, so T − A is only
  the top-gate contacts and the outer parts of the top-gate electrodes: the rule says ∂C
  must not cross T − A; it may cut the channel and arms.
- hard rule 2 (user, 2026-11-17): T − C is connected (one piece). The contacts must not
  cut the top gate into disjoint pieces; a contact that reaches an arm has to cover the
  arm's whole outer end, not cut a stub off it.
- arm tips = arms − BG (the overshoot); top-gate body = T − arm tips = channel ∪ (arms ∩ BG)
  ∪ top-gate contacts ∪ top-gate electrodes
- hard rule 3 (user, 2026-11-17): besides the arm tips, C stays away from the top gate:
  C ∩ (body grown by gap) = ∅, gap 0.15 um (Claude's number; the user said "stay away")
- room for the electrode heads: per arm, T ∩ C ∩ A at least 0.4 um along x' (Claude's number)
- after both etches the top graphite left is (TG ∩ T) − C: the top gate; the graphene left
  is G ∩ T (W and X hold no graphene)
- etch checker W (4/1), optional: with S = (TTBN ∩ TG) − (TBN ∪ G ∪ BBN ∪ BG) (only top-top
  hBN plus top graphite on bare substrate), W ⊆ R − (TBN ∪ G ∪ BBN ∪ BG), W ∩ S ≠ ∅ and
  W ∩ bare substrate ≠ ∅. Protected in the 7/0 etch, exposed in the 4/x etch: when the S
  part of W matches the bare substrate in it, the top-top hBN and the top graphite are gone
  where exposed, so the contact etch has reached the top hBN.

## Glossary

Definitions given by the user, in the user's terms. Keep it up to date. Terms of the top
gate (channel, arms, top gate T, ...) are in the `nanodevice_topgate` glossary.

| Term | Definition | Layer |
|---|---|---|
| big rectangle R | rectangle enclosing the union of all flakes | not written |
| shaded / unshaded | shaded = written, exposed and etched; unshaded = protected by PMMA | |
| top-gate etch mask M | R minus the top gate, the etch checker and the exposed bottom graphite X; the unwritten region is protected by PMMA; the etch goes all the way down to the bottom hBN; defines the channel of the top gate | 7/0 |
| contacts | rectangular exposed regions (as 4/0 in the reference writes.gds), etched only down to the top hBN: the top graphite there is removed, the graphene stays encapsulated. The electrodes (later skill) contact the graphene inside them | 4/0 |
| contact boundary ∂C | the edge of the contact layer, where the top graphite is cut | computed |
| arm tips | the parts of the arms past the bottom graphite (arms − BG); the only part of the top gate a contact may cover; also the room for the electrode head | computed |
| top-gate body | top gate minus the arm tips: channel, arms over BG, top-gate contacts, top-gate electrodes; contacts stay away from it | `tg_lib.body` |
| etch checker | an exposed rectangle over a region where optically only the top-top hBN and part of the top graphite are seen on bare substrate, including some bare substrate too; when its colour matches bare substrate, the top-top hBN and top graphite are etched away where exposed (drawn on 4/0 in the reference, off the graphene). Protected in the 7/0 etch, etched with the contacts. Specific to stacks that have such a region: draw it only if one exists | 4/1 |

Layer 7/0 is confirmed by the user; the reference draws this mask on 5/0, which the
topgate skill uses for the channel. 4/1 is Claude's choice: the reference draws the checker
on 4/0 with the contacts; a separate datatype keeps 4/0 = contacts for the later skills, and
both are written in the same 4/x etch.

## Procedure

```
cd <device>/klayoutclaw
P=<python>; S=<skill>/scripts; A="--flakes data/prepared.gds --params data/params.json --writes writes.gds"
$P $S/checker.py $A              # 1  etch checker W on 4/1
$P $S/mask.py $A                 # 2  top-gate etch mask M = R - (T ∪ W ∪ X) on 7/0
$P $S/contacts.py $A             # 3  contact rectangles on 4/0
$P $S/check.py $A
$P <KlayoutClaw>/skills/nanodevice_topgate/scripts/check.py $A   # top gate unchanged: all 8 pass
```
`<skill>` is `<KlayoutClaw>/skills/nanodevice_contacts`. Note `--margin` differs per script:
growth of R in mask.py (2 um), clearance from the stack below in checker.py (0.5 um).

1. **Etch checker** (4/1), `checker.py`. Optional, and specific to the stack: many stacks
   have no region where only the top-top hBN plus the top graphite lie on bare substrate.
   If there is one (a square with side at least `--min-seed` 1 um that fits inside S
   eroded by `--margin` 0.5 um; printed as "seed ... um square"), draw a large checker
   there that also holds some bare substrate; otherwise 4/1 is cleared, the script says
   so, and the procedure goes on.
   - Seed: the largest square in S (local frame, 0.1 um grid), cut to `--size`.
   - Growth: one grid step at a time inside R − ((TBN ∪ G ∪ BBN ∪ BG) grown by the margin),
     each side up to `--size` 10 um. Each step takes the direction whose new row/column
     holds the most S, then the most bare substrate. It stops when no step adds S and bare
     substrate is at least `--bare` 25% of W, or when it is blocked.
   - Asserts W ⊆ R, W ∩ (TBN ∪ G ∪ BBN ∪ BG) = ∅. If W holds no bare substrate, 4/1 is
     cleared and the procedure goes on, as when there is no seed.
   Seed, growth rule, numbers and layer are Claude's choices.
2. **Top-gate etch mask** (7/0), `mask.py [--margin 2]`. M = R − (T ∪ W ∪ X),
   X = BG − (TG ∪ TBN ∪ G ∪ BBN).
   Stops if there is no top gate. Asserts flakes ⊆ R, M ∩ (T ∪ W ∪ X) = ∅,
   M ∪ T ∪ W ∪ X = R.
3. **Contacts** (4/0), `contacts.py [--length auto]`. One rectangle per side, local frame:
   - x': inner edge `--gap` + 0.05 um past the bottom-graphite edge (as close to the
     graphite as rule 3 allows, for the most head room on the arm tip), so C ∩ BG = ∅ and
     C covers every arm's outer end (rule 2); outer edge `--length` further out (auto: 0.1 um
     past the farthest arm tip on that side, at least 3 um; arms run to the active-region edge, so a
     fixed 3 um cut long arm tips off the top gate).
   - y': the side's arm span grown by the corridor clearance (0.3 um), so C stays in the
     arm corridors, which the top-gate contacts and electrodes avoid (rule 1); then each
     y' edge is pulled in until C stays `--gap` (0.15 um) from the top-gate body (rule 3).
   - Asserts C ∩ BG = ∅ and C ∩ (body grown by gap) = ∅.
   These choices are Claude's, read from the reference (its 4/0 never touches 13/0 and
   covers the arm ends), not user rules yet.
4. **Checks**, `check.py`.

## Checks

```
$P <skill>/scripts/check.py $A
```
Exit 1 if any fails; prints failing pieces in x', y'. Then run the topgate skill's
`check.py` (all 8 must still pass); this skill must not change 5/0-5/3.
1. (T ∩ C) ∩ ∂C ⊆ A. Sets are closed: T and A are grown by 1 dbu.
2. T − C is one piece.
3. C ∩ (top-gate body grown by `--gap` 0.15 um) = ∅.
4. Head room: per arm, T ∩ C ∩ A reaches at least `--min-head` 0.4 um along x'.

Scripts reuse `nanodevice_topgate/scripts/tg_lib.py` (frame, layer I/O, .part writes).
In the user's hand-drawn reference, 4/0 holds one rectangle per side across the graphene
edges at the arms, overlapping the top gate, and the etch checker off the graphene.
A worked example on a real device is kept with the device data, not in this repo.
