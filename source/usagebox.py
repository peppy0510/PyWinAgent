# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

사용량 페이지의 캔버스 판. 같은 값을 `usageview` 는 웹뷰에 맡긴다 — mainapp 의
import 한 줄로 갈아 끼운다. 지금 걸려 있는 것은 웹뷰 쪽이다.

WhereMyTokens 에서 자주 보던 판을 옮겼다 — 오늘의 비용, 플랜 한도, 날짜별
추세, 시간대별 활동.

숫자를 모으는 데 1 초 남짓 걸려 창이 굳지 않도록 딴 실에서 불러 온다.
그림은 반드시 주 실에서 그려야 하므로 결과만 wx.CallAfter 로 건넨다.
'''


import threading
import wx

import usagedata

from controls import ActionCard
from controls import ScrollArea
from utilities import Canvas
from utilities import CARD_RADIUS
from utilities import draw_card_rim
from utilities import get_font
from utilities import mix


MARGIN = 16
TITLE_INSET = 3
TITLE_GAP = 8
CARD_GAP = 4
GROUP_GAP = 14

TODAY_HEIGHT = 64
TREND_HEIGHT = 130
HEAT_HEIGHT = 150


class Board(Canvas):
    '''카드 한 장. 바탕과 테두리는 여기서 그리고 안쪽만 자식이 채운다.'''

    PADDING = 16

    def __init__(self, parent, theme, height):
        super().__init__(parent, theme)
        self.data = None
        self.SetMinSize(wx.Size(-1, height))

    def set_data(self, data):
        self.data = data
        self.Refresh()

    def draw(self, gc, width, height):
        theme = self.theme
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(wx.Colour(theme['face'])))
        gc.DrawRoundedRectangle(0, 0, width, height, CARD_RADIUS)
        draw_card_rim(gc, theme['rim'], 0, 0, width, height)
        if self.data is None:
            self.draw_centered_text(gc, 'reading…', width / 2, height / 2 - 8,
                                    get_font(9), theme['dim'])
            return
        self.draw_body(gc, width, height)

    def draw_body(self, gc, width, height):
        pass

    def draw_caption(self, gc, text, x, y, colour):
        '''작은 대문자 이름표. 자간을 벌려야 제목처럼 읽힌다.'''
        gc.SetFont(get_font(7, bold=True), wx.Colour(colour))
        for letter in text:
            gc.DrawText(letter, x, y)
            x += gc.GetTextExtent(letter)[0] + 1.4
        return x


class TodayBoard(Board):
    '''왼쪽은 오늘 쓴 돈, 오른쪽은 캐시가 얼마나 먹혔는지.

    세 줄을 위에서부터 쌓되 자리는 잰 높이로 잡는다 — 글자 크기를 건드려도
    줄이 겹치거나 뜨지 않는다.'''

    PADDING = 12
    VALUE_SIZE = 11
    ROW_GAP = 2

    def __init__(self, parent, theme):
        super().__init__(parent, theme, TODAY_HEIGHT)

    def draw_column(self, gc, caption, value, detail, tint, x, align_right):
        '''한쪽 묶음을 그리고 쓴 높이를 돌려준다. align_right 면 오른쪽 맞춤이라
        줄마다 폭을 재서 자리를 잡는다.'''
        theme = self.theme
        top = self.PADDING

        gc.SetFont(get_font(7, bold=True), wx.Colour(tint))
        caption_width = sum(gc.GetTextExtent(letter)[0] + 1.4 for letter in caption)
        start = x - caption_width if align_right else x
        self.draw_caption(gc, caption, start, top, tint)
        top += gc.GetTextExtent(caption)[1] + self.ROW_GAP

        gc.SetFont(get_font(self.VALUE_SIZE, bold=True), wx.Colour(theme['text']))
        text_width, text_height = gc.GetTextExtent(value)[:2]
        gc.DrawText(value, x - text_width if align_right else x, top)
        top += text_height + self.ROW_GAP

        gc.SetFont(get_font(8), wx.Colour(tint if align_right else theme['dim']))
        text_width, text_height = gc.GetTextExtent(detail)[:2]
        gc.DrawText(detail, x - text_width if align_right else x, top)
        return top + text_height

    def draw_body(self, gc, width, height):
        data = self.data
        calls = '%s calls  /  %d sessions' % (usagedata.format_count(data['calls']),
                                              data['sessions'])
        self.draw_column(gc, 'TODAY COST', usagedata.format_money(data['cost']),
                         calls, self.theme['dim'], self.PADDING, False)

        saved = '+ %s saved today' % usagedata.format_money(data['saved'])
        self.draw_column(gc, 'CACHE EFFICIENCY', '%d%%' % round(data['ratio'] * 100),
                         saved, self.theme['mint'], width - self.PADDING, True)


class LimitBoard(Board):
    '''클로드 클라이언트가 보여 주는 5시간·주간 한도. 남은 양이 아니라 쓴 양이라
    막대가 오른쪽으로 갈수록 위험하다 — 색으로도 알린다.

    칸 수가 그때그때 달라지므로 값을 받고 나서 제 높이를 다시 잡는다.'''

    PADDING = 14
    BAR = 6
    TEXT = 14
    TEXT_GAP = 5
    ROW_GAP = 14

    SEVERITIES = {'critical': 'close', 'warning': 'warn'}

    def __init__(self, parent, theme, on_layout=None):
        super().__init__(parent, theme, self.get_height(2))
        self.on_layout = on_layout

    def get_height(self, rows):
        row = self.TEXT + self.TEXT_GAP + self.BAR
        return self.PADDING * 2 + rows * row + max(0, rows - 1) * self.ROW_GAP

    def set_data(self, data):
        limits = (data or {}).get('limits') or []
        height = self.get_height(max(1, len(limits)))
        if height != self.GetMinSize()[1]:
            self.SetMinSize(wx.Size(-1, height))
            self.GetParent().Layout()
            if self.on_layout:
                self.on_layout()
        super().set_data(data)

    def get_tint(self, severity):
        return self.theme[self.SEVERITIES.get(severity, 'accent')]

    def draw_body(self, gc, width, height):
        theme = self.theme
        limits = self.data.get('limits')
        if limits is None:
            self.draw_centered_text(gc, 'plan limits unavailable — sign in again',
                                    width / 2, height / 2 - 8, get_font(9),
                                    theme['dim'])
            return
        if not limits:
            self.draw_centered_text(gc, 'nothing running against a limit',
                                    width / 2, height / 2 - 8, get_font(9),
                                    theme['dim'])
            return

        left = self.PADDING
        span = width - self.PADDING * 2
        top = self.PADDING

        for limit in limits:
            tint = self.get_tint(limit['severity'])
            value = '%d%%' % limit['percent']

            gc.SetFont(get_font(9, bold=True), wx.Colour(tint))
            value_width, text_height = gc.GetTextExtent(value)[:2]
            gc.DrawText(value, left + span - value_width, top)

            gc.SetFont(get_font(9), wx.Colour(theme['text']))
            name_width = gc.GetTextExtent(limit['name'])[0]
            gc.DrawText(limit['name'], left, top)

            remains = usagedata.format_remaining(limit['remains'])
            if remains:
                gc.SetFont(get_font(8), wx.Colour(theme['dim']))
                room = span - name_width - value_width - 16
                gc.DrawText(self.fit_text(gc, remains, max(0, room)),
                            left + name_width + 8, top + 2)

            bar = top + text_height + self.TEXT_GAP
            gc.SetPen(wx.TRANSPARENT_PEN)
            gc.SetBrush(wx.Brush(wx.Colour(theme['grid'])))
            gc.DrawRoundedRectangle(left, bar, span, self.BAR, self.BAR / 2)
            filled = span * min(100, max(0, limit['percent'])) / 100.0
            if filled > 0:
                gc.SetBrush(wx.Brush(wx.Colour(tint)))
                gc.DrawRoundedRectangle(left, bar, max(self.BAR, filled), self.BAR,
                                        self.BAR / 2)
            top = bar + self.BAR + self.ROW_GAP


class TrendBoard(Board):
    '''날짜별 비용. 값이 아니라 모양을 보는 그림이라 눈금은 위아래 끝만 적는다.'''

    TOP = 26
    BOTTOM = 22
    DOT = 3

    def __init__(self, parent, theme):
        super().__init__(parent, theme, TREND_HEIGHT)

    def draw_body(self, gc, width, height):
        theme = self.theme
        points = [(day, cost) for day, cost in self.data['trend'] if day]
        if len(points) < 2:
            self.draw_centered_text(gc, 'not enough days yet', width / 2,
                                    height / 2 - 8, get_font(9), theme['dim'])
            return

        left = self.PADDING
        right = width - self.PADDING
        top = self.TOP
        floor = height - self.BOTTOM
        peak = max(cost for _, cost in points) or 1.0
        step = (right - left) / float(len(points) - 1)

        gc.SetPen(wx.Pen(wx.Colour(theme['grid']), 1))
        for ratio in (0.0, 0.5, 1.0):
            y = round(top + (floor - top) * ratio) + 0.5
            gc.StrokeLine(left, y, right, y)

        gc.SetFont(get_font(7), wx.Colour(theme['dim']))
        gc.DrawText(usagedata.format_money(peak), left, top - 12)
        gc.DrawText('$0', left, floor - 11)

        # 첫 날과 마지막 날만 적는다. 다 적으면 이 폭에서 겹친다.
        for index, anchor in ((0, 'left'), (len(points) - 1, 'right')):
            text = points[index][0][5:].replace('-', '/')
            text_width = gc.GetTextExtent(text)[0]
            x = left if anchor == 'left' else right - text_width
            gc.DrawText(text, x, floor + 6)

        places = [(left + step * index, floor - (cost / peak) * (floor - top))
                  for index, (_, cost) in enumerate(points)]

        path = gc.CreatePath()
        path.MoveToPoint(*places[0])
        for place in places[1:]:
            path.AddLineToPoint(*place)
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(theme['accent'])).Width(2)
                               .Cap(wx.CAP_ROUND).Join(wx.JOIN_ROUND)))
        gc.StrokePath(path)

        gc.SetPen(wx.TRANSPARENT_PEN)
        for index, (x, y) in enumerate(places):
            last = index == len(places) - 1
            size = self.DOT + (1 if last else 0)
            gc.SetBrush(wx.Brush(wx.Colour(theme['accent'])))
            gc.DrawEllipse(x - size, y - size, size * 2, size * 2)
            if not last:
                gc.SetBrush(wx.Brush(wx.Colour(theme['face'])))
                gc.DrawEllipse(x - size + 1, y - size + 1, (size - 1) * 2, (size - 1) * 2)


class HeatBoard(Board):
    '''날짜 × 시각. 칸의 짙기가 그 시간에 오간 줄 수다.'''

    TOP = 30
    CELL_GAP = 2
    ROW_LABEL = 30
    LEGEND = 18
    LEVELS = 4

    def __init__(self, parent, theme):
        super().__init__(parent, theme, HEAT_HEIGHT)

    def get_level(self, count, peak):
        if count <= 0:
            return 0
        # 한 시간이 유난히 바쁘면 나머지가 다 같은 색이 된다. 제곱근으로 눌러 편다.
        return max(1, min(self.LEVELS, int(round((count / float(peak)) ** 0.5
                                                 * self.LEVELS))))

    def get_fill(self, level):
        theme = self.theme
        if level <= 0:
            return mix(theme['face'], theme['grid'], 0.7)
        return mix(theme['grid'], theme['accent'], level / float(self.LEVELS))

    def draw_body(self, gc, width, height):
        theme = self.theme
        data = self.data
        days = data['days']
        hours = data['hours']

        left = self.PADDING + self.ROW_LABEL
        right = width - self.PADDING
        span = (right - left + self.CELL_GAP) / 24.0
        cell = max(3.0, span - self.CELL_GAP)
        rows = len(days)
        available = height - self.TOP - self.PADDING - self.LEGEND
        stride = available / float(rows)
        box = min(cell, max(4.0, stride - self.CELL_GAP))

        peak = max([count for key, count in hours.items() if key[0] in days] or [1])

        # 카드 위에 이미 묶음 제목이 있어 안에는 시각 눈금만 둔다.
        gc.SetFont(get_font(7), wx.Colour(theme['dim']))
        for hour in (0, 6, 12, 18):
            gc.DrawText(str(hour), left + span * hour, self.TOP - 13)

        gc.SetPen(wx.TRANSPARENT_PEN)
        for row, day in enumerate(days):
            y = self.TOP + stride * row
            gc.SetFont(get_font(7), wx.Colour(theme['dim']))
            name = day[5:].replace('-', '/')
            gc.DrawText(name, self.PADDING, y + (box - 8) / 2)
            for hour in range(24):
                level = self.get_level(hours.get((day, hour), 0), peak)
                gc.SetBrush(wx.Brush(self.get_fill(level)))
                gc.DrawRoundedRectangle(left + span * hour, y, box, box, 1.5)

        self.draw_legend(gc, right, height - self.PADDING - 9)

    def draw_legend(self, gc, right, y):
        theme = self.theme
        gc.SetFont(get_font(7), wx.Colour(theme['dim']))
        size = 8.0
        gap = 3.0
        width = gc.GetTextExtent('less')[0] + gc.GetTextExtent('more')[0] + 12
        width += (self.LEVELS + 1) * (size + gap)
        x = right - width

        gc.DrawText('less', x, y - 1)
        x += gc.GetTextExtent('less')[0] + 6
        gc.SetPen(wx.TRANSPARENT_PEN)
        for level in range(self.LEVELS + 1):
            gc.SetBrush(wx.Brush(self.get_fill(level)))
            gc.DrawRoundedRectangle(x, y, size, size, 1.5)
            x += size + gap
        gc.DrawText('more', x + 2, y - 1)


class UsageBox(ScrollArea):

    def __init__(self, parent, theme):
        super().__init__(parent, theme)
        board = self.content
        self.labels = []
        self.loading = False

        self.today = TodayBoard(board, theme)
        self.limits = LimitBoard(board, theme, self.fit)
        self.trend = TrendBoard(board, theme)
        self.heat = HeatBoard(board, theme)
        self.boards = (self.today, self.limits, self.trend, self.heat)
        self.refresh = ActionCard(board, theme, 'Refresh',
                                  'Ask ccusage again and re-read the records',
                                  'Reload', self.reload)

        self.build()
        self.bind_children()
        self.apply_theme(theme)
        self.reload()

    def add_title(self, sizer, text):
        label = wx.StaticText(self.content, label=text)
        label.SetFont(get_font(10, bold=True))
        self.labels.append(label)
        sizer.Add(label, 0, wx.LEFT, MARGIN + TITLE_INSET)
        sizer.AddSpacer(TITLE_GAP)

    def build(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(MARGIN)
        for title, board in (('Today', self.today), ('Plan limits', self.limits),
                             ('Trend', self.trend), ('Activity', self.heat)):
            self.add_title(sizer, title)
            sizer.Add(board, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGIN)
            sizer.AddSpacer(GROUP_GAP)
        sizer.Add(self.refresh, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGIN)
        sizer.AddSpacer(GROUP_GAP)
        self.content.SetSizer(sizer)

    def apply_theme(self, theme):
        self.set_theme(theme)
        for label in self.labels:
            label.SetForegroundColour(wx.Colour(theme['text']))
        for board in self.boards:
            board.set_theme(theme)
        self.refresh.set_theme(theme)
        self.Refresh()

    def reload(self):
        if self.loading:
            return
        self.loading = True
        self.refresh.set_caption('…')
        for board in self.boards:
            board.set_data(None)
        threading.Thread(target=self.gather, daemon=True).start()

    def gather(self):
        try:
            data = usagedata.collect()
        except Exception:
            data = None
        # 그림은 주 실에서만. 여기서 곧바로 건드리면 wx 가 죽는다.
        wx.CallAfter(self.settle, data)

    def settle(self, data):
        self.loading = False
        self.refresh.set_caption('Reload')
        if data is None:
            return
        for board in self.boards:
            board.set_data(data)

    def tick(self):
        pass
