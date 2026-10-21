# 2. Ship as its own repository, as a Vyom tool

**Status:** Accepted  
**Date:** 2026-10-19

## Context

tarang started as a script inside Vayu that piped rows into wofi. Living inside the desktop's dotfiles meant it couldn't be installed, versioned or tested on its own, and wofi's plain text list couldn't show live data, previews or actions.

## Decision

tarang is a Vyom tool in its own repository: a Python package with a `Plugin` class and a `plugin.toml`, loaded by the resident Vyom process. Vayu clones it into `~/.local/share/vyom/plugins/tarang`; anything Vayu-specific is a setting in `[plugin.tarang]`.

## Consequences

- It opens instantly (Vyom is already running) and shares Vyom's look, keys and footer.
- It can be installed without the rest of Vayu, on any layer-shell compositor.
- It depends on Vyom's plugin API: `plugin.toml` names the oldest Vyom it works with, and Vyom keeps that API compatible.
- Slow work must stay off the GTK main loop (`search()` runs in a thread, the rest goes through `self.background()`).
