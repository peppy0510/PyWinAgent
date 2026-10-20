# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import glob
import json
import os
import subprocess
import sys


APPDATA = os.environ.get('APPDATA', os.path.expanduser('~'))
LOCALAPPDATA = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))

SETTINGS_PATH = os.environ.get('PYWINAGENT_TTS_SETTINGS',
                               os.path.join(APPDATA, 'PyWinAgent', 'tts.json'))
MODEL_NAME = 'supertonic-3'
MODEL_DIR = os.environ.get('PYWINAGENT_TTS_MODEL',
                           os.path.join(LOCALAPPDATA, 'PyWinAgent', 'supertonic3'))
# clone voices live outside the model folder because a model download replaces it whole
VOICES_DIR = os.environ.get('PYWINAGENT_TTS_VOICES',
                            os.path.join(APPDATA, 'PyWinAgent', 'voices'))
SPEAK_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ttsspeak.py')

ONNX_FILES = ('duration_predictor.onnx', 'text_encoder.onnx',
              'vector_estimator.onnx', 'vocoder.onnx')

SAMPLE_TEXT = '안녕하세요. 지금 이 목소리로 알림을 읽어 드립니다.'

BUILTIN_VOICES = ('F1', 'F2', 'F3', 'F4', 'F5', 'M1', 'M2', 'M3', 'M4', 'M5')

DEFAULTS = {
    'notify': True,
    'readaloud': False,
    'hotkey': 'Ctrl+Alt+Shift+9',
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
    'lang': 'ko',
    'lang_pause': False,
    'chunk_min_chars': 40,
    'join_gap_ms': 20,
    'threads': 4,
}

LANGUAGES = (('en', 'English'), ('ko', 'Korean'), ('ja', 'Japanese'))

RANGES = {
    'chunk_min_chars': (10, 300, 10, 0),
    'join_gap_ms': (0, 200, 10, 0),
    # ONNX Runtime's default of one thread per logical core ran three times slower
    # (i7-13700, 24 threads: 2.0 s against 0.6 s for a short sentence); 2 to 4 is fastest
    'threads': (1, 16, 1, 0),
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
    # untouched defaults stay out of the file so the speaker defaults can still change
    merged = dict(raw)
    for key, value in values.items():
        if key in raw or value != DEFAULTS.get(key):
            merged[key] = value

    try:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, 'w', encoding='utf-8') as file:
            json.dump(merged, file, ensure_ascii=False, indent=2)
            file.write('\n')
    except Exception as error:
        return str(error)
    return None


def has_model():
    return all(os.path.exists(os.path.join(MODEL_DIR, 'onnx', name)) for name in ONNX_FILES)


def list_custom_voices():
    paths = glob.glob(os.path.join(VOICES_DIR, '*.json'))
    return {os.path.splitext(os.path.basename(path))[0]: path for path in paths}


def list_voices():
    if not has_model():
        return list(BUILTIN_VOICES), False
    names = [os.path.splitext(os.path.basename(path))[0]
             for path in glob.glob(os.path.join(MODEL_DIR, 'voice_styles', '*.json'))]
    names = set(names or BUILTIN_VOICES) | set(list_custom_voices())
    names = sorted(names, key=lambda name: (
        name[:1], int(name[1:]) if name[1:].isdigit() else 0, name))
    return names, True


def ensure_model():
    # two processes downloading at once would trample the same temporary folder
    if has_model():
        return True
    import msvcrt
    os.makedirs(os.path.dirname(MODEL_DIR), exist_ok=True)
    with open(MODEL_DIR + '.lock', 'a+b') as lock:
        lock.seek(0)
        while True:
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
                break
            except OSError:
                continue
        try:
            if not has_model():
                from supertonic.loader import download_model
                download_model(MODEL_DIR, MODEL_NAME)
        except Exception:
            pass
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    return has_model()


def get_pythonw():
    path = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    return path if os.path.exists(path) else sys.executable


def preview(voice, text=SAMPLE_TEXT):
    command = [get_pythonw(), SPEAK_SCRIPT, '--text', text, '--interrupt']
    if voice:
        command += ['--voice', voice]
    try:
        return subprocess.Popen(command, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:
        return None
