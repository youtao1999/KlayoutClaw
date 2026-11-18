"""Shared helpers for the top-gated Hall bar recipe (standalone klayout.db, no GUI).

All geometry scripts in this folder read/write GDS files so they can be re-run and
diffed; KLayout (MCP) is only needed for flake commit, auto_route and screenshots.
"""
import json
import math

import klayout.db as db


def load_params(path):
    with open(path) as f:
        return json.load(f)


class Design:
    """Wraps a Layout + top cell with the recipe's layer map and local strip frame."""

    def __init__(self, gds_path, params):
        self.p = params
        self.ly = db.Layout()
        self.ly.read(gds_path)
        tops = self.ly.top_cells()
        assert len(tops) == 1, "expected exactly one top cell, got %d" % len(tops)
        self.top = tops[0]
        self.dbu = self.ly.dbu
        self.T, self.frame = strip_frame(self.R("graphite"), self.dbu, params["gate_end"])
        self.Ti = self.T.inverted()

    # ---- layers
    def li(self, key):
        l, d = self.p["layers"][key]
        return self.ly.layer(l, d)

    def R(self, key):
        return db.Region(self.top.begin_shapes_rec(self.li(key))).merged()

    def Rl(self, l, d=0):
        return db.Region(self.top.begin_shapes_rec(self.ly.layer(l, d))).merged()

    def put(self, key, region):
        s = self.top.shapes(self.li(key))
        s.clear()
        s.insert(region)

    def clear(self, key):
        self.top.shapes(self.li(key)).clear()

    def markers(self):
        r = db.Region()
        for l, d in self.p["layers"]["markers"]:
            r += self.Rl(l, d)
        return r.merged()

    # ---- geometry in the local frame
    def um(self, x):
        return int(round(x / self.dbu))

    def box(self, x1, y1, x2, y2):
        """Local-frame box -> Region in layout dbu."""
        return db.Region((self.T * db.DPolygon(db.DBox(x1, y1, x2, y2))).to_itype(self.dbu))

    def path(self, pts, width):
        dp = db.DPath([db.DPoint(x, y) for x, y in pts], width)
        return db.Region((self.T * dp).to_itype(self.dbu).polygon())

    def to_local(self, x_um, y_um):
        q = self.Ti * db.DPoint(x_um, y_um)
        return q.x, q.y

    def local_bbox(self, poly):
        pts = [self.Ti * db.DPoint(q.x * self.dbu, q.y * self.dbu) for q in poly.each_point_hull()]
        return [min(q.x for q in pts), min(q.y for q in pts), max(q.x for q in pts), max(q.y for q in pts)]

    def graphite_edge(self, y, side):
        """x' of the graphite edge on the given side at local y'."""
        line = self.box(-40, y - 0.01, 40, y + 0.01) & self.R("graphite")
        assert not line.is_empty(), "graphite strip absent at y'=%.2f" % y
        b = line.bbox()
        xs = [self.to_local(b.left * self.dbu, b.bottom * self.dbu)[0], self.to_local(b.right * self.dbu, b.top * self.dbu)[0]]
        return min(xs) if side == "L" else max(xs)

    def write(self, path):
        self.ly.write(path)


def strip_frame(graphite, dbu, gate_end):
    """Local frame from the graphite strip: origin = hull-point mean, +y' along the major
    axis pointing towards gate_end ('north'|'south'|'east'|'west' in GDS terms)."""
    pts = [(q.x * dbu, q.y * dbu) for poly in graphite.each() for q in poly.each_point_hull()]
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts) / n
    syy = sum((p[1] - my) ** 2 for p in pts) / n
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts) / n
    ang = 0.5 * math.atan2(2 * sxy, sxx - syy)
    ax, ay = math.cos(ang), math.sin(ang)
    want = {"north": (0, 1), "south": (0, -1), "east": (1, 0), "west": (-1, 0)}[gate_end]
    if ax * want[0] + ay * want[1] < 0:
        ax, ay = -ax, -ay
    rot = math.degrees(math.atan2(ay, ax)) - 90.0
    T = db.DCplxTrans(1.0, rot, False, db.DVector(mx, my))
    return T, {"center_um": [round(mx, 3), round(my, 3)], "rot_deg": round(rot, 4)}


def min_gap(a, b, dbu, steps=(0.1, 0.2, 0.3, 0.4, 0.5, 0.55, 0.6, 0.7, 0.8, 1.0, 1.5, 2.0)):
    """Smallest step s at which a and b (each grown by s/2) touch; None if > max step."""
    for s in steps:
        h = int(round(s / 2 / dbu))
        if not (a.sized(h) & b.sized(h)).is_empty():
            return s
    return None


def convex_hull(region):
    pts = sorted(set((q.x, q.y) for p in region.each() for q in p.each_point_hull()))

    def cr(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lo, up = [], []
    for q in pts:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], q) <= 0:
            lo.pop()
        lo.append(q)
    for q in reversed(pts):
        while len(up) >= 2 and cr(up[-2], up[-1], q) <= 0:
            up.pop()
        up.append(q)
    return db.Region(db.Polygon([db.Point(x, y) for x, y in lo[:-1] + up[:-1]]))
