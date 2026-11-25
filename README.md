# Beam

Cast your Omarchy desktop to any AirPlay screen — Apple TV, AirPlay TVs
(Samsung, LG, Sony, TCL, Hisense, Roku…), Macs, and meeting-room or classroom
panels such as Horion — from a button in the bar.

- **Finds the screens** on your network by itself.
- **Share a display, one window or a region**, and switch mid-cast.
- **Sets itself up**: one terminal, one password, done.
- **Opens the firewall only while casting, and only for that one screen.**
- **Uninstalls cleanly**, undoing exactly what setup changed.

The streaming is done by [doubletake](https://github.com/omarroth/doubletake)
(LGPL-3.0), which speaks legacy AirPlay with FairPlay as well as AirPlay 2
pairing, so it reaches receivers other Linux senders can't.

## Requirements

- [Omarchy](https://omarchy.org) (Hyprland, Arch Linux), x86-64 or ARM64.
- The screen and the laptop on the same network: the same Wi-Fi, or the
  screen's own hotspot.

## Install

```sh
omarchy plugin add https://github.com/samundra0/beam.git --enable
```

A terminal opens by itself and runs Beam's setup; enter your password when it
asks. When it says **Ready to cast**, you're done.

If you closed that terminal, click the cast icon in the bar: the **Setup**
section lists what's missing, and **Set up Beam** opens the same terminal
again. From a terminal: `~/.config/omarchy/plugins/beam.cast/beamctl setup`.
[What setup changes](#what-beam-changes-on-your-system) is listed below.

## Use

1. Click the cast icon in the bar. Screens on your network appear under
   **Screens**.
2. Press **Cast** next to one, and confirm the firewall prompt (password or
   fingerprint).
3. Hyprland's picker appears: choose a **display, window or region**.
4. If the screen shows a pairing code, type it into the field in the panel.
   It's remembered for next time.
5. **Stop** in the panel, or right-click the bar icon, ends the cast.

**Source…** picks what to share. Before a cast it casts with the picker; during
a cast it restarts the cast with the picker so you can share something else
(the screen goes blank for a couple of seconds).

| Setting | What it does |
|---|---|
| Send sound to the screen | Routes your sound to the screen while casting, and puts your speakers back when you stop. See [known limitations](#known-limitations) |
| Show the mouse cursor | Turn off to hide the pointer on the screen |
| Ask what to share each time | Show the picker on every **Cast**. Off: reuse the last choice |

Keyboard: arrow keys move between screens, Enter casts or stops, Esc closes.

## Which screens work

Anything that advertises AirPlay on the network (`_airplay._tcp` /
`_raop._tcp` over mDNS) and can show a mirrored screen. Speakers — HomePods,
AirPort Express, Sonos and other audio-only receivers — are hidden
(`beamctl discover --all` shows them).

Tested on a Horion panel, both on its own hotspot and on a shared office
Wi-Fi. Other AirPlay screens use the same protocol and should work.

Some receivers advertise one port but mirror on another; a Horion advertises
7027 and mirrors on 47027. Beam tries each advertised port and 7000, and uses
the one that answers.

**Not supported:** Chromecast / Google Cast and Miracast-only screens.

## Known limitations

- **No sound on Horion panels yet.** Your sound is routed and sent, but the
  panel plays nothing; this is being investigated. Video works.
- **Mirroring only.** Using the screen as a second, extended desktop is planned.
- English only, so far.

## What Beam changes on your system

### Setup

Setup runs only the steps that are needed, and records each change in
`~/.local/share/beam/setup.json` so uninstall can undo exactly that.

| What | How |
|---|---|
| doubletake | Downloads the pinned v0.6.0 release for your machine into `~/.local/lib/beam/` and checks its SHA-256. No sudo |
| GStreamer packages | `sudo pacman -S --needed` whichever of `gst-plugins-base gst-plugins-good gst-plugins-bad gst-plugins-ugly gst-libav gst-plugin-pipewire gst-plugin-va gstreamer libpulse avahi` are missing |
| Screen discovery | `sudo systemctl enable --now avahi-daemon`, if it's off |
| Readable firewall prompts | Only if ufw is on: installs two small root-owned helpers into `/usr/local/libexec/beam/` and their polkit policy into `/usr/share/polkit-1/actions/` |

Optional: `libfdk-aac` adds AAC sound; without it doubletake uses ALAC.

### The firewall: open only while casting

The screen sends timing and sound back to the laptop on UDP ports 60000–60010.
With ufw on those packets are blocked, so for each cast Beam:

1. asks for your password (*"Beam wants to let the screen you're casting to
   send sound and timing back to this computer…"*) and adds
   `ufw allow from <screen-ip> to any port 60000:60010 proto udp` — that one
   screen, nothing else. Dismiss the prompt and the cast doesn't start;
2. when the cast ends — **Stop**, the screen disconnecting, or a crash — asks
   again (*"Casting has stopped…"*) and deletes that rule;
3. if a rule is ever left behind (say you logged out mid-cast), shows
   **Close firewall** in the panel.

The helpers accept only a single IPv4 address and add or remove only that rule.
Beam never removes a rule it didn't add: if one already lets the screen in, it
uses it without prompting. With ufw off, nothing is changed.

### Files

| Path | What |
|---|---|
| `~/.config/omarchy/plugins/beam.cast/` | The plugin |
| `~/.local/lib/beam/` | doubletake and its license |
| `~/.local/state/beam/` | Current cast, firewall state, `cast.log` |
| `~/.local/share/beam/` | Setup record |
| `~/.config/doubletake/` | doubletake's pairings and saved screen choices |

## Troubleshooting

| Symptom | What to check |
|---|---|
| No screens listed | Same network as the screen? Run `beamctl doctor`. Some guest or corporate Wi-Fi blocks device discovery; use the screen's hotspot instead |
| Screen listed as "not answering" | It's asleep, on another input, or a VPN is routing traffic away. Open the screen's casting page and look again |
| Connects, then drops or no picture | The firewall prompt was dismissed. `sudo ufw status` shows the 60000:60010 rule while casting |
| Black picture | `xdg-desktop-portal-hyprland` must be running. A shared window may go black when minimised or on another workspace; share the display instead |
| Asks for a code every time | Delete the screen's entry in `~/.config/doubletake/credentials.json` and pair again |
| No sound | See [known limitations](#known-limitations); also check *Send sound to the screen* is on |

The cast's log is at `~/.local/state/beam/cast.log`.

## Command line

`beamctl` does all the work. It prints JSON (the panel never parses text),
except `setup` and `uninstall`, which are meant for people.

```sh
beamctl discover [--all]              # screens, and the port that answers
beamctl doctor                        # setup checks and the commands that fix them
beamctl setup                         # set up this machine
beamctl start HOST PORT [--device-id ID] [--name NAME] [--audio] [--no-cursor] [--choose] [--code PIN]
beamctl change-source                 # restart the running cast with the picker
beamctl status                        # idle / connecting / pairing / live / failed
beamctl stop
beamctl firewall-close                # remove a per-cast rule left behind
beamctl uninstall [--dry-run] [--all-packages]
```

The cast runs detached and survives shell restarts. A doubletake started
outside Beam shows as live in the bar too, and **Stop** ends it.

## Update, disable, uninstall

```sh
omarchy plugin update beam.cast       # latest version
omarchy plugin disable beam.cast      # hide from the bar, keep everything
omarchy plugin enable beam.cast       # bring it back
```

**Uninstall Beam…** at the bottom of the panel opens a terminal that lists
every step and asks first. Or:

```sh
~/.config/omarchy/plugins/beam.cast/beamctl uninstall --dry-run   # just show the steps
~/.config/omarchy/plugins/beam.cast/beamctl uninstall
```

It stops any cast and closes its firewall rule, removes the helpers, turns
avahi off **only if setup turned it on**, removes the packages **setup
installed** (with `pacman -Rsu`, so anything another app needs stays), deletes
the files listed above, and removes the plugin.

Packages you had before setup are left alone. `--all-packages` also offers the
casting packages no other app requires, notes which apps use them optionally,
and keeps `gstreamer`, `libpulse`, `avahi` and the like when others need them.

## Development

```sh
bin/test       # unit tests
bin/install    # copy this checkout into the shell and restart it
```

The shell caches `Panel.qml` in memory, so only a shell restart loads panel
changes; `bin/install` does that (`--no-restart` when only `beamctl` changed).

`manifest.json` and `Panel.qml` are the plugin, `beamctl` is the helper
(Python, standard library only), `i18n/` holds the strings and `system/` the
firewall helpers. [AGENTS.md](AGENTS.md) has the architecture, the pitfalls,
sandbox testing and the open work, for contributors and AI agents alike.

## Credits

- [doubletake](https://github.com/omarroth/doubletake) by omarroth, LGPL-3.0 —
  the AirPlay sender. Beam downloads its release binary unmodified, with its
  license, and doesn't bundle it.
- Beam is MIT licensed.
