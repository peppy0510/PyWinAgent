# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import threading
import wx

import ttsconfig

from controls import ActionCard
from controls import ChipGrid
from controls import Panel
from controls import ScrollArea
from controls import SettingCard
from controls import SliderCard
from utilities import call_painted

SAVE_DELAY = 500

SLIDERS = {
    'speed': ('Speed', 'How fast the voice reads'),
    'steps': ('Quality steps', 'More steps sound better and take longer'),
    'max_chars': ('Max characters', 'Longer messages are cut at this length'),
    'silence_duration': ('Sentence pause', 'Silence inserted between sentences'),
    'trim_lead_ms': ('Trim lead', 'Silence kept at the start of each chunk'),
    'trim_trail_ms': ('Trim trail', 'Silence kept at the end of each chunk'),
    'end_trail_ms': ('Ending trail', 'Silence kept after the very last word'),
    'end_fade_ms': ('Ending fade', 'Fade-out window on the final chunk'),
    'fade_in_ms': ('Fade in', 'Volume ramp when playback starts'),
    'fade_out_ms': ('Fade out', 'Volume ramp when playback stops'),
    'reverb_wet': ('Reverb amount', 'How much of the reverb is mixed in'),
    'reverb_room': ('Room size', 'Size of the simulated space'),
    'reverb_width': ('Stereo width', 'How far apart the left and right sides sit'),
}

SWITCHES = {
    'notify': ('Speak notifications', 'Read each finished reply aloud'),
    'trim_silence': ('Trim silence', 'Cut the quiet edges off each chunk'),
    'reverb': ('Reverb', 'Add a small room around the voice'),
}

GROUPS = (
    ('Voice', ('speed', 'steps')),
    ('Reading', ('max_chars', 'silence_duration')),
    ('Trimming', ('trim_silence', 'trim_lead_ms', 'trim_trail_ms',
                  'end_trail_ms', 'end_fade_ms')),
    ('Fade and reverb', ('fade_in_ms', 'fade_out_ms', 'reverb',
                         'reverb_wet', 'reverb_room', 'reverb_width')),
)


class TtsBox(ScrollArea):

    def __init__(self, parent, theme, folds=None, on_fold=None):
        super().__init__(parent, theme)
        self.values, self.raw = ttsconfig.load()
        self.dirty = False
        self.cards = {}
        self.folds = folds if folds is not None else set()
        self.on_folds = on_fold

        board = self.content
        voices = list(ttsconfig.BUILTIN_VOICES)
        self.online = True if ttsconfig.has_model() else None
        self.grid = ChipGrid(board, theme, voices, self.on_change, self.fit)
        self.grid.SetValue(self.values.get('voice', voices[0]))
        self.preview = ActionCard(board, theme, 'Preview',
                                  'Save and read a sample line aloud',
                                  'Play', self.on_preview)

        for key, (label, description) in SWITCHES.items():
            self.cards[key] = SettingCard(board, theme, label, description,
                                          self.on_change)
        for key, (label, description) in SLIDERS.items():
            value = self.values.get(key, ttsconfig.DEFAULTS[key])
            self.cards[key] = SliderCard(board, theme, label, description,
                                         ttsconfig.bounds(key, value), self.on_change,
                                         default=ttsconfig.DEFAULTS[key])
        for key, card in self.cards.items():
            card.SetValue(self.values.get(key, ttsconfig.DEFAULTS[key]))

        self.build()
        self.bind_children()
        self.apply_theme(theme)

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_idle_save)
        # the first run downloads the voice model, so look for it off the UI thread
        threading.Thread(target=self.load_voices, daemon=True).start()

    def load_voices(self):
        voices, online = ttsconfig.list_voices()
        if not online:
            call_painted(self, self.set_voices, voices, None)
            ttsconfig.ensure_model()
            voices, online = ttsconfig.list_voices()
        call_painted(self, self.set_voices, voices, online)

    def set_voices(self, voices, online):
        if not self:
            return
        self.online = online
        self.grid.set_options(voices)
        self.voice_panel.header.set_subtitle(self.get_status())
        self.relayout_panels()

    def get_status(self):
        if self.online is None:
            return 'Downloading the Supertonic model'
        if self.online:
            return 'Supertonic ready · clone voices included'
        return 'Supertonic model missing · Windows voice is used'

    def add_panel(self, key, title, body, subtitle=''):
        return Panel(self.content, self.theme, 'tts.' + key, title, body, self.folds,
                     self.on_fold, subtitle=subtitle)

    def build(self):
        panels = [self.add_panel('notifications', 'Notifications', (self.cards['notify'],))]
        for title, keys in GROUPS:
            body = [self.cards[key] for key in keys]
            subtitle = ''
            if title == 'Voice':
                body = [self.grid, self.preview] + body
                subtitle = self.get_status()
            panels.append(self.add_panel(title.lower().replace(' ', '_'), title, body, subtitle))
            if title == 'Voice':
                self.voice_panel = panels[-1]
        self.set_panels(panels)

    def on_fold(self):
        self.relayout_panels()
        if self.on_folds:
            self.on_folds()

    def apply_theme(self, theme):
        self.set_theme(theme)
        for child in self.content.GetChildren():
            if hasattr(child, 'set_theme'):
                child.set_theme(theme)
        self.Refresh()

    def collect(self):
        values = {'voice': self.grid.GetValue()}
        for key, card in self.cards.items():
            values[key] = card.GetValue()
        return values

    def on_change(self):
        self.dirty = True
        self.timer.Start(SAVE_DELAY, wx.TIMER_ONE_SHOT)

    def on_idle_save(self, event):
        self.flush()

    def flush(self):
        if not self.dirty:
            return None
        self.timer.Stop()
        self.dirty = False
        self.values = self.collect()
        return ttsconfig.save(self.values, self.raw)

    def on_preview(self):
        self.flush()
        ttsconfig.preview(self.grid.GetValue())

    def tick(self):
        pass
