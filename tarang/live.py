"""The live view's drawings (the minute's graph, the signal line) and the
slower facts beside them (link rates from iw, since when from the journal).
The numbers and the sampler are in speed.py."""
import math
import re

import cairo
from gi.repository import Gtk, Pango, PangoCairo
from vyom import util

from .speed import (  # noqa: F401
    WINDOW,
    Traffic,
    counters,
    duration_text,
    nice_ceiling,
    rate_parts,
    rate_text,
    size_text,
)


def link_info(dev):
    """`iw dev <dev> link`: rx/tx bitrate and signal (dBm), when iw is there.
    Runs in a worker thread."""
    if not dev or not util.have("iw"):
        return {}
    _, out = util.run(["iw", "dev", dev, "link"], timeout=3)
    info = {}
    for key, pat in (("rx_rate", r"rx bitrate:\s*([\d.]+)\s*MBit/s"), ("tx_rate", r"tx bitrate:\s*([\d.]+)\s*MBit/s"),
                     ("dbm", r"signal:\s*(-?\d+)")):
        m = re.search(pat, out)
        if m:
            info[key] = float(m.group(1))
    return info


def connected_since(dev):
    """When the device last became connected (unix time), from
    NetworkManager's log; None when the journal can't be read. Worker thread."""
    if not dev or not util.have("journalctl"):
        return None
    _, out = util.run(["journalctl", "-b", "-u", "NetworkManager", "-o", "short-unix", "--no-pager", "-q",
                       "-g", rf"device \({re.escape(dev)}\): Activation: successful", "-n", "1"], timeout=4)
    lines = [ln for ln in out.splitlines() if ln[:1].isdigit()]
    try:
        return float(lines[-1].split()[0]) if lines else None
    except ValueError:
        return None


# ------------------------------------------------------------------ drawing
def _round_rect(cr, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def _curve(cr, pts):
    """A smooth line through pts (Catmull-Rom as Béziers), from the current point."""
    if len(pts) < 2:
        return
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        cr.curve_to(c1[0], c1[1], c2[0], c2[1], p2[0], p2[1])


class Swatch(Gtk.Box):
    """An invisible widget whose CSS colour the drawings borrow, so every
    colour comes from the theme (@sky, @lavender…)."""

    def __init__(self, cls):
        super().__init__()
        self.add_css_class(cls)
        self.set_size_request(0, 0)

    def rgba(self):
        c = self.get_color()
        return c.red, c.green, c.blue, c.alpha


class Graph(Gtk.Box):
    """The last minute of download (filled) and upload (line over a lighter
    fill), on a nice scale with faint guides, the peaks marked, a dot at now."""

    def __init__(self, traffic, height=92, labels=("Down", "Up")):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("tarang-graph")
        self.traffic = traffic
        self.labels = labels
        self.c_rx, self.c_tx = Swatch("tarang-rx"), Swatch("tarang-tx")
        self.c_grid, self.c_text = Swatch("tarang-grid"), Swatch("tarang-axis")
        self.c_pill = Swatch("tarang-pill")
        for s in (self.c_rx, self.c_tx, self.c_grid, self.c_text, self.c_pill):
            self.append(s)
        self.area = Gtk.DrawingArea(content_height=height, hexpand=True)
        self.area.set_draw_func(self.draw)
        self.append(self.area)

    def redraw(self):
        self.area.queue_draw()

    def text(self, cr, s, x, y, rgba, align=0.0, size=8.5, bold=False, pill=None):
        layout = PangoCairo.create_layout(cr)
        fd = Pango.FontDescription.from_string(f"Sans {'Bold ' if bold else ''}{size}")
        layout.set_font_description(fd)
        layout.set_text(s, -1)
        w, h = layout.get_pixel_size()
        if pill is not None:   # a rounded backing, so a label never sits on a line unreadably
            cr.set_source_rgba(*pill)
            _round_rect(cr, x - w * align - 5, y - 1, w + 10, h + 2, (h + 2) / 2)
            cr.fill()
        cr.set_source_rgba(*rgba)
        cr.move_to(x - w * align, y)
        PangoCairo.show_layout(cr, layout)
        cr.new_path()      # show_layout leaves a current point: the next arc would draw a line from it
        return w, h

    def draw(self, _area, cr, w, h):
        t = self.traffic
        top_pad, bot_pad, left, right = 16, 18, 2, 8
        gw, gh = w - left - right, h - top_pad - bot_pad
        rx, tx = list(t.rx), list(t.tx)
        peak = max(rx + tx + [0])
        scale = nice_ceiling(peak * 1.12)
        grid = self.c_grid.rgba()
        axis = self.c_text.rgba()
        # guides: top, middle, bottom; the scale written on the top one
        cr.set_line_width(1)
        for i, frac in enumerate((0.0, 0.5, 1.0)):
            y = round(top_pad + gh * frac) + 0.5
            cr.set_source_rgba(*grid)
            cr.set_dash([3, 4] if i < 2 else [], 0)
            cr.move_to(left, y)
            cr.line_to(left + gw, y)
            cr.stroke()
        cr.set_dash([], 0)
        self.text(cr, rate_text(scale, True), left, 0, axis)
        self.text(cr, rate_text(scale / 2, True), left, top_pad + gh / 2 - 13, axis)
        self.text(cr, f"{WINDOW} s ago", left, h - bot_pad + 3, axis, size=8)
        self.text(cr, "now", left + gw, h - bot_pad + 3, axis, align=1.0, size=8)
        if len(rx) < 2:
            self.text(cr, "Measuring…", left + gw / 2, top_pad + gh / 2 - 8, axis, align=0.5, size=9)
            return

        def pts(series):
            n = len(series)
            step = gw / (WINDOW - 1)
            x0 = left + gw - step * (n - 1)
            return [(x0 + i * step, top_pad + gh - gh * min(1.0, v / scale)) for i, v in enumerate(series)]

        for series, sw, fill_a in ((rx, self.c_rx, 0.32), (tx, self.c_tx, 0.20)):
            r, g, b, _a = sw.rgba()
            p = pts(series)
            # the area under the line, fading to nothing at the bottom
            grad = cairo.LinearGradient(0, top_pad, 0, top_pad + gh)
            grad.add_color_stop_rgba(0, r, g, b, fill_a)
            grad.add_color_stop_rgba(1, r, g, b, 0.0)
            cr.move_to(p[0][0], top_pad + gh)
            cr.line_to(*p[0])
            _curve(cr, p)
            cr.line_to(p[-1][0], top_pad + gh)
            cr.close_path()
            cr.set_source(grad)
            cr.fill()
            cr.move_to(*p[0])
            _curve(cr, p)
            cr.set_source_rgba(r, g, b, 1)
            cr.set_line_width(2)
            cr.set_line_join(1)
            cr.stroke()
            # now: a dot with a soft halo
            x, y = p[-1]
            cr.set_source_rgba(r, g, b, 0.25)
            cr.arc(x, y, 6, 0, 2 * math.pi)
            cr.fill()
            cr.set_source_rgba(r, g, b, 1)
            cr.arc(x, y, 3, 0, 2 * math.pi)
            cr.fill()
        # the minute's peaks: a ring and its number, kept inside the card,
        # above its line, and never on top of the other peak's number
        placed = []
        for series, sw, name in ((rx, self.c_rx, self.labels[0]), (tx, self.c_tx, self.labels[1])):
            if not series or max(series) <= 0:
                continue
            i = max(range(len(series)), key=lambda k: series[k])
            if i == len(series) - 1:
                continue    # the peak is now: the now dot says it
            x, y = pts(series)[i]
            r, g, b, _a = sw.rgba()
            cr.set_source_rgba(r, g, b, 1)
            cr.set_line_width(1.5)
            cr.arc(x, y, 3.5, 0, 2 * math.pi)
            cr.stroke()
            s = f"{name} peak {rate_text(series[i])}"
            align = 0.0 if x < left + gw * 0.55 else 1.0
            lw = 7 * len(s)                       # roughly, at 8 pt bold
            def box(ty, al):
                x0 = x + 8 if al == 0 else x - 8 - lw
                return (x0, ty, x0 + lw, ty + 14)
            def clear(b):
                return all(b[2] < o[0] or b[0] > o[2] or b[3] < o[1] or b[1] > o[3] for o in placed)
            tries = [(y - 18, align), (y + 6, align), (y - 18, 1.0 - align), (y + 6, 1.0 - align)]
            ok = [(ty, al) for ty, al in tries if 0 <= ty and ty + 14 <= top_pad + gh and clear(box(ty, al))]
            ty, align = ok[0] if ok else tries[0]
            placed.append(box(ty, align))
            self.text(cr, s, x + (8 if align == 0 else -8), ty, (r, g, b, 1), align=align, size=8, bold=True,
                      pill=self.c_pill.rgba())


class Spark(Gtk.Box):
    """The minute's signal as a small line, in the signal's colour."""

    def __init__(self, traffic, color, height=18):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.traffic = traffic
        self.sw = Swatch(f"t-{color}")
        self.append(self.sw)
        self.area = Gtk.DrawingArea(content_height=height, hexpand=True)
        self.area.set_draw_func(self.draw)
        self.append(self.area)

    def redraw(self):
        self.area.queue_draw()

    def draw(self, _area, cr, w, h):
        s = list(self.traffic.sig)
        r, g, b, _a = self.sw.rgba()
        cr.set_source_rgba(r, g, b, 0.18)    # a faint baseline the line moves over
        cr.set_line_width(1)
        cr.move_to(0, h - 0.5)
        cr.line_to(w, h - 0.5)
        cr.stroke()
        if len(s) < 2:
            return
        lo, hi = 0, 100
        step = (w - 6) / (WINDOW - 1)
        x0 = w - 3 - step * (len(s) - 1)
        pts = [(x0 + i * step, h - 3 - (h - 6) * (v - lo) / (hi - lo)) for i, v in enumerate(s)]
        cr.move_to(*pts[0])
        _curve(cr, pts)
        cr.set_source_rgba(r, g, b, 1)
        cr.set_line_width(1.6)
        cr.stroke()
        cr.arc(pts[-1][0], pts[-1][1], 2.6, 0, 2 * math.pi)
        cr.fill()
