"""nanodevice_prepare fit: an asymmetric flake drawn into a synthetic photo at a known rotation is found
over all rotations, and the 180 deg alternative is reported as worse."""
import os
import sys

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
pytest.importorskip("klayout.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "nanodevice_prepare", "scripts"))
from prep_lib import edge_dist, fit  # noqa: E402

FLAKE = np.array([[0, 0], [420, 0], [470, 90], [300, 260], [60, 200]], float)   # px, no symmetry


def test_fit_finds_rotation_and_reports_alternative():
    H, W = 900, 1200
    src = np.zeros((H, W), np.uint8)
    cv2.fillPoly(src, [np.round(FLAKE + [100, 100]).astype(np.int32)], 255)
    rot = 147.0
    M = cv2.getRotationMatrix2D((600, 450), -rot, 1.0)        # cv2 angle is counter-clockwise on screen
    M[:, 2] += [-150, 80]
    photo = np.full((H, W, 3), (200, 120, 190), np.uint8)
    photo[cv2.warpAffine(src, M, (W, H), flags=cv2.INTER_NEAREST) > 0] = (230, 200, 90)
    best, alt = fit(edge_dist(photo, 25.0)[0], src, (0, 0, W, H))
    assert abs(((best["rot_deg"] - rot) + 180) % 360 - 180) < 1.0
    assert best["cost_px"] < 1.5
    assert alt is not None and alt["cost_px"] > 2 * best["cost_px"]
