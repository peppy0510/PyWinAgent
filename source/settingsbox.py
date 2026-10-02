# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

앱 자신의 설정. 다루는 도구의 설정(TTS)은 그 페이지가 가지고, 여기에는 창과
사용량 페이지에 관한 것을 둔다. 사용량 쪽 묶음은 WhereMyTokens 설정의 짜임을
따른다 (Providers·Currency·Main Layout·Data).

값은 `get_values()` 로 한 번에 내준다. 저장과 적용은 mainapp 이 한다.
'''


import wx

from controls import ActionCard
from controls import ChoiceCard
from controls import LayoutCard
from controls import ScrollArea
from controls import SettingCard
from controls import SliderCard
from utilities import get_font


MARGIN = 16
# 타이틀바 바로 아래. 옆 여백보다 좁게 둔다.
TOP_MARGIN = 8
TITLE_INSET = 3
TITLE_GAP = 8
CARD_GAP = 4
GROUP_GAP = 14

AGENTS = (('claude', 'Claude', 'Count Claude Code usage'),
          ('codex', 'Codex', 'Count Codex usage'),
          ('antigravity', 'Antigravity', 'Count Antigravity conversations'))

SECTIONS = (('planUsage', 'Plan Usage'), ('codeOutput', 'Code Output'), ('trend', 'Trend'),
            ('sessions', 'Sessions'), ('activity', 'Activity'), ('modelUsage', 'Model Usage'))

CURRENCIES = (('USD', 'USD'), ('KRW', 'KRW'), ('CNY', 'CNY'))

THEMES = (('auto', 'Auto'), ('light', 'Light'), ('dark', 'Dark'))

# 끌기 애니메이션. 한 프레임마다 남은 거리의 이만큼씩 다가간다 (지수 감속).
DRAG_FRAME_MS = 16
DRAG_EASE = 0.35

REINDEX_NOTE = 'Rebuild the index from the record files'
# 처음 누르면 단추가 Confirm 으로 바뀌어 이만큼 기다린다. 그 안에 다시 눌러야 지운다.
REINDEX_CONFIRM_MS = 6000


class SettingsBox(ScrollArea):

    def __init__(self, parent, theme, settings, on_change, actions=None):
        super().__init__(parent, theme)
        self.on_change = on_change
        self.actions = actions or {}
        self.labels = []
        board = self.content

        def toggle(label, description):
            return SettingCard(board, theme, label, description, on_change)

        self.ontop = toggle('Always on top', 'Keep the window above others')
        self.theme_choice = ChoiceCard(board, theme, 'Theme', 'Auto follows Windows',
                                       THEMES, on_change)

        self.agents = {key: toggle(label, description) for key, label, description in AGENTS}


        self.widget = toggle('Floating usage widget', 'Small always-on-top quota pace window')

        self.currency = ChoiceCard(board, theme, 'Currency', 'Money on the usage page',
                                   CURRENCIES, on_change)
        self.krw = SliderCard(board, theme, 'KRW per USD', 'Exchange rate for KRW',
                              (900, 2000, 10, 0), on_change)
        self.cny = SliderCard(board, theme, 'CNY per USD', 'Exchange rate for CNY',
                              (5, 10, 0.05, 2), on_change)

        self.layout = {key: LayoutCard(board, theme, label, 'Drag to reorder · click to show or hide',
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
        self.reindex_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, lambda event: self.disarm_reindex(), self.reindex_timer)

        self.load(settings)
        self.build()
        self.bind_children()
        self.apply_theme(theme)

    def load(self, settings):
        self.ontop.SetValue(settings.get('on_top', False))
        self.theme_choice.SetValue(settings.get('theme', 'dark'))
        enabled = settings.get('agents', {})
        for key, card in self.agents.items():
            card.SetValue(enabled.get(key, True))
        self.widget.SetValue(settings.get('compact_widget', False))
        self.currency.SetValue(settings.get('currency', 'USD'))
        self.krw.SetValue(settings.get('usd_to_krw', 1380))
        self.cny.SetValue(settings.get('usd_to_cny', 7.2))
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

    def add_title(self, sizer, text):
        label = wx.StaticText(self.content, label=text)
        label.SetFont(get_font(10, bold=True))
        self.labels.append(label)
        sizer.Add(label, 0, wx.LEFT, MARGIN + TITLE_INSET)
        sizer.AddSpacer(TITLE_GAP)

    def add_cards(self, sizer, cards):
        for index, card in enumerate(cards):
            if index:
                sizer.AddSpacer(CARD_GAP)
            sizer.Add(card, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGIN)
        sizer.AddSpacer(GROUP_GAP)

    def build(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(TOP_MARGIN)
        groups = (
            ('Window', (self.ontop,)),
            ('Appearance', (self.theme_choice,)),
            ('Agents', tuple(self.agents.values())),
            ('Widget', (self.widget,)),
            ('Currency', (self.currency, self.krw, self.cny)),
        )
        for title, cards in groups:
            self.add_title(sizer, title)
            self.add_cards(sizer, cards)

        self.add_title(sizer, 'Main layout')
        self.layout_sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.layout_sizer, 0, wx.EXPAND)
        self.fill_layout()
        sizer.AddSpacer(CARD_GAP)
        self.add_cards(sizer, (self.reset_layout,))

        self.add_title(sizer, 'Data')
        self.add_cards(sizer, (self.projects, self.hidden, self.reindex))
        self.content.SetSizer(sizer)

    def fill_layout(self):
        # Clear 는 사이저 항목만 떼고 카드는 살려 둔다.
        self.layout_sizer.Clear()
        for index, key in enumerate(self.order):
            if index:
                self.layout_sizer.AddSpacer(CARD_GAP)
            self.layout_sizer.Add(self.layout[key], 0, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGIN)

    def relayout(self):
        self.content.Layout()
        self.fit()
        self.Refresh()

    def on_drag(self, card, phase, screen_y):
        '''카드 끌기. 끄는 카드는 마우스를 그대로 따라오고, 나머지는 새 차례의
        자리로 매 프레임 조금씩 미끄러진다. 놓으면 그 차례를 사이저에 넣는다.'''
        key = next(name for name, value in self.layout.items() if value is card)
        if phase == 'start':
            # 칸 자리는 지금 사이저가 놓은 자리에서 잰다. 카드 높이와 사이가 다 같다.
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

        # 끄는 카드의 자리: 마우스를 따르되 첫 칸과 끝 칸 밖으로는 안 나간다.
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
        '''색인은 지워진 기록 파일의 사용량을 담은 유일한 사본이다. 다시 만들면
        그 몫은 영영 사라지므로 두 번 눌러야 지운다. 첫 번째는 잃을 양을 센다.'''
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
            # 같은 요청이 WSL·Windows 사본에 함께 있으면 다시 읽혀 살아남는다. 그래서 상한이다.
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
            'agents': self.get_agents(),
            'compact_widget': self.widget.GetValue(),
            'currency': self.currency.GetValue(),
            'usd_to_krw': self.krw.GetValue(),
            'usd_to_cny': self.cny.GetValue(),
            'section_order': list(self.order),
            'hidden_sections': [key for key, card in self.layout.items() if not card.GetValue()],
        }

    def get_sections(self):
        return [{'id': key, 'hidden': not self.layout[key].GetValue()} for key in self.order]

    def get_rate(self):
        currency = self.currency.GetValue()
        if currency == 'KRW':
            return self.krw.GetValue()
        if currency == 'CNY':
            return self.cny.GetValue()
        return 1.0

    def apply_theme(self, theme):
        self.set_theme(theme)
        for label in self.labels:
            label.SetForegroundColour(wx.Colour(theme['text']))
        for child in self.content.GetChildren():
            if hasattr(child, 'set_theme'):
                child.set_theme(theme)
        self.Refresh()

    def tick(self):
        pass
