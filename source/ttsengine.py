# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import io
import wave

import numpy as np

import ttsconfig


SILENCE_LEVEL = 300 / 32768.0
EDGE_FADE = 0.008


class Engine:

    def __init__(self, threads=None):
        from supertonic import TTS
        self.tts = TTS(model=ttsconfig.MODEL_NAME, model_dir=ttsconfig.MODEL_DIR,
                       auto_download=False,
                       intra_op_num_threads=int(threads) if threads else None)
        self.rate = self.tts.sample_rate
        self.styles = {}

    def get_style(self, voice):
        if voice not in self.styles:
            custom = ttsconfig.list_custom_voices()
            if voice in custom:
                self.styles[voice] = self.tts.get_voice_style_from_path(custom[voice])
            else:
                self.styles[voice] = self.tts.get_voice_style(voice)
        return self.styles[voice]

    def synthesize(self, text, voice, lang, speed, steps, silence):
        try:
            style = self.get_style(voice)
        except Exception:
            style = self.get_style('F1')
        wav, _ = self.tts.synthesize(text, voice_style=style, total_steps=int(steps),
                                     speed=float(speed), silence_duration=float(silence),
                                     lang=lang)
        return np.asarray(wav, dtype=np.float32).reshape(-1, 1)


def fftconv(signal, response):
    size = len(signal) + len(response) - 1
    padded = 1 << (size - 1).bit_length()
    spectrum = np.fft.rfft(signal, padded) * np.fft.rfft(response, padded)
    return np.fft.irfft(spectrum, padded)[:size].astype(np.float32)


def make_response(rate, room, seed):
    length = max(8, int(rate * room))
    noise = np.random.default_rng(seed).standard_normal(length).astype(np.float32)
    response = noise * np.exp(-np.arange(length, dtype=np.float32) / (rate * room / 5.0))
    for delay, gain in ((13, 0.6), (21, 0.45), (31, 0.35), (43, 0.28), (57, 0.2)):
        index = int(rate * delay / 1000.0)
        if 0 < index < length:
            response[index] += gain
    response[0] = 0.0
    peak = float(np.max(np.abs(response)))
    return response / peak if peak > 1e-6 else response


def add_reverb(audio, rate, wet, room, width):
    # a mono voice gets a small room and a Haas delay so it opens up in stereo
    dry = audio.mean(axis=1)
    if not dry.size:
        return np.repeat(dry[:, None], 2, axis=1)
    width = max(0.0, min(1.0, width))
    wet_left = fftconv(dry, make_response(rate, room, 11))
    wet_right = fftconv(dry, make_response(rate, room, 29))
    size = max(len(wet_left), len(wet_right), len(dry))

    def pad(signal):
        return np.pad(signal, (0, size - len(signal))) if len(signal) < size else signal[:size]

    dry, wet_left, wet_right = pad(dry), pad(wet_left), pad(wet_right)
    haas = int(rate * 0.011 * width)
    dry_right = np.concatenate([np.zeros(haas, np.float32), dry])[:size] if haas else dry
    gain = 1.0 - 0.25 * wet
    stereo = np.stack([gain * dry + wet * wet_left, gain * dry_right + wet * wet_right], axis=1)
    peak = float(np.max(np.abs(stereo)))
    if peak > 0.99:
        stereo *= 0.99 / peak
    return stereo


def trim_silence(audio, rate, lead_ms, trail_ms):
    loud = np.flatnonzero(np.max(np.abs(audio), axis=1) > SILENCE_LEVEL)
    if not loud.size:
        return audio
    start = max(0, loud[0] - int(rate * lead_ms / 1000.0))
    end = min(len(audio), loud[-1] + 1 + int(rate * trail_ms / 1000.0))
    audio = audio[start:end].copy()
    # zero both edges so chunk joins do not click
    edge = min(int(rate * EDGE_FADE), len(audio) // 2)
    if edge:
        ramp = (np.arange(edge, dtype=np.float32) / edge)[:, None]
        audio[:edge] *= ramp
        audio[-edge:] *= ramp[::-1]
    return audio


def fade_tail(audio, rate, fade_ms):
    size = min(int(rate * fade_ms / 1000.0), len(audio) // 2)
    if size > 0:
        audio = audio.copy()
        audio[-size:] *= (np.arange(size, 0, -1, dtype=np.float32) / size)[:, None]
    return audio


def splice(parts):
    channels = max(part.shape[1] for part in parts)
    return np.concatenate([part if part.shape[1] == channels else
                           np.repeat(part, channels, axis=1) for part in parts])


def to_wav(audio, rate):
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype('<i2')
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as file:
        file.setnchannels(pcm.shape[1])
        file.setsampwidth(2)
        file.setframerate(rate)
        file.writeframes(pcm.tobytes())
    return buffer.getvalue()
