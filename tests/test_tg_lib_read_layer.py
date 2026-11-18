"""tg_lib.read_layer must return the shapes written by write_layer, including a lone
axis-aligned box (the channel 5/0 of a stack at rotation 0)."""
import gc
import os
import sys

import pytest

db = pytest.importorskip("klayout.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "nanodevice_topgate", "scripts"))
from tg_lib import read_layer, write_layer  # noqa: E402


@pytest.mark.parametrize("shape", [
    db.Box(97100, 194000, 102900, 208000),                                   # axis-aligned box
    db.Polygon([db.Point(0, 0), db.Point(5000, 600), db.Point(4400, 9000), db.Point(-600, 8400)]),
])
def test_written_layer_reads_back(tmp_path, shape):
    path = str(tmp_path / "writes.gds")
    write_layer(path, "5/0", db.Region(shape), 0.001)
    r, dbu = read_layer(path, "5/0")
    gc.collect()                                     # the Layout read inside read_layer is gone
    assert dbu == pytest.approx(0.001)
    assert r.count() == 1
    assert r.area() == db.Region(shape).area()
