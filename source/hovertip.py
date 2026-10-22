# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import ctypes
import wx

from ctypes import wintypes

from utilities import get_font
from utilities import get_text_width


FONT = 8
LINE = 15
PAD = 8
EDGE = 4
OFFSET_X = 14
OFFSET_Y = 18
MAX_WIDTH = 300

DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUNDSMALL = 3


class HoverTip(wx.PopupWindow):
    # a themed readout that follows the cursor; the native tooltip ignores the theme and
    # stays put while the mouse moves inside one window

    def __init__(self, parent):
        super().__init__(parent, wx.BORDER_NONE)
        self.theme = None
        self.lines = []
        self.owner = None
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        try:
            value = ctypes.c_int(DWMWCP_ROUNDSMALL)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(self.GetHandle()), DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass

    def show(self, owner, theme, lines, point=None):
        # lines: [(text, 'dim' or 'text')]
        self.owner = owner
        point = point or wx.GetMousePosition()
        font = get_font(FONT)
        lines = [(part, ink) for text, ink in lines for part in wrap(font, text)]
        width = max(get_text_width(font, text) for text, _ in lines) + PAD * 2
        height = len(lines) * LINE + EDGE * 2
        index = wx.Display.GetFromPoint(point)
        area = wx.Display(max(0, index)).GetClientArea()
        x, y = point.x + OFFSET_X, point.y + OFFSET_Y
        if x + width > area.x + area.width:
            x = point.x - OFFSET_X - width
        if y + height > area.y + area.height:
            y = point.y - OFFSET_Y // 2 - height
        self.SetSize(x, y, width, height)
        if lines != self.lines or theme is not self.theme:
            self.theme, self.lines = theme, lines
            self.Refresh()
        if not self.IsShown():
            self.Show()

    def hide(self):
        if self.IsShown():
            self.Hide()

    def on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        theme = self.theme
        if theme is None:
            return
        width, height = self.GetClientSize()
        dc.SetPen(wx.Pen(wx.Colour(theme['rim'])))
        dc.SetBrush(wx.Brush(wx.Colour(theme['band'])))
        dc.DrawRectangle(0, 0, width, height)
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return
        font = get_font(FONT)
        for index, (text, ink) in enumerate(self.lines):
            gc.SetFont(font, wx.Colour(theme[ink]))
            gc.DrawText(text, PAD, EDGE + index * LINE + (LINE - gc.GetTextExtent(text)[1]) / 2)


def wrap(font, text):
    if get_text_width(font, text) <= MAX_WIDTH:
        return [text]
    lines, line = [], ''
    for word in text.split(' '):
        candidate = word if not line else line + ' ' + word
        if line and get_text_width(font, candidate) > MAX_WIDTH:
            lines.append(line)
            line = word
        else:
            line = candidate
    return lines + [line] if line else lines


def show_hover_tip(window, theme, lines, point=None):
    top = window.GetTopLevelParent()
    tip = getattr(top, 'hover_tip', None)
    if not tip:
        tip = top.hover_tip = HoverTip(top)
    tip.show(window, theme, lines, point)


def hide_hover_tip(window):
    # a window refreshing its data must not hide the readout another window is showing
    tip = getattr(window.GetTopLevelParent(), 'hover_tip', None)
    if tip and tip.owner is window:
        tip.hide()
