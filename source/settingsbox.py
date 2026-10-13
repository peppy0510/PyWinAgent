# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import wx

from controls import ActionCard
from controls import ChoiceCard
from controls import LayoutCard
from controls import Panel
from controls import ScrollArea
from controls import SettingCard
from controls import SliderCard

AGENTS = (('claude', 'Claude', 'Count Claude Code usage'),
          ('codex', 'Codex', 'Count Codex usage'),
          ('antigravity', 'Antigravity', 'Count Antigravity conversations'))

SECTIONS = (('planUsage', 'Plan Usage'), ('codeOutput', 'Code Output'), ('trend', 'Trend'),
            ('sessions', 'Sessions'), ('activity', 'Activity'), ('modelUsage', 'Model Usage'))

CURRENCIES = (('USD', 'USD'), ('KRW', 'KRW'))

THEMES = (('auto', 'Auto'), ('light', 'Light'), ('dark', 'Dark'))

DRAG_FRAME_MS = 16
DRAG_EASE = 0.35

REINDEX_NOTE = 'Rebuild the index from the record files'
REINDEX_CONFIRM_MS = 6000


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
        self.theme_choice = ChoiceCard(board, theme, 'Theme', 'Auto follows Windows',
                                       THEMES, on_change)

        self.agents = {key: toggle(label, description) for key, label, description in AGENTS}

        self.wide = toggle('Wide layout', 'Lay sections out in columns when the window is wide')
        self.widget = toggle('Floating usage widget', 'Small always-on-top quota pace window')

        self.currency = ChoiceCard(board, theme, 'Currency', 'Money on the usage page',
                                   CURRENCIES, on_change)
        self.krw = SliderCard(board, theme, 'KRW per USD', 'Exchange rate for KRW',
                              (900, 2000, 10, 0), on_change, default=1380)

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

        self.load(settings)
        self.build()
        self.bind_children()
        self.apply_theme(theme)

    def load(self, settings):
        self.ontop.SetValue(settings.get('on_top', False))
        self.theme_choice.SetValue(settings.get('theme', 'dark'))
        self.wide.SetValue(settings.get('wide_layout', True))
        enabled = settings.get('agents', {})
        for key, card in self.agents.items():
            card.SetValue(enabled.get(key, True))
        self.widget.SetValue(settings.get('compact_widget', False))
        self.currency.SetValue(settings.get('currency', 'USD'))
        self.krw.SetValue(settings.get('usd_to_krw', 1380))
        order = [key for key in settings.get('section_order', []) if key in self.layout]
        self.order = order + [key for key in self.layout if key not in order]
        hidden = settings.get('hidden_sections', [])
        for key, card in self.layout.items():
            card.SetValue(key not in hidden)
        self.set_project_counts(len(settings.get('excluded_projects', [])),
                                len(settings.get('hidden_projects', [])))

    def set_project_counts(self, excluded, hidden):
        self.projects.description = ('%d left out of every number' % excluded if excluded
                                     else 'None — use Exclude on a session')
        self.hidden.description = ('%d hidden from the session list' % hidden if hidden
                                   else 'None — use Hide on a session')
        self.projects.Refresh()
        self.hidden.Refresh()

    def add_panel(self, key, title, body, rows=None):
        return Panel(self.content, self.theme, 'settings.' + key, title, body, self.folds,
                     self.on_fold, rows=rows)

    def build(self):
        panels = [self.add_panel(key, title, cards) for key, title, cards in (
            ('window', 'Window', (self.ontop,)),
            ('appearance', 'Appearance', (self.theme_choice, self.wide)),
            ('agents', 'Agents', tuple(self.agents.values())),
            ('widget', 'Widget', (self.widget,)),
            ('currency', 'Currency', (self.currency, self.krw)),
        )]

        self.layout_sizer = wx.BoxSizer(wx.VERTICAL)
        self.layout_panel = self.add_panel('layout', 'Main layout',
                                           (self.layout_sizer, self.reset_layout),
                                           rows=self.get_layout_rows())
        panels.append(self.layout_panel)
        self.fill_layout()

        panels.append(self.add_panel('data', 'Data', (self.projects, self.hidden, self.reindex)))
        self.set_panels(panels)

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
            text = 'Up to %s requests ($%s) from deleted files will be lost' % (
                format(requests, ','), format(round(cost), ','))
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
            'theme': self.theme_choice.GetValue(),
            'wide_layout': self.wide.GetValue(),
            'agents': self.get_agents(),
            'compact_widget': self.widget.GetValue(),
            'currency': self.currency.GetValue(),
            'usd_to_krw': self.krw.GetValue(),
            'section_order': list(self.order),
            'hidden_sections': [key for key, card in self.layout.items() if not card.GetValue()],
        }

    def get_sections(self):
        return [{'id': key, 'hidden': not self.layout[key].GetValue()} for key in self.order]

    def get_rate(self):
        currency = self.currency.GetValue()
        if currency == 'KRW':
            return self.krw.GetValue()
        return 1.0

    def apply_theme(self, theme):
        self.set_theme(theme)
        for child in self.content.GetChildren():
            if hasattr(child, 'set_theme'):
                child.set_theme(theme)
        self.Refresh()

    def tick(self):
        pass
