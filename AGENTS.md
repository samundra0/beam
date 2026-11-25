# Beam — notes for AI agents

Beam is an Omarchy shell **bar plugin** (id `beam.cast`) that mirrors the
desktop to AirPlay screens. Read this before changing anything; the README is
the user-facing doc.

## Layout

| Path | What it is |
|---|---|
| `manifest.json` | Plugin manifest (validated by `omarchy plugin validate .`); settings `sound`, `cursor`, `askSource` |
| `Panel.qml` | Bar icon + panel UI. Talks to `beamctl` only through `Process` and JSON |
| `beamctl` | Python 3, **standard library only**. Every command prints one JSON object, except `setup` and `uninstall`, which are human-readable (people type them) |
| `i18n/en.json` | UI strings, read through `Commons.Translations` (`strings.t("key")`) |
| `system/` | Root-owned firewall helpers + polkit policy, installed by `beamctl setup` |
| `tests/test_beamctl.py` | Unit tests (`bin/test`) |
| `bin/install` | Dev install: copies this checkout into `~/.config/omarchy/plugins/beam.cast` and restarts the shell |

The casting engine is **doubletake** v0.6.0 (LGPL-3.0,
github.com/omarroth/doubletake), downloaded unmodified with a pinned SHA-256
per architecture into `~/.local/lib/beam/`. Beam never bundles it.

## Runtime map

- `discover`: `avahi-browse` for `_airplay._tcp` + `_raop._tcp`, grouped by
  device id, speakers filtered out (`is_screen`), then the RTSP port probed:
  `_raop` port, `_airplay` port, 7000 — first to answer `GET /info` wins.
- `start`: opens the per-cast firewall rule (pkexec), optionally drops
  doubletake's saved portal pick (`--choose`), launches doubletake detached,
  and spawns `_watch` (closes firewall + restores sound when doubletake exits)
  and `_route-audio`.
- `change-source`: restarts the cast with the picker; `handoverFrom` in the
  session stops the old watcher from closing the firewall.
- `setup` / `fix` / `first-run`: install doubletake, run doctor's fix commands
  with sudo, record each change in `~/.local/share/beam/setup.json`.
- `uninstall`: undoes exactly what that record says, then removes the plugin.

State: `~/.local/state/beam/` (session.json, firewall.json, cast.log),
`~/.local/share/beam/` (setup record, first-run marker),
`~/.config/doubletake/credentials.json` (doubletake's pairings and
`restore_token`, the saved screen-share pick).

## Things that will bite you

- **The shell caches `Panel.qml` in memory.** Hot reload and plugin
  disable/enable keep the old panel. Only `omarchy restart shell` loads QML
  changes (`bin/install` does it; `--no-restart` when only `beamctl` changed).
- **The shell refuses symlinked plugins**, so dev installs are copies.
- **Horion panels** pose as `AppleTV3,2` (legacy AirPlay with FairPlay). They
  advertise `_airplay` on 7027 (an HTTP server) but mirror on 47027, their
  `_raop` port. That is why discovery probes ports instead of trusting them.
- **doubletake asks the portal for monitors only** (`types: 1`), but
  xdg-desktop-portal-hyprland ignores `types`, so its picker offers display,
  window and region anyway. The picker only appears when no `restore_token`
  is saved — hence `--choose`.
- **Firewall:** only `ufw allow from <screen-ip> to any port 60000:60010
  proto udp`, per cast, single IP. doubletake is always given
  `-port-range 60000-60010`. Never add subnet-wide or permanent rules.
- **Process detection** is by argv0 basename `doubletake`; doubletake forks an
  `--internal-audio-output-guard` helper with the same name, which is ignored.
- `pkill -f <pattern>` matches your own shell's command line; use explicit
  PIDs.

## Testing without touching the real machine

Unit tests: `bin/test`. For end-to-end runs, point Beam at a sandbox:

```sh
export XDG_STATE_HOME=$tmp/state XDG_CONFIG_HOME=$tmp/config XDG_DATA_HOME=$tmp/share
export BEAM_DOUBLETAKE=$tmp/bin/doubletake    # fake: `exec -a doubletake bash fake.sh "$@"`
export BEAM_UFW_RULES=$tmp/user.rules         # a rule covering the fake IP avoids pkexec
```

The fake should print `connected to:` / `mirror session ready` and on SIGINT
`shutting down...` / `stream ended`, like doubletake's log.

Do **not**, without the user asking: start a real cast, stop one they're
running, run `setup`/`uninstall` for real, or change ufw. Those need their
screen, their sudo password, or both.

## Conventions

- Keep `beamctl` stdlib-only and its output JSON; the panel never parses text.
- New UI strings go in `i18n/en.json`; add a test for any new `beamctl` logic.
- Run `bin/test` and `omarchy plugin validate .` before committing.
- Commit or push only when the user says so. Pushing over SSH fails on the
  author's machine (github.com isn't in known_hosts); use
  `git -c credential.helper='!gh auth git-credential' push` over HTTPS.
- Release: bump `version` in `manifest.json`, tag `vX.Y.Z`, push the tag,
  `gh release create`.

## Open items (after v1.0.0)

- **Sound doesn't play on the Horion.** Laptop-side routing works (default
  sink → `doubletake`, captured from its monitor). Suspects: doubletake picks
  AAC-ELD (Horion advertises feature bits 18–21 and libfdk-aac is installed)
  and the panel can't play it, or doubletake's initial-volume heuristics
  (Horion reports no `initialVolume`). Next step: a `-debug` cast while the
  user listens; the pedrocarv/airplay-mirror fork's
  `-preserve-receiver-volume` is a lead.
- **Extended display.** Plan: `hyprctl output create headless`, set it to the
  receiver's mode, cast that output (pick it in the portal picker), remove it
  when the cast ends. jonspinks/omarchy-airplay does this for AirPlay 2.
- Only English strings ship; no translations yet.
