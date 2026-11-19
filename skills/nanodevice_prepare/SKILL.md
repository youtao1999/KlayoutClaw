---
name: nanodevice_prepare
description: First step of the six-piece device design. Place every flake of a finished stack in chip coordinates and write the device folder's klayoutclaw/data/prepared.gds, which nanodevice_topgate and the later skills read. Aligns the full-stack photo to the chip template's fine markers, fits each flake's catalog GDS (or picture) into the photo over all rotations, and places the invisible graphene pieces from the stack plan (design.gds) through the flake that picked them up.
---

# nanodevice_prepare -- flakes in chip coordinates

Status: in development (2026-11-19). Align, fit, graphene and prepared exist; tested on one real
device (rebuilt its prepared.gds from params alone).

## Why

The design skills work on `data/prepared.gds`: the chip template plus every flake outline in chip
coordinates (um). The photo shows the stack, the catalog has each flake's outline (GDS from the
single-flake picture), the stack plan (`design.gds`, stack_design's blueprint) shows where the
graphene went. This skill joins them.

Monolayer graphene is invisible in every photo, so it can only come from the plan, placed relative to
the flake that picked it up (the top hBN). The plan is not what happened: the operator may turn a flake
during stacking (one device had its bottom hBN turned 180 deg). So:
- fit every visible flake over **all** rotations, never in a window taken from the plan;
- read the device's deviation note (what happened during stacking and how it differs from the plan)
  before trusting the plan for anything but the graphene; if there is none, ask the operator.

## Inputs

`<device>/klayoutclaw/data/params.json`, block `prepare` (paths relative to the device folder):

```json
"prepare": {
 "photo": "photos/full_stack_raw.png", "template": "Template.gds",
 "field_center_um": [2500, 2500], "rotation_hint_deg": 0, "um_per_px": 0.06173,
 "marker_layer": [19, 0], "marker_pitch_um": 50, "region_px": [1150, 600, 2700, 2200],
 "flakes": {
  "top_top_hBN": {"gds": "ingredients/BN003a.gds", "layer": [20, 0]},
  "top_graphite": {"gds": "ingredients/Gt001a.gds", "layer": [30, 0]},
  "top_hBN": {"gds": "ingredients/BN001a.gds", "layer": [20, 0]},
  "bottom_hBN": {"gds": "ingredients/BN002a.gds", "layer": [20, 0]},
  "graphite": {"image": "ingredients/bottom_graphite_cut.png"}
 },
 "graphene": {"design": "design.gds", "picked_by": "top_hBN", "picked_by_layer": [40, 0],
              "pieces_layer": [2, 0], "compare": {"bottom_hBN": [50, 0]}},
 "deviations": "operator's note: what happened during stacking, how it differs from the plan"
}
```

- `field_center_um` and `rotation_hint_deg` (0 or 180): the chip's fine-marker fields are identical,
  so the field and the 0/180 choice come from the operator.
- A flake is one of: a catalog GDS layer (`gds`, `layer`: 20/0 hBN, 30/0 graphite outline; the
  GDS frame is the picture in um, layer 0/0), a picture with a transparent background (`image`, e.g.
  a cut piece cropped in PowerPoint), or a polygon already in photo px (`polygon_px`, traced by hand).
  Optional `scale` (default 1: the same 50x camera) and `rot_range` [lo, hi] (only to pin a rotation
  the operator confirmed after an ambiguous fit).
- Roles: `top_top_hBN` 16/0, `top_graphite` 14/0, `top_hBN` 10/0, `bottom_hBN` 12/0, `graphite`
  (bottom graphite) 13/0; graphene pieces 11/1, 11/2, ... and their union 11/0.

Python: `python3` with klayout, numpy, scipy, opencv, gdstk.

## Procedure

```
P=<device>/klayoutclaw/data/params.json; S=<KlayoutClaw>/skills/nanodevice_prepare/scripts
python3 $S/align.py --params $P       # 1 marker alignment -> data/gds_warp_px.npy (+ gate)
python3 $S/fit.py --params $P         # 2 every visible flake, all rotations -> data/prepare/<role>.json
python3 $S/graphene.py --params $P    # 3 graphene pieces from the plan -> data/prepare/graphene.json
python3 $S/prepared.py --params $P    # 4 data/traces.json + data/prepared.gds
```

1. **Align.** `fine_marker_align.py`: marker response map, lattice from blob pairs, hypothesis
   search, per-site refinement. The search keeps only windows around the marker lattice (flakes light
   up the response as much as the markers), anchors on the blob with the most neighbours at the marker
   pitch, and picks which site is which by matching each site's coded square pattern. Gate: at least 4
   sites, mean residual < 0.3 um, pixel size within 2 % of `um_per_px`. Review
   `work/prepare/markers.png`: the template squares (green) must sit on every marker.
2. **Fit.** Each flake's outline is fitted rigidly to the photo's edges (place_stack's sweep and edge
   refine) over all rotations in 45 deg windows. The best fit and the best one at least 90 deg away
   are reported; if the alternative's cost is within 15 % of the best, the script warns: compare
   `work/prepare/fit_<role>.png` (best green, alternative magenta), ask the operator, pin `rot_range`.
3. **Graphene.** The plan's last step cell (`S<n>_...`, or `cell`) is mapped onto the photo by fitting
   its outline of the `picked_by` flake to that flake's fit (IoU, all rotations); the pieces follow,
   clipped to that flake. Other plan layers listed in `compare` are reported for information only: a
   low IoU means the stack deviated from the plan there or that fit is wrong. Review
   `work/prepare/graphene.png` (active region in white).
4. **Prepared.** Contours of every fitted flake and the pieces go to `data/traces.json`;
   `make_prepared.py` maps them through the alignment into the template (template layers that collide
   with the flake layers move to 1xx/0). Review `work/prepare/all.png`.

Then continue with nanodevice_topgate. The fits, the plan mapping and the alignment quality are added to
`data/record.json` (nanodevice_topgate, "Params and run record").

## Limits

- A flake whose edges are mostly hidden under others is fitted only to a few degrees; the graphene
  placed through it inherits that (about 2 um on the first device). Check the overlay.
- Through-PDMS photos (stamp) are magnified (~6 %) and blurred: use them only as a check, with `scale`.
- The plan is the only source for the graphene until AFM or a picture of the laser-cut graphene is
  available.
