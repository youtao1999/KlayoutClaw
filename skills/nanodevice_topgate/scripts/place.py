"""Top gate, placement search: choose the free parameters (arm shift, contact size) yourself.

Runs arms.py -> contacts.py -> electrodes.py -> check.py on scratch copies of writes.gds for each
(contact size, arm shift) candidate, then writes the chosen design into writes.gds.

Rule (user, 2026-11-17): take the largest contact size whose longest unbroken run of passing
shifts is at least --min-window wide; use the shift in the middle of that run.
Sizes are tried from --max-size down in --size-step steps, never below electrode width + 0.1
(smaller contacts leave the electrode router no start point). Shifts are scanned on a 0.05 um
grid (a run >= 0.05 wide always holds a grid point), then refined to --shift-step outward from
the two ends of each run of passing grid points.

Usage: python place.py --flakes prepared.gds --params params.json --writes writes.gds
                       --n 3 --width 1 --gap 1 [--contacts 2] [--min-window 0.05]
                       [--max-size 1.0] [--size-step 0.05] [--shift-step 0.01] [--electrode-width 0.5]
Run flakes.py and channel.py first.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

from tg_lib import NO_RECORD, Design, load_params, parse, read_layer, record

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--flakes", required=True)
ap.add_argument("--params", required=True)
ap.add_argument("--writes", required=True)
ap.add_argument("--n", type=int, required=True, help="arms per side")
ap.add_argument("--width", type=float, required=True, help="arm width, um")
ap.add_argument("--gap", type=float, required=True, help="gap between neighbouring arms, um")
ap.add_argument("--contacts", type=int, default=2, help="number of top-gate contacts")
ap.add_argument("--min-window", type=float, default=0.05, help="minimum width of the passing shift run, um")
ap.add_argument("--max-size", type=float, default=1.0)
ap.add_argument("--size-step", type=float, default=0.05)
ap.add_argument("--shift-step", type=float, default=0.01)
ap.add_argument("--electrode-width", type=float, default=0.5)
a = parse(ap, "topgate/place")

ch, _ = read_layer(a.writes, "5/0")
if ch.count() != 1:
    sys.exit("run flakes.py and channel.py first: no single channel on 5/0")
_, cy1, _, cy2 = Design(a.flakes, load_params(a.params)).local_bbox(next(ch.each()))
half = (cy2 - cy1 - (a.n * a.width + (a.n - 1) * a.gap)) / 2      # shift range is +-half
if half < 0:
    sys.exit("the arms do not fit along the channel")


def run(script, writes, *extra):
    cmd = [sys.executable, os.path.join(HERE, script), "--flakes", a.flakes, "--params", a.params,
           "--writes", writes] + [str(x) for x in extra]
    env = dict(os.environ, **({} if writes == a.writes else {NO_RECORD: "1"}))   # trials leave no record
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def design(writes, size, shift):
    """Run the four steps on writes; return None if all checks pass, else the failing step."""
    steps = [("arms.py", "--n", a.n, "--width", a.width, "--gap", a.gap, "--shift", "%.4f" % shift),
             ("contacts.py", "--n", a.contacts, "--size", size),
             ("electrodes.py", "--width", a.electrode_width),
             ("check.py",)]
    for s, *extra in steps:
        r = run(s, writes, *extra)
        if r.returncode:
            return s.split(".")[0]
    return None


tmp = tempfile.mkdtemp(prefix="topgate_place_")
try:
    trial = os.path.join(tmp, "writes.gds")

    def passes(size, shift):
        shutil.copyfile(a.writes, trial)
        return design(trial, size, shift) is None

    q = lambda x: round(x / a.shift_step) * a.shift_step
    choice = None
    table = {}
    size = a.max_size
    while size >= a.electrode_width + 0.1 - 1e-9 and choice is None:
        coarse = {q(-half + k * 0.05) for k in range(int(2 * half / 0.05) + 1)} | {q(-half), q(half)}
        coarse = sorted(s for s in coarse if abs(s) <= half + 1e-9)
        ok = [s for s in coarse if passes(size, s)]
        fine = set()
        groups = []                                     # runs of neighbouring passing grid points
        for s in ok:
            if groups and s - groups[-1][-1] < 0.05 * 1.5:
                groups[-1].append(s)
            else:
                groups.append([s])
        nk = int(round(0.05 / a.shift_step))
        for g in groups:
            # shortcut: fine points between two passing grid points count as passing (a failing pocket
            # < 0.05 um inside a run is missed); refine every fine point if a design ever shows one
            fine.update(q(g[0] + k * a.shift_step) for k in range(int(round((g[-1] - g[0]) / a.shift_step)) + 1))
            for start, sign in ((g[0], -1), (g[-1], 1)):   # refine outward from each end
                for k in range(1, nk):
                    s = q(start + sign * k * a.shift_step)
                    if abs(s) > half + 1e-9 or not passes(size, s):
                        break
                    fine.add(s)
        runs, cur = [], []
        for s in sorted(fine):                          # unbroken runs on the fine grid
            if cur and s - cur[-1] > a.shift_step * 1.5:
                runs.append(cur)
                cur = []
            cur.append(s)
        if cur:
            runs.append(cur)
        best = max(runs, key=lambda r: r[-1] - r[0], default=None)
        width = best[-1] - best[0] if best else -1
        print("size %.3f: passing shifts %s" % (size, ", ".join("%.2f..%.2f" % (r[0], r[-1]) for r in runs) or "none"))
        table["%.3f" % size] = [[r[0], r[-1]] for r in runs]
        if best and width >= a.min_window - 1e-9:
            choice = (size, q((best[0] + best[-1]) / 2), best)
        size = round(size - a.size_step, 6)
    if choice is None:
        sys.exit("no contact size has a passing shift run >= %.3f um" % a.min_window)
    size, shift, best = choice
    print("chosen: contact size %.3f um, arm shift %.3f um (middle of %.2f..%.2f)" % (size, shift, best[0], best[-1]))
    record(a.params, "topgate/place", chosen={"contact_size": size, "arm_shift": shift, "passing_run": [best[0], best[-1]]},
           passing_shifts=table)
    failed = design(a.writes, size, shift)
    r = run("check.py", a.writes)
    print(r.stdout, end="")
    if failed:
        sys.exit("chosen design failed at %s" % failed)
finally:
    shutil.rmtree(tmp)
