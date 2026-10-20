# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import wx
import wx.adv

from utilities import APP_NAME
from utilities import get_asset_path


class TrayIcon(wx.adv.TaskBarIcon):

    def __init__(self, frame):
        super().__init__()
        self.frame = frame
        self.SetIcon(wx.Icon(get_asset_path('icon', 'icon.ico'), wx.BITMAP_TYPE_ICO), APP_NAME)
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_UP, lambda event: self.frame.show_window())

    def CreatePopupMenu(self):
        menu = wx.Menu()
        show = menu.Append(wx.ID_ANY, 'Show ' + APP_NAME)
        menu.AppendSeparator()
        quit = menu.Append(wx.ID_EXIT, 'Quit')
        menu.Bind(wx.EVT_MENU, lambda event: self.frame.show_window(), show)
        menu.Bind(wx.EVT_MENU, lambda event: self.frame.quit(), quit)
        return menu
