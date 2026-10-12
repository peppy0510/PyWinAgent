# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

agent-toolkit 의 TTS 설정을 고치는 페이지. PyWinAudio 랙처럼 이름 띠가 달린 판을
쌓고, 판마다 접을 수 있다. 판이 창보다 길어 세로로 굴린다.

값이 바뀔 때마다 파일에 쓰지 않는다 — 슬라이더를 끄는 동안 UNC 너머로 수십
번 쓰게 된다. 잠깐 쉬면 그때 한 번 쓴다.
'''


import wx

import ttsconfig

from controls import ActionCard
from controls import ChipGrid
from controls import Panel
from controls import ScrollArea
from controls import SettingCard
from controls import SliderCard

# 값이 멎고 이만큼 지나면 저장한다.
SAVE_DELAY = 500

# (키, 이름, 설명). 값의 범위는 ttsconfig 가 정한다.
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
        # 접힌 판의 키. 앱이 설정 페이지와 함께 쥐고 저장한다.
        self.folds = folds if folds is not None else set()
        self.on_folds = on_fold

        board = self.content
        voices, self.online = ttsconfig.list_voices()
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

    def get_status(self):
        # Voice 판 이름 띠의 부제로 쓴다. 좁은 창에서 잘려도 앞말이 뜻을 지니게 짧게.
        if self.online:
            return 'Supertonic running · clone voices included'
        return 'Supertonic not answering · built-in voices only'

    def add_panel(self, key, title, body, subtitle=''):
        return Panel(self.content, self.theme, 'tts.' + key, title, body, self.folds,
                     self.on_fold, subtitle=subtitle)

    def build(self):
        # 소리를 낼지 말지가 먼저다. 나머지는 낸다고 했을 때의 이야기라 뒤에 둔다.
        panels = [self.add_panel('notifications', 'Notifications', (self.cards['notify'],))]
        for title, keys in GROUPS:
            body = [self.cards[key] for key in keys]
            subtitle = ''
            if title == 'Voice':
                body = [self.grid, self.preview] + body
                subtitle = self.get_status()
            panels.append(self.add_panel(title.lower().replace(' ', '_'), title, body, subtitle))
        # 묶음마다 판 하나. 넓은 창에서는 여러 단으로 나눠 담긴다 (Wide layout).
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
        # 끄는 동안은 계속 미룬다. 손을 멈춘 뒤에 한 번만 쓴다.
        self.timer.Start(SAVE_DELAY, wx.TIMER_ONE_SHOT)

    def on_idle_save(self, event):
        self.flush()

    def flush(self):
        '''미뤄 둔 저장을 지금 한다. 페이지를 떠나거나 창을 닫을 때도 부른다.'''
        if not self.dirty:
            return None
        self.timer.Stop()
        self.dirty = False
        self.values = self.collect()
        return ttsconfig.save(self.values, self.raw)

    def on_preview(self):
        '''speak.ps1 이 settings.json 을 새로 읽으므로 저장을 먼저 해야
        지금 화면의 값 그대로 들린다.'''
        self.flush()
        ttsconfig.preview(self.grid.GetValue())

    def tick(self):
        pass
