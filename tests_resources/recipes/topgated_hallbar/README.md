# Top-gated Hall bar recipe

Scripts used by a device folder's `instruction.md` (the full procedure, design rules and
reference numbers live there). Geometry is built offline on GDS files with `klayout.db`
(python from the `instrMCPdev` conda env); KLayout/MCP is only used for
auto_route, screenshots and viewing (`klayout_open.py`).

| Step | Script | In → Out |
|---|---|---|
| P3 | `fine_marker_align.py` | full-stack image + template → `gds_warp.npy`, `gds_warp_px.npy`, report |
| P4 | `make_prepared.py` | template + `traces.json` + warp (+ defects) → `prepared.gds` (template L11/L12 → 111/112) |
| D1 | `build_device.py` | `prepared.gds` + params → `device.gds` (L1, L5, L21 tips, L22, L25, L2 pads, L100 pins) + `design.json` |
| R1 | (KLayout `auto_route`, params `routing` block) | `device.gds` → `routed.gds` |
| R2 | `post_route.py` | `routed.gds` → `post.gds` (L23 electrodes incl. tips, L5, L2 per-net leads+pads; auto tip-escape fix) |
| E  | `etch_mask.py` | `post.gds` → `result.gds` (L15 clean simplified outline, L20 = L15 − L25 + straight 10 µm finger rectangles) |
| V  | `verify.py` | `result.gds` → `verify.json` (26 checks) |

Parameter files (`params_<device>.json`) hold device designs and stay in the device folder, out of git. The chain was re-run end to end on a
reference device on 2026-09-23 and reproduced the hand-made design (identical L1/L22, all checks PASS); the etch mask was then switched to the clean outline + straight-finger construction (also all checks PASS).
