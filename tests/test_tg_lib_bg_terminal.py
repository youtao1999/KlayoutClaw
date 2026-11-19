"""tg_lib.bg_terminal: exposed bottom graphite by default; with back_gate.edge_contact also the bottom
graphite under the bottom hBN, away from the top gate."""
import os
import sys

import pytest

db = pytest.importorskip("klayout.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "nanodevice_topgate", "scripts"))
from tg_lib import bg_terminal, write_layer  # noqa: E402

LAYERS = {"graphite": [13, 0], "bottom_hbn": [12, 0], "top_hbn": [10, 0], "top_graphite": [14, 0],
          "graphene_pieces": [[11, 1], [11, 2]]}


def box(x1, y1, x2, y2):
    return db.Region(db.Box(x1 * 1000, y1 * 1000, x2 * 1000, y2 * 1000))   # um -> dbu 0.001


@pytest.fixture
def device(tmp_path):
    flakes, writes = str(tmp_path / "prepared.gds"), str(tmp_path / "writes.gds")
    for spec, r in [("13/0", box(-1, -20, 1, 20)),            # bottom graphite strip
                    ("12/0", box(-10, -5, 10, 15)),           # bottom hBN over its middle
                    ("10/0", box(-10, -4, 10, 14)),           # top hBN
                    ("14/0", box(-10, -30, 10, 30)),          # top graphite over all of it: no bare BG
                    ("11/1", box(-8, 0, 8, 10)), ("11/2", box(-8, 1, 8, 11))]:
        write_layer(flakes, spec, r, 0.001)
    write_layer(writes, "5/0", box(-0.5, 0, 0.5, 10), 0.001)  # channel
    return flakes, writes


def test_default_is_exposed_bottom_graphite_only(device):
    flakes, writes = device
    assert bg_terminal(flakes, {"layers": LAYERS}, writes).is_empty()


def test_edge_contact_adds_bottom_graphite_under_bottom_hbn(device):
    flakes, writes = device
    x = bg_terminal(flakes, {"layers": LAYERS, "back_gate": {"edge_contact": True, "gap": 0.5}}, writes)
    expect = box(-1, -5, 1, 15) - box(-0.5, 0, 0.5, 10).sized(500)
    assert (x ^ expect).is_empty()

