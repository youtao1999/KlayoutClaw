"""Step R1 without the KLayout GUI: run tools/route_worker.py on a GDS file (same engine and
config keys as the MCP auto_route tool) and write the routes into a copy of the GDS.

Uses the params `routing` block: pin_layer_a / pin_layer_b / output_layer / obstacle_layers /
two_level / inner_margin / inner_width / outer_width / path_width / patch_size /
pin_safe_distance_a / pin_safe_distance_b / path_safe_distance / obs_safe_distance /
map_resolution / timeout.

Usage: python route_offline.py --in device.gds --params params.json --out routed.gds
(run with the instrMCPdev python: needs numpy, scikit-image, klayout)
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

import klayout.db as db

HERE = os.path.dirname(os.path.abspath(__file__))
WORKER = os.path.normpath(os.path.join(HERE, "..", "..", "..", "tools", "route_worker.py"))

ap = argparse.ArgumentParser()
ap.add_argument("--in", dest="inp", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()

R = json.load(open(a.params))["routing"]
ly = db.Layout()
ly.read(a.inp)
top = ly.top_cells()[0]

tmp = tempfile.mkdtemp(prefix="route_offline_")
cfg = {
    "gds_path": os.path.abspath(a.inp), "output_path": os.path.join(tmp, "out.json"),
    "cell_name": top.name, "dbu": ly.dbu,
    "pin_layer_a": R["pin_layer_a"], "pin_layer_b": R["pin_layer_b"],
    "obstacle_layers": R.get("obstacle_layers", []), "output_layer": R["output_layer"],
    "path_width_um": R.get("path_width", 4.0),
    "obs_safe_distance_um": R.get("obs_safe_distance", 5.0),
    "path_safe_distance_um": R.get("path_safe_distance", 5.0),
    "map_resolution_um": R.get("map_resolution", 2.0),
    "obs_hardness": R.get("obs_hardness", 20.0),
    "pin_safe_distance_a_um": R.get("pin_safe_distance_a", 5.0),
    "pin_safe_distance_b_um": R.get("pin_safe_distance_b", 5.0),
    "path_hardness": R.get("path_hardness", 10.0), "sort_pairs": R.get("sort_pairs", True),
    "obs_damping_step": R.get("obs_damping_step", 4), "dry_run": False,
    "auto_map_resolution": R.get("auto_map_resolution", False),
    "rescue_unrouted_nets": R.get("rescue_unrouted_nets", True), "two_level": R.get("two_level", "auto"),
}
for k in ("inner_width", "outer_width", "patch_size", "inner_margin", "per_pair_obstacle_layers", "pin_pairs_override"):
    if k in R:
        cfg[k] = R[k]
cfg_path = os.path.join(tmp, "config.json")
json.dump(cfg, open(cfg_path, "w"))

proc = subprocess.run([sys.executable, WORKER, cfg_path], capture_output=True, text=True, timeout=R.get("timeout", 600))
if not os.path.isfile(cfg["output_path"]):
    sys.exit("route_worker produced no output (exit %d):\n%s" % (proc.returncode, proc.stderr[-2000:]))
res = json.load(open(cfg["output_path"]))
if res.get("status") == "error":
    sys.exit("routing failed: %s" % "; ".join(res.get("errors", ["unknown"])))

l, d = (int(v) for v in R["output_layer"].split("/"))
li = ly.layer(l, d)
w_def = int(round(cfg["path_width_um"] / ly.dbu))
n_paths = 0
for p in res.get("paths", []):
    pts = p.get("points_dbu", [])
    if len(pts) < 2:
        continue
    w = int(round(float(p["width_um"]) / ly.dbu)) if p.get("width_um") is not None else w_def
    top.shapes(li).insert(db.Path([db.Point(int(round(x)), int(round(y))) for x, y in pts], w))
    n_paths += 1
for q in res.get("patches", []) or []:
    hs = int(round(q["size_dbu"])) // 2
    x, y = int(round(q["x_dbu"])), int(round(q["y_dbu"]))
    top.shapes(li).insert(db.Box(x - hs, y - hs, x + hs, y + hs))
ly.write(a.out)

n_nets = res.get("n_nets", min(res.get("total_pins_a", 0), res.get("total_pins_b", 0)))
summary = dict(status=res.get("status"), routed_pairs=res.get("routed_pairs", n_paths), n_nets=n_nets,
               paths=n_paths, patches=len(res.get("patches", []) or []), errors=res.get("errors", []),
               rescued_nets=res.get("rescued_nets", 0), out=a.out)
print(json.dumps(summary, indent=1))
sys.exit(0 if summary["routed_pairs"] == n_nets and not summary["errors"] else 2)
