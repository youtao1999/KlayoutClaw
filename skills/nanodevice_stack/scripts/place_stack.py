#!/usr/bin/env python
"""Place every flake of a stack.json in the full-stack image and write traces.json.

Evidence order (user rule, 2026-11-11): every layer that can be seen is placed from live images -
the full-stack photo and in-process photos (e.g. the stamp on PDMS). The blueprint is used only for
layers that cannot be seen (monolayer graphene / the active region), relative to the placed layer
that picked them up. Per role, one of:
  --outline role=mask.png             live outline already in full-stack px
  --area-target role=req.png[:allow]  flake mask fitted to a live full-stack region (rotation sweep + IoU)
  --edge-fit role=dark|bright         flake mask fitted to full-stack edges near the placed layers
  --follow role=leader                blueprint pose relative to the placed leader (invisible layers)
Pieces of one role keep their blueprint poses relative to the fitted piece; --clip keeps e.g.
graphene inside the top hBN that picked it up.
Outputs (in --out): placement.json, traces.json (full-stack px; pieces of a role as <role>_<k> on
datatype k, union on datatype 0), overlay.png, masks/<piece>_full.png.
"""
import argparse
import json
import math
import os
import sys

import cv2
import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stack_io import apply, compose, load_stack, similarity  # noqa: E402

LAYER_NUM = {"top_top_hBN": 16, "top_graphite": 14, "top_hBN": 10, "graphene": 11, "bottom_hBN": 12, "graphite": 13}
COLORS = {"top_top_hBN": (255, 255, 0), "top_graphite": (255, 0, 255), "top_hBN": (0, 255, 255),
          "graphene": (0, 0, 255), "bottom_hBN": (0, 200, 0), "graphite": (255, 128, 0)}


def edge_dist(img, tau):
    lab = cv2.cvtColor(cv2.GaussianBlur(img, (0, 0), 2.0), cv2.COLOR_BGR2LAB).astype(np.float32)
    g = sum(cv2.magnitude(cv2.Sobel(lab[..., k], cv2.CV_32F, 1, 0), cv2.Sobel(lab[..., k], cv2.CV_32F, 0, 1)) for k in range(3))
    thr = max(np.percentile(g, 97), 4.0 * np.median(g))   # well above the flat-substrate noise
    edges = (g > thr).astype(np.uint8)
    edges = cv2.ximgproc.thinning(edges * 255) if hasattr(cv2, "ximgproc") else edges * 255
    dt = cv2.distanceTransform(255 - edges, cv2.DIST_L2, 5)
    return np.minimum(dt, tau), edges


def outline_pts(mask, step=3):
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    pts = [c.reshape(-1, 2)[::step] for c in cs if cv2.contourArea(c) > 200]
    return np.vstack(pts).astype(float) if pts else np.zeros((0, 2))


def cost(dt, pts):
    h, w = dt.shape
    x = np.clip(np.round(pts[:, 0]).astype(int), 0, w - 1)
    y = np.clip(np.round(pts[:, 1]).astype(int), 0, h - 1)
    out = (pts[:, 0] < 0) | (pts[:, 0] >= w) | (pts[:, 1] < 0) | (pts[:, 1] >= h)
    d = dt[y, x]
    d[out] = dt.max()
    return float(d.mean())


def sweep(dt, pts, rots, scale, ds=4, region=None, sigma=3.0):
    """Best (rot, tx, ty) of a similarity applied to pts (rotation about pts centroid) by
    rotation sweep + template matching on an edge-proximity map at 1/ds resolution."""
    prox = np.exp(-(cv2.resize(dt, None, fx=1 / ds, fy=1 / ds) / ds) ** 2 / (2 * sigma ** 2)).astype(np.float32)
    if region is not None:
        x0, y0, x1, y1 = (int(v / ds) for v in region)
        mask = np.zeros_like(prox); mask[max(y0, 0):y1, max(x0, 0):x1] = 1; prox *= mask
    c = pts.mean(0)
    best = None
    for r in rots:
        q = apply(similarity(r, scale, 0, 0, *c), pts) / ds
        lo = np.floor(q.min(0)) - 2
        tpl = np.zeros((int(q[:, 1].max() - lo[1]) + 3, int(q[:, 0].max() - lo[0]) + 3), np.float32)
        qi = np.round(q - lo).astype(int)
        tpl[qi[:, 1], qi[:, 0]] = 1.0
        if tpl.shape[0] >= prox.shape[0] or tpl.shape[1] >= prox.shape[1]:
            continue
        res = cv2.matchTemplate(prox, tpl, cv2.TM_CCORR)
        _, mv, _, ml = cv2.minMaxLoc(res)
        score = mv / len(qi)
        if best is None or score > best[0]:
            # template top-left ml corresponds to lo -> shift in full res
            best = (score, r, (ml[0] - lo[0]) * ds, (ml[1] - lo[1]) * ds)
    _, r, tx, ty = best
    return similarity(r, scale, tx, ty, *c), r, best[0]


def refine(dt, pts, T0, max_rot, max_shift_px, scale_free=False):
    c = apply(T0, pts).mean(0)

    def T_of(x):
        r, tx, ty = x[:3]
        s = 1.0 + (x[3] if scale_free else 0.0)
        return compose(similarity(r, s, tx, ty, *c), T0)

    def f(x):
        pen = 0.0
        if abs(x[0]) > max_rot:
            pen += (abs(x[0]) - max_rot) * 10
        if math.hypot(x[1], x[2]) > max_shift_px:
            pen += (math.hypot(x[1], x[2]) - max_shift_px)
        return cost(dt, apply(T_of(x), pts)) + pen

    steps = [1.0, 15.0, 15.0] + ([0.01] if scale_free else [])
    best = None
    for start in ([0, 0, 0], [1.5, 0, 0], [-1.5, 0, 0]):
        st = np.array(start + ([0.0] if scale_free else []), float)
        simplex = np.vstack([st] + [st + np.eye(len(st))[i] * steps[i] for i in range(len(st))])
        r = minimize(f, st, method="Nelder-Mead",
                     options=dict(xatol=0.01, fatol=1e-4, maxiter=3000, initial_simplex=simplex))
        if best is None or r.fun < best.fun:
            best = r
    return T_of(best.x), best.x, best.fun


def footprint_target(img, thr=18.0):
    """+1 on non-substrate (flake) pixels, -1 on substrate; substrate = median Lab colour."""
    lab = cv2.cvtColor(cv2.GaussianBlur(img, (0, 0), 3.0), cv2.COLOR_BGR2LAB).astype(np.float32)
    sub = np.median(lab.reshape(-1, 3), axis=0)
    d = np.linalg.norm(lab - sub, axis=2)
    m = (d > thr).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    return m


def sweep_area(target, plan_masks, rots, scale, ds=4):
    """Global similarity (blueprint px -> full px) maximising (inside - outside) of the planned
    footprint on the target flake mask. plan_masks: list of (mask in image px, M image->blueprint)."""
    corners = []
    for m, M in plan_masks:
        x, y, w, h = cv2.boundingRect(m)
        corners.append(apply(M, np.array([[x, y], [x + w, y], [x, y + h], [x + w, y + h]], float)))
    pts = np.vstack(corners)
    lo = pts.min(0); hi = pts.max(0)
    W, H = int((hi[0] - lo[0]) / ds) + 1, int((hi[1] - lo[1]) / ds) + 1
    canvas = np.zeros((H, W), np.uint8)
    for m, M in plan_masks:
        A = np.vstack([np.asarray(M), [0, 0, 1]])
        S = np.array([[1 / ds, 0, -lo[0] / ds], [0, 1 / ds, -lo[1] / ds], [0, 0, 1]])
        canvas = np.maximum(canvas, cv2.warpAffine(m, (S @ A)[:2], (W, H), flags=cv2.INTER_NEAREST))
    tmap = target.astype(np.float32) if target.dtype != np.uint8 else target.astype(np.float32) / 255.0 * 2 - 1
    tgt = cv2.resize(tmap, None, fx=1 / ds, fy=1 / ds, interpolation=cv2.INTER_AREA)
    cy, cx = H / 2, W / 2
    diag = int(math.hypot(W, H)) + 2
    best = None
    for r in rots:
        R = cv2.getRotationMatrix2D((cx, cy), -r, scale)       # cv2 angle is CCW-positive on screen
        R[:, 2] += [diag / 2 - cx, diag / 2 - cy]
        tpl = (cv2.warpAffine(canvas, R, (diag, diag), flags=cv2.INTER_NEAREST) > 0).astype(np.float32)
        if tpl.sum() == 0 or diag >= min(tgt.shape):
            continue
        res = cv2.matchTemplate(tgt, tpl, cv2.TM_CCORR) / tpl.sum()
        _, mv, _, ml = cv2.minMaxLoc(res)
        if best is None or mv > best[0]:
            best = (mv, r, ml, R)
    mv, r, ml, R = best
    # blueprint px -> canvas(ds) -> rotated tpl -> target(ds) -> full px
    S = np.array([[1 / ds, 0, -lo[0] / ds], [0, 1 / ds, -lo[1] / ds], [0, 0, 1]])
    R3 = np.vstack([R, [0, 0, 1]])
    Tsh = np.array([[1, 0, ml[0]], [0, 1, ml[1]], [0, 0, 1.0]])
    Up = np.array([[ds, 0, 0], [0, ds, 0], [0, 0, 1.0]])
    return (Up @ Tsh @ R3 @ S)[:2], r, mv


def largest(mask):
    n, lab, st, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8))
    return np.where(lab == 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA])), 255, 0).astype(np.uint8) if n > 1 else mask


def tri_target(required, allowed=None):
    """+1 on required pixels, 0 on allowed-but-not-required (unknown), -1 elsewhere."""
    t = np.where(required > 0, 1.0, -1.0).astype(np.float32)
    if allowed is not None:
        t[(allowed > 0) & (required == 0)] = 0.0
    return t


def refine_area(target, mask, T0, max_rot=4.0, max_shift_px=80, ds=2, allowed=None):
    """Refine a similarity (image px -> full px) by maximising IoU(warped mask, target) near T0.
    Pixels in `allowed` but not in `target` are neutral (neither hit nor false positive)."""
    H, W = target.shape
    tg = cv2.resize(target, (W // ds, H // ds), interpolation=cv2.INTER_NEAREST) > 0
    al = (cv2.resize(allowed, (W // ds, H // ds), interpolation=cv2.INTER_NEAREST) > 0) & ~tg if allowed is not None else None
    S = np.array([[1 / ds, 0, 0], [0, 1 / ds, 0], [0, 0, 1.0]])
    c = apply(T0, np.argwhere(mask > 0)[:, ::-1].mean(0)[None])[0]

    def T_of(x):
        return compose(similarity(x[0], 1.0, x[1], x[2], *c), T0)

    def f(x):
        if abs(x[0]) > max_rot or math.hypot(x[1], x[2]) > max_shift_px:
            return 1.0 + abs(x[0]) / 100 + math.hypot(x[1], x[2]) / 1e4
        w = cv2.warpAffine(mask, (S @ np.vstack([T_of(x), [0, 0, 1]]))[:2], (W // ds, H // ds), flags=cv2.INTER_NEAREST) > 0
        if al is not None:
            w = w & ~al
        return 1.0 - (w & tg).sum() / max((w | tg).sum(), 1)

    best = None
    for st in ([0, 0, 0], [2, 0, 0], [-2, 0, 0]):
        st = np.array(st, float)
        simplex = np.vstack([st, st + [1.0, 0, 0], st + [0, 20, 0], st + [0, 0, 20]])
        r = minimize(f, st, method="Nelder-Mead", options=dict(xatol=0.02, fatol=1e-5, maxiter=2000, initial_simplex=simplex))
        if best is None or r.fun < best.fun:
            best = r
    return T_of(best.x), 1.0 - best.fun


def foreground(img, mode, thr=25.0, min_um2=100.0, ps=0.0617):
    """Bright/dark foreground (vs the median background) of an intermediate image, components >= min_um2."""
    g = cv2.GaussianBlur(img.astype(np.float32).mean(2), (0, 0), 3)
    d = (g - np.median(g)) if mode == "bright" else (np.median(g) - g)
    m = ((d > thr) * 255).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    keep = [k for k in range(1, n) if st[k, cv2.CC_STAT_AREA] * ps * ps >= min_um2]
    return np.where(np.isin(lab, keep), 255, 0).astype(np.uint8)


def segment(img, mode):
    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (0, 0), 2)
    bg = np.median(g)
    d = (bg - g) if mode == "dark" else (g - bg)
    d = np.clip(d, 0, 255).astype(np.uint8)
    _, m = cv2.threshold(d, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    if n < 2:
        raise SystemExit("segmentation found nothing")
    k = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    out = np.where(lab == k, 255, 0).astype(np.uint8)
    cs, _ = cv2.findContours(out, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(out, cs, -1, 255, -1)
    return out


def piece_contours(w, ps, min_px=200, eps=2.0):
    out = []
    for c in cv2.findContours(w, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0]:
        if cv2.contourArea(c) < min_px:
            continue
        c = cv2.approxPolyDP(c, eps, True)
        pts = c.reshape(-1, 2).tolist()
        out.append((c, dict(contour_px=pts, contour_um=[[round(x * ps, 3), round(y * ps, 3)] for x, y in pts],
                            area_um2=round(cv2.contourArea(c) * ps * ps, 3), num_points=len(pts))))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stack", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--outline", action="append", default=[],
                    help="role=mask.png: live outline already in full-stack px (e.g. segmented in an in-process photo and mapped)")
    ap.add_argument("--area-target", action="append", default=[],
                    help="role=required.png[:allowed.png]: fit the role's flake mask to a live full-stack region; "
                         "pixels in allowed but not required are neutral")
    ap.add_argument("--edge-fit", action="append", default=[],
                    help="role=dark|bright: fit the role's mask (segmented from its own image if the stack has none) "
                         "to full-stack edges near the placed layers")
    ap.add_argument("--follow", action="append", default=["graphene=top_hBN"],
                    help="role=leader: invisible role placed from the blueprint relative to the placed leader")
    ap.add_argument("--clip", action="append", default=["graphene=top_hBN"],
                    help="role=container: clip the placed role to the placed container")
    ap.add_argument("--check", action="append", default=[], help="role=mask.png: report coverage of a full-stack mask")
    ap.add_argument("--search-margin-um", type=float, default=15.0)
    ap.add_argument("--tau", type=float, default=25.0)
    a = ap.parse_args()

    S = load_stack(a.stack)
    D = S["_dir"]
    rel = lambda p: p if os.path.isabs(p) else os.path.join(D, p)
    os.makedirs(os.path.join(a.out, "masks"), exist_ok=True)
    fs = cv2.imread(rel(S["full_stack"]["raw"]))
    Hf, Wf = fs.shape[:2]
    ps = S["imaging"].get("um_per_px", 0.0617)
    dt, edges = edge_dist(fs, a.tau)
    kv = lambda lst: dict(x.split("=", 1) for x in lst)
    outl, area_t, edge_t, follow, clip = kv(a.outline), kv(a.area_target), kv(a.edge_fit), kv(a.follow), kv(a.clip)

    pieces = []
    for L in S["layers"]:
        for pc in L["pieces"]:
            m = cv2.imread(rel(pc["mask"]), 0) if pc.get("mask") else None
            pieces.append(dict(role=L["role"], id=pc["id"], image=L["image"], mask=m, twist=pc.get("twist_deg"),
                               M=np.array(pc["pose"]["M"]) if pc.get("pose") else None))
    roles = list(dict.fromkeys(p["role"] for p in pieces))
    finals, warped, report = {}, {}, dict(pieces={}, evidence={})
    I = np.array([[1.0, 0, 0], [0, 1.0, 0]])

    def carry(role, lead, T_lead):
        """Same-role pieces keep their blueprint pose relative to the fitted lead piece."""
        for q in pieces:
            if q["role"] != role:
                continue
            if q is lead or q["M"] is None or lead["M"] is None:
                finals[q["id"]] = T_lead
            else:
                finals[q["id"]] = compose(T_lead, (np.linalg.inv(np.vstack([lead["M"], [0, 0, 1]])) @ np.vstack([q["M"], [0, 0, 1]]))[:2])

    # 1) live outlines
    for role, mp in outl.items():
        mine = [p for p in pieces if p["role"] == role]
        if len(mine) != 1:
            sys.exit("--outline needs a single-piece role (%s has %d)" % (role, len(mine)))
        m = cv2.imread(rel(mp), 0)
        warped[mine[0]["id"]] = np.where(m > 0, 255, 0).astype(np.uint8)
        report["evidence"][role] = dict(method="live outline", source=mp)

    # 2) live area fits
    for role, spec in area_t.items():
        req_p, _, allow_p = spec.partition(":")
        req = largest(cv2.imread(rel(req_p), 0))
        allow = cv2.imread(rel(allow_p), 0) if allow_p else None
        mine = [p for p in pieces if p["role"] == role and p["mask"] is not None]
        lead = max(mine, key=lambda p: int((p["mask"] > 0).sum()))
        lm = largest(lead["mask"])
        T0, r0, sc = sweep_area(tri_target(req, allow), [(lm, I)], np.arange(0, 360, 1.0), 1.0)
        T, iou = refine_area(req, lm, T0, allowed=allow)
        carry(role, lead, T)
        report["evidence"][role] = dict(method="live area fit", required=req_p, allowed=allow_p or None,
                                        iou=round(float(iou), 3), rot_deg=round(math.degrees(math.atan2(T[1, 0], T[0, 0])) % 360, 2))

    def placed_region():
        ms = [warped[k] for k in warped] + [cv2.warpAffine(p["mask"], finals[p["id"]], (Wf, Hf), flags=cv2.INTER_NEAREST)
                                           for p in pieces if p["id"] in finals and p["mask"] is not None]
        ys, xs = np.nonzero(np.max(ms, axis=0))
        m = a.search_margin_um / ps
        return (xs.min() - m, ys.min() - m, xs.max() + m, ys.max() + m)

    # 3) live edge fits (e.g. a graphite needle)
    for role, mode in edge_t.items():
        mine = [p for p in pieces if p["role"] == role]
        lead = mine[0]
        if lead["mask"] is None:
            lead["mask"] = segment(cv2.imread(rel(lead["image"])), mode)
            cv2.imwrite(os.path.join(a.out, "masks", lead["id"] + "_source.png"), lead["mask"])
        pts = outline_pts(lead["mask"])
        T0, r0, sc = sweep(dt, pts, np.arange(0, 360, 1.0), 1.0, region=placed_region())
        T, _, c1 = refine(dt, pts, T0, 3.0, 40)
        carry(role, lead, T)
        report["evidence"][role] = dict(method="live edge fit", segmented_from=lead["image"] if lead["M"] is None else "stack mask",
                                        mean_edge_distance_px=round(c1, 2), rot_deg=round(math.degrees(math.atan2(T[1, 0], T[0, 0])) % 360, 2))

    # 4) invisible roles: blueprint pose relative to the placed leader
    for role, leader in follow.items():
        if role not in roles:
            continue
        ld = next((p for p in pieces if p["role"] == leader and p["id"] in finals and p["M"] is not None), None)
        if ld is None:
            sys.exit("%s follows %s, but %s was not placed by a fit with a blueprint pose" % (role, leader, leader))
        F = np.vstack([finals[ld["id"]], [0, 0, 1]]) @ np.linalg.inv(np.vstack([ld["M"], [0, 0, 1]]))  # blueprint -> full
        for p in pieces:
            if p["role"] == role:
                if p["M"] is None:
                    sys.exit("%s has no blueprint pose" % p["id"])
                finals[p["id"]] = (F @ np.vstack([p["M"], [0, 0, 1]]))[:2]
        report["evidence"][role] = dict(method="blueprint relative to %s" % leader, blueprint="%s slide %s" % (S["blueprint"]["source"], S["blueprint"]["slide"]))

    missing = [r for r in roles if r not in report["evidence"]]
    if missing:
        sys.exit("no evidence for %s: give --outline / --area-target / --edge-fit / --follow" % ", ".join(missing))

    for p in pieces:
        if p["id"] not in warped:
            warped[p["id"]] = cv2.warpAffine(p["mask"], finals[p["id"]], (Wf, Hf), flags=cv2.INTER_NEAREST)
    for p in pieces:
        cont = clip.get(p["role"])
        if cont:
            cm = np.max([warped[q["id"]] for q in pieces if q["role"] == cont], axis=0)
            before = int((warped[p["id"]] > 0).sum())
            warped[p["id"]] = cv2.bitwise_and(warped[p["id"]], cm)
            report["pieces"].setdefault(p["id"], {}).update(clipped_to=cont, clipped_away_um2=round((before - int((warped[p["id"]] > 0).sum())) * ps * ps, 1))
    for chk in a.check:
        role, mp = chk.split("=", 1)
        cm = cv2.imread(rel(mp), 0) > 0
        rm = np.max([warped[p["id"]] for p in pieces if p["role"] == role], axis=0) > 0
        report.setdefault("checks", {})["%s covers %s" % (role, os.path.basename(mp))] = round(float((cm & rm).sum() / max(cm.sum(), 1)), 3)

    # ---- outputs: per-piece layers (datatype k) for multi-piece roles, union per role (datatype 0)
    overlay = fs.copy()
    materials, layer_map, gid, union = {}, {}, 0, {}
    for p in pieces:
        w = warped[p["id"]]
        cv2.imwrite(os.path.join(a.out, "masks", p["id"] + "_full.png"), w)
        union[p["role"]] = np.maximum(union.get(p["role"], 0), w).astype(np.uint8)
        info = dict(area_um2=round(float((w > 0).sum()) * ps * ps, 1))
        if p["id"] in finals:
            T = finals[p["id"]]
            info.update(M_image_to_full=[[round(v, 6) for v in row] for row in T.tolist()],
                        rot_deg=round(math.degrees(math.atan2(T[1, 0], T[0, 0])) % 360, 3))
        report["pieces"].setdefault(p["id"], {}).update(info)
        if sum(1 for q in pieces if q["role"] == p["role"]) > 1:
            k = int(p["id"].rsplit("_", 1)[1])
            layer_map[p["id"]] = "%d/%d" % (LAYER_NUM[p["role"]], k)
            materials[p["id"]] = []
            for c, e in piece_contours(w, ps):
                gid += 1
                materials[p["id"]].append(dict(id=gid, twist_deg=p["twist"], **e))
                cv2.polylines(overlay, [c], True, (0, 0, 160), 1)
    for role, w in union.items():
        layer_map[role] = "%d/0" % LAYER_NUM[role]
        materials[role] = []
        for c, e in piece_contours(w, ps):
            gid += 1
            materials[role].append(dict(id=gid, **e))
            cv2.polylines(overlay, [c], True, COLORS.get(role, (255, 255, 255)), 3)
    multi = [r for r in roles if sum(1 for q in pieces if q["role"] == r) > 1]
    for r in multi:
        allp = np.min([warped[p["id"]] for p in pieces if p["role"] == r], axis=0)
        cv2.imwrite(os.path.join(a.out, "masks", "%s_all_pieces.png" % r), allp)
        report["%s_all_pieces_overlap_um2" % r] = round(float((allp > 0).sum()) * ps * ps, 1)
    order = []
    for r in roles:
        order += [r] + [p["id"] for p in pieces if p["role"] == r and p["id"] in materials and p["id"] != r]
    order = [k for k in order if k in materials]
    traces = dict(image=rel(S["full_stack"]["raw"]), pixel_size_um=ps, image_size_px=[Wf, Hf],
                  image_size_um=[round(Wf * ps, 3), round(Hf * ps, 3)], stack=order, layer_map=layer_map,
                  materials={k: materials[k] for k in order}, evidence=report["evidence"],
                  source="place_stack.py from %s" % os.path.basename(a.stack))
    json.dump(traces, open(os.path.join(a.out, "traces.json"), "w"), indent=1)
    json.dump(report, open(os.path.join(a.out, "placement.json"), "w"), indent=1)
    for i, role in enumerate(r for r in LAYER_NUM if r in union):
        cv2.putText(overlay, "%s: %s" % (role, report["evidence"][role]["method"]), (30, 60 + 45 * i), 0, 1.2, COLORS[role], 3)
    cv2.imwrite(os.path.join(a.out, "overlay.png"), overlay)
    print(json.dumps({k: v for k, v in report.items() if k != "pieces"}, indent=1, default=float))


if __name__ == "__main__":
    main()
