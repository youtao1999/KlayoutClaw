# Dual-gated Hall bar recipe (graphite top gate + graphite bottom gate)

Scripts used by a device folder's `instruction.md`, which holds the procedure, process and
design rules. Everything runs offline on GDS files with `klayout.db`
(python from the `instrMCPdev` conda env). Routing also runs offline
(`route_offline.py` runs the same `tools/route_worker.py` engine that MCP `auto_route` uses), so
KLayout is only needed for viewing and screenshots. Shared code comes from `../topgated_hallbar`:
`recipe_lib.py`, `fine_marker_align.py`, `make_prepared.py` and `klayout_open.py`.

Stack (top → bottom): top-top hBN L16 → top graphite L14 → top hBN L10 → graphene L11 →
bottom hBN L12 → bottom graphite L13 (the local frame is built from L13).

| Process step | What happens | Layers |
|---|---|---|
| 1 | One mask. CHF3 removes the top-top hBN, then O2 removes the top graphite outside the top gate | write **L31** = window − L1 − L26; L1 top gate (resist stays), L26 bottom-graphite protect |
| 2 | One write: graphene edge contacts, top-gate contact, bottom-gate contact, leads and pads. CHF3 etches the top hBN, then metal is evaporated | **L23** fine (incl. tips), **L24** top-gate contact, **L22** bottom-gate contact, **L2** wide leads + pads |
| 3 | Final etch: fingers between the electrodes. Resist stays on the top gate, every contact and the bridges | write **L20**; scratch L25 protect, L15 outline |

| Step | Script | In → Out |
|---|---|---|
| P3 | `../topgated_hallbar/fine_marker_align.py` | full-stack image + template → `gds_warp*.npy` |
| P4 | `../topgated_hallbar/make_prepared.py` | template + `traces.json` (from `combine_ingredients.py`) → `prepared.gds` |
| D1 | `build_device.py` | → `device.gds` (L1, L24, L22, L26, L31, L21 tips, L25, L2 pads, L100 pins) + `design.json` |
| R1 | `route_offline.py` | `device.gds` → `routed.gds` (params `routing` block) |
| R2 | `post_route.py` | → `post.gds` (L23 all fine electrodes, L2 one polygon per net; tip-escape fix) |
| E | `etch_mask.py` | → `result.gds` (L15, L20) |
| V | `verify.py` | → `verify.json` (about 40 checks: device, step 1, step 2, step 3, surviving graphene) |
| W | `export_writes.py` | `result.gds` → `writes.gds` + `writes.lyp` (one layer per EBL write) + `<image>.lyimg` (photo placed by the marker alignment) |

`selftest.py` builds rectangular flakes on your chip template (`--template`) and runs P4 through W with
`params_synthetic.json`; every check passes. Two deliberately bad designs are caught:
- `protect.top_gate_grow = 0.3` leaves an ungated graphene ring that joins the contacts, and
  verify fails.
- A top-gate contact placed over graphene makes post_route refuse the route.

Device parameter files (`params_<device>.json`) are designs, not code: they stay in the device
folder and out of git. `params_synthetic.json` is the only parameter file in the repo.

Since 2026-11-11 the recipe also has:
- an automatic channel set from the bottom-graphite edges (`channel.bg_inset`);
- graphene pieces (`layers.graphene_pieces`), with a check that the channel lies on all of them;
- `step1.bg_protect_regions`, to protect only some exposed bottom graphite, plus a hard gate-short
  check (no top graphite left on exposed bottom graphite after step 1) and a bottom-gate
  connectivity check;
- `arms.min_tip_graphene_frac`;
- exact distances through shapely (`dg_lib.py`);
- two contacts per gate (`tg_contact` / `graphite_contact` lists; verify enforces `min_gate_contacts`,
  default 2), bottom-gate contacts on graphene that sits directly on the bottom graphite
  (`isolated_graphene`, cut from the device in step 3), and step-3 resist on bare bottom graphite at
  each bottom-gate contact;
- per-side arm positions (`arms.y` = {"L": [...], "R": [...]}), overshoot and bridge, a hard check that
  every contact touches the overlap of all graphene pieces (`arms.min_active_overlap`), and straight
  escape stubs (`arms.escape`, `escape` on gate contacts) so routes start outside the device.

Design choices to confirm with the user:
- `protect.top_gate_grow = 0`: the step-3 resist edge sits exactly on the top-gate edge. Any grow
  leaves an ungated graphene ring around the top gate that shunts neighbouring probes.
- `finger.overshoot`: how far the top-gate arms reach past the bottom-graphite edge. earlier devices
  used 0.5-0.8.
- `arms.tip_length = 1.4`: contact length along the arm. Carried over from the top-gated recipe.
