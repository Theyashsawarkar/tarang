"""How fast the Wi-Fi card moves data: its byte counters, read once a second,
and the last minute kept. No GTK here (the unit tests run without it).

Nothing here makes network traffic: it reads the card's own counters
(/sys/class/net/<dev>/statistics) and signal level (/proc/net/wireless).
TARANG_SYS_NET and TARANG_PROC_WIRELESS point those reads elsewhere (the
headless tests' made-up counters).
"""
import math
import os
import time
from collections import deque

SYS_NET = os.environ.get("TARANG_SYS_NET", "/sys/class/net")
PROC_WIRELESS = os.environ.get("TARANG_PROC_WIRELESS", "/proc/net/wireless")
WINDOW = 60          # seconds of history the graph shows


# ------------------------------------------------------------------ numbers
def rate_parts(bps):
    """(number, unit) for bytes per second: ("12.4", "MB/s")."""
    bps = max(0.0, float(bps or 0))
    for unit, size in (("GB/s", 1e9), ("MB/s", 1e6), ("kB/s", 1e3)):
        if bps >= size:
            v = bps / size
            return (f"{v:.1f}" if v < 100 else f"{v:.0f}"), unit
    return f"{bps:.0f}", "B/s"


def rate_text(bps, short=False):
    n, u = rate_parts(bps)
    if short and n.endswith(".0"):
        n = n[:-2]
    return f"{n} {u}"


def size_text(b):
    b = max(0.0, float(b or 0))
    for unit, size in (("TB", 1e12), ("GB", 1e9), ("MB", 1e6), ("kB", 1e3)):
        if b >= size:
            v = b / size
            return f"{v:.1f} {unit}" if v < 100 else f"{v:.0f} {unit}"
    return f"{b:.0f} B"


def duration_text(sec):
    sec = int(max(0, sec))
    if sec < 60:
        return "less than a minute"
    m = sec // 60
    if m < 60:
        return f"{m} min"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h} h {m:02d} min"
    d, h = divmod(h, 24)
    return f"{d} d {h} h"


def nice_ceiling(v):
    """The graph's top: 1, 2 or 5 times a power of ten, at least 10 kB/s."""
    v = max(v, 10e3)
    p = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 5, 10):
        if v <= m * p:
            return m * p
    return 10 * p


# ------------------------------------------------------------------ reading
def counters(dev):
    """(rx_bytes, tx_bytes) of a network device, or None."""
    if not dev:
        return None
    try:
        base = os.path.join(SYS_NET, dev, "statistics")
        with open(os.path.join(base, "rx_bytes")) as f:
            rx = int(f.read().strip() or 0)
        with open(os.path.join(base, "tx_bytes")) as f:
            tx = int(f.read().strip() or 0)
        return rx, tx
    except (OSError, ValueError):
        return None


def wireless_level(dev):
    """(link quality 0..100, level in dBm or None) from /proc/net/wireless."""
    try:
        with open(PROC_WIRELESS) as f:
            for line in f:
                name, _, rest = line.partition(":")
                if name.strip() != dev:
                    continue
                parts = rest.split()
                q = float(parts[1].rstrip("."))
                dbm = float(parts[2].rstrip("."))
                return max(0, min(100, round(q * 100 / 70))), (int(dbm) if -120 < dbm < 0 else None)
    except (OSError, ValueError, IndexError):
        pass
    return None


# ------------------------------------------------------------------ the sampler
class Traffic:
    """The last minute of one device's speeds (and its signal), one sample a second."""

    def __init__(self):
        self.dev = None
        self.last = None            # (time, rx, tx)
        self.rx = deque(maxlen=WINDOW)
        self.tx = deque(maxlen=WINDOW)
        self.sig = deque(maxlen=WINDOW)
        self.totals = (0, 0)
        self.dbm = None

    def reset(self, dev=None):
        self.dev, self.last = dev, None
        self.rx.clear()
        self.tx.clear()
        self.sig.clear()

    def sample(self, dev, fallback_signal=None):
        """Read the counters once (cheap: two small sysfs files). A gap of more
        than 3 s (the panel was closed) starts the minute over."""
        if dev != self.dev:
            self.reset(dev)
        c = counters(dev)
        now = time.monotonic()
        if c is None:
            return False
        self.totals = c
        if self.last is not None and now - self.last[0] > 3:
            self.reset(dev)
        if self.last is not None:
            dt = max(0.2, now - self.last[0])
            self.rx.append(max(0, c[0] - self.last[1]) / dt)
            self.tx.append(max(0, c[1] - self.last[2]) / dt)
        self.last = (now, c[0], c[1])
        lv = wireless_level(dev)
        if lv:
            self.sig.append(lv[0])
            self.dbm = lv[1]
        elif fallback_signal is not None:
            self.sig.append(int(fallback_signal))
        return True

    def now(self):
        return (self.rx[-1] if self.rx else 0.0), (self.tx[-1] if self.tx else 0.0)

    def peak(self):
        return (max(self.rx) if self.rx else 0.0), (max(self.tx) if self.tx else 0.0)

    def average(self):
        return ((sum(self.rx) / len(self.rx)) if self.rx else 0.0), ((sum(self.tx) / len(self.tx)) if self.tx else 0.0)
