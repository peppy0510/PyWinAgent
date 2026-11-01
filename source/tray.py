# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import ctypes
import wx
import wx.adv

from ctypes import wintypes

from utilities import APP_NAME
from utilities import APP_VERSION
from utilities import get_asset_path


GA_ROOT = 2

# the shell keeps 127 characters of a tip and cuts the rest
TIP_LIMIT = 127

# a private handle: argtypes set here do not leak into other modules' user32 calls
user32 = ctypes.WinDLL('user32')
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND


def is_uncovered(window):
    rect = window.GetScreenRect()
    point = wintypes.POINT(rect.x + rect.width // 2, rect.y + rect.height // 2)
    handle = user32.WindowFromPoint(point)
    return bool(handle) and user32.GetAncestor(handle, GA_ROOT) == window.GetHandle()


class TrayIcon(wx.adv.TaskBarIcon):

    def __init__(self, frame):
        super().__init__()
        self.frame = frame
        self.icon = wx.Icon(get_asset_path('icon', 'icon.ico'), wx.BITMAP_TYPE_ICO)
        self.tip = APP_NAME
        self.SetIcon(self.icon, self.tip)
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_UP, self.on_left)

    def is_window_shown(self):
        return self.frame.IsShown() and not self.frame.IsIconized()

    def on_left(self, event):
        # a window behind others comes forward; only one in plain sight hides
        if self.is_window_shown() and is_uncovered(self.frame):
            self.frame.hide_window()
        else:
            self.frame.show_window()

    def set_tip(self, text):
        tip = f'{APP_NAME}\n{text}' if text else APP_NAME
        tip = tip[:TIP_LIMIT]
        if tip != self.tip:
            self.tip = tip
            self.SetIcon(self.icon, tip)

    def show_page(self, index):
        self.frame.show_window()
        self.frame.sidemenu.set_selection(index)
        self.frame.on_select(self.frame.sidemenu.get_page(index))

    def add(self, menu, label, action, checked=None):
        kind = wx.ITEM_NORMAL if checked is None else wx.ITEM_CHECK
        item = menu.Append(wx.ID_ANY, label, kind=kind)
        if checked is not None:
            item.Check(checked)
        if action is None:
            item.Enable(False)
        else:
            menu.Bind(wx.EVT_MENU, lambda event: action(), item)
        return item

    def CreatePopupMenu(self):
        frame = self.frame
        menu = wx.Menu()
        self.add(menu, f'{APP_NAME} {APP_VERSION}', None)
        menu.AppendSeparator()
        if self.is_window_shown():
            self.add(menu, 'Hide window', frame.hide_window)
        else:
            self.add(menu, 'Show window', frame.show_window)

        menu.AppendSeparator()
        current = frame.book.GetSelection() if self.is_window_shown() else -1
        for index, item in enumerate(frame.sidemenu.items):
            if item is None:
                menu.AppendSeparator()
                continue
            page = frame.sidemenu.get_page(index)
            self.add(menu, item[0], lambda index=index: self.show_page(index), page == current)

        # None in the list draws a separator, None as the action greys the item out
        extra = frame.get_tray_items()
        if extra:
            menu.AppendSeparator()
            for item in extra:
                if item is None:
                    menu.AppendSeparator()
                else:
                    self.add(menu, *item)

        menu.AppendSeparator()
        ontop = frame.settingsbox.ontop
        self.add(menu, 'Always on top', ontop.activate, ontop.GetValue())
        menu.AppendSeparator()
        self.add(menu, 'Quit', frame.quit)
        return menu
