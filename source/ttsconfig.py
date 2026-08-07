# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

agent-toolkit 의 TTS 설정을 읽고 쓴다. 그림 그리는 쪽과 섞지 않으려고 값에
관한 것만 여기 둔다 — 이름표와 묶음은 ttsbox 가 정한다.

설정 파일은 WSL 에 있고 speak.ps1 도 그 파일을 본다. 알림이 올 때마다 hook 이
speak.ps1 을 새로 띄우므로 여기서 저장하면 다음 발화부터 바로 먹는다.
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

# 서버가 죽어 있을 때 보여 줄 목록. 내장 보이스는 늘 이 열이다.
BUILTIN_VOICES = ('F1', 'F2', 'F3', 'F4', 'F5', 'M1', 'M2', 'M3', 'M4', 'M5')

# speak.ps1 의 $cfg 를 그대로 옮긴 것. 설정 파일에 없는 키는 이 값으로 동작하므로
# 화면에는 이 값을 보여 주고, 사용자가 건드리지 않은 키는 파일에 쓰지 않는다.
DEFAULTS = {
    # 알림을 소리로 읽을지. hook.ps1 이 이 값을 보고 speak.ps1 을 부를지 정한다.
    # 읽어주기 단축키와 미리듣기는 사람이 직접 부르는 것이라 여기 걸리지 않는다.
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

# (최소, 최대, 눈금, 소수점 자리). 자리가 0 이면 정수로 읽고 쓴다.
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
    '''★이미 파일에 적혀 있는 값이 우리가 정한 범위 밖일 수 있다. 그대로 두면
    슬라이더가 값을 끝으로 당겨 붙이고, 저장할 때 사용자가 손대지도 않은 설정을
    조용히 깎아 버린다. 범위 쪽을 늘려 값을 품는다.'''
    low, high, step, digits = RANGES[key]
    try:
        value = float(value)
    except (TypeError, ValueError):
        return (low, high, step, digits)
    return (min(low, value), max(high, value), step, digits)


def read_raw():
    '''파일에 실제로 적혀 있는 것만 돌려준다. 우리가 안 보여 주는 키도 들어 있어,
    저장할 때 그대로 되돌려 놓아야 남의 설정을 지우지 않는다.'''
    try:
        with open(SETTINGS_PATH, encoding='utf-8') as file:
            raw = json.load(file)
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def load():
    '''화면에 보일 값. 파일에 없는 키는 speak.ps1 의 기본값으로 채운다.'''
    raw = read_raw()
    values = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in raw:
            values[key] = raw[key]
    return values, raw


def save(values, raw):
    '''기본값과 같고 원래 파일에도 없던 키는 쓰지 않는다. speak.ps1 의 기본값이
    나중에 바뀌면 따라가야 하는데, 다 적어 두면 옛 값에 묶여 버린다.'''
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
    '''서버가 살아 있으면 클론 보이스까지 딸려 온다. 죽어 있으면 내장만 보여 준다.'''
    try:
        with urllib.request.urlopen(SERVER_URL + '/v1/styles', timeout=3) as response:
            styles = json.loads(response.read().decode('utf-8')).get('styles', [])
    except Exception:
        return list(BUILTIN_VOICES), False

    names = [style['name'] for style in styles if style.get('name')]
    # C10 이 C2 앞에 서지 않도록 글자와 숫자를 나눠 센다.
    names.sort(key=lambda name: (name[:1], int(name[1:]) if name[1:].isdigit() else 0))
    return names or list(BUILTIN_VOICES), True


def is_server_up():
    return list_voices()[1]


def preview(voice, text=SAMPLE_TEXT):
    '''미리듣기는 speak.ps1 에 맡긴다. 숫자 읽기·한영 나누기·이음매까지 실제
    알림과 같은 길을 타야 들리는 것이 곧 들릴 것이 된다. 그 스크립트가
    settings.json 을 매번 새로 읽으므로 저장을 먼저 하고 부를 것.

    Windows PowerShell 5.1 로 부른다 — speak.ps1 이 5.1 을 전제로 쓰였고,
    UNC 에서 복사된 적 없는 원본이라 서명 정책에 걸려 Bypass 가 필요하다.'''
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
