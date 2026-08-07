# PyWinAgent

A Windows front end for the local agent toolkit, drawn entirely on a wxPython canvas.
It edits settings that until now only existed as JSON on the WSL side.

The chassis is the one from [PyWinClock](https://github.com/peppy0510/PyWinClock) — custom
title bar, sliding side menu, canvas-drawn cards — and the same rule applies: no packaged
build. A sideloaded MSIX cannot run under Smart App Control without a trusted signature,
so the start menu link runs `pythonw.exe` against the sources directly.

## Features

- **TTS** — a master switch for spoken notifications, then every knob
  `agent-toolkit/tts/speak.ps1` reads, on one scrolling page. The
  voice is picked from a grid of chips filled from the running Supertonic server, so cloned
  voices appear beside the ten built-in ones; when the server is down the page says so and
  falls back to the built-ins. **Preview** saves and then hands the sample line to
  `speak.ps1` itself, so what you hear has been through number normalisation, the
  Korean/English chunker and the splice — the same path a real notification takes.
- **Usage** — today's cost with the call and session counts beside the cache hit rate and
  what the cache saved; the five-hour and weekly plan limits the Claude client shows; a
  daily cost trend; and an hour-by-day activity heatmap for the last week.
- **Settings** — always on top, auto hide menu, dark theme.

Values are written back to `agent-toolkit/tts/settings.json` over the WSL share. Nothing
needs restarting: the notification hook spawns `speak.ps1` fresh each time and it re-reads
the file, so a change is live from the next utterance.

## Turning the voice off

**Speak notifications** writes `notify` into the same settings file, and the guard that reads
it lives in `agent-toolkit/tts/hook.ps1`, not here — that is the script Claude Code runs when a
reply finishes, and it is the only thing that speaks without being asked. The read-aloud hotkey
and this app's own Preview call `speak.ps1` directly and keep working while the switch is off,
because pressing a hotkey *is* the request.

The guard is `$cfg.notify -ne $false`, so a settings file with no `notify` key still speaks.
An installation that never opens this app must not fall silent because a key it has never heard
of is missing.

## Handling of the settings file

That file is not ours alone, so the page is careful with it:

- Keys the page does not show — `voice_pool` today — are read and written back untouched.
- A key is only written if it was already in the file or its value differs from the
  `speak.ps1` default. Writing every key would freeze today's defaults into the file and
  the app would stop following upstream when those defaults change.
- A stored value outside a slider's declared range widens the range instead of being
  clamped to it. `max_chars` is 10000 here while the sensible span ends at 20000; clamping
  would quietly cut a setting the user never touched.

## Requirements

Python 3.13 with `wxPython`, `psutil` and `pywin32`. `pillow` is only needed by
`makeicon.py`.

## Run

```
pythonw source\main.pyw
```

## Start menu entry

```
python source\makeicon.py
python source\makeshortcut.py
```

`makeshortcut.py` creates `Start Menu\Programs\PyWinAgent.lnk` pointing at
`pythonw.exe "source\main.pyw"`. Remove that `.lnk` to uninstall.

## Layout

| File | Role |
| --- | --- |
| `source/main.pyw` | Entry point. Checks for a running instance, then calls `mainapp` |
| `source/mainapp.py` | `MainFrame`, page wiring, timer, theme and settings |
| `source/ttsbox.py` | TTS settings page: voice grid, preview and the value cards |
| `source/ttsconfig.py` | Reads and writes the toolkit's TTS settings; voice list; preview |
| `source/usageview.py` | Usage page as a WebView — the one currently wired up |
| `source/usage.htm` | The usage dashboard itself: HTML, CSS and the candle chart |
| `source/usagebox.py` | The same page drawn on canvas — swap it back in from `mainapp` |
| `source/usagedata.py` | Runs `ccusage` and scans the session records for what it lacks |
| `source/settingsbox.py` | Settings page of cards, opened from the side menu |
| `source/titlebar.py` | Canvas-drawn title bar replacing the system caption |
| `source/sidemenu.py` | Sliding side menu opened by the hamburger |
| `source/icons.py` | Line glyphs for the title bar and the side menu |
| `source/controls.py` | Canvas-drawn cards, sliders, chip grid and the scrolling area |
| `source/utilities.py` | `Canvas` base class, themes, fonts, settings, DWM frame |
| `source/wininstance.py` | Single instance check |
| `source/shortcut.py` | Shortcut helper |
| `source/makeshortcut.py` | Creates the start menu link |
| `source/makeicon.py` | Generates `assets/icon/icon.ico` |

Window position and app settings live in `%APPDATA%\PyWinAgent\settings.json`. Only one
instance runs at a time (`wininstance.has_running_instance`).

## Where the usage numbers come from

Cost and tokens come from `ccusage`, which is fast enough to call on demand — two months of
dailies come back in about a second. Everything it does not report is counted straight
out of `~/.claude/projects/**/*.jsonl` with one regex per line; a week of records is 370 MB
and scans in well under a second, so there is no index to build or invalidate.

Two definitions worth pinning down, because the obvious reading of each is wrong:

- **calls** is the number of distinct `requestId`s whose line falls on today in *local* time.
  Counting requests in files merely *touched* today pulls in yesterday's messages and roughly
  doubles the figure.
- **sessions** is the number of session files touched today. `ccusage session` counts distinct
  session ids that accrued cost, which is a different and smaller number.

The plan limits are the one thing neither `ccusage` nor the records can answer — they come
from Anthropic's OAuth usage endpoint, called with the token Claude Code already stores. The
Windows and WSL credential files are tried in turn and the first that answers wins, because a
token can be expired or revoked in one place while still good in the other. The token is read,
used for that one request and dropped; it is never logged or cached. When neither answers the
card says so rather than showing a stale bar — there is no way to refresh a token from here,
but running `claude` in WSL renews the one it uses.

Not carried over from WhereMyTokens: the green *net lines* series, which needs git statistics
collected across every sibling repository, and the live session panel.

## The trend chart

The trend is `TimeGraph` from itruck-service's comjs, ported to plain markup. Bars sit flush
against each other and grow from the bottom, the tallest value is the full height, and two
label plates hang off the top corners — the current value on the left, `Peak:` on the right —
with the graphic padded down so the bars never run under them. No charting library, there or
here. Only the colours changed: comjs draws light-theme greys, so the bars became a muted
accent with today's bar at full strength, since otherwise there is no telling which one is now.

The candle chart from [honeypot](https://github.com/peppy0510/honeypot) was tried first and
dropped. Candles need four numbers a period and a day has one, so the open had to be faked
from the previous day's close and the wicks were always zero — a bar chart wearing a costume.

## Two Usage pages

The Usage page exists twice over the same data, and `mainapp` picks one with a single import
— the arrangement `honeypot` uses for its three window shells.

`usageview.py` hosts a `wx.html2.WebView` on the Edge (Chromium) backend and hands the
drawing to `usage.htm`. `usagebox.py` draws the identical panels on `wx.GraphicsContext`.
The web version is 100 lines of Python and 324 of markup against 345 lines of canvas code,
and gets hover, text selection and a themed scrollbar for nothing. The canvas version has no
second runtime to keep alive and no second language to debug in.

Two things had to be right for the web version to fit this app at all, and both were measured
rather than assumed:

- A `WebView` is a native child window, so the sliding side menu drawn on canvas looked like
  it would be swallowed by it. It is not — `apply_clip_siblings` on the view plus `Raise()`
  on the overlay keeps the drawer on top. The custom title bar and menu survive unchanged.
- `AddScriptMessageHandler` must be called **before** `SetPage`. Registering it on
  `EVT_WEBVIEW_LOADED` is too late and silently drops the page's first message, which is the
  one that says it is ready for data.

Python pushes state with `RunScriptAsync('render(…)')` and the page answers over
`window.chrome.webview.postMessage`. Themes cross the same way, as CSS custom properties, so
the light and dark schemes stay defined in one place.

## Notes on the widgets

`controls.ScrollArea` does not use `wx.ScrolledWindow`. Its scrollbar is native, stays
light in a dark theme and cannot be recoloured from wx, so the area moves its content panel
by hand and draws a thin bar that fades out after the scrolling stops. Wheel events do not
travel up to a parent in wx, so every child in the area gets the handler bound to it
(`bind_children`).

`controls.ChipGrid` derives its height from its width, which is the wrap point of the rows.
It only asks for a new minimum size when the row count actually changes — a discrete value,
so the layout settles instead of feeding back.
