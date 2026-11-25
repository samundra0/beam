# Beam

Mirror your Omarchy desktop to any AirPlay screen — Apple TV, AirPlay-capable
TVs (Samsung, LG, Sony, TCL, Hisense, Roku…), Macs, and classroom or meeting-room
panels (Horion and similar) — from a button in the Omarchy bar.

Beam finds the screens on your network, checks that your machine can cast,
fixes what's missing, and starts or stops the cast. The streaming is done by
[doubletake](https://github.com/omarroth/doubletake) (LGPL-3.0), which speaks
both the legacy AirPlay protocol (with FairPlay) and AirPlay 2 pairing, so it
works with receivers that other Linux senders can't connect to.

## Install

On Omarchy:

```sh
omarchy plugin add https://github.com/samundra0/beam.git --enable
```

Then click the cast icon in the bar. The **Setup** section lists anything
missing:

- **Install doubletake** downloads the pinned doubletake release for your
  machine (x86-64 or ARM64) into `~/.local/lib/beam/` and checks its SHA-256.
- **Fix in terminal** opens a terminal running only the `sudo` commands that
  are needed (see below).

Prefer the terminal? This does both in one go:

```sh
~/.config/omarchy/plugins/beam.cast/beamctl setup
```

### What setup changes on your system

| Check | Fix command |
|---|---|
| GStreamer and audio packages | `sudo pacman -S --needed gstreamer gst-plugins-base gst-plugins-good gst-plugins-bad gst-plugins-ugly gst-libav gst-plugin-pipewire gst-plugin-va libpulse avahi` (only the missing ones) |
| Screen discovery | `sudo systemctl enable --now avahi-daemon` |

Optional: `libfdk-aac` gives AAC sound; without it doubletake falls back to
ALAC.

### The firewall: open only while casting

The screen sends its timing and audio traffic back to the laptop, on UDP ports
60000–60010 (Beam always starts doubletake with `-port-range 60000-60010`).
With ufw on, those packets are blocked, so Beam opens the ports **for the one
screen you cast to, only while you cast**:

1. You press **Cast**. Omarchy's password dialog asks to run
   `ufw allow from <screen-ip> to any port 60000:60010 proto udp`.
   Dismiss it and the cast doesn't start.
2. When the cast ends — **Stop**, the screen disconnecting, or doubletake
   exiting for any reason — a small watcher asks for your password again and
   runs `ufw delete allow from <screen-ip> …` to remove that rule.
3. If the rule is ever left behind (say you logged out mid-cast), the panel
   says so and offers **Close firewall**; `beamctl firewall-close` does the same.

Beam only removes the rule it added. If you already have a rule that lets the
screen in (for example a permanent one for your network), Beam uses it, doesn't
prompt, and never removes it. With ufw off, nothing is changed.

## Use

1. Be on the same network as the screen: the same Wi-Fi, or the screen's own
   hotspot (many meeting-room panels have one).
2. Click the cast icon in the bar. Screens appear under **Screens**.
3. Press **Cast**. If Hyprland's screen-share picker appears, pick your display.
4. If the screen shows a code, type it into the field Beam shows. The pairing
   is remembered.
5. **Stop** in the panel, or right-click the bar icon, ends the cast.

| Setting | What it does |
|---|---|
| Send sound to the screen | Makes doubletake's sound output the default while casting, and restores the previous one when you stop |
| Show the mouse cursor | Turn off to hide the pointer on the screen |

Keyboard: arrow keys move between screens, Enter casts or stops, Esc closes.

## Which screens it finds

Anything that advertises AirPlay over mDNS (`_airplay._tcp` / `_raop._tcp`)
and can take a mirrored screen. Speakers — HomePods, AirPort Express, Sonos and
other audio-only receivers — are hidden; `beamctl discover --all` lists them
too.

Some receivers advertise one port but mirror on another (a Horion panel
advertises AirPlay on 7027 and mirrors on 47027, its `_raop` port). Beam tries
the `_raop` port, the `_airplay` port and 7000, and uses the first that answers
an RTSP `GET /info`.

Not supported: Chromecast/Google Cast and Miracast-only screens (doubletake is
AirPlay only).

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| No screens listed | Not on the screen's network, or avahi isn't running. Run `beamctl doctor`. Guest/corporate Wi-Fi often blocks device discovery (client isolation): use the screen's hotspot instead |
| Screen listed but "not answering" | It's asleep or on another input, or a VPN is routing traffic away. Try again with the screen's casting/AirPlay page open |
| Connects, then drops or no picture | Firewall: the per-cast rule wasn't added (password dialog dismissed?). `sudo ufw status` shows the 60000:60010 rule while casting |
| Black picture | Pick a display (not a window) in the screen-share picker; check `xdg-desktop-portal-hyprland` is running |
| Asks for a code every time | Remove the old pairing: delete the screen's entry in `~/.config/doubletake/credentials.json` |
| No sound on the screen | Turn on *Send sound to the screen*, or pick **doubletake** as the output in your sound settings |

The cast's log is at `~/.local/state/beam/cast.log`.

## Command line

`beamctl` does all the work and answers in JSON, so the bar widget never parses
free text:

```sh
beamctl discover [--all]    # screens, and the port that answers
beamctl doctor              # setup checks and the commands that fix them
beamctl setup               # install doubletake and run those fixes (human-readable)
beamctl start HOST PORT [--device-id ID] [--name NAME] [--audio] [--no-cursor] [--code PIN]
beamctl status              # idle / connecting / pairing / live / failed
beamctl stop
beamctl firewall-close      # remove a per-cast firewall rule left behind
```

The cast runs detached and survives shell reloads. A doubletake started outside
Beam shows as live in the bar too, and **Stop** ends it.

## Update and remove

```sh
omarchy plugin update beam.cast
omarchy plugin remove beam.cast
rm -rf ~/.local/lib/beam ~/.local/state/beam      # doubletake and Beam's state
```

Removing doesn't uninstall the packages setup added. Run `beamctl firewall-close`
first if the panel shows a firewall rule left open.

## Development

```sh
bin/test       # unit tests for discovery, the screen filter, firewall rules and log parsing
bin/install    # copy this checkout into ~/.config/omarchy/plugins/beam.cast (hot-reloads)
```

Layout: `manifest.json` and `Panel.qml` are the plugin, `beamctl` is the
Python helper (standard library only), `i18n/` holds the strings.

## Credits

- [doubletake](https://github.com/omarroth/doubletake) by omarroth, LGPL-3.0 —
  the AirPlay sender. Beam downloads its release binary unmodified, with its
  license, and doesn't bundle it.
- Beam is MIT licensed.
