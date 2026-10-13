# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import winreg
import wx

from utilities import get_font
from utilities import mix


def is_windows_dark():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize')
        value, _ = winreg.QueryValueEx(key, 'AppsUseLightTheme')
        winreg.CloseKey(key)
        return value == 0
    except OSError:
        return True


class QuotaWidget(wx.Frame):

    WIDTH = 220
    ROW = 30
    PADDING = 10
    HEAD = 22

    def __init__(self, frame, theme, rect=None):
        style = wx.STAY_ON_TOP | wx.FRAME_TOOL_WINDOW | wx.FRAME_NO_TASKBAR | wx.BORDER_NONE
        super().__init__(frame, title='Quota Pace', style=style)
        self.frame = frame
        self.theme = theme
        self.limits = []
        self.drag = None
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_down)
        self.Bind(wx.EVT_MOTION, self.on_motion)
        self.Bind(wx.EVT_LEFT_UP, self.on_up)
        self.Bind(wx.EVT_RIGHT_UP, self.on_menu)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, lambda event: setattr(self, 'drag', None))
        self.fit()
        if rect and len(rect) == 2:
            self.SetPosition(wx.Point(*rect))
        else:
            area = wx.Display(0).GetClientArea()
            self.SetPosition(wx.Point(area.right - self.WIDTH - 24, area.bottom - self.GetSize()[1] - 24))

    def fit(self):
        rows = max(1, len(self.limits))
        self.SetSize(self.WIDTH, self.HEAD + rows * self.ROW + self.PADDING)

    def set_theme(self, theme):
        self.theme = theme
        self.Refresh()

    def update(self, data):
        self.limits = data.get('limits') or []
        self.fit()
        self.Refresh()

    def on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        theme = self.theme
        width, height = self.GetClientSize()
        dc.SetBackground(wx.Brush(wx.Colour(theme['face'])))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        gc.SetPen(wx.Pen(wx.Colour(theme['rim'])))
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        gc.DrawRectangle(0, 0, width - 1, height - 1)

        gc.SetFont(get_font(8, bold=True), wx.Colour(theme['text']))
        gc.DrawText('Quota Pace', self.PADDING, 5)
        gc.SetFont(get_font(7), wx.Colour(theme['dim']))
        note = 'used / elapsed'
        gc.DrawText(note, width - self.PADDING - gc.GetTextExtent(note)[0], 6)

        if not self.limits:
            gc.SetFont(get_font(8), wx.Colour(theme['dim']))
            gc.DrawText('no limits yet', self.PADDING, self.HEAD + 4)
            return
        bar_width = width - self.PADDING * 2
        for index, limit in enumerate(self.limits):
            top = self.HEAD + index * self.ROW
            gc.SetFont(get_font(8), wx.Colour(theme['text']))
            gc.DrawText(limit['name'], self.PADDING, top)
            right = '%d%%' % limit['percent']
            if limit.get('elapsed') is not None:
                right += ' / %d%%' % limit['elapsed']
            gc.DrawText(right, width - self.PADDING - gc.GetTextExtent(right)[0], top)
            bar_top = top + 16
            gc.SetPen(wx.TRANSPARENT_PEN)
            gc.SetBrush(wx.Brush(wx.Colour(theme['grid'])))
            gc.DrawRoundedRectangle(self.PADDING, bar_top, bar_width, 5, 2.5)
            if limit.get('elapsed') is not None:
                gc.SetBrush(wx.Brush(mix(theme['grid'], theme['dim'], 0.45)))
                gc.DrawRoundedRectangle(self.PADDING, bar_top,
                                        bar_width * limit['elapsed'] / 100.0, 5, 2.5)
            ahead = limit.get('elapsed') is not None and limit['percent'] > limit['elapsed']
            tint = theme['close'] if limit['severity'] == 'critical' else \
                theme['warn'] if limit['severity'] == 'warning' or ahead else theme['accent']
            gc.SetBrush(wx.Brush(wx.Colour(tint)))
            gc.DrawRoundedRectangle(self.PADDING, bar_top,
                                    bar_width * min(100, limit['percent']) / 100.0, 5, 2.5)

    def on_down(self, event):
        self.drag = (wx.GetMousePosition(), self.GetPosition(), False)
        self.CaptureMouse()

    def on_motion(self, event):
        if not self.drag or not event.Dragging():
            return
        start, origin, _ = self.drag
        delta = wx.GetMousePosition() - start
        if abs(delta.x) + abs(delta.y) > 3:
            self.drag = (start, origin, True)
            self.Move(origin + delta)

    def on_up(self, event):
        if self.HasCapture():
            self.ReleaseMouse()
        moved = self.drag and self.drag[2]
        self.drag = None
        if moved:
            self.frame.store_settings()
        else:
            self.frame.show_window()

    def on_menu(self, event):
        menu = wx.Menu()
        for label, handler in (('Open dashboard', lambda e: self.frame.show_window()),
                               ('Refresh now', lambda e: self.frame.usagebox.reload(
                                   force=True, git=True)),
                               ('Hide widget', lambda e: self.frame.hide_widget())):
            item = menu.Append(wx.ID_ANY, label)
            self.Bind(wx.EVT_MENU, handler, item)
        self.PopupMenu(menu)
        menu.Destroy()
