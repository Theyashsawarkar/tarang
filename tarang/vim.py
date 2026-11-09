"""tarang's vim keys, as data. NORMAL is the start; `/` types a filter.
Typing a password or a hotspot field puts the search box in INSERT mode by
itself: Enter submits, Esc cancels it, Ctrl+S shows what you type. The
modes, counts, which-key strip, help (?) and palette (Space Space) are
Vyom's (vyom/keys.py, vyom/modal.py; Vyom ADR 0008). Space groups follow
Vayu's shared letters (d delete, u toggles, y copy, t tabs); p (power) and
c (connection) are tarang's own.

An action "verb:arg" runs Plugin.v_<verb>(count, arg) in tarang/__init__.py,
or Vyom's own (moved, nop...).
"""
from vyom.keys import Bind

B = Bind
GROUPS = {" p": "power", " c": "connection"}
NETS, HOT = "networks", "hotspot"


def moved(seq, to, when=None):
    """An old key that moved in v0.5 (for one release): says where to."""
    return B(seq, f"moved:{to}", "", hidden=True, when=when)


NETWORKS = [
    B("<CR>", "activate", "Connect to the selected network (asks for its password if needed)", when=NETS),
    B("dd", "forget", "Forget the selected saved network (y confirms: its password goes too)", when=NETS),
    B("r", "rescan", "Rescan for networks now", when=NETS),
    moved("<C-f>", "d d", NETS),
]

HOTSPOT = [
    B("<CR>", "activate", "Edit the selected hotspot setting (the band: switch it)", when=HOT),
    B("e", "activate", "Edit the selected hotspot setting", when=HOT),
]

COMMON = [
    # The old Ctrl keys stay (they work while typing a password too); Ctrl+D
    # is half a page down now, as in every vim tool, and Ctrl+F moved to d d.
    B("<C-w>", "radio", "", mode="any", hidden=True),
    B("<C-t>", "hotspot", "", mode="any", hidden=True),
    B("<C-q>", "share", "", mode="any", hidden=True),
    B("<C-s>", "showpw", "Show or hide the password you type (works while typing)", mode="any"),
    B("<C-r>", "rescan", "", mode="any", hidden=True),
]

LEADER = [
    B(" pp", "radio", "Toggle Wi-Fi on or off"),
    B(" ph", "hotspot", "Toggle the hotspot on or off"),
    B(" cd", "disconnect", "Disconnect from the current network", when=NETS),
    B(" cq", "share", "Show the current network as a QR code (to share it)", when=NETS),
    B(" us", "showpw", "Toggle the passwords (show or hide them)"),
    B(" yp", "copy:password", "Copy the network's password (the hotspot's on its tab)"),
    B(" ys", "copy:ssid", "Copy the network's name (the hotspot's on its tab)"),
    B(" dd", "forget", "Forget the selected saved network (y confirms)", when=NETS),
]

HOT_LEADER = [
    B(" cq", "share", "Toggle the hotspot's QR code", when=HOT),
]

SECTIONS = [
    ("wifi", "normal", "Normal mode, Networks (where it opens; `/` types a filter)", NETWORKS),
    ("wifi hotspot", "normal", "Normal mode, Hotspot", HOTSPOT),
    ("wifi", "any", "Both modes", COMMON),
    ("wifi leader", "normal", "Leader (Space)", LEADER),
    ("wifi hotspot leader", "normal", "Leader (Space), Hotspot", HOT_LEADER),
]


def keys(_tab):
    return NETWORKS + HOTSPOT + COMMON + LEADER + HOT_LEADER
