# tarang

**tarang** (तरंग, "wave") — Wi‑Fi and the hotspot. A tool for [Vyom](https://github.com/Theyashsawarkar/vyom), the keyboard-driven panels of [Vayu](https://github.com/Theyashsawarkar/vayu); in Vayu it replaces networkmanager_dmenu (wifi-picker.py).

> Wi-Fi: networks with live signal, connect with the password typed inline, forget, rescan; and a hotspot tab (vayu-hotspot).

## Features

- Networks with **live signal bars** (rescanned every few seconds while open): the one you're on, then saved ones, then nearby.
- `Enter` connects; a secured network you haven't joined asks for its **password right in the search box**.
- Disconnect, forget, rescan, and a Wi‑Fi on/off switch; Ethernet shows when it's what you're on.
- The preview: signal, security, band, channel, BSSID, your address.
- A **Hotspot tab** (with Vayu's `vayu-hotspot`, or any command with its `status --json` / `on` / `off` interface): on/off, name and password, a **QR code** phones scan to join, connected devices.

## Keys

| Key | Action |
|---|---|
| `Enter` | Connect to the selected network (asks for its password if needed) |
| `Ctrl+D` | Disconnect from the current network |
| `Ctrl+F` | Forget the selected saved network |
| `Ctrl+R` | Rescan for networks |
| `Ctrl+W` | Turn Wi-Fi on or off |
| `Ctrl+H` | Switch between networks and the hotspot |
| `Esc` | close |

Every Vyom panel also has: `Up`/`Down` (or `Ctrl+K`/`Ctrl+J`) to move, `Page Up`/`Page Down`, `Tab` to switch to the next tool.

## Requirements

- [Vyom](https://github.com/Theyashsawarkar/vyom) 0.2 or newer (Python 3.11+, GTK 4, gtk4-layer-shell, a layer-shell compositor)
- `nmcli`
- optional: qrencode (the hotspot's QR code)

## Install

```sh
git clone https://github.com/Theyashsawarkar/tarang ~/.local/share/vyom/plugins/tarang
vyom reload        # or log out and in
vyom tarang         # open it (again: close it)
```

Bind it to a key, e.g. in sway:

```
bindsym $mod+<key> exec vyom tarang
```

Update: `git -C ~/.local/share/vyom/plugins/tarang pull && vyom reload`. `vyom list` shows every installed tool and why one would be skipped.

## Configuration

In `~/.config/vyom/config.toml` (all optional):

```toml
[plugin.tarang]
# hotspot_command: the hotspot command (the tab hides without it) (default: vayu-hotspot)
```

## License

MIT.
