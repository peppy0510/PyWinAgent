# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

description:
Claude Code hook entry that reads each finished reply aloud.
  prompt (UserPromptSubmit) binds the session to the foreground window
  stop   (Stop)             speaks the last assistant message with a window label
The hook JSON arrives on stdin. The speaker runs detached so a long reading is not
cut off by the hook timeout.

usage: python ttshook.py prompt|stop
'''


import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ttsconfig  # noqa: E402


TEMP_DIR = os.path.join(os.environ.get('TEMP', os.path.expanduser('~')), 'PyWinAgent', 'tts')
STORE_PATH = os.path.join(TEMP_DIR, 'sessions.json')
MUTEX_NAME = 'Local\\PyWinAgentTtsSessions'
STALE_SECONDS = 24 * 3600

HOOK_DEFAULTS = {
    'max_chars': 500,
    'voice_per_window': True,
    'voice_pool': ['F1', 'F3', 'F2', 'F4', 'F5', 'M1', 'M2', 'M3', 'M4', 'M5'],
}

# processes that host a Claude Code session window
HOST_PROCESSES = {
    'claude', 'windowsterminal', 'openconsole', 'conhost', 'pwsh', 'powershell', 'cmd',
    'code', 'wezterm', 'alacritty', 'hyper', 'tabby', 'mintty', 'conemu64', 'conemu',
    'electron'}

SINO = ('', '일', '이', '삼', '사', '오', '육', '칠', '팔', '구')
ROWS = ('상단', '중간', '하단')
COLUMNS = ('좌측', '가운데', '우측')


def read_hook():
    try:
        raw = sys.stdin.buffer.read().decode('utf-8', 'replace')
        hook = json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}
    return hook if isinstance(hook, dict) else {}


def load_config():
    config = dict(HOOK_DEFAULTS)
    config.update(ttsconfig.DEFAULTS)
    config.update(ttsconfig.read_raw())
    return config


def with_store(action):
    import win32event
    os.makedirs(TEMP_DIR, exist_ok=True)
    mutex = win32event.CreateMutex(None, False, MUTEX_NAME)
    win32event.WaitForSingleObject(mutex, 3000)
    try:
        try:
            with open(STORE_PATH, encoding='utf-8') as file:
                store = json.load(file)
        except (OSError, ValueError):
            store = {}
        if not isinstance(store, dict):
            store = {}
        result = action(store)
        with open(STORE_PATH, 'w', encoding='utf-8') as file:
            json.dump(store, file)
        return result
    finally:
        win32event.ReleaseMutex(mutex)


def assign_number(store, sid):
    # a small number per session, freed after a day idle
    now = time.time()
    for key in list(store):
        if key != sid and now - store[key].get('ts', now) > STALE_SECONDS:
            del store[key]
    entry = store.setdefault(sid, {})
    if not entry.get('n'):
        used = {item.get('n') for key, item in store.items() if key != sid}
        number = 1
        while number in used:
            number += 1
        entry['n'] = number
    entry['ts'] = now
    return entry


def get_foreground_host():
    import psutil
    import win32gui
    import win32process
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return 0
    try:
        pid = win32process.GetWindowThreadProcessId(hwnd)[1]
        name = os.path.splitext(psutil.Process(pid).name())[0].lower()
    except Exception:
        return 0
    return hwnd if name in HOST_PROCESSES else 0


def bind_window(sid):
    hwnd = get_foreground_host()

    def action(store):
        entry = assign_number(store, sid)
        if hwnd:
            entry['hwnd'] = hwnd
    with_store(action)


def get_session(sid):
    return with_store(lambda store: dict(assign_number(store, sid)))


def read_sino(number):
    if number <= 0 or number >= 100:
        return str(number)
    tens, ones = divmod(number, 10)
    text = '' if not tens else '십' if tens == 1 else SINO[tens] + '십'
    return text + SINO[ones]


def get_window_label(hwnd):
    # monitors count from the left by position, not by the Windows display number
    import win32api
    import win32gui
    if not hwnd or not win32gui.IsWindow(hwnd):
        return ''
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    x, y = (left + right) / 2.0, (top + bottom) / 2.0
    monitors = sorted((rect for _, _, rect in win32api.EnumDisplayMonitors()),
                      key=lambda rect: (rect[0], rect[1]))
    if not monitors:
        return ''
    index = next((i for i, (l, t, r, b) in enumerate(monitors)
                  if l <= x < r and t <= y < b), None)
    if index is None:
        index = min(range(len(monitors)), key=lambda i: (
            (x - (monitors[i][0] + monitors[i][2]) / 2.0) ** 2 +
            (y - (monitors[i][1] + monitors[i][3]) / 2.0) ** 2))
    l, t, r, b = monitors[index]
    column = min(2, max(0, int((x - l) * 3 // max(1, r - l))))
    row = min(2, max(0, int((y - t) * 3 // max(1, b - t))))
    return f'{read_sino(index + 1)}번 모니터 {ROWS[row]} {COLUMNS[column]}'


def read_last_reply(path):
    try:
        with open(path, 'rb') as file:
            lines = file.read().splitlines()
    except OSError:
        return ''
    for line in reversed(lines):
        if b'"assistant"' not in line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get('type') != 'assistant':
            continue
        content = (record.get('message') or {}).get('content') or []
        texts = [item.get('text') for item in content
                 if isinstance(item, dict) and item.get('type') == 'text' and item.get('text')]
        if texts:
            return ' '.join(texts)
    return ''


def strip_markdown(text, max_chars):
    text = re.sub(r'(?s)```.*?```', '. 코드 생략. ', text)
    text = re.sub(r'`([^`]*)`', r'\1', text)
    text = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'https?://\S+', ' 링크 ', text)
    text = re.sub(r'[#*_>~|]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > max_chars:
        text = text[:max_chars] + '. 이하 생략.'
    return text


def get_prefix(session):
    tag = (os.environ.get('CLAUDE_TTS_TAG') or '').strip()
    if tag:
        return f'{tag}번 창. ' if tag.isdigit() else f'{tag}. '
    label = get_window_label(session.get('hwnd'))
    if label:
        return f'{label} 클로드입니다. '
    return f'{int(session["n"])}번 창. '


def speak_detached(text, voice):
    command = [ttsconfig.get_pythonw(), ttsconfig.SPEAK_SCRIPT, '--text', text]
    if voice:
        command += ['--voice', voice]
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True)


def on_stop(sid, path):
    config = load_config()
    if config.get('notify') is False or not path:
        return
    text = strip_markdown(read_last_reply(path), int(config['max_chars']))
    if not text:
        return
    session = get_session(sid)
    voice = None
    pool = list(config.get('voice_pool') or HOOK_DEFAULTS['voice_pool'])
    if config.get('voice_per_window'):
        voice = pool[(session['n'] - 1) % len(pool)]
    speak_detached(get_prefix(session) + text, voice)


def main():
    event = sys.argv[1] if len(sys.argv) > 1 else ''
    hook = read_hook()
    path = hook.get('transcript_path')
    sid = hook.get('session_id') or (os.path.splitext(os.path.basename(path))[0] if path else '')
    if not sid:
        return
    try:
        if event == 'prompt':
            bind_window(sid)
        elif event == 'stop':
            on_stop(sid, path)
    except Exception:
        pass


if __name__ == '__main__':
    main()
