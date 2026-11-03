# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import subprocess
import wx

from controls import AboutCard
from controls import ActionCard
from controls import ChoiceCard
from controls import LayoutCard
from controls import Panel
from controls import ScrollArea
from controls import SettingCard
from controls import SliderCard
from utilities import APP_AUTHOR
from utilities import APP_EMAIL
from utilities import APP_HOME
from utilities import APP_NAME
from utilities import APP_VERSION
from utilities import get_asset_path

AGENTS = (('claude', 'Claude', 'Count Claude Code usage'),
          ('codex', 'Codex', 'Count Codex usage'),
          ('antigravity', 'Antigravity', 'Count Antigravity conversations'))

SECTIONS = (('planUsage', 'Plan Usage'), ('codeOutput', 'Code Output'), ('trend', 'Trend'),
            ('sessions', 'Sessions'), ('activity', 'Activity'), ('modelUsage', 'Model Usage'))

CURRENCIES = (('USD', 'USD'), ('KRW', 'KRW'), ('JPY', 'JPY'))

THEMES = (('auto', 'Auto'), ('light', 'Light'), ('dark', 'Dark'))

DRAG_FRAME_MS = 16
DRAG_EASE = 0.35

REINDEX_NOTE = 'Rebuild the index from the record files'
REINDEX_CONFIRM_MS = 6000

UPDATE_NOTE = 'Look for a new release on GitHub'
TRAY_NOTE = 'Also from the tray icon while the window is hidden'
TRAY_NOTE_OFF = 'Needs the tray icon, under Window'


class SettingsBox(ScrollArea):

    def __init__(self, parent, theme, settings, on_change, actions=None, folds=None,
                 on_fold=None):
        super().__init__(parent, theme)
        self.on_change = on_change
        self.actions = actions or {}
        self.folds = folds if folds is not None else set()
        self.on_folds = on_fold
        board = self.content

        def toggle(label, description):
            return SettingCard(board, theme, label, description, on_change)

        self.ontop = toggle('Always on top', 'Keep the window above others')
        self.tray = toggle('Tray icon', 'Show an icon in the notification area')
        self.close_to_tray = toggle('Close to tray',
                                    'Closing hides the window so the hotkey keeps working')
        self.autohide = toggle('Auto hide menu', 'Show the header only on hover')
        self.theme_choice = ChoiceCard(board, theme, 'Theme', 'Auto follows Windows',
                                       THEMES, on_change)

        self.agents = {key: toggle(label, description) for key, label, description in AGENTS}

        self.wide = toggle('Wide layout', 'Lay sections out in columns when the window is wide')
        self.elsewhere = toggle('Show elsewhere',
                                'Split plan limits into this device and other places')
        self.widget = toggle('Floating usage widget', 'Small always-on-top quota pace window')

        self.currency = ChoiceCard(board, theme, 'Currency', 'Money on the usage page',
                                   CURRENCIES, on_change)
        self.krw = SliderCard(board, theme, 'KRW per USD', 'Exchange rate for KRW',
                              (900, 2000, 10, 0), on_change, default=1380)
        self.jpy = SliderCard(board, theme, 'JPY per USD', 'Exchange rate for JPY',
                              (80, 250, 1, 0), on_change, default=150)

        self.layout = {key: LayoutCard(board, theme, label, 'Drag to reorder',
                                       on_change, self.on_drag)
                       for key, label in SECTIONS}
        self.drag = None
        self.drag_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_drag_frame, self.drag_timer)
        self.order = [key for key, _ in SECTIONS]
        self.reset_layout = ActionCard(board, theme, 'Reset layout',
                                       'Default order, every section shown', 'Reset',
                                       self.on_reset_layout)

        self.projects = ActionCard(board, theme, 'Excluded projects', '', 'Include all',
                                   lambda: self.run('include_projects'))
        self.hidden = ActionCard(board, theme, 'Hidden projects', '', 'Show all',
                                 lambda: self.run('show_projects'))
        self.reindex = ActionCard(board, theme, 'Usage history', REINDEX_NOTE, 'Reset index',
                                  self.on_reindex)
        self.reindex.set_captions('Confirm')
        self.reindex_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, lambda event: self.disarm_reindex(), self.reindex_timer)

        self.check_updates = toggle('Check for updates', 'Once a day, a notice when one is out')
        self.tray_notice = toggle('Tray notification', TRAY_NOTE)
        self.check_now = ActionCard(board, theme, 'Latest release', UPDATE_NOTE, 'Check now',
                                    lambda: self.run('check_updates'))

        self.load(settings)
        self.build()
        self.bind_children()
        self.apply_theme(theme)

    def load(self, settings):
        self.ontop.SetValue(settings.get('on_top', False))
        self.tray.SetValue(settings.get('tray_icon', True))
        self.close_to_tray.SetValue(settings.get('close_to_tray', False))
        self.autohide.SetValue(settings.get('auto_hide_menu', False))
        self.theme_choice.SetValue(settings.get('theme', 'dark'))
        self.wide.SetValue(settings.get('wide_layout', True))
        self.elsewhere.SetValue(settings.get('show_elsewhere', True))
        enabled = settings.get('agents', {})
        for key, card in self.agents.items():
            card.SetValue(enabled.get(key, True))
        self.widget.SetValue(settings.get('compact_widget', False))
        self.currency.SetValue(settings.get('currency', 'USD'))
        self.krw.SetValue(settings.get('usd_to_krw', 1380))
        self.jpy.SetValue(settings.get('usd_to_jpy', 150))
        order = [key for key in settings.get('section_order', []) if key in self.layout]
        self.order = order + [key for key in self.layout if key not in order]
        hidden = settings.get('hidden_sections', [])
        for key, card in self.layout.items():
            card.SetValue(key not in hidden)
        self.set_project_counts(len(settings.get('excluded_projects', [])),
                                len(settings.get('hidden_projects', [])))
        self.check_updates.SetValue(settings.get('update_check', True))
        self.tray_notice.SetValue(settings.get('update_tray', True))
        self.update_tray_note()

    def update_tray_note(self):
        # the balloon pops up from the tray icon
        note = TRAY_NOTE if self.tray.GetValue() else TRAY_NOTE_OFF
        if note != self.tray_notice.description:
            self.tray_notice.description = note
            self.tray_notice.Refresh()

    def set_project_counts(self, excluded, hidden):
        self.projects.description = (f'{int(excluded)} left out of every number' if excluded
                                     else 'None — use Exclude on a session')
        self.hidden.description = (f'{int(hidden)} hidden from the session list' if hidden
                                   else 'None — use Hide on a session')
        self.projects.Refresh()
        self.hidden.Refresh()

    def add_panel(self, key, title, body, rows=None):
        return Panel(self.content, self.theme, 'settings.' + key, title, body, self.folds,
                     self.on_fold, rows=rows)

    def build(self):
        panels = [self.add_panel(key, title, cards) for key, title, cards in (
            ('window', 'Window', (self.ontop, self.tray, self.close_to_tray, self.autohide)),
            ('appearance', 'Appearance', (self.theme_choice, self.wide, self.elsewhere)),
            ('agents', 'Agents', tuple(self.agents.values())),
            ('widget', 'Widget', (self.widget,)),
            ('currency', 'Currency', (self.currency, self.krw, self.jpy)),
        )]

        self.layout_sizer = wx.BoxSizer(wx.VERTICAL)
        self.layout_panel = self.add_panel('layout', 'Main layout',
                                           (self.layout_sizer, self.reset_layout),
                                           rows=self.get_layout_rows())
        panels.append(self.layout_panel)
        self.fill_layout()

        panels.append(self.add_panel('data', 'Data', (self.projects, self.hidden, self.reindex)))
        panels.append(self.add_panel('updates', 'Updates',
                                     (self.check_updates, self.tray_notice, self.check_now)))
        about = AboutCard(self.content, self.theme, f'{APP_NAME} {APP_VERSION}',
                          (APP_AUTHOR, APP_EMAIL), 'GitHub', self.on_home,
                          wx.Image(get_asset_path('icon', 'muteklab.png')))
        panels.append(self.add_panel('about', 'About', (about,)))
        self.set_panels(panels)

    def on_home(self):
        # explorer hands the link to the shell, so the browser does not inherit elevation
        subprocess.Popen(['explorer', APP_HOME])

    def on_fold(self):
        self.relayout_panels()
        if self.on_folds:
            self.on_folds()

    def get_layout_rows(self):
        return [self.layout[key] for key in self.order] + [self.reset_layout]

    def fill_layout(self):
        self.layout_sizer.Clear()
        for key in self.order:
            self.layout_sizer.Add(self.layout[key], 0, wx.EXPAND)
        self.layout_panel.set_rows(self.get_layout_rows())
        self.layout_panel.apply_fold()

    def relayout(self):
        self.content.Layout()
        self.fit()
        self.Refresh()

    def on_drag(self, card, phase, screen_y):
        key = next(name for name, value in self.layout.items() if value is card)
        if phase == 'start':
            slots = [self.layout[name].GetPosition().y for name in self.order]
            self.drag = {
                'key': key, 'order': list(self.order), 'slots': slots,
                'x': card.GetPosition().x,
                'grab': self.content.ScreenToClient(wx.Point(0, screen_y)).y - card.GetPosition().y,
                'y': {name: float(self.layout[name].GetPosition().y) for name in self.order},
                'mouse': screen_y, 'dropped': False,
            }
            card.Raise()
            self.drag_timer.Start(DRAG_FRAME_MS)
        elif phase == 'move' and self.drag:
            self.drag['mouse'] = screen_y
        elif phase == 'drop' and self.drag:
            self.drag['mouse'] = screen_y
            self.drag['dropped'] = True

    def on_drag_frame(self, event):
        drag = self.drag
        if not drag:
            self.drag_timer.Stop()
            return
        slots = drag['slots']
        stride = (slots[-1] - slots[0]) / float(len(slots) - 1) if len(slots) > 1 else 1
        key = drag['key']

        top = self.content.ScreenToClient(wx.Point(0, drag['mouse'])).y - drag['grab']
        top = min(max(top, slots[0]), slots[-1])
        index = int(round((top - slots[0]) / stride)) if stride else 0
        order = [name for name in drag['order'] if name != key]
        order.insert(index, key)
        drag['current'] = order

        settled = True
        for position, name in enumerate(order):
            if name == key and not drag['dropped']:
                target = top
                drag['y'][name] = target
            else:
                target = slots[position]
                drag['y'][name] += (target - drag['y'][name]) * DRAG_EASE
                if abs(target - drag['y'][name]) < 0.5:
                    drag['y'][name] = target
                else:
                    settled = False
            self.layout[name].SetPosition(wx.Point(drag['x'], int(round(drag['y'][name]))))
        self.layout_panel.set_rows([self.layout[name] for name in order] + [self.reset_layout])

        if drag['dropped'] and settled:
            self.drag_timer.Stop()
            self.drag = None
            changed = order != self.order
            self.order = order
            self.fill_layout()
            self.relayout()
            if changed:
                self.on_change()

    def on_reset_layout(self):
        self.order = [key for key, _ in SECTIONS]
        for card in self.layout.values():
            card.SetValue(True)
        self.fill_layout()
        self.relayout()
        self.on_change()

    def on_reindex(self):
        if self.reindex.tone == 'warn':
            self.disarm_reindex()
            self.run('reset_index')
            return
        self.reindex.set_tone('warn')
        self.reindex.set_caption('Confirm')
        self.reindex.set_description('Checking what only the index still holds…')
        self.reindex_timer.StartOnce(REINDEX_CONFIRM_MS)
        count = self.actions.get('count_orphans')
        if count:
            count(self.show_orphans)

    def show_orphans(self, requests, cost):
        if self.reindex.tone != 'warn':
            return
        if requests:
            text = (f'Up to {format(requests, ",")} requests (${format(round(cost), ",")}) from '
                    'deleted files will be lost')
        else:
            text = 'Nothing kept from deleted files. Safe to rebuild'
        self.reindex.set_description(text)

    def disarm_reindex(self):
        self.reindex_timer.Stop()
        self.reindex.set_tone('plain')
        self.reindex.set_caption('Reset index')
        self.reindex.set_description(REINDEX_NOTE)

    def run(self, name):
        action = self.actions.get(name)
        if action:
            action()

    def get_agents(self):
        return {key: card.GetValue() for key, card in self.agents.items()}

    def get_values(self):
        return {
            'on_top': self.ontop.GetValue(),
            'tray_icon': self.tray.GetValue(),
            'close_to_tray': self.close_to_tray.GetValue(),
            'auto_hide_menu': self.autohide.GetValue(),
            'theme': self.theme_choice.GetValue(),
            'wide_layout': self.wide.GetValue(),
            'show_elsewhere': self.elsewhere.GetValue(),
            'agents': self.get_agents(),
            'compact_widget': self.widget.GetValue(),
            'currency': self.currency.GetValue(),
            'usd_to_krw': self.krw.GetValue(),
            'usd_to_jpy': self.jpy.GetValue(),
            'section_order': list(self.order),
            'hidden_sections': [key for key, card in self.layout.items() if not card.GetValue()],
            'update_check': self.check_updates.GetValue(),
            'update_tray': self.tray_notice.GetValue(),
        }

    def get_sections(self):
        return [{'id': key, 'hidden': not self.layout[key].GetValue()} for key in self.order]

    def get_rate(self):
        currency = self.currency.GetValue()
        if currency == 'KRW':
            return self.krw.GetValue()
        if currency == 'JPY':
            return self.jpy.GetValue()
        return 1.0

    def apply_theme(self, theme):
        self.set_theme(theme)
        for child in self.content.GetChildren():
            if hasattr(child, 'set_theme'):
                child.set_theme(theme)
        self.Refresh()

    def tick(self):
        pass
