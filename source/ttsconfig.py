# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import json
import os
import subprocess
import urllib.request


WSL_ROOT = r'\\wsl.localhost\ubuntu-24.04\var\www\agent-toolkit\tts'

SETTINGS_PATH = os.environ.get('PYWINAGENT_TTS_SETTINGS',
                               os.path.join(WSL_ROOT, 'settings.json'))
SPEAK_SCRIPT = os.environ.get('PYWINAGENT_TTS_SPEAK',
                              os.path.join(WSL_ROOT, 'speak.ps1'))
SERVER_URL = os.environ.get('PYWINAGENT_TTS_URL', 'http://127.0.0.1:18000')

SAMPLE_TEXT = '안녕하세요. 지금 이 목소리로 알림을 읽어 드립니다.'

BUILTIN_VOICES = ('F1', 'F2', 'F3', 'F4', 'F5', 'M1', 'M2', 'M3', 'M4', 'M5')

DEFAULTS = {
    'notify': True,
    'voice': 'F1',
    'speed': 1.0,
    'steps': 8,
    'max_chars': 500,
    'silence_duration': 0.3,
    'trim_silence': True,
    'trim_lead_ms': 30,
    'trim_trail_ms': 110,
    'end_trail_ms': 260,
    'end_fade_ms': 400,
    'fade_in_ms': 150,
    'fade_out_ms': 180,
    'reverb': True,
    'reverb_wet': 0.1,
    'reverb_room': 0.32,
    'reverb_width': 0.6,
}

RANGES = {
    'speed': (0.5, 2.0, 0.05, 2),
    'steps': (4, 32, 1, 0),
    'max_chars': (100, 20000, 100, 0),
    'silence_duration': (0.0, 1.0, 0.05, 2),
    'trim_lead_ms': (0, 500, 10, 0),
    'trim_trail_ms': (0, 500, 10, 0),
    'end_trail_ms': (0, 800, 10, 0),
    'end_fade_ms': (0, 1200, 20, 0),
    'fade_in_ms': (0, 500, 10, 0),
    'fade_out_ms': (0, 500, 10, 0),
    'reverb_wet': (0.0, 1.0, 0.02, 2),
    'reverb_room': (0.0, 1.0, 0.02, 2),
    'reverb_width': (0.0, 1.0, 0.02, 2),
}


def bounds(key, value):
    # widen the range around out-of-range file values, or saving would clamp them
    low, high, step, digits = RANGES[key]
    try:
        value = float(value)
    except (TypeError, ValueError):
        return (low, high, step, digits)
    return (min(low, value), max(high, value), step, digits)


def read_raw():
    try:
        with open(SETTINGS_PATH, encoding='utf-8') as file:
            raw = json.load(file)
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def load():
    raw = read_raw()
    values = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in raw:
            values[key] = raw[key]
    return values, raw


def save(values, raw):
    # untouched defaults stay out of the file so speak.ps1 defaults can still change
    merged = dict(raw)
    for key, value in values.items():
        if key in raw or value != DEFAULTS.get(key):
            merged[key] = value

    path = SETTINGS_PATH
    try:
        with open(path, 'w', encoding='utf-8') as file:
            json.dump(merged, file, ensure_ascii=False, indent=2)
            file.write('\n')
    except Exception as error:
        return str(error)
    return None


def list_voices():
    try:
        with urllib.request.urlopen(SERVER_URL + '/v1/styles', timeout=3) as response:
            styles = json.loads(response.read().decode('utf-8')).get('styles', [])
    except Exception:
        return list(BUILTIN_VOICES), False

    names = [style['name'] for style in styles if style.get('name')]
    names.sort(key=lambda name: (name[:1], int(name[1:]) if name[1:].isdigit() else 0))
    return names or list(BUILTIN_VOICES), True


def is_server_up():
    return list_voices()[1]


def preview(voice, text=SAMPLE_TEXT):
    # speak.ps1 targets Windows PowerShell 5.1 and is unsigned on a UNC path
    command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
               '-File', SPEAK_SCRIPT, '-Text', text, '-Interrupt']
    if voice:
        command += ['-Voice', voice]
    try:
        return subprocess.Popen(command, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:
        return None
