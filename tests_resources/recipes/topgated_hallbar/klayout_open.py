"""KLayout-side helper (run INSIDE KLayout through the MCP execute_script tool).

    exec(open('<recipe>/klayout_open.py').read())
    result = open_design('<abs path>.gds', '<abs path>/image_placement.json')   # placement optional

Opens the GDS in a NEW tab (never touches the user's other tabs), adds the warped full-stack
image as background, applies the recipe's layer styles, and returns the new view index.
All later MCP tools (auto_route, screenshot, save_layout) act on the ACTIVE tab - before each of
them call  assert_active('<abs path>.gds')  which re-selects the tab and fails loudly otherwise.
"""
import json
import os

STYLES = {  # layer: (colour, dither pattern [0 solid, 1 hollow, 5/9 hatched], visible)
    10: (0x00c000, 1, True), 11: (0xff0000, 1, True), 12: (0x0060ff, 1, True), 13: (0xffb000, 1, True),
    50: (0xff00ff, 1, True),
    1: (0xff8c00, 0, True), 5: (0xc000c0, 0, True), 22: (0x6a0dad, 0, True), 23: (0x303030, 0, True),
    21: (0x0000a0, 0, True), 25: (0x00ffff, 1, True), 20: (0x00b4ff, 5, True), 15: (0x707070, 1, False),
    2: (0xb8b800, 1, True), 100: (0xff0000, 0, True),
}


def _find_view(gds):
    mw = pya.Application.instance().main_window()
    target = os.path.abspath(gds)
    for i in range(mw.views()):
        cv = mw.view(i).active_cellview()
        if cv.is_valid() and os.path.abspath(cv.filename() or "") == target:
            return i
    return None


def style_view(v):
    v.add_missing_layers()
    it = v.begin_layers()
    while not it.at_end():
        lp = it.current()
        s = STYLES.get(lp.source_layer) if lp.source_datatype == 0 else None
        if s:
            nl = lp.dup(); nl.fill_color = s[0]; nl.frame_color = s[0]; nl.dither_pattern = s[1]
            nl.visible = s[2]; nl.width = 2 if s[1] == 1 else 1
            v.set_layer_properties(it, nl)
        it.next()


def open_design(gds, placement=None):
    mw = pya.Application.instance().main_window()
    i = _find_view(gds)
    if i is None:
        mw.load_layout(os.path.abspath(gds), 1)          # mode 1 = new tab
        i = mw.current_view_index
    mw.select_view(i)
    v = mw.current_view()
    if placement and not list(v.each_image()):
        pl = json.load(open(placement))
        img = pya.Image(os.path.join(os.path.dirname(placement), pl["image_file"]))
        img.trans = pya.DCplxTrans(pl["pixel_size_um"], 0, False, pya.DVector(*pl["origin_um"]))
        v.insert_image(img)
    style_view(v)
    v.zoom_fit()
    return dict(view=i, title=v.title, file=v.active_cellview().filename(), images=len(list(v.each_image())))


def assert_active(gds):
    mw = pya.Application.instance().main_window()
    i = _find_view(gds)
    assert i is not None, "no open tab for %s" % gds
    mw.select_view(i)
    assert os.path.abspath(mw.current_view().active_cellview().filename()) == os.path.abspath(gds)
    return dict(view=i)
