# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import ctypes
import json
import math
import os
import wx

from ctypes import wintypes


APP_NAME = 'PyWinAgent'
APP_VERSION = '0.1.0'
APP_AUTHOR = 'Taehong Kim'
APP_EMAIL = 'peppy0510@hotmail.com'
APP_HOME = 'https://github.com/peppy0510/PyWinAgent'

CONTROL_HEIGHT = 28
ROUND_SIZE = 46
CARD_HEIGHT = 50
CARD_RADIUS = 6
CONTROL_GAP = 4

PANEL_RADIUS = 3
HEADER_BAND = 30
PANEL_MARGIN = 8
PANEL_GAP = 3
PANEL_PAD = 14
BUTTON_HEIGHT = 22
BUTTON_PAD = 11
BUTTON_GAP = 4
BUTTON_FONT = 8.5
BAND_INSET = (HEADER_BAND - BUTTON_HEIGHT) // 2
# choice chips: 7.5 pt is a whole 10 px, and its 7 px capitals sit 5 px from either edge
CHIP_HEIGHT = 17
CHIP_PAD = 7
CHIP_FONT = 7.5

TITLEBAR_HEIGHT = 32
CAPTION_WIDTH = 46

GWL_STYLE = -16
WS_CAPTION = 0x00C00000
WS_CLIPSIBLINGS = 0x04000000

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020

RDW_ALLCHILDREN = 0x0080
RDW_UPDATENOW = 0x0100

DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1 = 19
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35


THEMES = {
    'dark': {
        'bg': '#141517',
        'face': '#1d1f23',
        'band': '#17181b',
        'rim': '#2b2e33',
        'tick': '#6b727c',
        'tick_major': '#c8cdd4',
        'text': '#e6e9ed',
        'dim': '#8b929b',
        'faint': '#5a5e65',
        'accent': '#4c9aff',
        'on_accent': '#101215',
        'control': '#26282d',
        'control_hover': '#2f3237',
        'control_down': '#202226',
        'edge': '#363940',
        'track': '#2c2f35',
        'thumb': '#c4c7cc',
        'thumb_hover': '#e6e7e9',
        'thumb_line': '#2a2d32',
        'close': '#c42b1c',
        'mint': '#3fd6a0',
        'grid': '#2c2f35',
        'warn': '#ff9a3d',
        'titlebar_dark': True,
    },
    'light': {
        'bg': '#f4f5f7',
        'face': '#ffffff',
        'band': '#eef0f2',
        'rim': '#d5d9df',
        'tick': '#9aa1aa',
        'tick_major': '#3d434b',
        'text': '#1d2126',
        'dim': '#6b727c',
        'faint': '#a3a9b1',
        'accent': '#2b6cb0',
        'on_accent': '#ffffff',
        'control': '#eef0f3',
        'control_hover': '#e2e5ea',
        'control_down': '#d8dce2',
        'edge': '#c9ced5',
        'track': '#d5d9df',
        'thumb': '#5b626b',
        'thumb_hover': '#3d434b',
        'thumb_line': '#ffffff',
        'close': '#c42b1c',
        'mint': '#0f9d68',
        'grid': '#e2e5ea',
        'warn': '#b7791f',
        'titlebar_dark': False,
    },
}


class WindowRect(ctypes.Structure):
    _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                ('right', ctypes.c_long), ('bottom', ctypes.c_long)]


def get_colour_ref(colour):
    value = wx.Colour(colour)
    return (value.Blue() << 16) | (value.Green() << 8) | value.Red()


def apply_titlebar_theme(window, theme):
    try:
        handle = wintypes.HWND(window.GetHandle())
        value = ctypes.c_int(1 if theme['titlebar_dark'] else 0)
        for attribute in (DWMWA_USE_IMMERSIVE_DARK_MODE,
                          DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                handle, attribute, ctypes.byref(value), ctypes.sizeof(value))

        value = ctypes.c_int(get_colour_ref(theme['bg']))
        for attribute in (DWMWA_CAPTION_COLOR, DWMWA_BORDER_COLOR):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                handle, attribute, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        return

    if window.IsShown():
        width, height = window.GetSize()
        window.SetSize(width, height + 1)
        window.SetSize(width, height)


def apply_no_caption(window):
    try:
        handle = wintypes.HWND(window.GetHandle())
        # wx 3.3 keeps WS_CAPTION without wx.CAPTION and the system caption covers the title bar
        style = ctypes.windll.user32.GetWindowLongW(handle, GWL_STYLE)
        ctypes.windll.user32.SetWindowLongW(handle, GWL_STYLE, style & ~WS_CAPTION)
        ctypes.windll.user32.SetWindowPos(handle, 0, 0, 0, 0, 0,
                                          SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER |
                                          SWP_NOACTIVATE | SWP_FRAMECHANGED)
    except Exception:
        pass


def apply_clip_siblings(window):
    try:
        handle = wintypes.HWND(window.GetHandle())
        # wx children lack WS_CLIPSIBLINGS, so a repainting sibling erases a window floated over it
        style = ctypes.windll.user32.GetWindowLongW(handle, GWL_STYLE)
        ctypes.windll.user32.SetWindowLongW(handle, GWL_STYLE, style | WS_CLIPSIBLINGS)
    except Exception:
        pass


def paint_now(window):
    # WM_PAINT is only generated once the queue is empty, which a moving mouse never lets happen
    try:
        ctypes.windll.user32.RedrawWindow(wintypes.HWND(window.GetHandle()), None, None,
                                          RDW_UPDATENOW | RDW_ALLCHILDREN)
    except Exception:
        pass


def call_painted(window, function, *args):
    def run():
        function(*args)
        if window:
            paint_now(window)
    wx.CallAfter(run)


def get_frame_margins(window):
    rect = WindowRect()
    try:
        if ctypes.windll.dwmapi.DwmGetWindowAttribute(
                wintypes.HWND(window.GetHandle()), DWMWA_EXTENDED_FRAME_BOUNDS,
                ctypes.byref(rect), ctypes.sizeof(rect)) != 0:
            return (0, 0, 0, 0)
    except Exception:
        return (0, 0, 0, 0)

    outer = window.GetScreenRect()
    return (rect.left - outer.x, rect.top - outer.y,
            outer.x + outer.width - rect.right, outer.y + outer.height - rect.bottom)


def get_asset_path(*parts):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, 'assets', *parts)


def get_settings_path():
    return os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')),
                        APP_NAME, 'settings.json')


def load_settings():
    try:
        with open(get_settings_path(), encoding='utf-8') as file:
            return json.load(file)
    except Exception:
        return {}


def save_settings(settings):
    try:
        path = get_settings_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as file:
            json.dump(settings, file, ensure_ascii=False, indent=2)
    except Exception:
        pass


def mix(colour, other, ratio):
    first, second = wx.Colour(colour), wx.Colour(other)
    return wx.Colour(*[round(a + (b - a) * ratio) for a, b in
                       ((first.Red(), second.Red()),
                        (first.Green(), second.Green()),
                        (first.Blue(), second.Blue()))])


def shade(colour, factor):
    base = wx.Colour(colour)
    return wx.Colour(min(255, int(base.Red() * factor)),
                     min(255, int(base.Green() * factor)),
                     min(255, int(base.Blue() * factor)))


def draw_card_rim(gc, colour, x, y, width, height, radius=CARD_RADIUS):
    # a 1 px pen straddles two pixels on the left and top, so fill the rim instead
    path = gc.CreatePath()
    path.AddRoundedRectangle(x, y, width, height, radius)
    path.AddRoundedRectangle(x + 1, y + 1, width - 2, height - 2, max(0, radius - 1))
    gc.SetPen(wx.TRANSPARENT_PEN)
    gc.SetBrush(wx.Brush(wx.Colour(colour)))
    gc.FillPath(path, wx.ODDEVEN_RULE)


FONTS = {}


def get_font(size, bold=False):
    key = (size, bold)
    if key not in FONTS:
        # wxPython 4.3 rejects float sizes in wx.Font()
        info = wx.FontInfo(size).FaceName('Segoe UI')
        FONTS[key] = wx.Font(info.Bold() if bold else info)
    return FONTS[key]


INKS = {}
WIDTHS = {}


def get_luma(image, x, y):
    # ClearType shifts each channel by a third of a pixel
    return (image.GetRed(x, y) + image.GetGreen(x, y) + image.GetBlue(x, y)) / 3.0


def get_ink(font):
    key = font.GetNativeFontInfoDesc()
    if key not in INKS:
        bitmap = wx.Bitmap(80, 80, 24)
        dc = wx.MemoryDC(bitmap)
        dc.SetBackground(wx.BLACK_BRUSH)
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        gc.SetFont(font, wx.WHITE)
        gc.DrawText('H', 4, 0)
        del gc
        dc.SelectObject(wx.NullBitmap)
        image = bitmap.ConvertToImage()
        rows = [y for y in range(80) if any(get_luma(image, x, y) > 127 for x in range(80))]
        INKS[key] = (rows[0], rows[-1]) if rows else (0, 0)
    return INKS[key]


def get_text_width(font, text):
    key = (font.GetNativeFontInfoDesc(), text)
    if key not in WIDTHS:
        dc = wx.MemoryDC(wx.Bitmap(1, 1))
        gc = wx.GraphicsContext.Create(dc)
        gc.SetFont(font, wx.BLACK)
        WIDTHS[key] = int(math.ceil(gc.GetTextExtent(text)[0]))
        del gc
        dc.SelectObject(wx.NullBitmap)
    return WIDTHS[key]


SPANS = {}


def get_ink_span(font, text, colour='#ffffff', back='#000000'):
    # GDI+ extents pad the right side (2-3 px measured), so centre on the ink
    key = (font.GetNativeFontInfoDesc(), text, colour, back)
    if key not in SPANS:
        width = get_text_width(font, text) + 40
        fore, ground = wx.Colour(colour), wx.Colour(back)
        bitmap = wx.Bitmap(width, 60, 24)
        dc = wx.MemoryDC(bitmap)
        dc.SetBackground(wx.Brush(ground))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        gc.SetFont(font, fore)
        gc.DrawText(text, 20, 10)
        del gc
        dc.SelectObject(wx.NullBitmap)
        image = bitmap.ConvertToImage()
        base = (ground.Red() + ground.Green() + ground.Blue()) / 3.0
        limit = abs((fore.Red() + fore.Green() + fore.Blue()) / 3.0 - base) / 2.0
        columns = [x for x in range(width)
                   if any(abs(get_luma(image, x, y) - base) > limit for y in range(60))]
        SPANS[key] = (columns[0] - 20, columns[-1] - 20) if columns else (0, 0)
    return SPANS[key]


def get_text_top(font, top, height):
    ink_top, ink_bottom = get_ink(font)
    return int(round(top + (height - (ink_bottom - ink_top + 1)) / 2.0 - ink_top))


def draw_text_in(gc, text, rect, font, colour, align='center', back=None):
    gc.SetFont(font, wx.Colour(colour))
    width = get_text_width(font, text)
    if back is None:
        ink_left, ink_right = get_ink_span(font, text)
    else:
        ink_left, ink_right = get_ink_span(font, text, colour, back)
    if align == 'center':
        x = int(round(rect.x + (rect.width - (ink_right - ink_left + 1)) / 2.0 - ink_left))
    elif align == 'right':
        x = rect.x + rect.width - 1 - ink_right
    else:
        x = rect.x - ink_left
    gc.DrawText(text, x, get_text_top(font, rect.y, rect.height))
    return width


def fill_rect(gc, colour, x, y, width, height, radius=0):
    gc.SetPen(wx.TRANSPARENT_PEN)
    gc.SetBrush(wx.Brush(wx.Colour(colour)))
    if radius:
        gc.DrawRoundedRectangle(x, y, width, height, radius)
    else:
        gc.DrawRectangle(x, y, width, height)


def draw_frame(gc, colour, x, y, width, height):
    fill_rect(gc, colour, x, y, width, 1)
    fill_rect(gc, colour, x, y + height - 1, width, 1)
    fill_rect(gc, colour, x, y, 1, height)
    fill_rect(gc, colour, x + width - 1, y, 1, height)


def draw_chevron(gc, name, cx, cy, size, colour):
    gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(colour)).Width(1.5)
                           .Cap(wx.CAP_ROUND).Join(wx.JOIN_ROUND)))
    gc.SetBrush(wx.TRANSPARENT_BRUSH)
    half = size / 2
    path = gc.CreatePath()
    if name == 'down':
        path.MoveToPoint(cx - half * 0.7, cy - half * 0.35)
        path.AddLineToPoint(cx, cy + half * 0.35)
        path.AddLineToPoint(cx + half * 0.7, cy - half * 0.35)
    else:
        path.MoveToPoint(cx - half * 0.35, cy - half * 0.7)
        path.AddLineToPoint(cx + half * 0.35, cy)
        path.AddLineToPoint(cx - half * 0.35, cy + half * 0.7)
    gc.StrokePath(path)


class Canvas(wx.Panel):

    def __init__(self, parent, theme):
        super().__init__(parent, style=wx.FULL_REPAINT_ON_RESIZE)
        self.theme = theme
        # AutoBufferedPaintDC asserts on every paint without BG_STYLE_PAINT
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetDoubleBuffered(True)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: None)

    def set_theme(self, theme):
        self.theme = theme
        self.Refresh()

    def on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(wx.Colour(self.theme['bg'])))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return
        gc.SetAntialiasMode(wx.ANTIALIAS_DEFAULT)
        width, height = self.GetClientSize()
        self.draw(gc, width, height)

    def draw(self, gc, width, height):
        pass

    def draw_backdrop(self, gc):
        parent = self.GetParent()
        if not isinstance(parent, Canvas):
            return
        x, y = self.GetPosition()
        width, height = parent.GetClientSize()
        gc.PushState()
        gc.Translate(-x, -y)
        parent.draw(gc, width, height)
        gc.PopState()

    def fit_text(self, gc, text, limit):
        # no gc.Clip: draw_backdrop repaints the parent and its ResetClip drops ours
        if gc.GetTextExtent(text)[0] <= limit:
            return text
        while text and gc.GetTextExtent(text + '…')[0] > limit:
            text = text[:-1]
        return text + '…'

    def draw_centered_text(self, gc, text, cx, y, font, colour):
        gc.SetFont(font, wx.Colour(colour))
        tw, th = gc.GetTextExtent(text)[:2]
        gc.DrawText(text, cx - tw / 2, y)
        return th
