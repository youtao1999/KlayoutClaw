---
name: nanodevice_chain
description: Run the whole six-piece dual-gated device design on a device folder in one command, from its klayoutclaw/data/params.json - nanodevice_prepare, _topgate, _contacts, _electrodes, _pads, _fingers, _finalcheck (check and export) - re-running every earlier check after each skill, stopping at the first failure, resumable with --from.
---

# nanodevice_chain -- the six-piece design in one run

Status: in development (2026-11-19). Ran end to end on one real device.

## Files

```
<device>/                      design.gds (the stack plan: outlines + a rough layout; read, never written),
                               photos/, ingredients/ (catalog GDS per flake), Template.gds
<device>/klayoutclaw/
  data/params.json             every input of the chain (template: nanodevice_topgate/params_six_piece.json)
  data/prepared.gds            template + the flakes where they landed (nanodevice_prepare)
  data/record.json             run record: every step's arguments and choices
  result.gds  + result.lyp     the design file: template, flakes, every design layer (review this)
  writes.gds  + writes.lyp     only the EBL write layers, exported from result.gds (send this)
  <photo>.lyimg                the full-stack photo placed by the marker alignment
  work/                        review renders (scratch)
```

Flakes shift during stacking, so the plan only gives each flake's outline and the graphene (invisible
in every photo); every visible flake is refitted to the photo. Read the device's deviation note
first (what happened during stacking, how it differs from the plan) and set `prepare` accordingly.

## Run

```
python3 <KlayoutClaw>/skills/nanodevice_chain/scripts/run.py --params <device>/klayoutclaw/data/params.json
python3 .../run.py --params ... --list              # the steps
python3 .../run.py --params ... --from topgate/place # resume after fixing params
```

The steps, in order: `prepare/align, fit, graphene, prepared`; `topgate/flakes, channel, place`;
`contacts/checker, mask, contacts`; `electrodes/electrodes`; `pads/pads`; `fingers/fingers`;
after each skill the checks of it and of every earlier skill; then `finalcheck/check` and
`finalcheck/export`. Each step is the skill's own script; see that skill's SKILL.md for its rules.

When it stops:
- `prepare/align`: wrong `field_center_um` / `rotation_hint_deg`, or markers hidden; see
  `work/prepare/markers.png`.
- `prepare/fit` exit 3: a flake fits almost as well turned by about 180 deg. Compare
  `work/prepare/fit_<role>.png`, ask the operator, pin `rot_range` for that flake.
- `topgate/place`: no arm placement passes. Fewer arms (`args.topgate/place.n`), narrower gap, or
  check the channel (`channel.y`, "auto" by default in the template).
- a check after a later skill: that skill changed an earlier layer; it must not.

Design choices go in params (`args`, per script); the run record (`data/record.json`) holds what was
used and chosen.
