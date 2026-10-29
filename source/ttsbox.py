# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import threading
import wx

import readaloud
import ttsconfig
import ttssetup

from controls import ActionCard
from controls import ChipGrid
from controls import ChoiceCard
from controls import Panel
from controls import ScrollArea
from controls import SettingCard
from controls import SliderCard
from utilities import call_painted

SAVE_DELAY = 500

HOTKEY_HINT = 'Click and press new keys to change'
CAPTURE_CAPTION = 'Press keys'

SLIDERS = {
    'chunk_min_chars': ('Sentence group', 'Short sentences are joined up to this length'),
    'join_gap_ms': ('Language join', 'Silence kept where Korean and English meet'),
    'threads': ('CPU threads', 'Threads per reading · 2 to 4 is fastest on this PC'),
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
    'readaloud': ('Read-aloud hotkey', 'Reads the selected text in any app'),
    'trim_silence': ('Trim silence', 'Cut the quiet edges off each chunk'),
    'reverb': ('Reverb', 'Add a small room around the voice'),
    'lang_pause': ('Pause at language switch', 'Add a comma where Korean and English meet'),
}

GROUPS = (
    ('Voice', ('speed', 'steps')),
    ('Language', ('lang', 'lang_pause', 'chunk_min_chars', 'join_gap_ms')),
    ('Performance', ('threads',)),
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

        self.hook = ActionCard(board, theme, 'Claude Code hook', '', 'Install', self.on_hook)
        self.hook.set_captions('Install', 'Remove')
        self.update_hook()
        self.hotkey_text = self.values.get('hotkey') or ttsconfig.DEFAULTS['hotkey']
        self.hotkey_card = ActionCard(board, theme, 'Hotkey', HOTKEY_HINT,
                                      self.hotkey_text, self.on_capture)
        self.hotkey_card.set_captions(CAPTURE_CAPTION)

        for key, (label, description) in SWITCHES.items():
            self.cards[key] = SettingCard(board, theme, label, description,
                                          self.on_change)
        languages = list(ttsconfig.LANGUAGES)
        current = self.values.get('lang', ttsconfig.DEFAULTS['lang'])
        if current not in [code for code, _ in languages]:
            languages.append((current, current.upper()))
        self.cards['lang'] = ChoiceCard(board, theme, 'Language',
                                        'Korean text still reads English words in English',
                                        languages, self.on_change)
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

        self.hotkey = readaloud.Hotkey(self.GetTopLevelParent(), self.hotkey_text)
        self.capturing = False
        self.apply_hotkey()

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
        panels = [self.add_panel('notifications', 'Notifications',
                                 (self.cards['notify'], self.hook, self.cards['readaloud'],
                                  self.hotkey_card))]
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
        values = {'voice': self.grid.GetValue(), 'hotkey': self.hotkey_text}
        for key, card in self.cards.items():
            values[key] = card.GetValue()
        return values

    def update_hook(self):
        state = ttssetup.get_hook_state()
        self.hook.set_caption('Remove' if state == 'installed' else 'Install')
        self.hook.set_description({
            'installed': 'Claude Code calls this app when a reply ends',
            'toolkit': 'The agent toolkit reads replies now · install to take over',
            'missing': 'Not installed in Claude Code',
        }[state])

    def on_hook(self):
        try:
            if ttssetup.get_hook_state() == 'installed':
                ttssetup.remove_hooks()
            else:
                ttssetup.install_hooks()
        except Exception as error:
            self.hook.set_description(f'Could not change the hook: {error}')
            return
        self.update_hook()

    def apply_hotkey(self, toggled=False):
        wanted = self.cards['readaloud'].GetValue()
        if wanted and not self.hotkey.active:
            ttssetup.take_listener()
            if not self.hotkey.set_active(True):
                self.hotkey_card.set_description('Another app holds ' + self.hotkey_text)
        elif not wanted and self.hotkey.active:
            self.hotkey.set_active(False)
            if toggled:
                ttssetup.restore_listener()

    def on_capture(self):
        # the live hotkey would fire while the new keys are pressed
        if self.capturing:
            return
        self.capturing = True
        self.paused = self.hotkey.active
        self.hotkey.set_active(False)
        self.hotkey_card.set_caption(CAPTURE_CAPTION)
        self.hotkey_card.set_description('Press the new keys · Esc keeps the old ones')
        threading.Thread(target=lambda: call_painted(self, self.set_capture, readaloud.capture()),
                         daemon=True).start()

    def set_capture(self, text):
        if not self:
            return
        self.capturing = False
        description = HOTKEY_HINT
        old = self.hotkey_text
        if text and text != old and self.hotkey.set_text(text):
            self.hotkey_text = text
        if self.paused and not self.hotkey.set_active(True):
            description = f'{self.hotkey_text} is taken by another app'
            self.hotkey.set_text(old)
            self.hotkey_text = old
            self.hotkey.set_active(True)
        elif self.hotkey_text != old:
            self.on_change()
        self.hotkey_card.set_captions(self.hotkey_text)
        self.hotkey_card.set_caption(self.hotkey_text)
        self.hotkey_card.set_description(description)

    def on_change(self):
        if self.cards['readaloud'].GetValue() != self.hotkey.active:
            self.apply_hotkey(toggled=True)
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
