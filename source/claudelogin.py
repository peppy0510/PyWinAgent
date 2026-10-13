# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import json
import os
import shutil
import subprocess
import time


CREDENTIALS = os.path.join(os.path.expanduser('~'), '.claude', '.credentials.json')

REFRESH_ARGS = ['-p', 'ok', '--model', 'haiku', '--strict-mcp-config',
                '--mcp-config', '{"mcpServers":{}}', '--no-session-persistence']
REFRESH_TIMEOUT = 120
REFRESH_SKEW = 5 * 60


def find_claude():
    appdata = os.environ.get('APPDATA', '')
    candidates = [
        os.path.join(appdata, 'npm', 'node_modules', '@anthropic-ai', 'claude-code', 'bin',
                     'claude.exe'),
        os.path.join(appdata, 'npm', 'claude.cmd'),
        shutil.which('claude.exe') or '',
        shutil.which('claude.cmd') or '',
        os.path.join(os.path.expanduser('~'), '.local', 'bin', 'claude.exe'),
    ]
    return next((path for path in candidates if path and os.path.exists(path)), None)


def read_expiry():
    try:
        with open(CREDENTIALS, encoding='utf-8') as file:
            oauth = json.load(file)['claudeAiOauth']
    except Exception:
        return None
    if not oauth.get('refreshToken'):
        return None
    return (oauth.get('expiresAt') or 0) / 1000.0


def refresh(claude):
    before = read_expiry()
    if before is None or before > time.time() + REFRESH_SKEW:
        return False
    # Claude Code refreshes its own token; using the refresh token here would rotate it
    command = [claude] + REFRESH_ARGS
    if claude.lower().endswith('.cmd'):
        command = [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c'] + command
    try:
        subprocess.run(command, cwd=os.path.expanduser('~'), timeout=REFRESH_TIMEOUT,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return False
    after = read_expiry()
    return after is not None and after != before and after > time.time()


def open_login(claude):
    terminal = shutil.which('wt.exe') or os.path.join(
        os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'WindowsApps', 'wt.exe')
    login = [claude, 'auth', 'login']
    if claude.lower().endswith('.cmd'):
        login = [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/k'] + login
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        if os.path.exists(terminal):
            subprocess.Popen([terminal, '-w', 'new', 'new-tab', '--title', 'Claude Code login'] +
                             login, cwd=os.path.expanduser('~'), creationflags=flags)
        else:
            subprocess.Popen(login, cwd=os.path.expanduser('~'),
                             creationflags=subprocess.CREATE_NEW_CONSOLE)
    except OSError:
        return False
    return True


def sign_in():
    claude = find_claude()
    if not claude:
        return 'missing'
    if refresh(claude):
        return 'refreshed'
    return 'login' if open_login(claude) else 'failed'
