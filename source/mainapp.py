# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import os
import subprocess
import threading
import time
import wx
import wx.adv

from companions import QuotaWidget
from companions import is_windows_dark
from settingsbox import SettingsBox
from sidemenu import SideMenu
from titlebar import TitleBar
from tray import TrayIcon
from ttsbox import TtsBox
from updatebox import UpdateBox
from updater import Updater
from updater import restart_source
from usagebox import UsageBox
from utilities import APP_NAME
from utilities import THEMES
from utilities import apply_clip_siblings
from utilities import apply_no_caption
from utilities import apply_titlebar_theme
from utilities import get_asset_path
from utilities import get_frame_margins
from utilities import load_settings
from utilities import paint_now
from utilities import save_settings


TICK_INTERVAL = 150
DEFAULT_SIZE = (480, 720)
MIN_SIZE = (360, 480)

MENU_ITEMS = (('Usage', 'chart'), ('TTS', 'sound'), None, ('Settings', 'settings'))

FRAME_STYLE = wx.DEFAULT_FRAME_STYLE & ~wx.CAPTION

MIN_VISIBLE_WIDTH = 120
MIN_VISIBLE_HEIGHT = 32


class Pacer(threading.Thread):
    # WM_TIMER starves while the mouse keeps moving; a thread keeps the beat

    def __init__(self, frame):
        super().__init__(name='tick-pacer', daemon=True)
        self.frame = frame
        self.running = True
        self.pending = False

    def run(self):
        interval = TICK_INTERVAL / 1000
        target = time.perf_counter()
        while self.running:
            target += interval
            delay = target - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                target = time.perf_counter()
            if not self.pending:
                self.pending = True
                try:
                    wx.CallAfter(self.frame.on_tick)
                except Exception:
                    return


class MainFrame(wx.Frame):

    stored_rect = None
    started = False
    restore_bounds = None
    tray = None
    quitting = False

    def __init__(self):
        settings = load_settings()
        super().__init__(None, title=APP_NAME, size=wx.Size(*DEFAULT_SIZE),
                         style=FRAME_STYLE)
        apply_no_caption(self)
        self.SetMinSize(wx.Size(*MIN_SIZE))

        self.theme_name = self.resolve_theme(settings.get('theme', 'dark'))
        theme = THEMES[self.theme_name]
        self.widget = None
        self.tray = None
        self.widget_position = settings.get('compact_widget_position')
        self.last_data = None

        self.set_icon()

        self.folds = set(settings.get('folded_panels', []))

        self.book = wx.Simplebook(self)
        self.ttsbox = TtsBox(self.book, theme, self.folds, self.store_settings)
        self.usagebox = UsageBox(self.book, theme, settings, self.store_settings)
        self.usagebox.on_data = self.on_usage
        self.settingsbox = SettingsBox(self.book, theme, settings, self.on_settings, {
            'include_projects': lambda: self.set_projects('excluded'),
            'show_projects': lambda: self.set_projects('hidden'),
            'reset_index': self.usagebox.reset_index,
            'count_orphans': self.usagebox.count_orphans,
            'check_updates': self.on_check_updates,
        }, self.folds, self.store_settings)
        for page in (self.usagebox, self.ttsbox, self.settingsbox):
            self.book.AddPage(page, '')

        self.titlebar = TitleBar(self, theme, self.on_menu, self.toggle_maximize)
        # before the menu, which opens over it
        self.updatebox = UpdateBox(self, theme, self.on_update_action)
        self.updater = Updater(settings, self.on_update_checked)
        self.release = None
        self.sidemenu = SideMenu(self, theme, MENU_ITEMS, self.on_select)
        apply_clip_siblings(self.book)
        apply_clip_siblings(self.updatebox)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.titlebar, 0, wx.EXPAND)
        sizer.Add(self.updatebox, 0, wx.EXPAND)
        sizer.Add(self.book, 1, wx.EXPAND)
        self.SetSizer(sizer)

        self.apply_theme()
        self.on_settings()

        self.pacer = Pacer(self)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_MAXIMIZE, self.on_maximize)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.pacer.start()
        self.on_tick()
        self.restore_rect(settings)
        self.started = True

    def is_rect_visible(self, rect):
        for index in range(wx.Display.GetCount()):
            shared = wx.Display(index).GetClientArea().Intersect(rect)
            if shared.width >= MIN_VISIBLE_WIDTH and shared.height >= MIN_VISIBLE_HEIGHT:
                return True
        return False

    def centre_on_primary(self):
        primary = wx.Display(wx.Display.GetFromPoint(wx.Point(0, 0))).GetClientArea()
        width, height = self.GetSize()
        self.SetPosition(wx.Point(primary.x + (primary.width - width) // 2,
                                  primary.y + (primary.height - height) // 2))

    def restore_rect(self, settings):
        stored = settings.get('rect')
        if stored and len(stored) == 4:
            rect = wx.Rect(*stored)
            if self.is_rect_visible(rect):
                self.SetRect(rect)
                self.stored_rect = list(stored)
                return
            self.SetSize(rect.GetSize())

        self.centre_on_primary()
        self.stored_rect = list(self.GetRect())

    def set_icon(self):
        path = get_asset_path('icon', 'icon.ico')
        if os.path.exists(path):
            self.SetIcon(wx.Icon(path, wx.BITMAP_TYPE_ICO))

    def apply_theme(self):
        theme = THEMES[self.theme_name]
        self.SetBackgroundColour(wx.Colour(theme['bg']))
        self.book.SetBackgroundColour(wx.Colour(theme['bg']))
        self.titlebar.set_theme(theme)
        self.sidemenu.set_theme(theme)
        self.updatebox.set_theme(theme)

        self.ttsbox.apply_theme(theme)
        self.usagebox.apply_theme(theme)
        self.settingsbox.apply_theme(theme)

        apply_titlebar_theme(self, theme)
        self.Refresh()

    def on_menu(self):
        self.sidemenu.toggle()

    def on_select(self, index):
        self.ttsbox.flush()
        self.book.SetSelection(index)
        self.on_tick()

    def toggle_maximize(self):
        # Windows maximizes a captionless frame past the work area and over the taskbar
        if self.restore_bounds is not None:
            bounds, self.restore_bounds = self.restore_bounds, None
            self.SetRect(wx.Rect(*bounds))
        else:
            self.restore_bounds = list(self.GetRect())
            index = max(0, wx.Display.GetFromWindow(self))
            work = wx.Display(index).GetClientArea()
            left, top, right, bottom = get_frame_margins(self)
            self.SetRect(wx.Rect(work.x - left, work.y - top,
                                 work.width + left + right,
                                 work.height + top + bottom))
        self.titlebar.set_maximized(self.restore_bounds is not None)

    def on_maximize(self, event):
        if not self.IsMaximized():
            return
        self.Maximize(False)
        if self.restore_bounds is None:
            self.toggle_maximize()

    def on_char(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE and self.sidemenu.is_open():
            self.sidemenu.close()
            return
        event.Skip()

    @staticmethod
    def resolve_theme(choice):
        if choice == 'auto':
            return 'dark' if is_windows_dark() else 'light'
        return choice if choice in THEMES else 'dark'

    def on_settings(self):
        values = self.settingsbox.get_values()
        style = self.GetWindowStyle()
        if values['on_top']:
            self.SetWindowStyle(style | wx.STAY_ON_TOP)
        else:
            self.SetWindowStyle(style & ~wx.STAY_ON_TOP)

        theme_name = self.resolve_theme(values['theme'])
        if theme_name != self.theme_name:
            self.theme_name = theme_name
            self.apply_theme()
        theme = THEMES[self.theme_name]

        self.usagebox.set_options(agents=values['agents'], currency=values['currency'],
                                  rate=self.settingsbox.get_rate(),
                                  sections=self.settingsbox.get_sections(),
                                  wide=values['wide_layout'], elsewhere=values['show_elsewhere'])
        self.settingsbox.set_wide(values['wide_layout'])
        self.ttsbox.set_wide(values['wide_layout'])
        if values['compact_widget'] and self.widget is None:
            self.widget = QuotaWidget(self, theme, self.widget_position)
            if self.last_data:
                self.widget.update(self.last_data)
            self.widget.Show()
        elif not values['compact_widget'] and self.widget is not None:
            self.close_widget()
        if values['tray_icon'] and self.tray is None:
            self.tray = TrayIcon(self)
            # tray.py is shared with the sibling apps, the balloon is ours
            self.tray.Bind(wx.adv.EVT_TASKBAR_BALLOON_CLICK, lambda event: self.show_window())
            self.update_tray()
        elif not values['tray_icon'] and self.tray is not None:
            self.remove_tray()
        self.settingsbox.update_tray_note()
        self.store_settings()

    def on_usage(self, data):
        self.last_data = data
        if self.widget is not None:
            self.widget.update(data)
        self.update_tray()

    def set_projects(self, key):
        self.usagebox.set_project_list(key, [])

    def close_widget(self):
        self.widget_position = list(self.widget.GetPosition())
        self.widget.Destroy()
        self.widget = None

    def hide_widget(self):
        self.settingsbox.widget.SetValue(False)
        self.on_settings()

    def remove_tray(self):
        self.tray.RemoveIcon()
        self.tray.Destroy()
        self.tray = None

    def quit(self):
        self.quitting = True
        self.Close(True)

    def show_window(self):
        if self.IsIconized():
            self.Iconize(False)
        self.Show()
        self.Raise()
        self.SetFocus()

    def hide_window(self):
        self.ttsbox.flush()
        if self.IsIconized() is False and self.IsMaximized() is False:
            self.stored_rect = list(self.GetRect())
        self.store_settings()
        # a second launch may have shown the window behind wx's back
        self.Show(True)
        self.Hide()

    def toggle_tts(self, key):
        self.ttsbox.cards[key].activate()
        self.ttsbox.flush()

    def get_tray_items(self):
        widget, cards = self.settingsbox.widget, self.ttsbox.cards
        return [('Floating usage widget', widget.activate, widget.GetValue()),
                ('Speak notifications', lambda: self.toggle_tts('notify'),
                 cards['notify'].GetValue()),
                ('Read-aloud hotkey', lambda: self.toggle_tts('readaloud'),
                 cards['readaloud'].GetValue())]

    def update_tray(self):
        if self.tray is None or not self.last_data:
            return
        limits = self.last_data.get('limits') or []
        self.tray.set_tip('\n'.join(f'{limit["name"]} {int(limit["percent"])}%'
                                    for limit in limits))

    def on_check_updates(self):
        self.settingsbox.check_now.set_tone('plain')
        self.settingsbox.check_now.set_description('Checking…')
        self.updater.check(forced=True)

    def get_checked_time(self):
        return time.strftime('%H:%M', time.localtime(self.updater.checked_at))

    def on_update_checked(self, release, result, forced):
        # a queued call can arrive after close
        if not self:
            return
        card = self.settingsbox.check_now
        card.set_tone('warn' if result == 'error' else 'plain')
        if result == 'error':
            card.set_description('Could not reach GitHub')
            return
        self.store_settings()
        if result == 'found':
            card.set_description(f'{release["version"]} is available')
            self.show_update(release)
        elif result == 'skipped':
            card.set_description(f'{self.updater.skipped} skipped, '
                                 f'checked at {self.get_checked_time()}')
        else:
            card.set_description(f'Up to date, checked at {self.get_checked_time()}')

    def show_update(self, release):
        # a notice already updating stays as it is
        if self.updatebox.IsShown() and self.updatebox.state == 'busy':
            return
        self.release = release
        self.updatebox.show_release(release)
        if not self.updatebox.IsShown():
            self.updatebox.Show()
            self.Layout()
        if (self.tray is not None and self.settingsbox.tray_notice.GetValue()
                and not self.tray.is_window_shown()):
            self.tray.ShowBalloon(f'{APP_NAME} {release["version"]}',
                                  'A new version is available', 10000, wx.ICON_INFORMATION)

    def hide_update(self):
        self.updatebox.Hide()
        self.Layout()

    def on_update_action(self, key):
        release = self.release
        if key == 'skip':
            self.updater.skipped = release['version']
            self.store_settings()
            self.settingsbox.check_now.set_description(f'{release["version"]} skipped')
            self.hide_update()
        elif key == 'later':
            self.hide_update()
        elif key == 'cancel':
            self.updater.cancel()
        elif release['kind'] == 'page':
            # explorer hands the link to the shell, as the About card does
            subprocess.Popen(['explorer', release['page']])
            self.hide_update()
        else:
            if release['kind'] == 'installer':
                self.updatebox.set_busy('Downloading 0%', 0.0)
            else:
                self.updatebox.set_busy('Updating…')
            self.updater.update(release, self.on_update_progress, self.on_update_done)

    def on_update_progress(self, ratio):
        if not self or self.updatebox.state != 'busy':
            return
        message = f'Downloading {int(ratio * 100)}%'
        if message != self.updatebox.message:
            self.updatebox.set_busy(message, ratio)

    def on_update_done(self, error):
        if not self:
            return
        if error is not None:
            self.updatebox.set_failed(error)
            return
        if self.release['kind'] == 'git':
            try:
                restart_source()
            except OSError:
                self.updatebox.set_failed('Updated, start the app again to use it')
                return
        # the installer replaces the app's files once it is gone
        self.quit()

    def on_size(self, event):
        self.sidemenu.place(TitleBar.HEIGHT)
        event.Skip()

    def on_tick(self):
        # a queued call can arrive after close; a destroyed window is falsy
        if not self:
            return
        self.pacer.pending = False
        page = self.book.GetCurrentPage()
        if page is not None:
            page.tick()
        if page is not self.usagebox:
            self.usagebox.tick()

        visible = (not self.settingsbox.autohide.GetValue() or
                   page is self.settingsbox or
                   self.sidemenu.is_open() or
                   self.GetScreenRect().Contains(wx.GetMousePosition()))
        self.titlebar.set_visible(visible)
        self.titlebar.set_menu_open(self.sidemenu.is_open())
        self.updater.tick(self.settingsbox.check_updates.GetValue())
        paint_now(self)
        if self.widget is not None:
            paint_now(self.widget)

    def store_settings(self):
        if not self.started:
            return
        settings = self.settingsbox.get_values()
        settings.update(self.usagebox.get_options())
        if self.widget is not None:
            self.widget_position = list(self.widget.GetPosition())
        settings.update({
            'rect': self.stored_rect,
            'compact_widget_position': self.widget_position,
            'folded_panels': sorted(self.folds),
            'update_checked_at': self.updater.checked_at,
            'update_skipped': self.updater.skipped,
        })
        save_settings(settings)
        options = self.usagebox.get_options()
        self.settingsbox.set_project_counts(len(options['excluded_projects']),
                                            len(options['hidden_projects']))

    def on_close(self, event):
        values = self.settingsbox.get_values()
        if (self.tray is not None and values['close_to_tray'] and not self.quitting
                and event.CanVeto()):
            event.Veto()
            self.hide_window()
            return
        self.pacer.running = False
        self.updater.cancel()
        # the drawer's capture and slide timer crash a closing frame (0xc0000374)
        self.sidemenu.close()
        self.sidemenu.timer.Stop()
        self.ttsbox.flush()
        if self.restore_bounds is not None:
            self.stored_rect = list(self.restore_bounds)
        elif self.IsIconized() is False and self.IsMaximized() is False:
            self.stored_rect = list(self.GetRect())
        self.store_settings()
        if self.widget is not None:
            self.widget.Destroy()
            self.widget = None
        # a live tray icon keeps the app running after the frame is gone
        if self.tray is not None:
            self.remove_tray()
        event.Skip()


def launch_mainapp():
    app = wx.App(False)
    frame = MainFrame()
    frame.Show()
    apply_titlebar_theme(frame, THEMES[frame.theme_name])
    app.MainLoop()
