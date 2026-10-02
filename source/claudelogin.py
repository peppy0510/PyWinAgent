# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

사용량 페이지의 "Sign in" 단추. Claude 로그인 토큰이 만료돼 한도를 못 물을 때 쓴다.
WhereMyTokens 의 `claudeLoginLauncher.js` 를 옮겼다.

1. 먼저 Claude Code 를 조용히 한 번 돌린다 (`claude -p ok --model haiku`). 토큰은
   Claude Code 가 스스로 갱신한다 — refresh token 을 우리가 직접 쓰면 바뀌어서
   Claude Code 의 로그인이 풀리지만, 이 길은 그런 일이 없다. 대신 아주 작은 요청 하나가
   계정 사용량에 잡힌다.
2. 그래도 토큰이 새로 안 생기면 (refresh token 까지 만료) 터미널에 `claude auth login`
   을 띄워 사람이 다시 로그인하게 한다.
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
# 만료 5 분 전부터는 갱신 대상으로 본다. 그보다 넉넉히 남았는데도 거절됐다면 로그인 문제다.
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
    '''토큰 만료 시각(초). refresh token 이 없으면 None — 다시 로그인하는 수밖에 없다.'''
    try:
        with open(CREDENTIALS, encoding='utf-8') as file:
            oauth = json.load(file)['claudeAiOauth']
    except Exception:
        return None
    if not oauth.get('refreshToken'):
        return None
    return (oauth.get('expiresAt') or 0) / 1000.0


def refresh(claude):
    '''조용히 갱신해 본다. 새 토큰이 생겼으면 참.'''
    before = read_expiry()
    if before is None or before > time.time() + REFRESH_SKEW:
        return False
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
    '''터미널에 `claude auth login` 을 띄운다. Windows Terminal 이 없으면 콘솔 창으로.'''
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
    '''('refreshed' | 'login' | 'missing' | 'failed'). 부르는 쪽이 스레드로 돌릴 것 —
    조용한 갱신은 길면 수십 초 걸린다.'''
    claude = find_claude()
    if not claude:
        return 'missing'
    if refresh(claude):
        return 'refreshed'
    return 'login' if open_login(claude) else 'failed'
