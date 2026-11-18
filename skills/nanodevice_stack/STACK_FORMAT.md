# Stack file format (`stack.json`, format `klayoutclaw.stack/0.1`)

The hand-off from stack design (flake_catalog → stack_design) to KlayoutClaw. One file per device, at
`<device>/plan/stack.json` in the device folder layout (flake_catalog `device_pipeline_roadmap.md`):
`plan/` (blueprint, stack.json, stack/masks), `ingredients/` (single-flake images, catalog GDS/JSON),
`photos/` (full stack, in-process photos, chip template), `klayoutclaw/` (KlayoutClaw output). Paths are
relative to the folder holding stack.json, so ingredients and photos appear as `../ingredients/...`,
`../photos/...`.
Today it is written by `pptx_to_stack.py` from a hand-made blueprint deck; later `stack_design`
writes it directly.

```jsonc
{
  "format": "klayoutclaw.stack/0.1",
  "sample": "sample01",
  "device": { "type": "hall_bar_dualgated_graphite", "recipe": "dualgated_hallbar" },
  "imaging": { "objective": "50x", "um_per_px": 0.06173, "image_size_px": [3584, 2748],
               "um_per_px_source": "catalog GDS frame (221.24 um / 3584 px)" },
  "full_stack": { "raw": "../photos/full_stack_raw.png", "lut": "../photos/full_stack_w_LUT.png" },
  "template": { "gds": "../photos/Template.gds", "field": "bottom-left",
                "field_center_um": [2500, 2500], "rotation_hint_deg": 0 },
  "blueprint": { "source": "blueprint.pptx", "slide": 6,
                 "frame": "blueprint px: slide EMU / emu_per_px, y down, 1 blueprint px = 1 image px",
                 "emu_per_px": 2495.6 },
  "layers": [                                   // stack order, top -> bottom
    { "role": "top_hBN",                        // material key used downstream (traces.json / layers)
      "material": "hBN", "flake_id": "BN001a",
      "image": "../ingredients/top_BN.png",     // single-flake image (same objective as full stack)
      "outline": { "source": "catalog",         // catalog | pptx_alpha | mask | none
                   "gds": "../ingredients/top_BN.gds", "layer": [20, 0], "json": "../ingredients/top_BN.json" },
      "pieces": [                               // >= 1; several pieces = one flake cut and restacked
        { "id": "top_hBN",
          "crop_px": [x0, y0, x1, y1],          // region of `image` that belongs to this piece
          "mask": "stack/masks/top_hBN.png",    // binary mask in `image` px (written by the converter)
          "pose": { "M": [[a, b, tx], [c, d, ty]],   // image px -> blueprint px
                    "rot_deg": 98.83, "scale": 1.0, "flip": false },
          "twist_deg": null } ] },
    { "role": "graphite", "flake_id": null, "image": "../ingredients/bottom_graphite.png",
      "outline": { "source": "mask" }, "pieces": [ { "id": "graphite", "pose": null, ... } ] }
  ],
  "ignored": [ { "picture": "Picture 7", "media": "image8.png", "reason": "..." } ],
  "notes": [ "..." ]
}
```

Rules
- Material keys: `top_top_hBN` (16/0), `top_graphite` (14/0), `top_hBN` (10/0), `graphene` (11/0),
  `bottom_hBN` (12/0), `graphite` (= bottom graphite, 13/0). Pieces of one material get datatypes
  1, 2, 3 … on the same layer (e.g. graphene pieces 11/1, 11/2, 11/3); datatype 0 is their union.
- `pose: null` means "not planned": the piece is found in the full stack without a prior.
- Catalog GDS frames are the whole image in um, origin bottom-left, y up
  (`px = x_um / um_per_px`, `row = (H_um - y_um) / um_per_px`).
- The blueprint is a plan. `place_stack.py` fits it to the full stack (one global similarity, then
  a small per-layer correction) and reports how far each layer moved from the plan.
