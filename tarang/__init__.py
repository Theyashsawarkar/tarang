"""tarang (तरंग, "wave"): Wi-Fi for Vyom, through NetworkManager.

Networks with their signal (rescanned every few seconds while open),
the one you're on and the saved ones first. Enter connects; a secured
network you haven't joined asks for its password right in the search
box. A Hotspot tab drives vayu-hotspot (or any command with its
`status --json` / `on` / `off` interface) when it's installed.
"""
import json
import os
import re
import time

from gi.repository import GLib, Gtk

from vyom import Hint, Row, Section, ui, util
from vyom import Plugin as Base

# keybind: Vyom/wifi | Enter | Connect to the selected network (asks for its password if needed)
# keybind: Vyom/wifi | Ctrl+D | Disconnect from the current network
# keybind: Vyom/wifi | Ctrl+F | Forget the selected saved network
# keybind: Vyom/wifi | Ctrl+R | Rescan for networks
# keybind: Vyom/wifi | Ctrl+W | Turn Wi-Fi on or off

BARS = ["\U000f092f", "\U000f091f", "\U000f0922", "\U000f0925", "\U000f0928"]  # wifi strength 0..4
LOCK = "\U000f033e"


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


def bars(signal):
    return BARS[min(4, max(0, (int(signal or 0) + 10) // 22))]


class Plugin(Base):
    name, title, icon, color = "tarang", "Wi-Fi", "\U000f05a9", "sky"
    placeholder = "Filter networks…"
    preview = True
    preview_width = 290
    live = 4
    hints = [Hint("Enter", "connect"), Hint("Ctrl+D", "disconnect"), Hint("Ctrl+F", "forget"), Hint("Ctrl+R", "rescan")]

    def __init__(self, vyom, conf):
        super().__init__(vyom, conf)
        self.tab = "networks"
        self.asking = None          # SSID whose password is being typed
        self.last_scan = 0
        self.hotspot = util.expand(self.conf.get("hotspot_command", "vayu-hotspot"))
        self.switch = None
        # Networks / Hotspot tabs (Ctrl+H/L, Ctrl+1/2: Vyom), when there's a hotspot command.
        self.tabs = [("networks", "Networks"), ("hotspot", "Hotspot")] if util.have(self.hotspot) else []

    def wifi_device(self):
        code, out = util.run("nmcli -t -f DEVICE,TYPE device")
        return next((fields(l)[0] for l in out.splitlines() if fields(l)[1:2] == ["wifi"]), None)

    def available(self):
        return (self.wifi_device() is not None, "no Wi-Fi device")

    # ------------------------------------------------------------ header
    def header_extra(self):
        box = Gtk.Box(spacing=8)
        self.switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.switch.set_can_focus(False)
        self.switch.set_tooltip_text("Wi-Fi on/off (Ctrl+W)")
        self.switch_handler = self.switch.connect("state-set", lambda _s, on: (self.set_radio(on), False)[1])
        box.append(self.switch)
        return box

    def tab_changed(self, key):
        self.cancel_password()
        self.refresh()

    def set_radio(self, on):
        self.background(lambda: util.run(["nmcli", "radio", "wifi", "on" if on else "off"]),
                        lambda _r: self.refresh())

    def opened(self, args):
        super().opened(args)
        self.cancel_password()
        if self.tabs:
            self.select_tab("hotspot" if args and args[0] == "hotspot" else "networks")

    # ------------------------------------------------------------ data
    def search(self, q):
        if self.asking:
            return [Row(f"Password for {self.asking}", "Enter connects · Esc cancels", icon=LOCK, color="sky",
                        data={"kind": "asking"})]
        radio = util.run("nmcli radio wifi")[1] == "enabled"
        GLib.idle_add(self.sync_switch, radio)
        if self.tab == "hotspot":
            return self.hotspot_rows()
        if not radio:
            return [Row("Wi-Fi is off", "Ctrl+W or the switch turns it on", icon="\U000f05aa", color="red",
                        data={"kind": "radio-off"})]
        if time.time() - self.last_scan > 12:   # a fresh scan now and then, in the background
            self.last_scan = time.time()
            util.spawn(["nmcli", "device", "wifi", "rescan"])
        saved = self.saved()
        nets = {}
        _, out = util.run("nmcli -t -f IN-USE,SSID,SECURITY,SIGNAL,FREQ,CHAN,BSSID device wifi list --rescan no")
        for line in out.splitlines():
            f = fields(line)
            if len(f) < 7 or not f[1]:
                continue
            inuse, ssid, sec, sig, freq, chan, bssid = f[:7]
            n = nets.get(ssid)
            if n is None or int(sig or 0) > int(n["signal"] or 0) or inuse == "*":
                nets[ssid] = {"ssid": ssid, "security": sec, "signal": sig, "freq": freq, "chan": chan,
                              "bssid": bssid, "active": inuse == "*" or (n or {}).get("active", False),
                              "saved": ssid in saved, "conn": saved.get(ssid)}
        rows, active, known, other = [], [], [], []
        wired = self.wired()
        if wired:
            rows.append(Row(f"Ethernet · {wired}", "wired connection in use", icon="\U000f0200", color="green",
                            data={"kind": "wired"}))
        for n in sorted(nets.values(), key=lambda n: -int(n["signal"] or 0)):
            if q and util.fuzzy(q, n["ssid"]) is None:
                continue
            (active if n["active"] else known if n["saved"] else other).append(self.net_row(n))
        for title, group in (("Connected", active), ("Saved", known), ("Nearby", other)):
            if group:
                rows.append(Section(title))
                rows += group
        return rows

    def net_row(self, n):
        ghz = "5 GHz" if n["freq"].startswith("5") else "6 GHz" if n["freq"].startswith("6") else "2.4 GHz"
        sub = " · ".join(x for x in ("Connected" if n["active"] else "Saved" if n["saved"] else "",
                                     n["security"] or "Open", ghz) if x)
        return Row(n["ssid"], sub, icon=bars(n["signal"]), color="sky" if n["active"] else "gray",
                   meta=(LOCK + " " if n["security"] else "") + f"{n['signal']}%", data={"kind": "net", **n})

    def saved(self):
        """SSID -> saved connection name."""
        _, out = util.run("nmcli -t -f NAME,TYPE connection show")
        res = {}
        for line in out.splitlines():
            f = fields(line)
            if len(f) >= 2 and f[1] == "802-11-wireless" and f[0] != "Vayu Hotspot":
                ssid = util.run(["nmcli", "-g", "802-11-wireless.ssid", "connection", "show", f[0]])[1] or f[0]
                res[ssid] = f[0]
        return res

    def wired(self):
        _, out = util.run("nmcli -t -f TYPE,STATE,CONNECTION device")
        return next((fields(l)[2] for l in out.splitlines() if fields(l)[:2] == ["ethernet", "connected"]), "")

    # ------------------------------------------------------------ hotspot
    def hotspot_status(self):
        code, out = util.run([self.hotspot, "status", "--json"], timeout=8)
        try:
            return json.loads(out) if code == 0 else None
        except ValueError:
            return None

    def hotspot_rows(self):
        st = self.hotspot_status()
        if not st:
            return [Row("Hotspot unavailable", f"{self.hotspot} didn't answer", icon="\U000f0003", color="red",
                        data={"kind": "none"})]
        rows = [Row("Hotspot is on" if st["on"] else "Hotspot is off",
                    f"sharing {st['internet']}" if st["on"] and st.get("internet") else
                    "Enter starts it" if not st["on"] else "no internet to share",
                    icon="\U000f0003", color="teal" if st["on"] else "gray", meta="Enter " + ("stop" if st["on"] else "start"),
                    data={"kind": "hotspot-toggle", "st": st})]
        if st.get("ssid"):
            rows.append(Row(st["ssid"], "network name", icon="\U000f05a9", color="gray", meta="Enter copy",
                            data={"kind": "copy", "text": st["ssid"], "st": st}))
            rows.append(Row(st.get("password", ""), "password", icon=LOCK, color="gray", meta="Enter copy",
                            data={"kind": "copy", "text": st.get("password", ""), "st": st}))
        if st["on"]:
            rows.append(Section(f"Connected · {st.get('client_count', 0)}"))
            for c in st.get("clients", []):
                rows.append(Row(c.get("name") or "unknown device", f"{c.get('ip', '')} · {c.get('mac', '')}",
                                icon="\U000f011c", color="teal", data={"kind": "client", "st": st}))
        return rows

    def qr(self, st):
        path = os.path.join(util.CACHE, "tarang-qr.png")
        if not util.have("qrencode"):
            return None
        os.makedirs(util.CACHE, exist_ok=True)
        esc = lambda s: re.sub(r'([\;,:"])', r"\\\1", s)
        util.run(["qrencode", "-o", path, "-s", "6", "-m", "2",
                  f"WIFI:T:WPA;S:{esc(st['ssid'])};P:{esc(st.get('password', ''))};;"])
        return path if os.path.exists(path) else None

    # ------------------------------------------------------------ preview
    def build_preview(self, row):
        d = row.data or {}
        kind = d.get("kind")
        if kind == "net":
            parts = [ui.hbox(ui.label(bars(d["signal"]), "tarang-big"),
                             ui.vbox(ui.title(d["ssid"]), ui.meta("Connected" if d["active"] else
                                                                  "Saved" if d["saved"] else "Not saved"), spacing=2),
                             spacing=12),
                     ui.kv([("Signal", f"{d['signal']}%"), ("Security", d["security"] or "Open"),
                            ("Frequency", d["freq"]), ("Channel", d["chan"]), ("BSSID", d["bssid"])])]
            if d["active"]:
                dev = self.wifi_device()
                ip = util.run(["nmcli", "-g", "IP4.ADDRESS", "device", "show", dev])[1].split("|")[0] if dev else ""
                if ip:
                    parts.append(ui.kv([("Address", ip)]))
                parts.append(ui.buttons([("Disconnect", self.disconnect, "danger")]))
            else:
                btns = [("Connect", lambda: self.connect(d), "primary")]
                if d["saved"]:
                    btns.append(("Forget", lambda: self.forget(d), "danger"))
                parts.append(ui.buttons(btns))
            return ui.vbox(*parts, spacing=12)
        if kind in ("hotspot-toggle", "copy", "client"):
            st = d["st"]
            parts = [ui.title("Hotspot"), ui.meta(f"{st.get('band', '')} · {st.get('device', '')}")]
            qr = self.qr(st) if st.get("ssid") else None
            if qr:
                pic = ui.picture(qr, 170)
                parts.append(pic)
                parts.append(ui.meta("Scan with a phone's camera to join"))
            parts.append(ui.kv([("Name", st.get("ssid", "")), ("Password", st.get("password", "")),
                                ("Internet", st.get("internet") or "none")]))
            parts.append(ui.buttons([("Stop" if st["on"] else "Start", self.toggle_hotspot,
                                      "danger" if st["on"] else "primary")]))
            return ui.vbox(*parts, spacing=10)
        if kind == "wired":
            return ui.vbox(ui.title("Ethernet"), ui.body("You're on a wired connection; Wi-Fi networks are below."))
        return None

    # ------------------------------------------------------------ actions
    def connect(self, n, password=None):
        ssid = n["ssid"]
        if n.get("conn") and password is None:
            cmd = ["nmcli", "connection", "up", "id", n["conn"]]
        elif n["security"] and password is None:
            self.ask_password(ssid)
            return
        else:
            cmd = ["nmcli", "device", "wifi", "connect", ssid] + (["password", password] if password else [])
        self.set_status(f"connecting to {ssid}…")

        def done(r):
            code, out = r if isinstance(r, tuple) else (1, str(r))
            self.set_status("")
            if code == 0:
                util.notify("Wi-Fi", f"Connected to {ssid}", icon="network-wireless")
                self.close()
            else:
                self.set_status(f"couldn't connect to {ssid}")
                util.notify("Wi-Fi", f"Couldn't connect to {ssid}", icon="network-wireless-offline")
                self.refresh()
        self.background(lambda: util.run(cmd, timeout=45), done)

    def ask_password(self, ssid):
        self.asking = ssid
        e = self.panel.entry
        e.set_text("")
        e.set_visibility(False)
        e.set_placeholder_text(f"Password for {ssid}")
        self.refresh()

    def cancel_password(self):
        if self.asking and self.panel:
            e = self.panel.entry
            e.set_visibility(True)
            e.set_placeholder_text(self.placeholder)
            e.set_text("")
        self.asking = None

    def disconnect(self):
        dev = self.wifi_device()
        self.background(lambda: util.run(["nmcli", "device", "disconnect", dev]), lambda _r: self.refresh())

    def forget(self, n):
        if n.get("conn"):
            self.background(lambda: util.run(["nmcli", "connection", "delete", "id", n["conn"]]),
                            lambda _r: self.refresh())

    def toggle_hotspot(self):
        st = self.hotspot_status() or {"on": False}
        self.set_status("stopping the hotspot…" if st["on"] else "starting the hotspot…")
        self.background(lambda: util.run([self.hotspot, "off" if st["on"] else "on"], timeout=40),
                        lambda _r: (self.set_status(""), self.refresh()))

    def activate(self, row, mods):
        d = row.data or {}
        kind = d.get("kind")
        if kind == "asking":
            pw = self.panel.entry.get_text()
            ssid = self.asking
            self.cancel_password()
            self.connect({"ssid": ssid, "security": "x"}, password=pw)
        elif kind == "net":
            if not d["active"]:
                self.connect(d)
        elif kind == "radio-off":
            self.set_radio(True)
        elif kind == "hotspot-toggle":
            self.toggle_hotspot()
        elif kind == "copy":
            util.copy(d["text"])
            self.set_status("copied")
        return False

    def sync_switch(self, on):
        if self.switch is not None and self.switch.get_active() != on:
            self.switch.handler_block(self.switch_handler)
            self.switch.set_active(on)
            self.switch.handler_unblock(self.switch_handler)
        return False

    def key(self, name, row, mods):
        if name == "Escape" and self.asking:
            self.cancel_password()
            self.refresh()
            return True
        if "ctrl" not in mods:
            return False
        if name == "d":
            self.disconnect()
        elif name == "f" and row is not None and (row.data or {}).get("kind") == "net":
            self.forget(row.data)
        elif name == "r":
            self.last_scan = 0
            self.refresh()
        elif name == "w":
            self.set_radio(not (self.switch and self.switch.get_active()))
        else:
            return False
        return True

    def closed(self):
        self.cancel_password()
