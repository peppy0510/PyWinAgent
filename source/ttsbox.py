# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

agent-toolkit 의 TTS 설정을 고치는 페이지. Windows 11 설정처럼 그룹 제목
아래 카드를 쌓는다. 카드가 창보다 길어 세로로 굴린다.

값이 바뀔 때마다 파일에 쓰지 않는다 — 슬라이더를 끄는 동안 UNC 너머로 수십
번 쓰게 된다. 잠깐 쉬면 그때 한 번 쓴다.
'''


import wx

import ttsconfig

from controls import ActionCard
from controls import ChipGrid
from controls import ScrollArea
from controls import SettingCard
from controls import SliderCard
from utilities import get_font


MARGIN = 16
# 카드 테두리는 선이지만 제목은 글자라, 같은 여백이면 제목이 왼쪽으로 삐져나와 보인다.
TITLE_INSET = 3
TITLE_GAP = 8
CARD_GAP = 4
GROUP_GAP = 14

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

    def __init__(self, parent, theme):
        super().__init__(parent, theme)
        self.values, self.raw = ttsconfig.load()
        self.dirty = False
        self.cards = {}
        self.labels = []

        board = self.content
        voices, self.online = ttsconfig.list_voices()
        self.grid = ChipGrid(board, theme, voices, self.on_change, self.fit)
        self.grid.SetValue(self.values.get('voice', voices[0]))
        self.preview = ActionCard(board, theme, 'Preview',
                                  'Save and read a sample line aloud',
                                  'Play', self.on_preview)
        self.status = wx.StaticText(board, label=self.get_status())
        self.status.SetFont(get_font(8))

        for key, (label, description) in SWITCHES.items():
            self.cards[key] = SettingCard(board, theme, label, description,
                                          self.on_change)
        for key, (label, description) in SLIDERS.items():
            value = self.values.get(key, ttsconfig.DEFAULTS[key])
            self.cards[key] = SliderCard(board, theme, label, description,
                                         ttsconfig.bounds(key, value), self.on_change)
        for key, card in self.cards.items():
            card.SetValue(self.values.get(key, ttsconfig.DEFAULTS[key]))

        self.build()
        self.bind_children()
        self.apply_theme(theme)

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_idle_save)

    def get_status(self):
        if self.online:
            return 'Supertonic is running — clone voices included.'
        return 'Supertonic is not answering — showing built-in voices only.'

    def add_title(self, sizer, text):
        label = wx.StaticText(self.content, label=text)
        label.SetFont(get_font(10, bold=True))
        self.labels.append(label)
        sizer.Add(label, 0, wx.LEFT, MARGIN + TITLE_INSET)
        sizer.AddSpacer(TITLE_GAP)

    def build(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(MARGIN)

        self.add_title(sizer, 'Voice')
        sizer.Add(self.grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGIN)
        sizer.AddSpacer(CARD_GAP)
        sizer.Add(self.status, 0, wx.LEFT | wx.RIGHT, MARGIN + TITLE_INSET)
        sizer.AddSpacer(CARD_GAP * 2)
        sizer.Add(self.preview, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGIN)

        for title, keys in GROUPS:
            # 첫 묶음의 제목은 보이스 격자가 이미 달고 있다.
            if title != 'Voice':
                sizer.AddSpacer(GROUP_GAP)
                self.add_title(sizer, title)
            for key in keys:
                sizer.AddSpacer(CARD_GAP)
                sizer.Add(self.cards[key], 0, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGIN)

        sizer.AddSpacer(GROUP_GAP)
        self.content.SetSizer(sizer)

    def apply_theme(self, theme):
        self.set_theme(theme)
        for label in self.labels:
            label.SetForegroundColour(wx.Colour(theme['text']))
        self.status.SetForegroundColour(wx.Colour(theme['dim']))
        self.grid.set_theme(theme)
        self.preview.set_theme(theme)
        for card in self.cards.values():
            card.set_theme(theme)
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
