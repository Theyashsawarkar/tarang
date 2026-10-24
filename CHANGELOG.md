# Changelog

Newest first. Releases are tags (`vX.Y.Z`).

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
