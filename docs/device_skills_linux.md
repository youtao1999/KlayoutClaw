# Device-design skills on Linux

How to run the six-piece device skills (`nanodevice_prepare`, `_topgate`, `_contacts`, `_electrodes`,
`_pads`, `_fingers`, `_finalcheck`, and `nanodevice_chain`, which runs them all) on Linux, e.g. in a
Docker container on a lab PC. The SKILL.md files also mention the Mac setup (`instrMCPdev` conda env,
zsh); on Linux none of that applies.

## Python

Plain `python3` (no conda). Packages: `pip install -r requirements.txt` from the KlayoutClaw root plus
the `klayout` pip module (no KLayout app needed for the skills). The skills use klayout.db (and
klayout.lay for the photo overlay), numpy, scipy, opencv (headless is enough), gdstk, shapely.
Tested with klayout 0.30.13, OpenCV 5.0, Python 3.12.

Run the commands in bash as written in each SKILL.md: `$A` splits normally, no `bash -c` wrapper.
Device folders can live anywhere (a mounted data volume is typical); the skills take paths from
`--params` (and the `prepare` paths are relative to the device folder).

```
P=<device>/klayoutclaw/data/params.json
python3 <KlayoutClaw>/skills/nanodevice_chain/scripts/run.py --params $P
```

Unit tests: `python3 -m pytest tests/test_tg_lib_*.py tests/test_prepare_fit.py` (pytest may need a
user install: `pip install --user pytest`, or `--target <dir>` plus `PYTHONPATH` on a system Python
that refuses user installs).

## Reviewing the result

KLayout runs natively on Windows and macOS: open `result.gds`, load `result.lyp` (layer names), then
File > Add Image... > `<photo>.lyimg` (the full-stack photo, placed so its markers sit on the template
markers). `writes.gds` + `writes.lyp` is the EBL file.

## MCP server (optional for these skills)

The skills run offline on GDS files and do not need the KLayout GUI or the MCP server. If the MCP
`auto_route` / `evaluate_design` tools are used, set `PYTHON_PATH=/usr/bin/python3` (they otherwise look
for a conda env); `install.py` copies the plugin and workers to `~/.klayout/pymacros/`, the same path as
on macOS.
