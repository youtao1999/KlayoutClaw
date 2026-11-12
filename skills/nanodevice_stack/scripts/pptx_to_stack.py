#!/usr/bin/env python
"""Convert a hand-made blueprint deck (one slide of cropped / rotated flake pictures) into stack.json.

Each picture on the slide is identified with one of the device folder's single-flake images by
comparing its opaque pixels (the deck stores background-removed copies, possibly downscaled). Its
crop, flip, rotation and position become a pose: image px -> blueprint px. Several pictures of the
same image are pieces of one flake (e.g. graphene cut for twisted stacking).

Device folder layout (stack_design / flake_catalog device_pipeline_roadmap.md): the deck is read from
<dir>/plan/, the single-flake images and catalog GDS/JSON from <dir>/ingredients/, the full stack and the
chip template from <dir>/photos/. Writes <dir>/plan/stack.json and <dir>/plan/stack/masks/*.png; paths in
stack.json are relative to plan/ (../ingredients/..., ../photos/...).

Usage:
  python pptx_to_stack.py --dir <device_folder> --pptx blueprint.pptx --slide 6 \
     --sample sample01 --order top_top_hBN,top_graphite,top_hBN,graphene,bottom_hBN,graphite \
     --role toptopbn.png=top_top_hBN:BN001b --role top_graphite.png=top_graphite \
     --role top_BN.png=top_hBN:BN001a --role graphene.png=graphene:Gr001a \
     --role bottom_BN.png=bottom_hBN:BN002a --role bottom_graphite.png=graphite \
     --catalog top_BN.png=top_BN.gds:20/0 --catalog graphene.png=graphene.gds:1/0 \
     --catalog bottom_BN.png=bottom_BN.gds:20/0 \
     --twist graphene=1.9 --template Template.gds --field bottom-left --field-center 2500,2500 \
     --device hall_bar_dualgated_graphite:dualgated_hallbar --out stack.json
Also renders plan/stack/blueprint_slide<N>.png.
"""
import argparse
import json
import math
import os
import re
import sys
import zipfile

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stack_io import catalog_mask  # noqa: E402



def read_slide(z, n):
    x = z.read("ppt/slides/slide%d.xml" % n).decode()
    rels = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="\.\./media/([^"]+)"',
                           z.read("ppt/slides/_rels/slide%d.xml.rels" % n).decode()))
    if re.search(r"<p:grpSp>.*?<p:pic>", x, re.S):
        sys.exit("slide %d has grouped pictures - ungroup them in PowerPoint first" % n)
    pics = []
    for pic in re.findall(r"<p:pic>.*?</p:pic>", x, re.S):
        name = re.search(r'name="([^"]*)"', pic).group(1)
        media = rels[re.search(r'<a:blip r:embed="(rId\d+)"', pic).group(1)]
        sr = re.search(r"<a:srcRect([^/]*)/>", pic)
        crop = {k: int(v) / 1e5 for k, v in re.findall(r'(\w)="(-?\d+)"', sr.group(1))} if sr else {}
        xf = re.search(r"<a:xfrm([^>]*)>\s*<a:off x=\"(-?\d+)\" y=\"(-?\d+)\"/>\s*<a:ext cx=\"(\d+)\" cy=\"(\d+)\"/>", pic)
        attrs = xf.group(1)
        rot = re.search(r'rot="(-?\d+)"', attrs)
        pics.append(dict(name=name, media=media, crop=crop, rot=int(rot.group(1)) / 60000 if rot else 0.0,
                         flipH='flipH="1"' in attrs, flipV='flipV="1"' in attrs,
                         off=(int(xf.group(2)), int(xf.group(3))), ext=(int(xf.group(4)), int(xf.group(5)))))
    texts = [t for t in re.findall(r"<a:t>([^<]*)</a:t>", x) if t.strip()]
    return pics, texts


def pose_emu(p, W, H):
    """2x3: media px -> slide EMU (PowerPoint: crop, flip, scale to ext, rotate about box centre)."""
    l, t, r, b = (p["crop"].get(k, 0.0) for k in "ltrb")
    x0, y0, x1, y1 = W * l, H * t, W * (1 - r), H * (1 - b)
    sx, sy = p["ext"][0] / (x1 - x0), p["ext"][1] / (y1 - y0)
    th = math.radians(p["rot"])
    R = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
    A = R @ np.diag([(-1 if p["flipH"] else 1) * sx, (-1 if p["flipV"] else 1) * sy])
    c_src = np.array([(x0 + x1) / 2, (y0 + y1) / 2])
    c_dst = np.array([p["off"][0] + p["ext"][0] / 2, p["off"][1] + p["ext"][1] / 2])
    return np.hstack([A, (c_dst - A @ c_src)[:, None]]), (x0, y0, x1, y1), (sx, sy)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="device folder (plan/, ingredients/, photos/)")
    ap.add_argument("--pptx", required=True)
    ap.add_argument("--slide", type=int, required=True)
    ap.add_argument("--sample", required=True)
    ap.add_argument("--order", required=True, help="roles top -> bottom, comma separated")
    ap.add_argument("--role", action="append", default=[], help="image=role[:flake_id]")
    ap.add_argument("--catalog", action="append", default=[], help="image=catalog.gds:layer/dt")
    ap.add_argument("--twist", action="append", default=[], help="role=deg (nominal twist between pieces)")
    ap.add_argument("--template")
    ap.add_argument("--field")
    ap.add_argument("--field-center")
    ap.add_argument("--rotation-hint", type=float, default=0.0)
    ap.add_argument("--device", help="type:recipe")
    ap.add_argument("--objective", default="50x")
    ap.add_argument("--full-stack", default="full_stack_raw.png")
    ap.add_argument("--full-stack-lut", default="full_stack_w_LUT.png")
    ap.add_argument("--match-max", type=float, default=5.0, help="max mean |diff| on opaque px to accept a match")
    ap.add_argument("--out", default="stack.json")
    a = ap.parse_args()
    PL, ING, PH = (os.path.join(a.dir, sub) for sub in ("plan", "ingredients", "photos"))
    ing, ph = (lambda f: "../ingredients/" + f), (lambda f: "../photos/" + f)   # stored relative to plan/
    os.makedirs(os.path.join(PL, "stack", "masks"), exist_ok=True)

    roles = {}
    for s in a.role:
        img, _, rest = s.partition("=")
        role, _, fid = rest.partition(":")
        roles[img] = (role, fid or None)
    cats = {}
    for s in a.catalog:
        img, _, rest = s.partition("=")
        gds, _, ld = rest.rpartition(":")
        cats[img] = (gds, [int(v) for v in ld.split("/")])
    twists = {k: float(v) for k, v in (s.split("=") for s in a.twist)}

    images = {f: cv2.imread(os.path.join(ING, f)) for f in roles}
    for f, im in images.items():
        if im is None:
            sys.exit("cannot read %s" % f)
    H0, W0 = next(iter(images.values())).shape[:2]

    z = zipfile.ZipFile(os.path.join(PL, a.pptx))
    pics, texts = read_slide(z, a.slide)

    placed, ignored, emu_px = [], [], []
    media_cache = {}
    for p in pics:
        if p["media"] not in media_cache:
            buf = np.frombuffer(z.read("ppt/media/" + p["media"]), np.uint8)
            media_cache[p["media"]] = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
        m = media_cache[p["media"]]
        if m is None or m.ndim != 3:
            ignored.append(dict(picture=p["name"], media=p["media"], reason="unreadable media")); continue
        alpha = m[..., 3] if m.shape[2] == 4 else np.full(m.shape[:2], 255, np.uint8)
        best = None
        for f, im in images.items():
            ims = cv2.resize(im, (m.shape[1], m.shape[0]), interpolation=cv2.INTER_AREA) if im.shape[:2] != m.shape[:2] else im
            fg = alpha > 128
            d = float(np.abs(ims[fg].astype(int) - m[..., :3][fg].astype(int)).mean())
            if best is None or d < best[0]:
                best = (d, f)
        if best[0] > a.match_max:
            ignored.append(dict(picture=p["name"], media=p["media"],
                                reason="not one of the provided images (best %s, mean diff %.1f)" % (best[1], best[0])))
            continue
        f = best[1]
        Mm, (x0, y0, x1, y1), (sx, sy) = pose_emu(p, m.shape[1], m.shape[0])
        k = m.shape[1] / W0                                   # media px per image px
        M = Mm @ np.array([[k, 0, 0], [0, k, 0], [0, 0, 1.0]])  # image px -> EMU
        emu_px.append(sx * k)
        crop = [x0 / k, y0 / k, x1 / k, y1 / k]
        a_full = cv2.resize(alpha, (W0, H0), interpolation=cv2.INTER_NEAREST)
        placed.append(dict(p=p, image=f, M=M, crop=crop, alpha=a_full, match=round(best[0], 2)))

    epx = float(np.median(emu_px))
    layers = []
    for role in a.order.split(","):
        img = next((f for f, (r, _) in roles.items() if r == role), None)
        if img is None:
            sys.exit("no --role image for %s" % role)
        fid = roles[img][1]
        mine = [q for q in placed if q["image"] == img]
        if img in cats:
            gds, ld = cats[img]
            base = catalog_mask(os.path.join(ING, gds), ld, (H0, W0))
            js = os.path.splitext(gds)[0] + ".json"
            outline = dict(source="catalog", gds=ing(gds), layer=ld, json=ing(js) if os.path.exists(os.path.join(ING, js)) else None)
        elif mine:
            base = np.where(mine[0]["alpha"] > 128, 255, 0).astype(np.uint8)
            outline = dict(source="pptx_alpha", media=mine[0]["p"]["media"])
        else:
            base, outline = None, dict(source="none")
        pieces = []
        if not mine:
            pieces.append(dict(id=role, crop_px=None, mask=None, pose=None, twist_deg=None))
        rots = [q["p"]["rot"] for q in mine]
        for i, q in enumerate(sorted(mine, key=lambda q: q["p"]["rot"])):
            pid = role if len(mine) == 1 else "%s_%d" % (role, i + 1)
            M = q["M"] / epx                                  # image px -> blueprint px
            x0, y0, x1, y1 = (int(round(v)) for v in q["crop"])
            msk = np.zeros((H0, W0), np.uint8)
            if base is not None:
                msk[max(y0, 0):y1, max(x0, 0):x1] = base[max(y0, 0):y1, max(x0, 0):x1]
            mpath = os.path.join("stack", "masks", pid + ".png")
            cv2.imwrite(os.path.join(PL, mpath), msk)
            sc = math.hypot(M[0, 0], M[1, 0])
            pieces.append(dict(id=pid, picture=q["p"]["name"], media=q["p"]["media"], crop_px=[x0, y0, x1, y1],
                               mask=mpath, mask_area_px=int((msk > 0).sum()),
                               pose=dict(M=[[round(v, 6) for v in row] for row in M.tolist()],
                                         rot_deg=round(q["p"]["rot"], 3), scale=round(sc, 4),
                                         flip=bool(q["p"]["flipH"] or q["p"]["flipV"])),
                               twist_deg=round(q["p"]["rot"] - min(rots), 3) if len(mine) > 1 else None,
                               match_mean_diff=q["match"]))
        layers.append(dict(role=role, flake_id=fid, image=ing(img), outline=outline, pieces=pieces,
                           nominal_twist_deg=twists.get(role)))

    stack = {"format": "klayoutclaw.stack/0.1", "sample": a.sample,
             "imaging": dict(objective=a.objective, image_size_px=[W0, H0])}
    cat_um = None
    for img, (gds, ld) in cats.items():
        import klayout.db as db
        ly = db.Layout(); ly.read(os.path.join(ING, gds))
        b = db.Region(ly.top_cells()[0].begin_shapes_rec(ly.layer(0, 0))).bbox()
        if not b.empty():
            cat_um = b.width() * ly.dbu / W0
            break
    if cat_um:
        stack["imaging"].update(um_per_px=round(cat_um, 6), um_per_px_source="catalog GDS image frame (layer 0/0 width / image width)")
    if a.device:
        t, _, r = a.device.partition(":")
        stack["device"] = dict(type=t, recipe=r or None)
    stack["full_stack"] = dict(raw=ph(a.full_stack), lut=ph(a.full_stack_lut) if os.path.exists(os.path.join(PH, a.full_stack_lut)) else None)
    if a.template:
        stack["template"] = dict(gds=ph(a.template), field=a.field,
                                 field_center_um=[float(v) for v in a.field_center.split(",")] if a.field_center else None,
                                 rotation_hint_deg=a.rotation_hint)
    stack["blueprint"] = dict(source=a.pptx, slide=a.slide, slide_text=texts, emu_per_px=round(epx, 2),
                              frame="blueprint px = slide EMU / emu_per_px, y down; 1 blueprint px = 1 image px")
    stack["layers"] = layers
    stack["ignored"] = ignored
    json.dump(stack, open(os.path.join(PL, a.out), "w"), indent=1)

    # render the plan (outlines in blueprint px) for a visual check
    cols = [(255, 255, 0), (255, 0, 255), (0, 255, 255), (0, 0, 255), (0, 200, 0), (255, 0, 0), (0, 128, 255)]
    allpts = []
    for L in layers:
        for pc in L["pieces"]:
            if pc["pose"] and pc["mask"]:
                cs, _ = cv2.findContours(cv2.imread(os.path.join(PL, pc["mask"]), 0), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                M = np.array(pc["pose"]["M"])
                pc["_c"] = [c.reshape(-1, 2) @ M[:, :2].T + M[:, 2] for c in cs]
                allpts += [c for c in pc["_c"]]
    if allpts:
        P = np.vstack(allpts); lo = P.min(0) - 40; hi = P.max(0) + 40
        can = np.full((int(hi[1] - lo[1]), int(hi[0] - lo[0]), 3), 255, np.uint8)
        for i, L in enumerate(layers):
            for pc in L["pieces"]:
                for c in pc.pop("_c", []):
                    cv2.polylines(can, [np.round(c - lo).astype(np.int32)], True, cols[i % len(cols)], 3)
            cv2.putText(can, L["role"], (10, 30 + 30 * i), 0, 0.9, cols[i % len(cols)], 2)
        cv2.imwrite(os.path.join(PL, "stack", "blueprint_slide%d.png" % a.slide), can)
    print(json.dumps(dict(layers=[(L["role"], [(p["id"], p["pose"]["rot_deg"] if p["pose"] else None, p.get("mask_area_px")) for p in L["pieces"]]) for L in layers],
                          ignored=ignored, emu_per_px=epx, um_per_px=stack["imaging"].get("um_per_px")), indent=1))


if __name__ == "__main__":
    main()
