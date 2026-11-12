"""Exact Euclidean distance helpers for the dual-gated recipe (klayout.db regions -> shapely).

(Region.separation_check reports spurious 0-distance pairs for some polygon pairs, and sizing-based
distances under-estimate diagonal gaps because sized corners reach beyond a true radius.)"""
import klayout.db as db
from shapely.geometry import MultiPolygon, Polygon


def _shp(r):
    polys = []
    for p in r.merged().each():
        hull = [(q.x, q.y) for q in p.each_point_hull()]
        holes = [[(q.x, q.y) for q in p.each_point_hole(i)] for i in range(p.holes())]
        polys.append(Polygon(hull, holes))
    return MultiPolygon(polys)


def dist(a, b, dbu, dmax=10.0):
    """Minimum distance (um) between regions a and b; 0 if they touch/overlap, None if > dmax."""
    if a.is_empty() or b.is_empty():
        return None
    d = _shp(a).distance(_shp(b)) * dbu
    return None if d > dmax else round(d, 3)


def space(r, dbu, dmax=10.0):
    """Minimum spacing (um) between the separate polygons of r; None if > dmax or < 2 polygons."""
    polys = [db.Region(p) for p in r.merged().each()]
    best = None
    for i, x in enumerate(polys):
        for y in polys[i + 1:]:
            d = dist(x, y, dbu, dmax)
            if d is not None and (best is None or d < best):
                best = d
    return best
