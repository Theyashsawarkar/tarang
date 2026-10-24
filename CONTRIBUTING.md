# Contributing to tarang

Thanks for wanting to make tarang better. Bug reports, ideas and pull
requests are all welcome.

## Reporting a bug

Open an [issue](https://github.com/Theyashsawarkar/tarang/issues/new/choose) with what you did, what you
expected, the output of `vyom list`, and anything relevant from
the daemon's log (`journalctl --user -u vyom -u vyom-daemon -b`). If the problem shows in every Vyom panel,
not just wi-fi, it belongs in [Vyom](https://github.com/Theyashsawarkar/vyom/issues).

## Development setup

tarang is a [Vyom](https://github.com/Theyashsawarkar/vyom) tool: a Python package loaded by the Vyom
daemon. Work on a clone linked into Vyom's plugin directory:

```sh
git clone https://github.com/Theyashsawarkar/tarang ~/code/tarang
ln -sfn ~/code/tarang ~/.local/share/vyom/plugins/tarang
vyom quit; vyom tarang        # restart the daemon with your code, open the panel
journalctl --user -u vyom -u vyom-daemon -b | grep -A20 Traceback
```

The API is documented in Vyom's `vyom/plugin.py`; `tarang/__init__.py` holds
the `Plugin` class.

## Rules of thumb

- **Never block the GTK main loop.** `search()` runs in a worker thread and
  must not touch widgets; anything slow elsewhere goes through
  `self.background(work, then)`, and only `then` touches widgets.
- **Detect, don't assume.** A missing tool or device means a clear row or
  message (or `available()` saying why), never a crash.
- **Every key is discoverable.** A new key gets a
  `# keybind: Vyom/<scope> | <keys> | <Verb> <object>` line next to its code
  and a row in the README's key table (CI checks this).
- **Works without Vayu.** Desktop-specific behaviour goes behind a setting in
  `[plugin.tarang]`.
- Every change gets a `CHANGELOG.md` entry. Releases are tags `vX.Y.Z` with
  `version` in `plugin.toml` bumped.

## Pull requests

Keep them focused on one change, describe what and why, and tick the
checklist in the template. By contributing you agree your work is released
under the [MIT License](LICENSE).
