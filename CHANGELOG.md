# Changelog

Newest first. Releases are tags (`vX.Y.Z`).

## v0.3.1 -- 2026-11-07

- The signal meter no longer makes GTK warn about its size (its bar had a negative width).

## v0.3.0 -- 2026-11-07

- A new look (Vyom 0.6.0's status strip). The network you're on is a card at the top: signal ring,
  link speed, band and channel, security, your address, and Share / Disconnect buttons with their
  keys on them. When you're not connected it says why (Wi-Fi off, on Ethernet, NetworkManager not
  running, no Wi-Fi card) instead of an empty list.
- Signal is bars and a word (Excellent, Good, Fair, Weak) instead of a bare percentage; saved
  networks have a star; open networks a yellow "Open" chip, WEP/WPA1 a red one; Saved and Nearby
  sections with counts. The top bar shows when it's scanning and how long ago it last scanned.
- Connecting shows its steps (Associating, Authenticating, Getting an address) as NetworkManager
  goes through them, and a failure says why in red: wrong password (it asks again right away),
  out of range, no address from the router, a WPA Enterprise network, a password that's too short.
  The panel stays open, so you see it connect.
- The preview has a signal meter with what it means in plain words, security as a chip (with a
  warning on open and weak networks), band and channel, speed, metered, BSSID.
- Forget asks first: press `Ctrl+F` twice (it can't be undone).
- New: `Ctrl+Q` shares the network you're on as a QR code phones scan to join (needs qrencode;
  without it, the password is shown); `Ctrl+S` shows or hides a password.
- The Hotspot tab: a QR code to join, name, password (hidden until `Ctrl+S`), band and what it
  shares, the connected devices, `Ctrl+T` (or the switch) to turn it on or off, and name, password
  and band as settings that are read-only until you press `Enter` on one. Errors from the hotspot
  command show in red with its reason.
- The on/off switch is a pill that says On or Off. Needs Vyom 0.6.0.
- Every corner is rounded: the website's callouts.
- A logo and a shloka at the top of the README and the website: every Vayu tool has them now.
- Screenshots in the README and on the website.

## v0.2.0 -- 2026-10-24

- The Networks / Hotspot tabs switch like every Vyom tool's tabs (Vyom 0.3.0): `Ctrl+H` /
  `Ctrl+L` for the previous / next tab and `Ctrl+1` / `Ctrl+2`. `Ctrl+H` was a toggle; it
  still switches between the two. Needs Vyom 0.3.0.

## v0.1.3 -- 2026-10-21

- A website (GitHub Pages, https://theyashsawarkar.github.io/tarang/): the README as a home page, the
  changelog, and architecture decision records (`docs/adr/`), built from these files by
  `scripts/build-site.py`; CI checks the site is up to date.

## v0.1.2 -- 2026-10-21

- Documentation for open source: a logo and banner, a full README (features,
  install, usage, configuration, troubleshooting, the whole Vyom family),
  CONTRIBUTING, SECURITY and CODE_OF_CONDUCT, issue and pull request
  templates, and CI (compiles, checks plugin.toml and that every key is
  documented).

## v0.1.1 -- 2026-10-19

- Keys are spelled out (Ctrl+Enter, Shift+Enter, Backspace) instead of symbols
  (⌃↵, ⇧↵, ⌫) in the footer and on rows and buttons.

## v0.1.0 -- 2026-10-19

- First release, as its own repository: wi‑Fi and the hotspot. Replaces networkmanager_dmenu (wifi-picker.py) in Vayu.
- Networks with **live signal bars** (rescanned every few seconds while open): the one you're on, then saved ones, then nearby.
- `Enter` connects; a secured network you haven't joined asks for its **password right in the search box**.
- Disconnect, forget, rescan, and a Wi‑Fi on/off switch; Ethernet shows when it's what you're on.
- The preview: signal, security, band, channel, BSSID, your address.
- A **Hotspot tab** (with Vayu's `vayu-hotspot`, or any command with its `status --json` / `on` / `off` interface): on/off, name and password, a **QR code** phones scan to join, connected devices.
