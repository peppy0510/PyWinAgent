# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import os
import wx

from companions import QuotaWidget
from companions import is_windows_dark
from settingsbox import SettingsBox
from sidemenu import SideMenu
from titlebar import TitleBar
from ttsbox import TtsBox
# 사용량 페이지는 두 벌이다. 같은 값을 usagebox 는 캔버스에 손으로 그리고
# usageview 는 웹뷰에 맡긴다. 이 줄을 바꿔 갈아 끼운다.
# from usagebox import UsageBox
from usageview import UsageView
from utilities import APP_NAME
from utilities import THEMES
from utilities import apply_clip_siblings
from utilities import apply_no_caption
from utilities import apply_titlebar_theme
from utilities import get_asset_path
from utilities import get_frame_margins
from utilities import load_settings
from utilities import save_settings


# 시계가 아니라 설정 창이다. 타이틀바를 숨겼을 때 마우스를 알아채는 데만 쓰므로
# 이 정도면 충분하다.
TICK_INTERVAL = 150
DEFAULT_SIZE = (460, 720)

# 사이드 메뉴의 차례가 곧 페이지의 차례다. None 은 구분선이라 페이지가 없다.
MENU_ITEMS = (('Usage', 'chart'), ('TTS', 'sound'), None, ('Settings', 'settings'))

# 캡션을 떼고 그 자리를 직접 그린다. 크기 조절과 스냅은 그대로 남는다.
FRAME_STYLE = wx.DEFAULT_FRAME_STYLE & ~wx.CAPTION

# 기억된 위치가 이만큼도 화면에 안 걸리면 사라진 모니터로 본다.
MIN_VISIBLE_WIDTH = 120
MIN_VISIBLE_HEIGHT = 32


class MainFrame(wx.Frame):

    stored_rect = None
    # 생성이 끝나기 전에는 저장하지 않는다. 창 자리를 되살리기 전이라 빈 값이 덮인다.
    started = False
    # 흉내 낸 최대화 이전의 자리. None 이면 최대화 상태가 아니다.
    restore_bounds = None

    def __init__(self):
        settings = load_settings()
        super().__init__(None, title=APP_NAME, size=wx.Size(*DEFAULT_SIZE),
                         style=FRAME_STYLE)
        apply_no_caption(self)

        self.theme_name = self.resolve_theme(settings.get('theme', 'dark'))
        theme = THEMES[self.theme_name]
        self.widget = None
        self.widget_position = settings.get('compact_widget_position')
        self.last_data = None

        self.set_icon()

        # 접어 둔 판의 키 (TTS·설정 페이지 공용). 접고 펼 때마다 바로 저장한다.
        self.folds = set(settings.get('folded_panels', []))

        self.book = wx.Simplebook(self)
        self.ttsbox = TtsBox(self.book, theme, self.folds, self.store_settings)
        self.usagebox = UsageView(self.book, theme, settings, self.store_settings)
        self.usagebox.on_data = self.on_usage
        self.settingsbox = SettingsBox(self.book, theme, settings, self.on_settings, {
            'include_projects': lambda: self.set_projects('excluded'),
            'show_projects': lambda: self.set_projects('hidden'),
            'reset_index': self.usagebox.reset_index,
            'count_orphans': self.usagebox.count_orphans,
        }, self.folds, self.store_settings)
        for page in (self.usagebox, self.ttsbox, self.settingsbox):
            self.book.AddPage(page, '')

        self.titlebar = TitleBar(self, theme, self.on_menu, self.toggle_maximize)
        self.sidemenu = SideMenu(self, theme, MENU_ITEMS, self.on_select)
        # 서랍은 페이지 위에 떠 있다. 페이지 쪽이 형제를 클립해 주어야 살아남는다.
        apply_clip_siblings(self.book)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.titlebar, 0, wx.EXPAND)
        sizer.Add(self.book, 1, wx.EXPAND)
        self.SetSizer(sizer)

        self.apply_theme()
        self.on_settings()

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_tick)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_MAXIMIZE, self.on_maximize)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.timer.Start(TICK_INTERVAL)
        self.on_tick(None)
        self.restore_rect(settings)
        self.started = True

    def is_rect_visible(self, rect):
        # 모니터 구성이 바뀌면 기억된 좌표가 아무 화면에도 안 걸릴 수 있다.
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

        self.ttsbox.apply_theme(theme)
        self.usagebox.apply_theme(theme)
        self.settingsbox.apply_theme(theme)

        apply_titlebar_theme(self, theme)
        self.Refresh()

    def on_menu(self):
        self.sidemenu.toggle()

    def on_select(self, index):
        # 페이지를 떠나면 미뤄 둔 저장을 먼저 끝낸다.
        self.ttsbox.flush()
        self.book.SetSelection(index)
        self.on_tick(None)

    def toggle_maximize(self):
        '''캡션이 없는 창을 Windows 가 최대화하면 보이지 않는 여백만큼 화면
        밖으로 넘치고 작업 표시줄까지 덮는다. 작업 영역에 맞춰 직접 채운다.'''
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
        # 화면 위로 던지거나 Win+Up 을 눌러도 같은 자리에 오도록 되돌려 잡는다.
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
                                  wide=values['wide_layout'])
        self.settingsbox.set_wide(values['wide_layout'])
        self.ttsbox.set_wide(values['wide_layout'])
        if values['compact_widget'] and self.widget is None:
            self.widget = QuotaWidget(self, theme, self.widget_position)
            if self.last_data:
                self.widget.update(self.last_data)
            self.widget.Show()
        elif not values['compact_widget'] and self.widget is not None:
            self.close_widget()
        self.store_settings()

    def on_usage(self, data):
        '''사용량 페이지가 새로 모을 때마다. 떠 있는 위젯이 같은 값을 받는다.'''
        self.last_data = data
        if self.widget is not None:
            self.widget.update(data)

    def set_projects(self, key):
        self.usagebox.set_project_list(key, [])

    def close_widget(self):
        self.widget_position = list(self.widget.GetPosition())
        self.widget.Destroy()
        self.widget = None

    def hide_widget(self):
        self.settingsbox.widget.SetValue(False)
        self.on_settings()

    def show_window(self):
        if self.IsIconized():
            self.Iconize(False)
        self.Show()
        self.Raise()
        self.SetFocus()

    def on_size(self, event):
        self.sidemenu.place(TitleBar.HEIGHT)
        event.Skip()

    def on_tick(self, event):
        page = self.book.GetCurrentPage()
        if page is not None:
            page.tick()
        # 알림과 트레이는 사용량 페이지를 안 보고 있어도 새 값을 받아야 한다.
        if page is not self.usagebox:
            self.usagebox.tick()

        self.titlebar.set_menu_open(self.sidemenu.is_open())

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
        })
        save_settings(settings)
        options = self.usagebox.get_options()
        self.settingsbox.set_project_counts(len(options['excluded_projects']),
                                            len(options['hidden_projects']))

    def on_close(self, event):
        self.timer.Stop()
        # 마우스를 잡은 채로 창이 사라지면 나중에 죽는다. 먼저 놓게 한다.
        self.sidemenu.close()
        self.ttsbox.flush()
        # 최소화/최대화 상태의 좌표를 저장하면 다음 실행이 이상해진다.
        if self.restore_bounds is not None:
            self.stored_rect = list(self.restore_bounds)
        elif self.IsIconized() is False and self.IsMaximized() is False:
            self.stored_rect = list(self.GetRect())
        self.store_settings()
        if self.widget is not None:
            self.widget.Destroy()
            self.widget = None
        event.Skip()


def launch_mainapp():
    app = wx.App(False)
    frame = MainFrame()
    frame.Show()
    apply_titlebar_theme(frame, THEMES[frame.theme_name])
    app.MainLoop()
