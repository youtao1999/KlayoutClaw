"""tg_lib.parse / record: per-script defaults from params.json args, command line wins, run record."""
import argparse
import json
import os
import sys

import pytest

pytest.importorskip("klayout.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "nanodevice_topgate", "scripts"))
import tg_lib  # noqa: E402


def parser():
    ap = argparse.ArgumentParser()
    for k in ("--flakes", "--params", "--writes"):
        ap.add_argument(k, required=True)
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--gap", type=float, default=1.0)
    return ap


@pytest.fixture
def params(tmp_path, monkeypatch):
    monkeypatch.delenv(tg_lib.NO_RECORD, raising=False)
    p = tmp_path / "params.json"
    p.write_text(json.dumps({"layers": {}, "args": {"topgate/place": {"n": 6, "gap": 0.75, "_note": "x"}}}))
    return p


def run(monkeypatch, params, *extra, step="topgate/place", check=False):
    monkeypatch.setattr(sys, "argv", ["x", "--flakes", "f", "--params", str(params), "--writes", "w", *extra])
    return tg_lib.parse(parser(), step, check=check)


def test_params_supply_required_and_defaults(monkeypatch, params):
    a = run(monkeypatch, params)
    assert (a.n, a.gap) == (6, 0.75)
    rec = json.loads((params.parent / "record.json").read_text())
    assert rec["topgate/place"]["args"] == {"n": 6, "gap": 0.75}


def test_command_line_wins(monkeypatch, params):
    assert run(monkeypatch, params, "--n", "3").n == 3


def test_unknown_key_stops_a_writer_but_not_a_check(monkeypatch, params):
    params.write_text(json.dumps({"args": {"topgate/place": {"n": 2, "typo": 1}}}))
    with pytest.raises(SystemExit):
        run(monkeypatch, params)
    assert run(monkeypatch, params, check=True).n == 2
    assert not (params.parent / "record.json").exists()      # checks record nothing


def test_no_record_env(monkeypatch, params):
    monkeypatch.setenv(tg_lib.NO_RECORD, "1")
    run(monkeypatch, params)
    assert not (params.parent / "record.json").exists()
