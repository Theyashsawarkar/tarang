# 3. Talk to NetworkManager through nmcli

**Status:** Accepted  
**Date:** 2026-10-19

## Context

Wi‑Fi on Linux desktops is almost always NetworkManager. Its D-Bus API is large; nmcli is stable, scriptable and always installed with it.

## Decision

tarang runs `nmcli` (terse output) in the background for scanning, connecting and forgetting. The hotspot tab is delegated to any command with a `status --json` / `on` / `off` interface (Vayu's `vayu-hotspot`).

## Consequences

- No NetworkManager means a clear message, not a crash.
- Hardware-specific hotspot logic stays out of the tool.
