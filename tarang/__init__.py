"""tarang (तरंग, "wave"): Wi-Fi for Vyom, through NetworkManager.

The network you're on is a card at the top (signal ring, band, its live
download and upload; Share and Disconnect) and the list's first row; picked,
the right side shows it live (live.py: speeds, the minute's graph, totals,
signal, addresses). Below it the saved networks, then the nearby ones,
strongest first, each with signal bars and a word. Enter connects; a secured network you haven't joined asks
for its password right in the search box, and connecting shows its steps
(and why it failed, when it does). A Hotspot tab drives vayu-hotspot (or
any command with its `status --json` / `on` / `off` interface) when it's
installed.
"""
import hashlib
import json
import os
import re
import subprocess
import threading
import time

from gi.repository import GLib, Gtk, Pango

from vyom import Hint, Row, Section, ui, util
from vyom import Plugin as Base

from . import live, vim

# KEYBINDS (generated from tarang/vim.py by scripts/keybinds.py; don't edit by hand)
# keybind: Vyom/wifi:normal | Enter | Connect to the selected network (asks for its password if needed)
# keybind: Vyom/wifi:normal | d d | Forget the selected saved network (y confirms: its password goes too)
# keybind: Vyom/wifi:normal | r | Rescan for networks now
# keybind: Vyom/wifi hotspot:normal | Enter | Edit the selected hotspot setting (the band: switch it)
# keybind: Vyom/wifi hotspot:normal | e | Edit the selected hotspot setting
# keybind: Vyom/wifi | Ctrl+s | Show or hide the password you type (works while typing)
# keybind: Vyom/wifi leader:normal | Space p p | Toggle Wi-Fi on or off
# keybind: Vyom/wifi leader:normal | Space p h | Toggle the hotspot on or off
# keybind: Vyom/wifi leader:normal | Space c d | Disconnect from the current network
# keybind: Vyom/wifi leader:normal | Space c q | Show the current network as a QR code (to share it)
# keybind: Vyom/wifi leader:normal | Space u s | Toggle the passwords (show or hide them)
# keybind: Vyom/wifi leader:normal | Space y p | Copy the network's password (the hotspot's on its tab)
# keybind: Vyom/wifi leader:normal | Space y s | Copy the network's name (the hotspot's on its tab)
# keybind: Vyom/wifi leader:normal | Space d d | Forget the selected saved network (y confirms)
# keybind: Vyom/wifi hotspot leader:normal | Space c q | Toggle the hotspot's QR code
# END KEYBINDS

WIFI, WIFI_OFF, LOCK, LOCK_OPEN = "\U000f05a9", "\U000f05aa", "\U000f033e", "\U000f033f"
STAR, QR, LINK_OFF, SPEED = "\U000f04ce", "\U000f0432", "\U000f0338", "\U000f04c5"
SHIELD, ALERT, ETHERNET, HOTSPOT = "\U000f0565", "\U000f0026", "\U000f0200", "\U000f0003"
PHONE, KEY, LOGIN, DELETE, EYE = "\U000f011c", "\U000f0306", "\U000f0342", "\U000f01b4", "\U000f0208"
REFRESH, CHECK = "\U000f0450", "\U000f012c"
DOWN, UP, CLOCK, GLOBE = "\U000f0045", "\U000f005d", "\U000f0954", "\U000f02e9"

STEPS = ["Associating", "Authenticating", "Getting an address"]
# NetworkManager's connectivity, in a word and a colour (peach: something to look at)
INTERNET = {"full": ("Online", "green", CHECK), "limited": ("Limited", "yellow", ALERT),
            "portal": ("Sign in", "peach", LOGIN), "none": ("No internet", "red", LINK_OFF),
            "unknown": ("Not checked", "gray", GLOBE)}
ENV = dict(os.environ, LC_ALL="C", LANG="C")   # English messages, so errors can be read


def fields(line):
    """nmcli -t output: ':'-separated, with '\\:' inside a field."""
    out, cur, esc = [], "", False
    for ch in line:
        if esc:
            cur += ch
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def unesc(s):
    return fields(s)[0] if s else ""


def quality(signal):
    """(level 0..4, word, colour, plain note) for a signal in percent."""
    s = int(signal or 0)
    if s >= 75:
        return 4, "Excellent", "green", "Fast and steady: fine for anything."
    if s >= 55:
        return 3, "Good", "green", "Fine for video calls. Move closer for big downloads."
    if s >= 35:
        return 2, "Fair", "yellow", "Browsing is fine; calls may stutter."
    return (1 if s > 0 else 0), "Weak", "red", "Expect drops and slow pages: move closer to the router."


def security(sec):
    """(short name, chip colour, word, kind) for nmcli's SECURITY field."""
    sec = "" if sec in ("", "--") else sec
    if not sec:
        return "Open", "yellow", "no password", "open"
    if "802.1X" in sec:
        return ("WPA3 Enterprise" if "WPA3" in sec else "WPA2 Enterprise"), "gray", "asks for a user name", "enterprise"
    if "WPA3" in sec:
        return "WPA3", "green", "strong", "strong"
    if "WPA2" in sec:
        return "WPA2", "gray", "good", "ok"
    return ("WEP" if "WEP" in sec else "WPA1"), "red", "weak", "weak"


def band(freq):
    f = str(freq or "")
    return "5 GHz" if f.startswith("5") else "6 GHz" if f.startswith("6") else "2.4 GHz"


def rate(r):
    return (r or "").replace("Mbit/s", "Mb/s").strip()


def ago(ts):
    try:
        ts = int(ts or 0)
    except ValueError:
        ts = 0
    if ts <= 0:
        return ""
    d = time.time() - ts
    if d < 3600:
        return "used just now" if d < 120 else f"used {int(d // 60)} min ago"
    days = int((time.time() // 86400) - (ts // 86400))
    if days <= 0:
        return "used today"
    if days == 1:
        return "last used yesterday"
    if days < 14:
        return f"last used {days} days ago"
    if days < 60:
        return f"last used {days // 7} weeks ago"
    return "last used months ago"


def why(text, code):
    """nmcli's error, in plain words."""
    t = (text or "").strip()
    low = t.lower()
    if code == 124 or "timeout" in low or "timed out" in low:
        return "No answer in time: the network may be out of range or busy."
    if "psk" in low and "invalid" in low:
        return "That can't be the password: Wi-Fi passwords are 8 to 63 characters."
    if "secrets were required" in low or "no secrets" in low or "need auth" in low or "4-way" in low:
        return "Wrong password. Enter tries again with a new one."
    if "no network with ssid" in low or "could not be found" in low or "not found" in low:
        return "Out of range: the network isn't visible any more. Move closer, or rescan with r."
    if "ip configuration" in low or "dhcp" in low:
        return "Joined, but the router didn't hand out an address (DHCP). Try again, or restart the router."
    if "802-1x" in low or "802.1x" in low or "enterprise" in low or "identity" in low:
        return "This network asks for a user name (WPA Enterprise): set it up once with nm-connection-editor."
    if "not authorized" in low or "insufficient privileges" in low or "permission" in low:
        return "NetworkManager didn't allow it (permissions)."
    if "not ready" in low or "unavailable" in low or "not available" in low:
        return "The Wi-Fi card isn't ready: is Wi-Fi on?"
    if code == 127 and not t:
        return "nmcli didn't run."
    last = [l for l in t.splitlines() if l.strip()]
    return (last[-1].removeprefix("Error: ") if last else f"nmcli failed (exit {code}).")


def qr_png(payload):
    """A QR code PNG for `payload` (cached by its hash), or None without qrencode."""
    if not util.have("qrencode"):
        return None
    os.makedirs(util.CACHE, exist_ok=True)
    path = os.path.join(util.CACHE, "tarang-qr-" + hashlib.sha1(payload.encode()).hexdigest()[:12] + ".png")
    if not os.path.exists(path):
        util.run(["qrencode", "-o", path, "-s", "6", "-m", "2", payload])
    return path if os.path.exists(path) else None


def bigtile(icon, color):
    t = ui.tile(icon, color, 26)
    t.add_css_class("big")
    return t


def wifi_payload(ssid, password, kind="WPA"):
    esc = lambda s: re.sub(r'([\\;,:"])', r"\\\1", s)
    if not password:
        return f"WIFI:T:nopass;S:{esc(ssid)};;"
    return f"WIFI:T:{kind};S:{esc(ssid)};P:{esc(password)};;"


# Ctrl+<key> the search box keeps while it's a password or name field: select all,
# copy, cut, paste, undo, redo, and the word moves and deletes.
EDIT_CHORDS = {"a", "c", "x", "v", "z", "y", "Z", "BackSpace", "Delete", "KP_Delete", "Left", "Right", "Home", "End"}


class Plugin(Base):
    name, title, icon, color = "tarang", "Wi-Fi", WIFI, "sky"
    placeholder = "Filter networks…"
    preview = True
    preview_width = 380
    live = 4
    hints = [Hint("Enter", "connect"), Hint("d d", "forget"), Hint("Space c q", "share"),
             Hint("Space p p", "Wi-Fi on/off")]
    typing_hints = [Hint("Enter", "submit"), Hint("Esc", "cancel"), Hint("Ctrl+S", "show")]
    modal = True                # vim keys (Vyom 0.7): NORMAL first, / filters; a password types in INSERT
    start_mode = "normal"
    key_groups = vim.GROUPS

    def __init__(self, vyom, conf):
        super().__init__(vyom, conf)
        self.tab = "networks"
        self.asking = None          # the network (dict) whose password is being typed
        self.ask_error = ""         # why the last try failed (wrong password)
        self.edit_error = ""        # why a hotspot field wasn't saved
        self.editing = None         # hotspot field being edited: "ssid" / "password"
        self.show_pw = False        # Ctrl+S: passwords in clear
        self.scan_asked = 0         # when we last asked NetworkManager to rescan
        self.conn = None            # {"ssid", "step", "state": now/done/failed, "why"} while/after connecting
        self.sharing = None         # {"ssid", "password", "qr", "error", "loading"} after Ctrl+Q
        self.hs_busy = ""           # "starting" / "stopping" / "saving" the hotspot
        self.hs_error = ""
        self.hs_qr = True
        self.snap = {}              # what search() found, for the strip (networks tab)
        self.hs = None              # the hotspot's status (hotspot tab)
        self.ssid_cache = {}        # connection uuid -> (ssid, metered)
        self.switch = self.switch_label = self.scan_chip = None
        self.tick_id = None
        self.traffic = live.Traffic()   # the last minute of speeds (read while the panel is open)
        self.strip_rate = None      # the card's live ↓ ↑ line
        self.live_w = None          # the dashboard's moving parts: {"rx", "tx", "graph", …}
        self.since = {}             # (dev, ssid) -> when it connected (NetworkManager's log)
        self.hotspot = util.expand(self.conf.get("hotspot_command", "vayu-hotspot"))
        # Networks / Hotspot tabs (Ctrl+H/L, Ctrl+1/2: Vyom), when there's a hotspot command.
        self.tabs = [("networks", "Networks"), ("hotspot", "Hotspot")] if util.have(self.hotspot) else []

    def wifi_device(self):
        code, out = util.run("nmcli -t -f DEVICE,TYPE device")
        return next((fields(l)[0] for l in out.splitlines() if fields(l)[1:2] == ["wifi"]), None)

    # ------------------------------------------------------------ header
    def header_extra(self):
        self.scan_chip = Gtk.Box(spacing=5, valign=Gtk.Align.CENTER)
        self.scan_chip.add_css_class("chip")
        self.scan_glyph = ui.label(REFRESH, "glyph", "chip-icon")
        self.scan_text = ui.label("")
        self.scan_chip.append(self.scan_glyph)
        self.scan_chip.append(self.scan_text)
        self.scan_chip.set_visible(False)
        self.switch_label = ui.label("Wi-Fi", "tarang-switch-label", valign=Gtk.Align.CENTER)
        # An on/off pill (a word and a colour) rather than a Gtk.Switch, whose
        # hidden state images warn about baselines in the top bar (GTK 4).
        self.switch_on = False
        self.switch = Gtk.Button(valign=Gtk.Align.CENTER)
        self.switch.add_css_class("tarang-onoff")
        self.switch.set_can_focus(False)
        self.switch.set_child(ui.hbox(ui.vbox(cls="tarang-knob"), ui.label("Off"), spacing=6))
        self.switch.connect("clicked", lambda *_: self.on_switch(not self.switch_on))
        box = ui.hbox(self.scan_chip, self.switch_label, self.switch, spacing=8)
        box.set_valign(Gtk.Align.CENTER)
        return box

    def on_switch(self, on):
        if self.tab == "hotspot":
            if bool(self.hs and self.hs.get("on")) != on:
                self.toggle_hotspot()
        else:
            self.set_radio(on)

    def sync_switch(self):
        if self.switch is None:
            return False
        if self.tab == "hotspot":
            on, what, tip = bool(self.hs and self.hs.get("on")), "Hotspot", "Hotspot on/off (Space p h)"
        else:
            on, what, tip = self.snap.get("radio") is True, "Wi-Fi", "Wi-Fi on/off (Space p p)"
        self.switch_label.set_label(what)
        self.switch.set_tooltip_text(tip)
        self.switch_on = on
        self.switch.get_child().get_last_child().set_label("On" if on else "Off")
        (self.switch.add_css_class if on else self.switch.remove_css_class)("on")
        self.update_scan_chip()
        return False

    def update_scan_chip(self):
        """Scanning (yellow, for a few seconds after a rescan) or how long ago."""
        c = self.scan_chip
        if c is None:
            return
        show = self.tab != "hotspot" and self.snap.get("radio") is True and self.scan_asked > 0
        c.set_visible(show)
        if not show:
            return
        age = int(time.time() - self.scan_asked)
        scanning = age < 4
        for k in ("c-yellow", "c-gray"):
            c.remove_css_class(k)
        c.add_css_class("c-yellow" if scanning else "c-gray")
        self.scan_glyph.set_visible(scanning)
        self.scan_text.set_label("Scanning…" if scanning else
                                 f"Scanned {age} s ago" if age < 60 else f"Scanned {age // 60} min ago")

    def tick(self):
        if not (self.panel and self.panel.get_visible()):
            self.tick_id = None
            return False
        self.update_scan_chip()
        self.sample_traffic()
        return True

    def traffic_dev(self):
        """The device whose speeds to show: the Wi-Fi card while it's connected,
        or hosting the hotspot."""
        if self.tab == "hotspot":
            st = self.hs or {}
            return (st.get("device") or self.snap.get("dev")) if st.get("on") else None
        return self.snap.get("dev") if self.snap.get("active") else None

    def sample_traffic(self):
        dev = self.traffic_dev()
        if not dev:
            return
        a = self.snap.get("active") or {}
        self.traffic.sample(dev, fallback_signal=a.get("signal") or None)
        self.update_live()

    def update_live(self):
        t = self.traffic
        now_rx, now_tx = t.now()
        if self.strip_rate is not None:
            self.strip_rate.set_label(f"↓ {live.rate_text(now_rx)}   ↑ {live.rate_text(now_tx)}")
        w = self.live_w
        if not w:
            return
        peak_rx, peak_tx = t.peak()
        avg_rx, avg_tx = t.average()
        for key, now, peak, avg in (("rx", now_rx, peak_rx, avg_rx), ("tx", now_tx, peak_tx, avg_tx)):
            num, unit = live.rate_parts(now)
            w[key][0].set_label(num)
            w[key][1].set_label(unit)
            w[key][2].set_label(f"peak {live.rate_text(peak)} · avg {live.rate_text(avg)}")
        if "total_rx" in w:
            w["total_rx"].set_label(live.size_text(t.totals[0]))
            w["total_tx"].set_label(live.size_text(t.totals[1]))
        if "since" in w and w.get("since_ts"):
            w["since"].set_label(live.duration_text(time.time() - w["since_ts"]))
        if "dbm" in w:
            dbm = t.dbm
            w["dbm"].set_label(f"{dbm} dBm" if dbm is not None else "")
        w["graph"].redraw()
        if "spark" in w:
            w["spark"].redraw()

    HOTSPOT_HINTS = [Hint("e", "edit"), Hint("Space p h", "on / off"), Hint("Space c q", "QR code"),
                     Hint("Space u s", "password")]

    def tab_hints(self):
        return self.HOTSPOT_HINTS if self.tab == "hotspot" else self.hints

    def mode_hints(self, mode):
        if self.asking or self.editing:
            return self.typing_hints
        return super().mode_hints(mode)

    def tab_changed(self, key):
        self.cancel_entry()
        self.sharing = None
        self.sync_switch()
        self.refresh()

    def set_radio(self, on):
        self.background(lambda: util.run(["nmcli", "radio", "wifi", "on" if on else "off"]),
                        lambda _r: (self.rescan() if on else None, self.refresh()))

    def opened(self, args):
        super().opened(args)
        self.cancel_entry()
        self.sharing = None
        if self.conn and self.conn["state"] != "now":
            self.conn = None
        if self.tabs:
            self.select_tab("hotspot" if args and args[0] == "hotspot" else "networks")
        if self.tick_id is None:
            self.tick_id = GLib.timeout_add_seconds(1, self.tick)
        self.traffic.reset()

    # ------------------------------------------------------------ data
    def search(self, q):
        if self.tab == "hotspot":
            return self.hotspot_rows(q)
        snap = self.collect()
        self.snap = snap
        GLib.idle_add(self.sync_switch)
        if self.asking:
            n = self.asking
            return [Section("Join", "", "Enter connects · Esc cancels"), self.net_row(n)]
        if snap.get("error"):
            self.empty_text = snap["error"]
            return []
        if not snap["radio"]:
            self.empty_text = "Wi-Fi is off: Space p p turns it on"
            return [Row("Wi-Fi is off", "Enter or Space p p turns it on", icon=WIFI_OFF, color="gray",
                        data={"kind": "off"})]
        self.empty_text = "No networks match" if q else "No networks found yet: r rescans"
        saved, nearby, here = [], [], []
        for n in snap["nets"]:
            if q and util.fuzzy(q, n["ssid"]) is None:
                continue
            (here if n["active"] else saved if n["saved"] else nearby).append(self.net_row(n))
        rows = []
        if here:   # the network you're on first: its row opens the live view
            rows += [Section("Connected", "", "live speeds on the right")] + here
        if saved:
            rows += [Section("Saved", len(saved), "Enter connects")] + saved
        if nearby:
            rows += [Section("Nearby", len(nearby), "strongest first")] + nearby
        return rows

    def collect(self):
        """Everything the networks tab shows, read in the worker thread."""
        code, out = util.run("nmcli -t -f RUNNING general")
        if code == 127 and not util.have("nmcli"):
            return {"error": "nmcli isn't installed: tarang needs NetworkManager", "radio": None}
        if out.strip() != "running":
            return {"error": "NetworkManager isn't running (systemctl start NetworkManager)", "radio": None}
        dev = self.wifi_device()
        wired = self.wired()
        if dev is None:
            return {"error": "No Wi-Fi card found", "radio": None, "wired": wired}
        radio = util.run("nmcli radio wifi")[1] == "enabled"
        snap = {"radio": radio, "dev": dev, "wired": wired, "nets": [], "active": None, "ip": ""}
        if not radio:
            return snap
        if time.time() - self.scan_asked > 15 and not (self.conn and self.conn["state"] == "now"):
            self.rescan(refresh=False)
        saved = self.saved()
        nets = {}
        _, out = util.run("nmcli -t -f IN-USE,SSID,SECURITY,SIGNAL,FREQ,CHAN,BSSID,RATE device wifi list --rescan no")
        for line in out.splitlines():
            f = fields(line)
            if len(f) < 8 or not f[1]:
                continue
            inuse, ssid, sec, sig, freq, chan, bssid, rt = f[:8]
            n = nets.get(ssid)
            if n is None or int(sig or 0) > int(n["signal"] or 0) or inuse == "*":
                conn = saved.get(ssid) or {}
                nets[ssid] = {"ssid": ssid, "security": "" if sec == "--" else sec, "signal": sig, "freq": freq,
                              "chan": chan, "bssid": bssid, "rate": rt,
                              "active": inuse == "*" or (n or {}).get("active", False),
                              "saved": bool(conn), "conn": conn.get("uuid"), "conn_name": conn.get("name"),
                              "ts": conn.get("ts", 0), "metered": conn.get("metered", "")}
        snap["nets"] = sorted(nets.values(), key=lambda n: -int(n["signal"] or 0))
        snap["active"] = next((n for n in snap["nets"] if n["active"]), None)
        if snap["active"]:
            snap.update(self.details(dev, snap["active"]))
        return snap

    def details(self, dev, a):
        """Addresses, internet state, link rates and since when, for the network
        you're on (worker thread; reads only, nothing goes out on the network)."""
        keys = ["IP4.ADDRESS", "IP4.GATEWAY", "IP4.DNS", "IP6.ADDRESS", "GENERAL.HWADDR"]
        vals = util.run(["nmcli", "-g", ",".join(keys), "device", "show", dev])[1].splitlines() + [""] * len(keys)
        first = lambda v: unesc(v.split(" | ")[0].strip()) if v else ""
        ip6 = [unesc(x.strip()).split("/")[0] for x in vals[3].split(" | ") if x.strip()]
        ip6 = [x for x in ip6 if not x.lower().startswith("fe80")] or ip6
        d = {"ip": first(vals[0]).split("/")[0], "gateway": first(vals[1]),
             "dns": ", ".join(unesc(x.strip()) for x in vals[2].split(" | ") if x.strip()),
             "ip6": ip6[0] if ip6 else "", "mac": first(vals[4])}
        d["internet"] = util.run("nmcli -t -f CONNECTIVITY general")[1].strip() or "unknown"
        d["link"] = live.link_info(dev)
        key = (dev, a["ssid"], a.get("bssid"))
        if key not in self.since:
            self.since = {key: live.connected_since(dev)}
        d["since"] = self.since[key]
        return d

    def rescan(self, refresh=True):
        self.scan_asked = time.time()
        util.spawn(["nmcli", "device", "wifi", "rescan"])
        GLib.idle_add(self.update_scan_chip)
        if refresh:   # NetworkManager takes a few seconds to scan
            GLib.timeout_add_seconds(4, lambda: (self.refresh(), False)[1])

    def net_row(self, n):
        name, color, _word, kind = security(n["security"])
        lv, word, lcolor, _ = quality(n["signal"])
        extra = ago(n.get("ts")) if n["saved"] else ("asks for a user name" if kind == "enterprise" else "")
        sub = " · ".join(x for x in (name, band(n["freq"]), extra) if x)
        chips = []
        c = self.conn
        if n["active"] and not (c and c["ssid"] == n["ssid"]):
            chips.append(("Connected", "green"))
        if c and c["ssid"] == n["ssid"]:
            chips.append(("Connecting…", "yellow") if c["state"] == "now" else
                         ("Failed", "red") if c["state"] == "failed" else ("Connected", "green"))
        if kind == "open":
            chips.append(("Open", "yellow"))
        elif kind == "weak":
            chips.append((f"{name}: weak", "red"))
        return Row(n["ssid"], sub, icon=WIFI, color="sky" if n["saved"] else "yellow" if kind == "open" else "gray",
                   badge=STAR if n["saved"] else "", badge_color="yellow",
                   chips=chips, level=lv, level_text=word, level_color=lcolor, data={"kind": "net", **n})

    def saved(self):
        """SSID -> {uuid, name, ts, metered} of saved Wi-Fi connections."""
        _, out = util.run("nmcli -t -f NAME,UUID,TYPE,TIMESTAMP connection show")
        res = {}
        for line in out.splitlines():
            f = fields(line)
            if len(f) >= 4 and f[2] == "802-11-wireless" and f[0] != "Vayu Hotspot":
                uuid = f[1]
                if uuid not in self.ssid_cache:
                    vals = util.run(["nmcli", "-g", "802-11-wireless.ssid,connection.metered,802-11-wireless.mode",
                                     "connection", "show", "uuid", uuid])[1].splitlines() + ["", "", ""]
                    self.ssid_cache[uuid] = (unesc(vals[0]) or f[0], vals[1], vals[2])
                ssid, metered, mode = self.ssid_cache[uuid]
                if mode == "ap":        # a hotspot of its own, not a network to join
                    continue
                res[ssid] = {"uuid": uuid, "name": f[0], "ts": f[3], "metered": metered}
        return res

    def wired(self):
        _, out = util.run("nmcli -t -f TYPE,STATE,CONNECTION device")
        return next((fields(l)[2] for l in out.splitlines() if fields(l)[:2] == ["ethernet", "connected"]), "")

    # ------------------------------------------------------------ the status strip
    def build_strip(self):
        try:
            return self.hotspot_strip() if self.tab == "hotspot" else self.network_strip()
        except Exception:   # the strip must never take the panel down
            import logging
            logging.getLogger("vyom.tarang").exception("strip")
            return None

    def network_strip(self):
        s = self.snap
        self.strip_rate = None
        if self.asking:
            return self.join_strip(self.asking)
        if self.conn and self.conn["state"] in ("now", "failed"):
            return self.connect_strip()
        if self.sharing:
            return self.share_strip()
        if s.get("error"):
            return ui.hero(ui.ring(0, "red", 64, 6, ui.label(WIFI_OFF, "glyph", "tarang-ring-glyph", "t-red")),
                           self.grow(ui.vbox(ui.hbox(ui.label("Wi-Fi isn't available", "hero-title"),
                                                     ui.chip("Unavailable", "red", ALERT), spacing=8),
                                             ui.label(s["error"], "hero-sub", xalign=0, wrap=True), spacing=6)),
                           color="red")
        if s.get("radio") is False:
            sub = (f"You're on Ethernet ({s['wired']}). " if s.get("wired") else "") + \
                  "Turn it on to see the networks around you."
            return ui.hero(ui.ring(0, "gray", 64, 6, ui.label(WIFI_OFF, "glyph", "tarang-ring-glyph")),
                           self.grow(ui.vbox(ui.hbox(ui.label("Wi-Fi is off", "hero-title"),
                                                     ui.chip("Off", "gray", WIFI_OFF), spacing=8),
                                             ui.label(sub, "hero-sub", xalign=0, wrap=True), spacing=6)),
                           ui.button("Turn on", lambda: self.set_radio(True), "primary", WIFI, "Space p p"),
                           color="gray")
        a = s.get("active")
        if not a:
            if s.get("wired"):
                return ui.hero(ui.ring(1, "green", 64, 6, ui.label(ETHERNET, "glyph", "tarang-ring-glyph", "t-green")),
                               self.grow(ui.vbox(ui.hbox(ui.label(s["wired"], "hero-title"),
                                                         ui.chip("On Ethernet", "green", CHECK), spacing=8),
                                                 ui.label("Wi-Fi isn't connected: you don't need it while the cable "
                                                          "is in. Pick a network below to join one anyway.",
                                                          "hero-sub", xalign=0, wrap=True), spacing=6)),
                               color="green")
            return ui.hero(ui.ring(0, "gray", 64, 6, ui.label(WIFI, "glyph", "tarang-ring-glyph")),
                           self.grow(ui.vbox(ui.hbox(ui.label("Not connected", "hero-title"),
                                                     ui.chip("Offline", "gray", LINK_OFF), spacing=8),
                                             ui.label("Pick a network below and press Enter to join it.",
                                                      "hero-sub", xalign=0, wrap=True), spacing=6)),
                           color="gray")
        lv, word, lcolor, _ = quality(a["signal"])
        sname, _sc, _sw, _k = security(a["security"])
        chips = [(f"{word} · {a['signal']}%", lcolor, WIFI), (f"{band(a['freq'])} · ch {a['chan']}", "gray")]
        if sname == "Open":
            chips.append(("Open", "yellow", LOCK_OPEN))
        self.strip_rate = ui.label("", "tarang-strip-rate", xalign=0)
        text = ui.vbox(ui.hbox(ui.label(a["ssid"], "hero-title", ellipsize=Pango.EllipsizeMode.END),
                               ui.chip("Connected", "green", CHECK), spacing=8),
                       ui.chips(*chips), self.strip_rate, spacing=6)
        GLib.idle_add(lambda: (self.update_live(), False)[1])
        return ui.hero(ui.ring(int(a["signal"] or 0) / 100, lcolor, 56, 6,
                               ui.label(WIFI, "glyph", "tarang-ring-glyph", f"t-{lcolor}")),
                       self.grow(text),
                       ui.vbox(self.tip(ui.button("Share", self.share, "", QR), "Space c q"),
                               self.tip(ui.button("Disconnect", self.disconnect, "danger", LINK_OFF), "Space c d"),
                               spacing=6),
                       color="green")

    @staticmethod
    def tip(button, keys):
        """A button whose keys are in its tooltip (and the footer), so the card stays narrow."""
        button.set_tooltip_text(keys)
        return button

    @staticmethod
    def grow(w):
        w.set_hexpand(True)
        w.set_valign(Gtk.Align.CENTER)
        return w

    def join_strip(self, n):
        sname, scolor, sword, _ = security(n["security"])
        pw_hint = "shown" if self.show_pw else "hidden"
        return ui.hero(ui.ring(0, "yellow", 64, 6, ui.label(KEY, "glyph", "tarang-ring-glyph", "t-yellow")),
                       self.grow(ui.vbox(ui.hbox(ui.label(f"Join {n['ssid']}", "hero-title"),
                                                 ui.chip(f"{sname} · {sword}", scolor, LOCK), spacing=8),
                                         ui.label(f"Type its password in the box above ({pw_hint}: Ctrl+S "
                                                  f"{'hides' if self.show_pw else 'shows'} it). Nothing is sent "
                                                  "until you press Enter; Esc cancels.",
                                                  "hero-sub", xalign=0, wrap=True),
                                         ui.label(f"Couldn't join: {self.ask_error}", "hero-sub", "t-red",
                                                  xalign=0, wrap=True) if self.ask_error else
                                         ui.steps([(t, "todo") for t in STEPS]), spacing=7)),
                       ui.vbox(ui.button("Connect", self.submit_password, "primary", LOGIN, "Enter"),
                               ui.button("Hide" if self.show_pw else "Show", self.toggle_show, "", EYE, "Ctrl+S"),
                               spacing=6),
                       color="red" if self.ask_error else "yellow")

    def step_items(self):
        c = self.conn
        if c["state"] == "done":
            return [(t, "done") for t in STEPS]
        items = []
        for i, t in enumerate(STEPS):
            if i < c["step"]:
                items.append((t, "done"))
            elif i == c["step"]:
                items.append((t, "now" if c["state"] == "now" else "todo"))
            else:
                items.append((t, "todo"))
        return items

    def connect_strip(self):
        c = self.conn
        if c["state"] == "failed":
            return ui.hero(ui.ring(0, "red", 64, 6, ui.label(ALERT, "glyph", "tarang-ring-glyph", "t-red")),
                           self.grow(ui.vbox(ui.hbox(ui.label(f"Couldn't join {c['ssid']}", "hero-title", "t-red"),
                                                     ui.chip("Failed", "red", ALERT), spacing=8),
                                             ui.label(c["why"], "hero-sub", xalign=0, wrap=True),
                                             None if c.get("nosteps") else ui.steps(self.step_items()),
                                             spacing=7)),
                           color="red")
        return ui.hero(ui.ring((c["step"] + 0.5) / len(STEPS), "yellow", 64, 6,
                               ui.label(WIFI, "glyph", "tarang-ring-glyph", "t-yellow")),
                       self.grow(ui.vbox(ui.hbox(ui.label(f"Connecting to {c['ssid']}", "hero-title"),
                                                 ui.chip("Connecting…", "yellow"), spacing=8),
                                         ui.label(f"{STEPS[c['step']]}…", "hero-sub", xalign=0),
                                         ui.steps(self.step_items()), spacing=7)),
                       color="yellow")

    def share_strip(self):
        sh = self.sharing
        close = ui.button("Close", self.stop_sharing, "", "", "Esc")
        if sh.get("loading"):
            return ui.hero(self.grow(ui.vbox(ui.label(f"Share {sh['ssid']}", "hero-title", xalign=0),
                                             ui.label("Reading the password from NetworkManager…", "hero-sub",
                                                      xalign=0), spacing=6)), close, color="yellow")
        if sh.get("error"):
            return ui.hero(self.grow(ui.notice(f"Can't share {sh['ssid']}", sh["error"], "red")), close, color="red")
        pw = sh.get("password") or ""
        shown = pw if (self.show_pw or not sh.get("qr")) else "•" * min(len(pw), 14)
        kv = [("Name", sh["ssid"]), ("Password", shown if pw else "none (an open network)")]
        parts = [ui.label(f"Share {sh['ssid']}", "hero-title", xalign=0)]
        if sh.get("qr"):
            parts.append(ui.label("Scan the code with a phone camera to join. No typing needed.", "hero-sub",
                                  xalign=0, wrap=True))
        else:
            parts.append(ui.notice("qrencode isn't installed",
                                   "Install qrencode to show a QR code; until then, here's the password.", "yellow"))
        parts.append(ui.kv(kv, wrap=False))
        btns = [close]
        if pw and sh.get("qr"):
            btns.insert(0, ui.button("Hide" if self.show_pw else "Show", self.toggle_show, "", EYE, "Space u s"))
        pic = None
        if sh.get("qr"):
            pic = ui.picture(sh["qr"], 132)
            pic.set_size_request(132, 132)
            pic.add_css_class("tarang-qr")
        return ui.hero(pic, self.grow(ui.vbox(*parts, spacing=7)), ui.vbox(*btns, spacing=6), color="green")

    # ------------------------------------------------------------ hotspot
    def hotspot_status(self):
        code, out, err = util.run_full([self.hotspot, "status", "--json"], timeout=8)
        try:
            return json.loads(out) if code == 0 else {"error": (err or "").strip().splitlines()[-1:] or [""]}
        except ValueError:
            return {"error": [f"{os.path.basename(self.hotspot)} gave an answer tarang can't read"]}

    def hotspot_rows(self, q):
        st = self.hotspot_status()
        if st.get("error") is not None:
            msg = st["error"][0] if st["error"] else ""
            msg = msg.removeprefix("vayu-hotspot: ")
            st = {"failed": (msg[:1].upper() + msg[1:]) if msg else f"{self.hotspot} didn't answer"}
        elif st.get("ssid") and util.have("qrencode"):
            st["qr"] = qr_png(wifi_payload(st["ssid"], st.get("password", "")))
        st["wifi"] = (self.snap.get("active") or {}).get("ssid", "")
        self.hs = st
        GLib.idle_add(self.sync_switch)
        if st.get("failed"):
            self.empty_text = "The hotspot can't be used here"
            return []
        if self.editing:
            return [Section("Edit", "", "Enter saves · Esc cancels"), self.setting_rows(st)[0 if self.editing == "ssid" else 1]]
        rows = []
        if st.get("on"):
            devs = [c for c in st.get("clients", []) if not q or util.fuzzy(q, c.get("name") or "") is not None
                    or q in (c.get("ip") or "")]
            rows.append(Section("Connected devices", len(st.get("clients", [])), "on the hotspot now"))
            for c in devs:
                name = (c.get("name") or "").replace("-", " ") or "Unknown device"
                rows.append(Row(name, " · ".join(x for x in (c.get("ip"), c.get("mac")) if x), icon=PHONE,
                                color="green", chips=[("Joined", "green")], data={"kind": "client", **c}))
            if not st.get("clients"):
                rows.append(Row("No devices yet", "Scan the QR code with a phone camera to join", icon=PHONE,
                                color="gray", dim=True, data={"kind": "none"}))
        rows.append(Section("Settings", "", "read-only until Enter"))
        rows += self.setting_rows(st)
        return rows

    def setting_rows(self, st):
        pw = st.get("password", "")
        other = "2.4 GHz" if st.get("band") == "5 GHz" else "5 GHz"
        restart = "restarts the hotspot" if st.get("on") else "starts the hotspot"
        return [Row("Name", st.get("ssid") or "set when it first starts", icon=HOTSPOT, color="teal",
                    meta="e edit", data={"kind": "setting", "field": "ssid"}),
                Row("Password", (pw if self.show_pw else "•" * len(pw)) if pw else "generated when it first starts",
                    icon=KEY, color="teal", meta="Space u s show · e edit", data={"kind": "setting", "field": "password"}),
                Row("Band", st.get("band") or "2.4 GHz", icon=WIFI, color="teal",
                    meta=f"Enter: {other}", data={"kind": "setting", "field": "band", "other": other,
                                                  "restart": restart})]

    def hotspot_strip(self):
        st = self.hs
        if st is None:
            return None
        if st.get("failed"):
            return ui.hero(ui.ring(0, "red", 64, 6, ui.label(HOTSPOT, "glyph", "tarang-ring-glyph", "t-red")),
                           self.grow(ui.vbox(ui.hbox(ui.label("Hotspot unavailable", "hero-title"),
                                                     ui.chip("Unavailable", "red", ALERT), spacing=8),
                                             ui.label(st["failed"], "hero-sub", xalign=0, wrap=True), spacing=6)),
                           color="red")
        if self.hs_busy:
            what = {"starting": "Starting the hotspot", "stopping": "Stopping the hotspot",
                    "saving": "Saving and restarting the hotspot"}[self.hs_busy]
            return ui.hero(ui.ring(0.5, "yellow", 64, 6, ui.label(HOTSPOT, "glyph", "tarang-ring-glyph", "t-yellow")),
                           self.grow(ui.vbox(ui.hbox(ui.label(what + "…", "hero-title"),
                                                     ui.chip("Working…", "yellow"), spacing=8),
                                             ui.label("This takes a few seconds.", "hero-sub", xalign=0),
                                             spacing=6)), color="yellow")
        pw = st.get("password", "")
        pw_text = (pw if self.show_pw else "•" * min(len(pw), 14)) if pw else "—"
        error = ui.notice("Couldn't change the hotspot", self.hs_error, "red") if self.hs_error else None
        if self.editing:
            what = "name" if self.editing == "ssid" else "password"
            return ui.hero(self.grow(ui.vbox(ui.label(f"New hotspot {what}", "hero-title", xalign=0),
                                             ui.label(f"Type it in the box above; Enter saves it and "
                                                      f"{'restarts' if st.get('on') else 'starts'} the hotspot, "
                                                      "Esc cancels." + (" At least 8 characters."
                                                                        if self.editing == "password" else ""),
                                                      "hero-sub", xalign=0, wrap=True),
                                             ui.label(self.edit_error, "hero-sub", "t-red", xalign=0, wrap=True)
                                             if self.edit_error else None, spacing=6)),
                           ui.button("Save", self.submit_edit, "primary", CHECK, "Enter"),
                           color="red" if self.edit_error else "yellow")
        if st.get("on"):
            share = st.get("internet")
            kv = [("Password", pw_text), ("Band", st.get("band") or "—"),
                  ("Sharing", f"{share.split(' (')[0]} → Wi-Fi" if share else "nothing: no internet to share"),
                  ("Devices", str(st.get("client_count", 0)))]
            parts = [ui.hbox(ui.label(st.get("ssid", ""), "hero-title"), ui.chip("Sharing", "green", HOTSPOT),
                             spacing=8),
                     ui.label("Scan the code with a phone camera to join. No typing needed." if st.get("qr") and
                              self.hs_qr else "Space c q shows a QR code phones scan to join." if st.get("qr") else
                              "Install qrencode for a QR code phones scan to join.",
                              "hero-sub", xalign=0, wrap=True, max_width_chars=34),
                     ui.kv(kv, wrap=False)]
            if not share:
                parts.append(ui.chip("No internet to share: plug in a cable or tether a phone", "yellow", ALERT))
            if error:
                parts.append(error)
            pic = None
            if st.get("qr") and self.hs_qr:
                # a fixed size (a Gtk.Picture grows to the QR file's own size, widening the panel)
                pic = Gtk.Image.new_from_file(st["qr"])
                pic.set_pixel_size(132)
                pic.set_valign(Gtk.Align.CENTER)
                pic.add_css_class("tarang-qr")
            return ui.hero(pic, self.grow(ui.vbox(*parts, spacing=7)),
                           ui.vbox(self.tip(ui.button("Turn off", self.toggle_hotspot, "", HOTSPOT), "Space p h"),
                                   self.tip(ui.button("Hide QR" if self.hs_qr else "Show QR", self.toggle_qr, "", QR),
                                            "Space c q"),
                                   self.tip(ui.button("Hide" if self.show_pw else "Show", self.toggle_show, "", EYE),
                                            "Space u s"),
                                   spacing=6),
                           color="green")
        notes = ["Share this laptop's internet over Wi-Fi: phones join it like any network."]
        parts = [ui.hbox(ui.label("Hotspot is off", "hero-title"), ui.chip("Off", "gray", HOTSPOT), spacing=8),
                 ui.label(notes[0], "hero-sub", xalign=0, wrap=True)]
        if st.get("wifi"):
            parts.append(ui.chip(f"Starting it drops your Wi-Fi ({st['wifi']}): the card hosts or joins, not both",
                                 "yellow", ALERT))
        elif not st.get("internet"):
            parts.append(ui.chip("No internet to share yet: plug in a cable or tether a phone", "yellow", ALERT))
        if error:
            parts.append(error)
        return ui.hero(ui.ring(0, "gray", 64, 6, ui.label(HOTSPOT, "glyph", "tarang-ring-glyph")),
                       self.grow(ui.vbox(*parts, spacing=7)),
                       ui.button("Turn on", self.toggle_hotspot, "primary", HOTSPOT, "Space p h"), color="gray")

    # ------------------------------------------------------------ preview
    def build_preview(self, row):
        self.live_w = None
        try:
            w = self.preview_for(row.data or {})
        except Exception:   # a preview must never take the panel down
            import logging
            logging.getLogger("vyom.tarang").exception("preview")
            return None
        self.update_live()
        return w

    def preview_for(self, d):
        kind = d.get("kind")
        if kind == "net" and d.get("active"):
            return self.dashboard(d)
        if kind == "net":
            return self.net_preview(d)
        if kind == "off":
            return self.off_preview()
        if self.tab == "hotspot" and (self.hs or {}).get("on"):
            rest = self.hotspot_detail(d)
            return ui.vbox(self.hotspot_live(), rest, spacing=16) if rest is not None else self.hotspot_live()
        return self.hotspot_detail(d)

    def hotspot_detail(self, d):
        kind = d.get("kind")
        if kind == "client":
            name = (d.get("name") or "").replace("-", " ") or "Unknown device"
            return ui.vbox(ui.hbox(bigtile(PHONE, "green"),
                                   ui.vbox(ui.title(name), ui.meta("On your hotspot now"), spacing=2), spacing=12),
                           ui.kv([("Address", d.get("ip") or "—"), ("MAC", d.get("mac") or "—")]),
                           ui.body("Names come from what the device told the hotspot when it joined."), spacing=14)
        if kind == "setting":
            f = d["field"]
            text = {"ssid": "The name phones see in their Wi-Fi list.",
                    "password": "What phones type to join (the QR code carries it too). At least 8 characters.",
                    "band": "2.4 GHz reaches further and every device sees it; 5 GHz is faster nearby, but some "
                            "Wi-Fi cards refuse to host on it."}[f]
            parts = [ui.title({"ssid": "Name", "password": "Password", "band": "Band"}[f]), ui.body(text)]
            if f == "band":
                cur = (self.hs or {}).get("band") or "2.4 GHz"
                parts.append(ui.segmented([("2.4 GHz", "2.4 GHz"), ("5 GHz", "5 GHz")], cur,
                                          lambda k: k != cur and self.set_band(k)))
                parts.append(ui.meta(f"Enter switches to {d['other']} ({d['restart']})."))
            else:
                parts.append(ui.notice("Read-only until you press Enter",
                                       "so stray typing changes nothing. Saving "
                                       + ("restarts" if (self.hs or {}).get("on") else "starts") + " the hotspot.",
                                       "gray", LOCK))
            return ui.vbox(*parts, spacing=12)
        return None

    # ------------------------------------------------------------ the live view
    def stat(self, key, arrow, name):
        """One big speed: an arrow and a word, the number and its unit, peak and average."""
        num = ui.label("0", "tarang-num", f"tarang-{key}", xalign=0, valign=Gtk.Align.BASELINE)
        unit = ui.label("B/s", "tarang-unit", xalign=0, valign=Gtk.Align.BASELINE)
        sub = ui.label("", "tarang-stat-sub", xalign=0, ellipsize=Pango.EllipsizeMode.END)
        head = ui.hbox(ui.label(arrow, "glyph", "tarang-arrow", f"tarang-{key}"), ui.label(name, "tarang-stat-name"),
                       spacing=5)
        box = ui.vbox(head, ui.hbox(num, unit, spacing=5), sub, spacing=2, cls="tarang-stat")
        box.add_css_class(f"tarang-stat-{key}")
        box.set_hexpand(True)
        return box, (num, unit, sub)

    def cell(self, key, value, wide=False):
        """A small fact: its name over its value (text or a widget)."""
        if isinstance(value, str):
            value = ui.label(value or "—", "tarang-cell-val", xalign=0, ellipsize=Pango.EllipsizeMode.MIDDLE)
            value.set_tooltip_text(value.get_label())
        box = ui.vbox(ui.label(key, "tarang-cell-key", xalign=0), value, spacing=3, cls="tarang-cell")
        box.set_hexpand(True)
        box.wide = wide
        return box

    def cells(self, items, per_row=2):
        """Facts `per_row` to a row; a wide one (an IPv6 address) gets its own row."""
        g = Gtk.Grid(column_spacing=8, row_spacing=8, column_homogeneous=True)
        r = c = 0
        for it in items:
            if it is None:
                continue
            if it.wide:
                if c:
                    r, c = r + 1, 0
                g.attach(it, 0, r, per_row, 1)
                r += 1
                continue
            g.attach(it, c, r, 1, 1)
            c += 1
            if c == per_row:
                r, c = r + 1, 0
        return g

    def live_block(self, labels=("Download", "Upload"), short=("Down", "Up")):
        """The two speeds over the minute's graph; their widgets go in self.live_w."""
        rx, rx_w = self.stat("rx", DOWN, labels[0])
        tx, tx_w = self.stat("tx", UP, labels[1])
        graph = live.Graph(self.traffic, labels=short)
        self.live_w = {"rx": rx_w, "tx": tx_w, "graph": graph}
        return ui.vbox(ui.hbox(rx, tx, spacing=10, cls="tarang-stats"),
                       ui.vbox(graph, cls="tarang-graph-card"), spacing=10)

    def dashboard(self, a):
        """The network you're on: live speeds, the minute's graph, totals, the
        signal and every address, at a glance."""
        s = self.snap
        lv, word, lcolor, note = quality(a["signal"])
        sname, scolor, sword, skind = security(a["security"])
        since = s.get("since")
        head = ui.hbox(ui.label("\u25CF", "tarang-live-dot"), ui.label("LIVE", "tarang-live"),
                       ui.label(a["ssid"], "tarang-dash-ssid", xalign=0, hexpand=True,
                                ellipsize=Pango.EllipsizeMode.END), spacing=6)
        block = self.live_block()
        if since:
            dur = ui.label(live.duration_text(time.time() - since), "tarang-since")
            at = time.strftime("%H:%M" if time.time() - since < 86400 else "%d %b %H:%M", time.localtime(since))
            clock = ui.hbox(ui.label(CLOCK, "glyph", "tarang-since-icon"), dur,
                            ui.label(f"since {at}", "tarang-since-at"), spacing=5)
            clock.set_tooltip_text(f"Connected at {at}")
            head.append(clock)
            self.live_w.update({"since": dur, "since_ts": since})
        # received, sent and the signal side by side
        got = ui.label("", "tarang-cell-val", "tarang-rx", xalign=0)
        sent = ui.label("", "tarang-cell-val", "tarang-tx", xalign=0)
        spark = live.Spark(self.traffic, lcolor)
        dbm = ui.label("", "tarang-dbm", xalign=1, hexpand=True)
        sig = ui.vbox(ui.hbox(ui.label("Signal", "tarang-cell-key", xalign=0), dbm, spacing=6),
                      ui.label(f"{word} · {a['signal']}%", "tarang-sig-word", f"t-{lcolor}", xalign=0), spacing=3,
                      cls="tarang-cell")
        sig.append(spark)
        sig.set_tooltip_text(note)
        sig.set_hexpand(True)
        self.live_w.update({"total_rx": got, "total_tx": sent, "spark": spark, "dbm": dbm})
        trow = Gtk.Box(spacing=8, homogeneous=True)
        for c in (self.cell("Received", got), self.cell("Sent", sent), sig):
            trow.append(c)
        trow.set_tooltip_text("Received and sent: since the Wi-Fi card came up")
        internet = INTERNET.get(s.get("internet") or "unknown", INTERNET["unknown"])
        link = s.get("link") or {}
        if link.get("rx_rate") or link.get("tx_rate"):
            linktext = f"↓ {link.get('rx_rate', 0):.0f} ↑ {link.get('tx_rate', 0):.0f} Mb/s"
        else:
            linktext = rate(a.get("rate")) or "—"
        mhz = (a.get("freq") or "").replace(" MHz", "")
        bandcell = self.cell("Band", f"{band(a['freq'])} · ch {a['chan']}")
        if mhz:
            bandcell.set_tooltip_text(f"{mhz} MHz")
        facts = [self.cell("Internet", ui.chip(*internet)),
                 self.cell("Security", ui.chip(f"{sname} · {sword}", scolor, SHIELD if skind in ("strong", "ok")
                                               else LOCK_OPEN if skind == "open" else ALERT)),
                 bandcell,
                 self.cell("IP address", s.get("ip") or "—"),
                 self.cell("Router", s.get("gateway") or "—"),
                 self.cell("Link rate", linktext),
                 self.cell("DNS", s.get("dns") or "—", wide=False),
                 self.cell("Access point", a.get("bssid") or "—"),
                 self.cell("IPv6", s.get("ip6") or "none")]
        parts = [head, block, trow, self.cells(facts, 3)]
        if s.get("internet") in ("limited", "none"):
            parts.append(ui.notice("Joined, but no internet", "The router answers, but nothing gets past it: restart "
                                   "the router, or check the line.", "yellow" if s.get("internet") == "limited"
                                   else "red"))
        if s.get("internet") == "portal":
            parts.append(ui.notice("Sign in to use the internet", "This network shows a sign-in page first: open any "
                                   "website in a browser to get it.", "peach", LOGIN))
        if a.get("metered") in ("yes", "guess-yes"):
            parts.append(ui.notice("Metered", "This network counts against a data plan: big downloads cost.", "yellow"))
        return ui.vbox(*parts, spacing=10, cls="tarang-dash")

    def hotspot_live(self):
        """The hotspot's own traffic: what the devices on it send and get."""
        st = self.hs or {}
        n = st.get("client_count", len(st.get("clients", [])))
        head = ui.hbox(ui.label("\u25CF", "tarang-live-dot"), ui.label("LIVE", "tarang-live"),
                       ui.label(st.get("ssid", "Hotspot"), "tarang-dash-ssid", xalign=0, hexpand=True,
                                ellipsize=Pango.EllipsizeMode.END),
                       ui.chip(f"{n} device{'s' if n != 1 else ''}", "green" if n else "gray", PHONE), spacing=6)
        block = self.live_block(("From devices", "To devices"), ("From", "To"))
        totals = [self.cell("Received", ui.label("", "tarang-cell-val", "tarang-rx", xalign=0)),
                  self.cell("Sent", ui.label("", "tarang-cell-val", "tarang-tx", xalign=0)),
                  self.cell("Sharing", (st.get("internet") or "no internet").split(" (")[0])]
        self.live_w["total_rx"] = totals[0].get_last_child()
        self.live_w["total_tx"] = totals[1].get_last_child()
        trow = Gtk.Box(spacing=8, homogeneous=True)
        for c in totals:
            trow.append(c)
        return ui.vbox(head, block, trow, spacing=12, cls="tarang-dash")

    def off_preview(self):
        s = self.snap
        parts = [ui.hbox(bigtile(WIFI_OFF, "gray"),
                         ui.vbox(ui.title("Wi-Fi is off"), ui.meta("The card is off: no scanning, no networks."),
                                 spacing=2), spacing=12)]
        if s.get("wired"):
            parts.append(ui.notice(f"You're online over Ethernet ({s['wired']})",
                                   "Wi-Fi isn't needed while the cable is in.", "green", ETHERNET))
        else:
            parts.append(ui.notice("You're offline", "Nothing else connects this laptop right now.", "gray", LINK_OFF))
        parts.append(ui.buttons([("Turn Wi-Fi on", lambda: self.set_radio(True), "primary", WIFI, "Enter")]))
        parts.append(ui.meta("Space p p turns it on or off from anywhere in the panel."))
        return ui.vbox(*parts, spacing=14)

    def net_preview(self, d):
        lv, word, lcolor, note = quality(d["signal"])
        sname, scolor, sword, skind = security(d["security"])
        state = ("Saved" + (f" · {ago(d['ts'])}" if ago(d["ts"]) else "")) if d["saved"] \
            else "New: you haven't joined it"
        parts = [ui.hbox(bigtile(WIFI, "sky" if d["saved"] else "gray"),
                         ui.vbox(ui.title(d["ssid"]), ui.meta(state), spacing=2), spacing=12)]
        # the signal, and how it compares with the network you're on
        cur = self.snap.get("active")
        cmp = ""
        if cur and cur["ssid"] != d["ssid"]:
            diff = int(d["signal"] or 0) - int(cur["signal"] or 0)
            cmp = (f"{abs(diff)} points {'stronger' if diff > 0 else 'weaker'} than {cur['ssid']} ({cur['signal']}%)"
                   if diff else f"as strong as {cur['ssid']}")
        sig = ui.vbox(ui.hbox(ui.label("Signal", "tarang-cell-key", xalign=0, hexpand=True),
                              ui.label(f"{word} · {d['signal']}%", "tarang-sig-word", f"t-{lcolor}"), spacing=6),
                      ui.progress(int(d["signal"] or 0) / 100, lcolor),
                      ui.label(cmp or note, "tarang-note", xalign=0, wrap=True), spacing=6, cls="tarang-cell")
        parts.append(sig)
        mhz = (d.get("freq") or "").replace(" MHz", "")
        facts = [self.cell("Security", ui.chip(f"{sname} · {sword}", scolor, SHIELD if skind in ("strong", "ok") else
                                               LOCK_OPEN if skind == "open" else ALERT if skind == "weak" else LOCK)),
                 self.cell("Band", f"{band(d['freq'])} · ch {d['chan']}"),
                 self.cell("Frequency", f"{mhz} MHz" if mhz else "—"),
                 self.cell("Up to", rate(d.get("rate")) or "—"),
                 self.cell("Saved", "yes" if d["saved"] else "no"),
                 self.cell("Access point", d["bssid"] or "—")]
        if d.get("metered") in ("yes", "guess-yes"):
            metered = self.cell("Metered", ui.chip("Yes", "yellow"))
            metered.set_tooltip_text("It counts against a data plan")
            facts.append(metered)
        parts.append(self.cells(facts, 3))
        if skind == "open":
            parts.append(ui.notice("Open network", "Anyone nearby can read unencrypted traffic. Prefer https "
                                   "sites or a VPN here.", "yellow"))
        elif skind == "weak":
            parts.append(ui.notice(f"Weak security ({sname})", "It can be broken in minutes: avoid anything "
                                   "private on it.", "red"))
        elif skind == "enterprise" and not d["saved"]:
            parts.append(ui.notice("Asks for a user name", "WPA Enterprise needs a user name and certificate: "
                                   "set it up once with nm-connection-editor.", "yellow"))
        c = self.conn
        if c and c["ssid"] == d["ssid"]:
            if c["state"] == "failed" and not c.get("nosteps"):
                parts.append(ui.notice(f"Couldn't join {d['ssid']}", c["why"], "red"))
            elif c["state"] == "now":
                parts.append(ui.steps(self.step_items()))
        btns = []
        if d["active"]:
            btns.append(("Disconnect", self.disconnect, "danger", LINK_OFF, "Space c d"))
        elif not (skind == "enterprise" and not d["saved"]):
            btns.append(("Connect", lambda: self.connect(d), "primary", LOGIN, "Enter"))
        if d["saved"]:
            btns.append(("Forget", lambda: self.forget(d), "danger", DELETE, "d d"))
        if btns:
            parts.append(ui.buttons(btns))
        return ui.vbox(*parts, spacing=14)

    # ------------------------------------------------------------ connecting
    def connect(self, n, password=None):
        if n.get("active") or (self.conn and self.conn["state"] == "now"):
            return
        ssid = n["ssid"]
        _s, _c, _w, kind = security(n["security"])
        last_failed = self.conn and self.conn["ssid"] == ssid and self.conn["state"] == "failed" \
            and self.conn.get("wrong_pw")
        if password is None and (kind not in ("open", "enterprise")) and (not n.get("conn") or last_failed):
            self.ask_password(n)
            return
        if kind == "enterprise" and not n.get("conn"):
            self.conn = {"ssid": ssid, "step": 0, "state": "failed", "nosteps": True,
                         "why": why("802.1x", 1)}
            self.after_change()
            return
        dev = self.snap.get("dev")
        if n.get("conn") and password is not None:
            cmds = [["nmcli", "connection", "modify", "uuid", n["conn"], "802-11-wireless-security.psk", password],
                    ["nmcli", "connection", "up", "uuid", n["conn"]]]
        elif n.get("conn"):
            cmds = [["nmcli", "connection", "up", "uuid", n["conn"]]]
        else:
            cmds = [["nmcli", "device", "wifi", "connect", ssid] + (["password", password] if password else [])
                    + (["ifname", dev] if dev else [])]
        self.sharing = None
        self.conn = {"ssid": ssid, "step": 0, "state": "now", "why": "", "net": n}
        self.ask_error = ""
        self.after_change()
        threading.Thread(target=self.connect_worker, args=(cmds, dev, self.conn), daemon=True).start()

    def connect_worker(self, cmds, dev, conn):
        """Runs nmcli and watches the device's state for the steps."""
        code, err = 0, ""
        for cmd in cmds:
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=ENV)
            except OSError as e:
                code, err = 127, str(e)
                break
            start = time.time()
            while p.poll() is None:
                if time.time() - start > 60:
                    p.kill()
                    code = 124
                    break
                if dev:
                    st = util.run(["nmcli", "-g", "GENERAL.STATE", "device", "show", dev], timeout=2)[1]
                    m = re.match(r"(\d+)", st)
                    if m:
                        s = int(m.group(1))
                        step = 0 if s < 60 else 1 if s == 60 else 2 if s < 100 else 2
                        if step > conn["step"]:
                            GLib.idle_add(self.set_step, conn, step)
                time.sleep(0.4)
            out, e = p.communicate()
            code = code or p.returncode
            err = (e or "") + ("\n" + out if code and out else "")
            if code:
                break
        GLib.idle_add(self.connect_done, conn, code, err)

    def set_step(self, conn, step):
        if conn is self.conn and conn["state"] == "now":
            conn["step"] = max(conn["step"], step)
            self.after_change(list_too=False)
        return False

    def connect_done(self, conn, code, err):
        if conn is not self.conn:
            return False
        visible = self.panel and self.panel.get_visible()
        if code == 0:
            conn["state"] = "done"
            if visible and not self.asking:
                self.panel.entry.set_text("")   # the filter that found it has done its job
            if not visible:
                util.notify("Wi-Fi", f"Connected to {conn['ssid']}", icon="network-wireless")
            self.conn = None
        else:
            conn["state"] = "failed"
            conn["why"] = why(err, code)
            conn["wrong_pw"] = conn["why"].startswith("Wrong password")
            if not visible:
                util.notify("Wi-Fi", f"Couldn't join {conn['ssid']}", conn["why"], icon="network-wireless-offline")
            elif conn["wrong_pw"] and conn.get("net") and not self.asking:
                # Straight back to the password, with why in red.
                self.ask_password(conn["net"], error=conn["why"])
                return False
        self.after_change()
        return False

    def after_change(self, list_too=True):
        if not self.panel:
            return
        self.panel.refresh_strip()
        self.panel.update_preview_soon()
        if list_too:
            self.refresh()

    # ------------------------------------------------------------ the search box as a field
    def ask_password(self, n, error=""):
        self.asking = n
        self.ask_error = error
        self.show_pw = False
        e = self.panel.entry
        e.set_text("")
        e.set_visibility(False)
        e.set_placeholder_text(f"Password for {n['ssid']}")
        self.set_vim_mode("insert")
        self.after_change()

    def edit_field(self, field):
        st = self.hs or {}
        self.editing = field
        self.edit_error = ""
        e = self.panel.entry
        e.set_visibility(field != "password" or self.show_pw)
        e.set_placeholder_text("New hotspot name" if field == "ssid" else "New hotspot password (8+ characters)")
        e.set_text(st.get(field, "") if field == "ssid" else "")
        self.set_vim_mode("insert")
        e.set_position(-1)
        self.after_change()

    def cancel_entry(self):
        if (self.asking or self.editing) and self.panel:
            e = self.panel.entry
            e.set_visibility(True)
            e.set_placeholder_text(self.placeholder)
            e.set_text("")
            self.asking = self.editing = None
            self.set_vim_mode("normal")
        self.asking = self.editing = None

    def submit_password(self):
        n = self.asking
        if not n:
            return
        pw = self.panel.entry.get_text()
        if not pw or (len(pw) < 8 and security(n["security"])[3] != "weak"):
            self.ask_error = "Type the password first." if not pw else \
                "Too short: Wi-Fi passwords are at least 8 characters."
            self.after_change(list_too=False)
            return
        self.cancel_entry()
        self.connect(n, password=pw)

    def submit_edit(self):
        f = self.editing
        val = self.panel.entry.get_text()
        bad = "Too short: the password needs at least 8 characters." if f == "password" and len(val) < 8 else \
            "A name is 1 to 32 characters." if f == "ssid" and not (0 < len(val.encode()) <= 32) else ""
        if bad:
            self.edit_error = bad
            self.after_change(list_too=False)
            return
        self.cancel_entry()
        self.hotspot_on(["--ssid" if f == "ssid" else "--password", val], "saving")

    def toggle_show(self):
        self.show_pw = not self.show_pw
        if self.asking or self.editing == "password":
            self.panel.entry.set_visibility(self.show_pw)
        self.after_change(list_too=self.tab == "hotspot")

    # ------------------------------------------------------------ actions
    def disconnect(self):
        dev = self.snap.get("dev")
        if not dev or not self.snap.get("active"):
            self.set_status("not connected to a Wi-Fi network")
            return
        self.sharing = None
        self.set_status(f"disconnecting from {self.snap['active']['ssid']}…")
        self.background(lambda: util.run(["nmcli", "device", "disconnect", dev], timeout=15),
                        lambda _r: (self.set_status(""), self.refresh()))

    def forget(self, n):
        """Asks first (y forgets, any other key keeps it): its saved password goes too."""
        if not n.get("conn"):
            self.set_status(f"{n['ssid']} isn't saved", "bad")
            return

        def go():
            self.ssid_cache.pop(n["conn"], None)

            def done(r):
                code = r[0] if isinstance(r, tuple) else 1
                self.set_status(f"forgot {n['ssid']}" if code == 0 else f"couldn't forget {n['ssid']}",
                                "ok" if code == 0 else "bad")
                self.refresh()
            self.background(lambda: util.run(["nmcli", "connection", "delete", "uuid", n["conn"]]), done)
        self.confirm(f"Forget {n['ssid']}? Its saved password goes too; this can't be undone.", go)

    def share(self):
        a = self.snap.get("active")
        if not a:
            self.set_status("not connected: nothing to share")
            return
        if self.sharing:
            self.stop_sharing()
            return
        self.sharing = {"ssid": a["ssid"], "loading": True}
        self.show_pw = False
        sh = self.sharing

        def work():
            pw = ""
            if security(a["security"])[3] != "open":
                if a.get("conn"):
                    pw = util.run(["nmcli", "-s", "-g", "802-11-wireless-security.psk", "connection", "show",
                                   "uuid", a["conn"]])[1]
                if not pw:
                    out = util.run(["nmcli", "device", "wifi", "show-password"] +
                                   (["ifname", self.snap["dev"]] if self.snap.get("dev") else []))[1]
                    m = re.search(r"^Password:\s*(.*)$", out, re.M)
                    pw = m.group(1).strip() if m else ""
                if not pw:
                    return {"error": "NetworkManager didn't give out the password (it may be kept in a keyring "
                                     "only you can unlock, or be a WPA Enterprise login)."}
            kind = "SAE" if security(a["security"])[0] == "WPA3" else "WPA"
            return {"password": pw, "qr": qr_png(wifi_payload(a["ssid"], pw, kind))}

        def done(r):
            if self.sharing is sh:
                sh.pop("loading", None)
                sh.update(r if isinstance(r, dict) else {"error": str(r)})
                self.after_change(list_too=False)
        self.after_change(list_too=False)
        self.background(work, done)

    def stop_sharing(self):
        self.sharing = None
        self.show_pw = False
        self.after_change(list_too=False)

    def toggle_qr(self):
        self.hs_qr = not self.hs_qr
        self.after_change(list_too=False)

    def toggle_hotspot(self):
        st = self.hs or {}
        if self.hs_busy or st.get("failed"):
            return
        if st.get("on"):
            self.hs_busy, self.hs_error = "stopping", ""
            self.after_change(list_too=False)
            self.background(lambda: util.run_full([self.hotspot, "off"], timeout=40), self.hotspot_done)
        else:
            self.hotspot_on([], "starting")

    def set_band(self, text):
        self.hotspot_on(["--band", "a" if text.startswith("5") else "bg"], "saving")

    def hotspot_on(self, extra, busy):
        self.hs_busy, self.hs_error = busy, ""
        self.after_change(list_too=False)
        self.background(lambda: util.run_full([self.hotspot, "on"] + extra, timeout=60), self.hotspot_done)

    def hotspot_done(self, r):
        code, _out, err = r if isinstance(r, tuple) else (1, "", str(r))
        self.hs_busy = ""
        if code:
            last = [l for l in (err or "").splitlines() if l.strip()]
            self.hs_error = (last[-1].removeprefix("vayu-hotspot: ") if last else f"it stopped with exit {code}")
        self.after_change()

    def activate(self, row, mods):
        d = row.data or {}
        kind = d.get("kind")
        if self.asking:
            self.submit_password()
        elif self.editing:
            self.submit_edit()
        elif kind == "net":
            self.connect(d)
        elif kind == "off":
            self.set_radio(True)
        elif kind == "setting":
            if d["field"] == "band":
                self.set_band(d["other"])
            else:
                self.edit_field(d["field"])
        return False

    def key(self, name, row, mods):
        if name == "Escape":
            if self.asking or self.editing:
                self.cancel_entry()
                self.after_change()
                return True
            if self.sharing:
                self.stop_sharing()
                return True
            if self.conn and self.conn["state"] == "failed":
                self.conn = None
                self.after_change()
                return True
            return False
        if self.asking or self.editing:
            # Typing a field: Enter submits, Ctrl+S shows it; no tab switching or other actions,
            # but the box's own editing chords (paste a password, delete a word) still work.
            if name in ("Tab", "ISO_Left_Tab") or (mods == {"ctrl"} and name != "s" and name not in EDIT_CHORDS):
                return True
        return False

    # ------------------------------------------------------------ vim keys
    def keys(self, tab):
        return vim.keys(tab)

    def selected(self):
        row = self.panel.selected_row() if self.panel else None
        return (row.data or {}) if row is not None else {}

    def v_radio(self, _n, _a):
        self.set_radio(not self.snap.get("radio"))

    def v_hotspot(self, _n, _a):
        if not self.tabs:
            self.set_status("no hotspot command here (vayu-hotspot)", "bad")
            return
        if self.hs is None:
            self.select_tab("hotspot")   # reads its state first; Space p h again toggles it
            return
        self.toggle_hotspot()

    def v_share(self, _n, _a):
        if self.tab == "hotspot":
            self.toggle_qr()
        else:
            self.share()

    def v_showpw(self, _n, _a):
        self.toggle_show()

    def v_rescan(self, _n, _a):
        self.rescan()
        self.refresh()

    def v_refresh(self, n, a):
        self.v_rescan(n, a)

    def v_disconnect(self, _n, _a):
        self.disconnect()

    def v_forget(self, _n, _a):
        d = self.selected()
        if d.get("kind") != "net":
            self.set_status("no network selected", "bad")
            return
        self.forget(d)

    def v_copy(self, _n, what):
        if self.tab == "hotspot":
            st = self.hs or {}
            text = st.get(what if what == "ssid" else "password", "")
            self.done_copy(text, what)
            return
        d = self.selected()
        n = d if d.get("kind") == "net" else self.snap.get("active") or {}
        if not n:
            self.set_status("no network selected", "bad")
            return
        if what == "ssid":
            self.done_copy(n.get("ssid", ""), what)
            return
        if not n.get("conn"):
            self.set_status(f"{n.get('ssid', 'it')} isn't saved: no password to copy", "bad")
            return
        self.background(lambda: util.run(["nmcli", "-s", "-g", "802-11-wireless-security.psk", "connection", "show",
                                          "uuid", n["conn"]])[1].strip(),
                        lambda pw: self.done_copy(pw if isinstance(pw, str) else "", what))

    def done_copy(self, text, what):
        if not text:
            self.set_status(f"no {'name' if what == 'ssid' else 'password'} to copy", "bad")
            return
        util.copy(text)
        self.set_status("copied the name" if what == "ssid" else "copied the password", "ok")

    def closed(self):
        self.cancel_entry()
        self.sharing = None
        self.show_pw = False
