## Features

* Usage dashboard for Claude Code: cost, cache efficiency, plan limits, tokens, tool usage and lines committed.
* Local text-to-speech with the Supertonic model on the CPU, with voice preview and settings.
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
