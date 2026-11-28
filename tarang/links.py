"""Every way this machine is online, each the same way: Wi-Fi, Ethernet, a
phone over USB, mobile broadband, Bluetooth, VPN and WireGuard (a VPN shown
as riding on the connection under it). Plain data, no GTK (the unit tests
run without it).

The list comes from Vyom's live state (Vyom 0.12: live.get("wifi")
["connections"], kept by NetworkManager's own signals, the primary one
first). An older Vyom has only the wired connection's name; then the
device comes from its net history. Without a live state, nmcli says
(worker thread only)."""

# the type's glyph (Material Design Icons, in the Nerd Font) and its word
WIFI, ETHERNET, USB, MOBILE = "\U000f05a9", "\U000f0200", "\U000f0553", "\U000f08be"
BLUETOOTH, VPN, HOTSPOT, LAN, NETWORK = "\U000f00af", "\U000f099d", "\U000f0003", "\U000f0317", "\U000f06f3"
GLYPHS = {"wifi": WIFI, "ethernet": ETHERNET, "usb": USB, "mobile": MOBILE, "bluetooth": BLUETOOTH,
          "vpn": VPN, "wireguard": VPN, "hotspot": HOTSPOT, "bridge": LAN, "bond": LAN, "vlan": LAN,
          "team": LAN}
LABELS = {"wifi": "Wi-Fi", "ethernet": "Ethernet", "usb": "USB", "mobile": "Mobile", "bluetooth": "Bluetooth",
          "vpn": "VPN", "wireguard": "WireGuard", "hotspot": "Hotspot", "bridge": "Bridge", "bond": "Bond",
          "vlan": "VLAN", "team": "Team", "other": "Network"}
# what each is, in a few words (the details' "Kind" line)
WHAT = {"wifi": "Wi-Fi", "ethernet": "Ethernet cable", "usb": "Phone over USB (tethering)",
        "mobile": "Mobile broadband", "bluetooth": "Phone over Bluetooth", "vpn": "VPN",
        "wireguard": "WireGuard VPN", "bridge": "Bridge", "other": "Network"}
# nmcli's device TYPE -> ours (the fallback without a live state)
NMCLI_TYPES = {"ethernet": "ethernet", "wifi": "wifi", "gsm": "mobile", "cdma": "mobile", "bt": "bluetooth",
               "vpn": "vpn", "wireguard": "wireguard", "tun": "vpn", "bridge": "bridge", "bond": "bond",
               "vlan": "vlan", "team": "team"}
HIDDEN = {"loopback", "veth", "dummy", "wifi-p2p", "ovs-port", "ovs-bridge", "ovs-interface", "unknown"}
USB_TETHER = {"rndis_host", "cdc_ether", "cdc_ncm", "cdc_eem", "ipheth", "cdc_subset"}
VIRTUAL = ("docker", "br-", "virbr", "lxcbr", "lxdbr", "cni", "podman")


def glyph(kind):
    return GLYPHS.get(kind, NETWORK)


def label(kind):
    return LABELS.get(kind, "Network")


def speed_text(mbps):
    """Link speed in Mb/s, in words: "1 Gb/s", "100 Mb/s", "2.5 Gb/s"; "" when unknown."""
    try:
        v = float(mbps or 0)
    except (TypeError, ValueError):
        return ""
    if v <= 0:
        return ""
    if v >= 1000:
        g = v / 1000
        return f"{g:.0f} Gb/s" if g == int(g) else f"{g:.1f} Gb/s"
    return f"{v:.0f} Mb/s"


def first_ip(addrs, v6=False):
    """The address to show from ["192.168.1.4/24", ...] (IPv6: not the link-local one when there's another)."""
    ips = [a.split("/")[0] for a in addrs or () if a]
    if v6:
        ips = [x for x in ips if not x.lower().startswith("fe80")] or ips
    return ips[0] if ips else ""


def from_live(ls, net_devices=(), wifi_dev=""):
    """The connections from Vyom's live Wi-Fi state, the primary one first,
    or None when it doesn't say (Vyom before 0.12): then `wired` (a name)
    becomes an Ethernet connection, its device the first device the net
    history has up that isn't the Wi-Fi card."""
    if not ls or not ls.get("running"):
        return None
    conns = ls.get("connections")
    if conns is not None:
        return [dict(c) for c in conns if c.get("type") != "hotspot"]
    out = []
    if ls.get("wired"):
        dev = next((d for d in net_devices or () if d and d != (wifi_dev or ls.get("device"))), "")
        out.append({"name": ls["wired"], "type": "ethernet", "label": "Ethernet", "device": dev, "primary": True,
                    "ip4": [], "ip6": [], "gateway": "", "dns": [], "old": True})
    a = ls.get("active")
    if a and a.get("ssid") and not (ls.get("hotspot") or {}).get("on"):
        out.append({"name": (ls.get("connection") or {}).get("name") or a["ssid"], "type": "wifi",
                    "label": "Wi-Fi", "device": ls.get("device", ""), "ssid": a["ssid"],
                    "strength": a.get("strength", 0), "primary": not out, "ip4": ls.get("ip4", []),
                    "ip6": ls.get("ip6", []), "gateway": ls.get("gateway", ""), "dns": ls.get("dns", []),
                    "bitrate": ls.get("bitrate", 0)})
    return out


def kind_of(nm_type, driver="", iface=""):
    """nmcli's TYPE (and the driver) -> ours, or None for plumbing."""
    if nm_type in HIDDEN or (nm_type == "bridge" and iface.startswith(VIRTUAL)):
        return None
    k = NMCLI_TYPES.get(nm_type, "other")
    if k == "ethernet" and driver in USB_TETHER:
        return "usb"
    return k


def parse_nmcli(device_lines, show):
    """The connections from `nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device`
    (lines, already split into fields) and show(dev) -> {key: value} of
    `nmcli -g ... device show` for each connected device."""
    out = []
    for f in device_lines:
        if len(f) < 4 or not f[2].startswith("connected") or "externally" in f[2]:
            continue
        dev, nm_type, _st, name = f[:4]
        d = show(dev) if nm_type != "wifi" else {}
        kind = kind_of(nm_type, d.get("driver", ""), dev)
        if kind is None or kind == "wifi":
            continue      # Wi-Fi is said by the networks list itself
        out.append({"name": name or dev, "type": kind, "label": label(kind), "device": dev,
                    "ip4": d.get("ip4", []), "ip6": d.get("ip6", []), "gateway": d.get("gateway", ""),
                    "dns": d.get("dns", []), "mac": d.get("mac", ""), "speed": d.get("speed", 0),
                    "driver": d.get("driver", ""), "vpn": kind in ("vpn", "wireguard")})
    if out:
        out[0]["primary"] = True
    return out


def subtitle(c):
    """The row's line under the name: the kind, the link speed, the address."""
    kind = c.get("type")
    bits = [c.get("label") or label(kind)]
    if kind in ("vpn", "wireguard"):
        if c.get("via"):
            bits.append(f"over {c['via']}")
    elif kind == "mobile" and c.get("operator"):
        bits.append(f"operator {c['operator']}")
    elif kind == "bluetooth" and c.get("peer"):
        bits.append(f"through {c['peer']}")
    else:
        sp = speed_text(c.get("speed"))
        if sp:
            bits.append(sp)
    ip = first_ip(c.get("ip4")) or first_ip(c.get("ip6"), v6=True)
    if ip:
        bits.append(ip)
    return " · ".join(bits)


def facts(c, primary_name=""):
    """[(name, value)] of the connection's details, by kind."""
    kind = c.get("type")
    out = [("Kind", WHAT.get(kind, c.get("label") or "Network"))]
    if kind in ("vpn", "wireguard"):
        out.append(("Server", c.get("server") or "—"))
        if c.get("via"):
            out.append(("Rides on", c["via"] + (f" ({c['via_device']})" if c.get("via_device") else "")))
    sp = speed_text(c.get("speed"))
    if kind == "ethernet" or (kind == "usb" and sp):
        out.append(("Link speed", (sp or "not reported") + (f" · {c['duplex']} duplex" if c.get("duplex") else "")))
    if kind == "mobile":
        out.append(("Operator", c.get("operator") or "—"))
        out.append(("APN", c.get("apn") or "—"))
    if kind == "bluetooth" and c.get("peer"):
        out.append(("Through", c["peer"]))
    out.append(("IP address", first_ip(c.get("ip4")) or "—"))
    out.append(("Gateway" if kind in ("vpn", "wireguard", "mobile") else "Router", c.get("gateway") or "—"))
    out.append(("DNS", ", ".join(c.get("dns") or []) or "—"))
    out.append(("IPv6", first_ip(c.get("ip6"), v6=True) or "none"))
    if c.get("primary"):
        out.append(("Route", "Default: your traffic goes this way"))
    elif primary_name:
        out.append(("Route", f"Standby: {primary_name} is used first"))
    dev = c.get("vpn_device") or c.get("device")
    if dev:
        out.append(("Device", dev + (f" · {c['driver']}" if c.get("driver") and kind != "vpn" else "")))
    if c.get("mac"):
        out.append(("Hardware address", c["mac"]))
    return out


def graph_device(c):
    """The interface whose counters the graph draws: the VPN's own (wg0,
    tun0) when it has one, else the device it rides on."""
    return c.get("vpn_device") or c.get("device") or c.get("via_device") or ""
