---
name: nanodevice_topgate
description: Write the top gate (channel, arms, top-gate contacts, top-gate electrodes) of a six-piece dual-gated graphene device (bottom graphite, bottom hBN, graphene, top hBN, top graphite, top-top hBN) into a device folder's result.gds (the design file; writes.gds is exported from it at the end), then check it. The top gate is etched from the top graphite, not evaporated, so it is built from parts that belong to different etch steps.
---

# nanodevice_topgate -- top gate of a six-piece stack

Status: in development. Channel, arms, contacts, top-gate electrodes and the final checks
exist.

## Why a separate skill

The stack has six pieces (top to bottom): top-top hBN, top graphite, top hBN, graphene,
bottom hBN, bottom graphite. The top gate is etched from the top graphite. It cannot be
written and evaporated: it is made by an etch mask followed by an etch. Different parts of
the top gate belong to different etch steps, so the top gate is the combination of
several layers, not one layer drawn in one pass.

## Design principle: set arithmetic

The design is a set-arithmetic problem on flake regions. Every part is a region built
with union, intersection and difference of flake regions; every requirement is a set
relation (subset, strict subset, non-empty intersection, connectedness). Define a new
part or rule as a set expression first (glossary + checks), then implement it with
klayout `Region` boolean operations. Prefer set rules over hand-tuned coordinates.

Current rules, with G_i the graphene pieces, BG bottom graphite, TBN top hBN, TG top
graphite:
- graphene G = ∪ G_i; active region A = ∩ G_i
- top gate T = channel ∪ arms ∪ contacts ∪ top-gate electrodes
- arm corridors K = ((arms − channel) extended outward along x', grown by clearance) − channel
- arms ⊆ A;  channel ⊆ BG;  contacts ⊆ (TBN − G) − K;  top-gate electrodes E ⊆ (TG ∩ TBN) − K;
  every E touches the channel;  T connected;  T ⊊ TG
- channel and arms lie inside A and contacts outside it, so T is connected only through E

## Glossary

Definitions given by the user. Keep this list up to date: add every new definition the
user gives, in the user's terms, and use these terms in code, output and replies.

| Term | Definition | Layer |
|---|---|---|
| bottom graphite (back-gate graphite) | the bottom gate flake | 13/0 |
| bottom hBN | dielectric between bottom graphite and graphene | 12/0 |
| graphene pieces | the separate graphene flakes of the stack (e.g. a twisted trilayer) | 11/1, 11/2, 11/3 (params `layers.graphene_pieces`) |
| graphene | union of all graphene pieces | computed (not 11/0, which can differ from it) |
| active region (graphene active region) | by definition the intersection of all graphene pieces | 11/4 |
| top hBN | dielectric between graphene and top graphite | 10/0 |
| top graphite | the flake the top gate is etched from | 14/0 |
| top-top hBN | hBN above the top graphite (pickup layer) | 16/0 |
| channel | rectangular bar along the bottom graphite, narrower than it | 5/0 |
| arms | bars from the channel across and past the bottom-graphite edge; the user sets their number, width and the gap between them | 5/1 |
| overlap | how far an arm reaches into the channel | default 0.5 um |
| overshoot | how far an arm reaches past the bottom-graphite edge. Default: as far as the active region allows (0.1 um inside its edge), so the arm tip leaves room for the electrode head (user, 2026-11-17: make the arms longer for head room; was 0.5 um) | `arms.py --overshoot max` |
| top-gate contacts | little islands of the top gate where it is contacted; completely inside top hBN minus graphene (so outside the active region) | 5/2 |
| shift | how far the arm group is moved along the channel from centred (+ = towards gate_end); a free parameter to free room for the top-gate electrodes | `arms.py --shift` |
| top-gate electrodes | top-graphite bars joining each top-gate contact to the channel: they come out of the channel (not an arm), stay clear of the arms (each arm later gets its own electrode), and run only where top hBN separates them from the graphene. Part of the top gate, etched with it. Not the same as "electrode" (2/0 metal) | 5/3 |
| arm corridors | each arm outside the channel extended outward along x' by `escape` and grown by `clearance`, minus the channel; room for the arm's own electrode | computed, `tg_lib.arm_keepout` |
| top gate (top gate region) | channel union arms union top-gate contacts union top-gate electrodes | 5/0 + 5/1 + 5/2 + 5/3 |
| etch cut-out | the top gate T, written by this skill on 5/0-5/3 (drawn on 3/0 in the reference writes.gds; nothing is written to 3/0) | 5/0-5/3 |

Defaults confirmed by the user (2026-11-17): `--n` counts arms per side; contacts must
also lie on the top graphite; arm corridors (escape 50 um, clearance 0.3 um); electrode
width 0.5 um; routing grid 0.05 um with a 1 um penalty per corner; check 4 read as "the
top gate is one connected polygon"; 2 top-gate contacts; placement rule: largest contact size with a passing shift run of at least 0.05 um, shift in its middle.

## Scope

This skill writes only the top gate: channel (5/0), arms (5/1), top-gate contact islands
(5/2) and top-gate electrodes (5/3), plus the flake copies and the active region (11/4)
it reads from. The top gate T is the etch cut-out: in the reference writes.gds it is
drawn on 3/0. Do not write these layers; they belong to subsequent steps:

| Layer | Name (reference writes.gds) |
|---|---|
| 4/0 | contact |
| 2/0 | electrode (fine metal, small beam current) |
| 2/1 | big pads (pads and wide leads, large beam current) |
| 3/1 | (later step) |
| 3/0 | the etch cut-out in the reference; the top gate is not copied onto it |

6/0 is also in the reference writes.gds; ignore it for now.

## Inputs

All in the device folder's `klayoutclaw/`:
- `data/prepared.gds`: the chip template and the flakes where they landed, in chip coordinates (from
  `nanodevice_prepare`). In future the capture
  program delivers a GDS per flake (graphite included); they replace this file.
- `data/params.json`: only `gate_end`, the `layers` map and the `channel` block (`y`,
  `bg_inset`, `min_width`) are used. Other blocks (`arms`, `finger`, `tg_contact`,
  `bridge`, `pads`, ...) are left from earlier designs: ignore them, they are not inputs.
  Coordinates are in the local strip frame: x' across the bottom graphite, y' along it,
  origin at the bottom-graphite hull centroid.
- `result.gds`: the design file, started by the first step as a copy of prepared.gds; every later step
  adds its layers. It holds everything (template, flakes, design). The stack plan `design.gds` is never
  written. `writes.gds` (only the EBL layers) is exported from it by `nanodevice_finalcheck/export.py`.
- From the user: arms per side, arm width, gap between arms.

Python: on Linux plain `python3` (`docs/device_skills_linux.md`); on the Mac the `instrMCPdev` conda env (`klayout` module); on macOS run shell loops under
`bash -c` (zsh does not split variables). Scripts are in `scripts/` next to this file.
Each script replaces only its own layer(s), so a step can be rerun without undoing the
others.

## Params and run record (whole chain)

One `data/params.json` per device holds everything the chain needs (template:
`params_six_piece.json` next to this file): `gate_end`, `layers`, `channel`, `back_gate`, and
`args`, one block per script, keyed `<skill>/<script>` (e.g. `topgate/place`,
`contacts/contacts`, `electrodes/electrodes`) with argument names as keys (`n`, `tail_slots`).
`tg_lib.parse` reads a script's block as its defaults: the command line still wins, unknown keys
stop the script, required arguments may come from the block. Check scripts read their writer's
block, so a check sees the values its writer used. Put the per-device choices there (arms per
side, width, gap, ...) and run every script without design arguments.

Each writer adds its effective arguments and its choices (arm shift and contact size, contact
rectangles, lead paths and tails, pad radius, the final verdict) to `data/record.json`, next to
params.json: the device's run record. place.py's trial runs record nothing
(`KLAYOUTCLAW_NO_RECORD`).

## Procedure (one run)

```
cd <device>/klayoutclaw
P=<python>; S=<skill>/scripts; A="--flakes data/prepared.gds --params data/params.json --writes result.gds"
$P $S/flakes.py $A                                   # 0  flakes + active region
$P $S/channel.py $A                                  # 1  channel
$P $S/place.py $A --n 3 --width 1 --gap 1            # 2-4 arms, contacts, electrodes + checks
```

0. **Flakes and active region.** Copies the six flake layers (`top_top_hbn` 16/0,
   `top_graphite` 14/0, `top_hbn` 10/0, `graphene` 11/0, `bottom_hbn` 12/0, `graphite`
   13/0) and the `graphene_pieces`: starts result.gds as a copy of prepared.gds and writes the active
   region to 11/4.
   Stops if a layer is empty or the pieces do not overlap.
1. **Channel** (5/0). Rectangle along the bottom graphite, narrower than it by
   `channel.bg_inset` on each side, over `channel.y`: [y1, y2] in the local frame, or `"auto"`, the
   longest stretch where the active region reaches `channel.arm_reach` (0.7 um) past both
   bottom-graphite edges and both hBN cover the graphite (where arms and their contacts fit). Stops if it would be narrower than
   `channel.min_width` or leave the bottom graphite.
2. **Placement search** (`place.py`) chooses the free parameters and writes parts 2-4,
   then runs the checks. See "Deciding the placement yourself".

The parts `place.py` writes, each also runnable on its own:

- **Arms** (5/1), `arms.py --n --width --gap --shift`. `--n` arms per side, `--width`
  wide, `--gap` apart, centred along the channel and moved by `--shift` along y'
  (+ = towards `gate_end`), opposite arms at the same y'. Each starts `--overlap`
  inside the channel and runs out past the bottom-graphite edge as far as it stays
  `--edge-margin` 0.1 um inside the active region (`--overshoot max`, the default; a
  number in um gives a fixed overshoot). Stops if the arms leave the channel.
- **Top-gate contacts** (5/2), `contacts.py --n 2 --size`. Little islands: squares
  completely inside top hBN minus graphene, on the top graphite and outside the arm
  corridors. One per allowed area, largest areas first, as close to the top gate as they
  fit. It does not check that an electrode can reach them; the search does. Stops if
  fewer than `--n` fit.
- **Top-gate electrodes** (5/3), `electrodes.py`. Thin bridges, one per contact, 0.5 um
  wide: the shortest Manhattan route (local frame, 1 um penalty per corner) inside
  (TG ∩ TBN) − arm corridors, from the contact into the channel, both ends fully inside.
  They may cross from graphene to non-graphene; top hBN separates them from it. Stops if
  no route exists.

## Deciding the placement yourself

The user fixes the rules and some numbers. The rest are free parameters; choose them
yourself by searching them against the set rules, not by asking.

- Fixed: arms per side, arm width, gap (user, per device); 2 top-gate contacts;
  electrode width 0.5 um; overlap 0.5 um; overshoot to the active-region edge (0.1 um
  inside); corridor clearance 0.3 um.
- Free: arm shift, in ±(channel length − arm span)/2 with arm span =
  n·width + (n − 1)·gap; contact size, at least electrode width + 0.1 um (smaller
  contacts leave the router no start point). Later also the channel placement itself.

Think in sets first. The arm corridors cut the contact region TBN − G into separate
zones, and an electrode can only reach the channel through a side or end of the channel
that no corridor covers. Moving the arms one way frees that side of the channel. If the
top graphite stops at one end of the channel, that end is closed and the electrode has to
use a side.

Choice rule (user, 2026-11-17): take the largest contact size whose longest unbroken run
of passing shifts is at least 0.05 um wide, and the shift in the middle of that run. A
size that passes only in a narrower run is on a knife edge and is skipped. `place.py`
does this: sizes from 1.0 um down in 0.05 um steps; shifts on a 0.05 um grid, refined to
0.01 um at the ends of each passing run; each candidate runs arms, contacts, electrodes and
check on a temporary copy. Report its table and the choice.

A worked example on a real device is kept with the device data, not in this repo.

## Checks

Run at the very end. Exit code 1 if any check fails; do not hand over a failing design.
```
python <skill>/scripts/check.py --flakes data/prepared.gds --params data/params.json --writes result.gds
```
1. Arms are a subset of the active region.
2. Channel is a subset of the bottom graphite.
3. Top-gate contacts are a subset of top hBN minus graphene.
4. Channel, arms, top-gate contacts and top-gate electrodes are connected: the top gate
   is one polygon, so the circuit is not broken. (The user's wording: "channel intersection arms intersection
   top-gate contacts must be non-zero; they must not be cut off from each other".)
5. The top gate is a strict subset of the top graphite.
6. Top-gate electrodes are a subset of top hBN.
7. Every top-gate electrode touches the channel.
8. Top-gate contacts and electrodes stay out of the arm corridors.

When unsure how to execute a step, compare with the user's hand-drawn reference writes.gds
of a device, if one is available (it is kept with the device data, not in this repo). It is
optional: the procedure and checks are enough.
