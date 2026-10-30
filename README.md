## Features

* Usage dashboard for Claude Code: cost, cache efficiency, plan limits, tokens, tool usage and lines committed. Codex and Antigravity can be turned on under Settings > Agents.
* Sessions are read on Windows and in the default WSL distro, whatever it is named.
* An estimate of how much of each plan limit this device used, and how much went elsewhere.
* Costs in USD, KRW or JPY, at exchange rates you set. Projects can be left out of the numbers or hidden from the session list.
* Local text-to-speech with the Supertonic model on the CPU, with voice preview and settings.
* Reads each finished Claude Code reply aloud through a hook installed from the TTS page.
* Read-aloud hotkey (Ctrl+Alt+Shift+9 by default, changeable) reads the selected text in any app.
* Tray icon, with an option to close to the tray.
* Floating usage widget.
* Auto, dark and light themes.

## How to install

* Download or clone a repository, install Python packages in the requirements.pip file, then execute source/main.pyw with pythonw.exe. Python 3.x is required.
* The voice model (about 400 MB) downloads on first use into %LOCALAPPDATA%\PyWinAgent\supertonic3. Clone voices go in %APPDATA%\PyWinAgent\voices.
* `pythonw source/ttsspeak.py --text "..."` reads text aloud from the command line.
* Execute source/makeshortcut.py to put a shortcut in the Start menu.

## Supported platforms

* Microsoft Windows 11
* Other versions of Windows have not been tested yet.
