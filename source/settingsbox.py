# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

앱 자신의 설정. 다루는 도구의 설정은 각 페이지가 가지고, 여기에는 창에
관한 것만 둔다.
'''


import wx

from controls import SettingCard
from utilities import get_font


MARGIN = 16
TITLE_INSET = 3
TITLE_GAP = 8
CARD_GAP = 4
GROUP_GAP = 14


class SettingsBox(wx.Panel):

    def __init__(self, parent, theme, settings, on_change):
        super().__init__(parent)
        self.ontop = SettingCard(self, theme, 'Always on top',
                                 'Keep the window above others', on_change)
        self.autohide = SettingCard(self, theme, 'Auto hide menu',
                                    'Show the header only on hover', on_change)
        self.dark = SettingCard(self, theme, 'Dark theme',
                                'Use the dark colour scheme', on_change)
        self.cards = (self.ontop, self.autohide, self.dark)

        self.ontop.SetValue(settings.get('on_top', False))
        self.autohide.SetValue(settings.get('auto_hide_menu', False))
        self.dark.SetValue(settings.get('theme', 'dark') == 'dark')

        self.groups = []
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(MARGIN)
        for title, cards in (('Window', (self.ontop, self.autohide)),
                             ('Appearance', (self.dark,))):
            label = wx.StaticText(self, label=title)
            label.SetFont(get_font(10, bold=True))
            self.groups.append(label)
            sizer.Add(label, 0, wx.LEFT, MARGIN + TITLE_INSET)
            sizer.AddSpacer(TITLE_GAP)
            for index, card in enumerate(cards):
                if index:
                    sizer.AddSpacer(CARD_GAP)
                sizer.Add(card, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGIN)
            sizer.AddSpacer(GROUP_GAP)
        sizer.AddStretchSpacer()
        self.SetSizer(sizer)
        self.apply_theme(theme)

    def apply_theme(self, theme):
        self.SetBackgroundColour(wx.Colour(theme['bg']))
        for label in self.groups:
            label.SetForegroundColour(wx.Colour(theme['text']))
        for card in self.cards:
            card.set_theme(theme)
        self.Refresh()

    def tick(self):
        pass
