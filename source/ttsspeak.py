# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

description:
Reads text aloud with the local Supertonic model, one process per reading.
The first sentence plays as soon as it is ready while a thread renders the rest.
A newer reading claims the player: a normal one lets the old reading finish its
sentence, an interrupting one (read-aloud) cuts it short. Falls back to SAPI.

usage: pythonw ttsspeak.py --text TEXT [--voice F1] [--interrupt]
       pythonw ttsspeak.py --file PATH [--voice F1] [--interrupt]
'''


import argparse
import os
import re
import sys
import threading
import time
import winsound

import psutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numnorm  # noqa: E402
import ttsconfig  # noqa: E402
import ttsengine  # noqa: E402


ENGINE_DEFAULTS = {
    'lang': 'ko',
    'chunk_min_chars': 40,
    'lang_pause': False,
    'join_gap_ms': 20,
}

TEMP_DIR = os.path.join(os.environ.get('TEMP', os.path.expanduser('~')), 'PyWinAgent', 'tts')
PID_PATH = os.path.join(TEMP_DIR, 'player.pid')
MUTEX_NAME = 'Local\\PyWinAgentTtsPlayer'

DEBUG = bool(os.environ.get('PYWINAGENT_TTS_DEBUG'))
STARTED = time.monotonic()

WAIT_NORMAL = 8.0
WAIT_INTERRUPT = 2.5
ITEM_TIMEOUT = 90.0

KOREAN = re.compile('[가-힣ㄱ-ㅎㅏ-ㅣ]')
LATIN = re.compile('[A-Za-z]')
SENTENCE_END = re.compile(r'(?<=[.!?。！？])\s+')


def debug(message):
    if not DEBUG:
        return
    try:
        os.makedirs(TEMP_DIR, exist_ok=True)
        with open(os.path.join(TEMP_DIR, 'speak-debug.log'), 'a', encoding='utf-8') as file:
            file.write('%s pid=%d +%.2fs %s\n' % (time.strftime('%H:%M:%S'), os.getpid(),
                                                  time.monotonic() - STARTED, message))
    except OSError:
        pass


def load_config(voice=None):
    config = dict(ENGINE_DEFAULTS)
    config.update(ttsconfig.DEFAULTS)
    config.update(ttsconfig.read_raw())
    if voice:
        config['voice'] = voice
    return config


def normalize(text):
    if not (re.search(r'\d', text) or re.search('[A-Z]{2}', text)
            or re.search('tkmix', text, re.I)):
        return text
    try:
        return numnorm.normalize(text) or text
    except Exception:
        return text


def add_lang_pauses(text):
    text = re.sub(r'([가-힣])\s+([A-Za-z])', r'\1, \2', text)
    return re.sub(r'([A-Za-z])\s+([가-힣])', r'\1, \2', text)


def split_chunks(text, min_chars):
    text = text.strip()
    parts = [part.strip() for part in SENTENCE_END.split(text) if part.strip()]
    if len(parts) <= 1:
        return [text] if text else []
    chunks = []
    buffer = ''
    for part in parts:
        buffer = buffer + ' ' + part if buffer else part
        if len(buffer) >= min_chars:
            chunks.append(buffer)
            buffer = ''
    if buffer:
        chunks.append(buffer)
    return chunks


def split_lang_runs(text, default_lang):
    # one request carries one language token, so English inside Korean is read in its own run
    runs = []
    buffer = ''
    current = None
    for char in text:
        kind = 'ko' if KOREAN.match(char) else 'en' if LATIN.match(char) else None
        if kind is None or kind == current or current is None:
            buffer += char
            current = current or kind
            continue
        runs.append({'text': buffer, 'lang': current})
        buffer = char
        current = kind
    if buffer.strip():
        runs.append({'text': buffer, 'lang': current or default_lang})
    return [run for run in runs if run['text'].strip()]


def split_units(text, min_chars, default_lang):
    text = text.strip()
    if not text:
        return []
    has_korean = bool(re.search('[가-힣]', text))
    has_latin = bool(LATIN.search(text))
    if not (has_korean and has_latin):
        lang = 'en' if has_latin else default_lang
        return [{'runs': [{'text': chunk, 'lang': lang}]}
                for chunk in split_chunks(text, min_chars)]
    units = []
    for chunk in split_chunks(text, min_chars):
        runs = split_lang_runs(chunk, default_lang)
        if runs:
            units.append({'runs': runs})
    return units


def plan_items(units, config):
    # the first sentence plays one language run at a time so the first sound comes early
    items = []
    first = units[0]['runs']
    for index, run in enumerate(first):
        items.append({'runs': [run],
                      'lead': config['trim_lead_ms'] if index == 0 else config['join_gap_ms'],
                      'trail': (config['trim_trail_ms'] if index == len(first) - 1
                                else config['join_gap_ms'])})
    items.extend(dict(unit) for unit in units[1:])
    items[-1]['trail'] = config['end_trail_ms']
    return items


def render_run(engine, run, config, lead, trail):
    audio = engine.synthesize(run['text'], config['voice'], run['lang'] or config['lang'],
                              config['speed'], config['steps'], config['silence_duration'])
    if config['reverb']:
        try:
            audio = ttsengine.add_reverb(audio, engine.rate, float(config['reverb_wet']),
                                         float(config['reverb_room']),
                                         float(config['reverb_width']))
        except Exception:
            pass
    if config['trim_silence']:
        audio = ttsengine.trim_silence(audio, engine.rate, lead, trail)
    return audio


def render_item(engine, item, config):
    runs = item['runs']
    lead = item.get('lead', config['trim_lead_ms'])
    trail = item.get('trail', config['trim_trail_ms'])
    parts = []
    for index, run in enumerate(runs):
        try:
            parts.append(render_run(
                engine, run, config,
                lead if index == 0 else config['join_gap_ms'],
                trail if index == len(runs) - 1 else config['join_gap_ms']))
        except Exception:
            continue
    return ttsengine.splice(parts) if parts else None


class Player:

    def __init__(self, interrupt):
        import win32event
        self.win32event = win32event
        self.pid = os.getpid()
        self.mode = 'fast' if interrupt else 'normal'
        os.makedirs(TEMP_DIR, exist_ok=True)

    def locked(self, action):
        mutex = self.win32event.CreateMutex(None, False, MUTEX_NAME)
        self.win32event.WaitForSingleObject(mutex, 5000)
        try:
            return action()
        finally:
            self.win32event.ReleaseMutex(mutex)

    def read_owner(self):
        try:
            with open(PID_PATH, encoding='utf-8') as file:
                return file.read().split()
        except OSError:
            return []

    def claim(self):
        def action():
            owner = self.read_owner()
            with open(PID_PATH, 'w', encoding='utf-8') as file:
                file.write('%d %s' % (self.pid, self.mode))
            if owner and owner[0].isdigit() and int(owner[0]) != self.pid:
                return int(owner[0])
            return None
        old = self.locked(action)
        self.clear(old)

    def clear(self, old):
        # the old reading gets its grace period, then is stopped so voices never overlap
        if not old:
            return
        try:
            process = psutil.Process(old)
            if 'python' not in process.name().lower():
                return
            process.wait(WAIT_INTERRUPT if self.mode == 'fast' else WAIT_NORMAL)
        except psutil.TimeoutExpired:
            try:
                process.kill()
            except psutil.Error:
                pass
            time.sleep(0.08)
        except psutil.Error:
            pass

    def is_current(self):
        owner = self.read_owner()
        return not owner or owner[0] == str(self.pid)

    def release(self):
        def action():
            if self.read_owner()[:1] == [str(self.pid)]:
                try:
                    os.remove(PID_PATH)
                except OSError:
                    pass
        self.locked(action)


def speak_sapi(text):
    try:
        import win32com.client
        voice = win32com.client.Dispatch('SAPI.SpVoice')
        voices = voice.GetVoices('Language=412')
        if voices.Count:
            voice.Voice = voices.Item(0)
        voice.Speak(text)
    except Exception:
        pass


def wait_ready(event, player):
    deadline = time.monotonic() + ITEM_TIMEOUT
    while not event.wait(0.025):
        if not player.is_current() or time.monotonic() > deadline:
            return False
    return True


def play(items, engine, config, player):
    rendered = [None] * len(items)
    ready = [threading.Event() for _ in items]
    stopped = threading.Event()

    def produce():
        for index in range(1, len(items)):
            if stopped.is_set():
                break
            try:
                rendered[index] = render_item(engine, items[index], config)
            except Exception:
                rendered[index] = None
            ready[index].set()

    rendered[0] = render_item(engine, items[0], config)
    ready[0].set()
    debug('item 0 ready of %d' % len(items))
    threading.Thread(target=produce, daemon=True).start()

    player.claim()
    debug('claimed')
    try:
        for index in range(len(items)):
            if not wait_ready(ready[index], player) or not player.is_current():
                break
            audio = rendered[index]
            rendered[index] = None
            if audio is None or not len(audio):
                continue
            if index == len(items) - 1:
                audio = ttsengine.fade_tail(audio, engine.rate, config['end_fade_ms'])
            debug('play %d %.2fs' % (index, len(audio) / float(engine.rate)))
            winsound.PlaySound(ttsengine.to_wav(audio, engine.rate),
                               winsound.SND_MEMORY | winsound.SND_NODEFAULT)
    finally:
        stopped.set()
        player.release()
        debug('done')


def speak(text, voice=None, interrupt=False):
    config = load_config(voice)
    text = normalize(text)
    if config['lang_pause']:
        text = add_lang_pauses(text)
    units = split_units(text, int(config['chunk_min_chars']), config['lang'])
    if not units:
        return
    player = Player(interrupt)

    engine = None
    if ttsconfig.ensure_model():
        try:
            engine = ttsengine.Engine()
        except Exception:
            engine = None
    debug('engine %s, %d units' % ('loaded' if engine else 'missing', len(units)))
    if engine is None:
        player.claim()
        try:
            speak_sapi(text)
        finally:
            player.release()
        return
    play(plan_items(units, config), engine, config, player)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--text')
    parser.add_argument('--file')
    parser.add_argument('--voice')
    parser.add_argument('--interrupt', action='store_true')
    args = parser.parse_args()
    text = args.text or ''
    if args.file:
        with open(args.file, encoding='utf-8') as file:
            text = file.read()
    if text.strip():
        speak(text, args.voice, args.interrupt)


if __name__ == '__main__':
    main()
