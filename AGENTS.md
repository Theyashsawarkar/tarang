# tarang -- notes for AI agents (same as CLAUDE.md)

A Vyom tool (wi‑fi and the hotspot), in its own repo per Vayu's plugin rule (github.com/Theyashsawarkar/vayu, CLAUDE.md "Plugins"). It must work on any layer-shell compositor without Vayu; Vayu-specific behaviour only through `[plugin.tarang]` in ~/.config/vyom/config.toml.

- `plugin.toml` names it, its version and the tools it `requires`; `tarang/__init__.py` holds the `Plugin` class (API: vyom/plugin.py in the Vyom repo: search() runs in a worker thread and must not touch widgets; everything else is on the GTK main loop; slow work goes through self.background()).
- Every key has a `# keybind: Vyom/<scope> | <keys> | <Verb> ...` line (Vayu's keybinding search and this README's key table read them).
- Detect, don't assume: no tool or hardware means a clear row or `available()` returning why, never a crash.
- Every change: a CHANGELOG.md entry; releases are tags with `version` in plugin.toml bumped.
- Test live: link the repo into ~/.local/share/vyom/plugins/tarang, `vyom quit; vyom tarang`, screenshot it (grim), close it.
