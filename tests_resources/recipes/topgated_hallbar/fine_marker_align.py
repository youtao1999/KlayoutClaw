"""Step P3: register the full-stack image to a template's FINE marker field (e.g. L19 1-4 um
squares on a 50 um pitch) when the template has no L5 marker pairs.

Pattern-matching approach (generalised from an earlier device session):
  1. marker response map = top-hat(R - B) + top-hat(R) (orange/gold markers on SiO2);
  2. initial lattice angle/scale from blob pair vectors (|v| ~ pitch/pixel_size);
  3. hypothesis search: 4 rotations (x2 if --allow-mirror) x every lattice site as anchor,
     scored by the response sampled on the rendered marker squares; Nelder-Mead refinement;
  4. per-site local refinement, weak sites (under flakes) dropped, LSQ similarity fit.
All fine-marker fields of such chips are identical and 180-deg point symmetric, so the FIELD
and the 0/180 choice must come from the user (--field, --rot-hint).

Outputs (in --out): gds_warp.npy (image-um -> GDS-um, 2x3, commit_gds convention),
gds_warp_px.npy (image-px -> GDS-um), gds_alignment_report.json, 03_detections.png

Usage: python fine_marker_align.py --image full_stack_raw.png --template Template.gds --ps 0.06162 \
         --field 2500 2500 --rot-hint 0 --out output/gdsalign
"""
import argparse
import json
import os

import cv2
import gdstk
import numpy as np
from scipy.optimize import minimize

ap = argparse.ArgumentParser()
ap.add_argument("--image", required=True)
ap.add_argument("--template", required=True)
ap.add_argument("--ps", type=float, required=True, help="nominal um/px")
ap.add_argument("--field", type=float, nargs=2, required=True, help="centre of the chosen fine-marker field (um)")
ap.add_argument("--rot-hint", type=float, default=0.0, help="0 or 180: pick the hypothesis nearest this rotation")
ap.add_argument("--layer", type=int, nargs=2, default=[19, 0])
ap.add_argument("--pitch", type=float, default=50.0)
ap.add_argument("--allow-mirror", action="store_true")
ap.add_argument("--out", required=True)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
OUT = a.out.rstrip("/") + "/"

im = cv2.imread(a.image)
H, W = im.shape[:2]
b, g, r = cv2.split(im.astype(np.float32))
k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (61, 61))
R = cv2.GaussianBlur(cv2.morphologyEx(r - b, cv2.MORPH_TOPHAT, k) + cv2.morphologyEx(r, cv2.MORPH_TOPHAT, k), (0, 0), 2.0)
R = np.clip(R - np.median(R), 0, None); R /= np.percentile(R, 99.9)
Rs = cv2.GaussianBlur(R, (0, 0), 4.0)

# ---- template marker squares of the chosen field, grouped into lattice sites
top = gdstk.read_gds(a.template).top_level()[0]
sq = []
for p in top.get_polygons():
    if (p.layer, p.datatype) == tuple(a.layer):
        (x0, y0), (x1, y1) = p.bounding_box(); sq.append(((x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0))
sq = np.array(sq)
fx, fy = a.field
fs = sq[(abs(sq[:, 0] - fx) < 6 * a.pitch) & (abs(sq[:, 1] - fy) < 6 * a.pitch)]
assert len(fs), "no marker squares near --field"
offx = np.median((fs[:, 0] - fx) % a.pitch); offy = np.median((fs[:, 1] - fy) % a.pitch)
site_of = lambda x, o, c: c + o + a.pitch * np.round((x - c - o) / a.pitch)
sites = np.unique(np.c_[site_of(fs[:, 0], offx, fx), site_of(fs[:, 1], offy, fy)], axis=0)

def subpts(squares):
    out = []
    for cx, cy, w, h in squares:
        n = max(2, int(round(w * 2)))
        for u in np.linspace(-w / 2 + w / (2 * n), w / 2 - w / (2 * n), n):
            for v in np.linspace(-h / 2 + h / (2 * n), h / 2 - h / (2 * n), n):
                out.append((cx + u, cy + v))
    return np.array(out)
sub = subpts(fs)

def samp(Rm, pts):
    x = np.clip(pts[:, 0], 0, W - 1.001); y = np.clip(pts[:, 1], 0, H - 1.001)
    x0 = x.astype(int); y0 = y.astype(int); dx = x - x0; dy = y - y0
    return Rm[y0, x0] * (1 - dx) * (1 - dy) + Rm[y0, x0 + 1] * dx * (1 - dy) + Rm[y0 + 1, x0] * (1 - dx) * dy + Rm[y0 + 1, x0 + 1] * dx * dy

def Amat(s, th, mir):                     # GDS um -> image px (y flipped unless mirrored)
    Rm = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    return s * Rm @ (np.eye(2) if mir else np.diag([1, -1]))

def score(prm, mir, Rm=R, pts=sub):
    s, th, tx, ty = prm
    Pp = pts @ Amat(s, th, mir).T + [tx, ty]
    ins = (Pp[:, 0] > 5) & (Pp[:, 0] < W - 6) & (Pp[:, 1] > 5) & (Pp[:, 1] < H - 6)
    return samp(Rm, Pp[ins]).sum() / np.sqrt(ins.sum()) if ins.sum() else 0

# ---- initial lattice from blobs
th_map = cv2.GaussianBlur(cv2.morphologyEx(r - b, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (71, 71))), (0, 0), 1.5)
thr = max(25, np.percentile(th_map, 99.95) * 0.4)
n, lab, st, cen = cv2.connectedComponentsWithStats((th_map > thr).astype(np.uint8))
bl = np.array([(cen[i][0], cen[i][1], st[i][4]) for i in range(1, n) if 20 < st[i][4] < 3000])
assert len(bl) >= 3, "too few marker blobs detected"
L0 = a.pitch / a.ps
angs = []
for i in range(len(bl)):
    for j in range(len(bl)):
        v = bl[j, :2] - bl[i, :2]; d = np.hypot(*v)
        if abs(d - L0) < 0.12 * L0:
            angs.append(np.arctan2(v[1], v[0]) % (np.pi / 2))
assert angs, "no blob pairs at the expected marker pitch - check --ps"
angs = np.array(angs)
th0 = np.angle(np.mean(np.exp(4j * angs))) / 4          # circular mean mod 90 deg
s0 = 1 / a.ps
anchor = bl[np.argmax(bl[:, 2]), :2]

res = []
for mir in ([False, True] if a.allow_mirror else [False]):
    for kk in range(4):
        th = th0 + kk * np.pi / 2
        A = Amat(s0, th, mir)
        for stt in sites:
            t = anchor - A @ stt
            best = (-1, None)
            for dx in range(-40, 41, 8):
                for dy in range(-40, 41, 8):
                    sc = score((s0, th, t[0] + dx, t[1] + dy), mir, Rs)
                    if sc > best[0]:
                        best = (sc, (s0, th, t[0] + dx, t[1] + dy))
            res.append((best[0], mir, kk, tuple(stt), best[1]))
res.sort(key=lambda z: -z[0])
ref = []
for z in res[:8]:
    p0 = np.array(z[4]); mir = z[1]
    o = minimize(lambda p: -score(p, mir, Rs), p0, method="Nelder-Mead",
                 options=dict(xatol=1e-4, fatol=1e-5, maxiter=3000, initial_simplex=[p0, p0 + [0.2, 0, 0, 0], p0 + [0, 0.005, 0, 0], p0 + [0, 0, 10, 0], p0 + [0, 0, 0, 10]]))
    o2 = minimize(lambda p: -score(p, mir, R), o.x, method="Nelder-Mead",
                  options=dict(xatol=1e-5, fatol=1e-6, maxiter=3000, initial_simplex=[o.x, o.x + [0.05, 0, 0, 0], o.x + [0, 0.001, 0, 0], o.x + [0, 0, 2, 0], o.x + [0, 0, 0, 2]]))
    ref.append(dict(score=float(-o2.fun), mirror=bool(mir), params=[float(v) for v in o2.x]))
ref.sort(key=lambda z: -z["score"])
angdist = lambda deg: abs(((deg - a.rot_hint) + 180) % 360 - 180)
cands = [z for z in ref if angdist(np.degrees(z["params"][1])) < 45]
assert cands, "no hypothesis near --rot-hint"
h = cands[0]
s, th, tx, ty = h["params"]; M = Amat(s, th, h["mirror"])

# ---- lattice-offset check: score() rewards hypotheses that put more squares in view, so a
# neighbouring site row/column can win. Re-pick the offset by the MEAN marker response on the squares.
def mean_score(t):
    Pp = sub @ M.T + t
    ins = (Pp[:, 0] > 5) & (Pp[:, 0] < W - 6) & (Pp[:, 1] > 5) & (Pp[:, 1] < H - 6)
    return float(samp(R, Pp[ins]).mean()) if ins.sum() > 50 else 0.0
offs = []
for i in range(-2, 3):
    for j in range(-2, 3):
        t = np.array([tx, ty]) - M @ np.array([i * a.pitch, j * a.pitch])
        offs.append((mean_score(t), i, j, t))
offs.sort(key=lambda z: -z[0])
lattice_check = dict(chosen_offset_sites=[offs[0][1], offs[0][2]], mean_response=round(offs[0][0], 4),
                     runner_up=dict(offset_sites=[offs[1][1], offs[1][2]], mean_response=round(offs[1][0], 4)),
                     unshifted=round(next(z[0] for z in offs if z[1] == 0 and z[2] == 0), 4))
tx, ty = offs[0][3]

# ---- per-site refinement + LSQ similarity, iterated: each pass searches around the sites predicted
# by the previous LSQ fit, so a small lattice scale error (pixels add up across the field) is removed
predict = lambda stt: M @ stt + [tx, ty]
for it in range(4):
    per = []
    for stt in sites:
        c = predict(stt)
        if not (60 < c[0] < W - 60 and 60 < c[1] < H - 60):
            continue
        m = (abs(fs[:, 0] - stt[0]) < 12) & (abs(fs[:, 1] - stt[1]) < 12)
        ss = subpts(fs[m])
        shift = c - (M @ stt + [tx, ty])
        best = (-1, 0, 0)
        for dx in np.arange(-15, 15.1, 0.5):
            for dy in np.arange(-15, 15.1, 0.5):
                sc = score((s, th, tx + shift[0] + dx, ty + shift[1] + dy), h["mirror"], R, ss)
                if sc > best[0]:
                    best = (sc, dx, dy)
        per.append(dict(site_gds=stt.tolist(), img_px=(c + [best[1], best[2]]).tolist(), score=float(best[0])))
    scs = np.array([p["score"] for p in per]); good = [p for p in per if p["score"] > 0.35 * np.median(scs)]
    assert len(good) >= 4, "fewer than 4 usable marker sites"
    src = np.array([p["img_px"] for p in good]); dst = np.array([p["site_gds"] for p in good])
    pc = src[:, 0] - 1j * src[:, 1]; gc = dst[:, 0] + 1j * dst[:, 1]       # g = A*conj(p) + B  (image y-down -> GDS y-up)
    (Aa, Bb), *_ = np.linalg.lstsq(np.vstack([pc, np.ones_like(pc)]).T, gc, rcond=None)
    resid = np.abs(Aa * pc + Bb - gc)
    # inverse: pc = (g - B) / A with pc = x - iy
    predict = lambda stt, Aa=Aa, Bb=Bb: (lambda z: np.array([z.real, -z.imag]))((stt[0] + 1j * stt[1] - Bb) / Aa)  # pc = x - iy
    if resid.mean() < 0.05:
        break
ps = abs(Aa)
Mpx = np.array([[Aa.real, Aa.imag, Bb.real], [Aa.imag, -Aa.real, Bb.imag]])
Mum = Mpx.copy(); Mum[:, :2] /= ps
np.save(OUT + "gds_warp.npy", Mum); np.save(OUT + "gds_warp_px.npy", Mpx)
for p in per:
    q = np.array(p["img_px"]); gg = Mpx[:, :2] @ q + Mpx[:, 2]
    p["residual_um"] = float(np.hypot(*(gg - p["site_gds"]))); p["used"] = p in good
rep = dict(status="complete", method="fine_marker_align.py (L%d/%d pattern registration)" % tuple(a.layer),
           pixel_size_nominal_um=a.ps, pixel_size_measured_um=float(ps),
           transform=dict(rotation_deg=float(np.degrees(np.angle(Aa))), reflected=True, translation_um=[float(Bb.real), float(Bb.imag)],
                          note="reflected=True is the ordinary image(y-down)->GDS(y-up) flip"),
           lattice_offset_check=lattice_check,
           quality=dict(inliers=len(good), n_sites_in_fov=len(per), mean_residual_um=float(resid.mean()), max_residual_um=float(resid.max())),
           field=dict(center_um=[fx, fy], rot_hint=a.rot_hint, note="fields are identical and 180-deg symmetric: field + rot-hint are user choices"),
           hypotheses=ref[:4], sites=per)
json.dump(rep, open(OUT + "gds_alignment_report.json", "w"), indent=1)
vis = im.copy()
for p in per:
    c = tuple(int(v) for v in p["img_px"]); cv2.circle(vis, c, 45, (0, 255, 0) if p["used"] else (0, 0, 255), 4)
cv2.imwrite(OUT + "03_detections.png", cv2.resize(vis, None, fx=0.35, fy=0.35))
print(json.dumps(dict(ps_measured=round(float(ps), 5), rotation_deg=round(float(np.degrees(np.angle(Aa))), 3),
                      inliers=len(good), of=len(per), mean_res_um=round(float(resid.mean()), 3), max_res_um=round(float(resid.max()), 3))))
