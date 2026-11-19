"""Run the whole six-piece device design from one params.json: nanodevice_prepare -> _topgate -> _contacts
-> _electrodes -> _pads -> _fingers -> _finalcheck (check, export). After each skill the checks of every
earlier skill run again (each must still pass). Stops at the first failing step; --from resumes there.

Usage: python run.py --params <device>/klayoutclaw/data/params.json [--from STEP] [--to STEP] [--list]
Steps are named <skill>/<script>, e.g. prepare/fit, topgate/place, finalcheck/export.
Works in <device>/klayoutclaw: data/prepared.gds (flakes), result.gds (design file), writes.gds (EBL).
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2]
PREPARE = ["prepare/align", "prepare/fit", "prepare/graphene", "prepare/prepared"]
DESIGN = [("topgate", ["flakes", "channel", "place"]), ("contacts", ["checker", "mask", "contacts"]),
          ("electrodes", ["electrodes"]), ("pads", ["pads"]), ("fingers", ["fingers"])]
STEPS = list(PREPARE)
done = []
for skill, scripts in DESIGN:
    STEPS += ["%s/%s" % (skill, s) for s in scripts]
    done.append(skill)
    STEPS += ["%s/check" % k for k in done]          # this skill's check and every earlier one again
STEPS += ["finalcheck/check", "finalcheck/export"]

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--params", required=True)
ap.add_argument("--from", dest="start", help="first step to run")
ap.add_argument("--to", dest="stop", help="last step to run")
ap.add_argument("--list", action="store_true", help="print the steps and exit")
a = ap.parse_args()
if a.list:
    print("\n".join(STEPS))
    sys.exit(0)
params = Path(a.params).resolve()
work = params.parent.parent                          # <device>/klayoutclaw
for s in (a.start, a.stop):
    if s and s not in STEPS:
        sys.exit("unknown step %s (see --list)" % s)
i0 = STEPS.index(a.start) if a.start else 0
i1 = STEPS.index(a.stop) if a.stop else len(STEPS) - 1
for k, step in enumerate(STEPS[i0:i1 + 1], i0):
    skill, script = step.split("/")
    path = SKILLS / ("nanodevice_" + skill) / "scripts" / (script + ".py")
    cmd = [sys.executable, str(path), "--params", str(params)]
    if skill != "prepare":
        cmd += ["--flakes", "data/prepared.gds", "--writes", "result.gds"]
    t = time.time()
    r = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip().splitlines()
    print("%-22s %s  %5.1f s%s" % (step, "ok  " if r.returncode == 0 else "FAIL", time.time() - t,
          ("  " + out[-1][:110]) if out else ""), flush=True)
    if r.returncode:
        print("\n".join(out[-25:]))
        sys.exit("stopped at %s (exit %d); fix it and rerun with --from %s" % (step, r.returncode, step))
print("done: review %s/result.gds with result.lyp and the photo overlay; send writes.gds" % work)
