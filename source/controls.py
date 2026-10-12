# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

네이티브 wx.Button / wx.CheckBox 는 Windows 에서 배경색을 따르지 않아
다크 테마에서 혼자 밝게 남는다. 캔버스로 직접 그려 대체한다.
'''


import math
import time
import wx

from utilities import BAND_INSET
from utilities import BUTTON_FONT
from utilities import BUTTON_GAP
from utilities import BUTTON_HEIGHT
from utilities import BUTTON_PAD
from utilities import CARD_HEIGHT
from utilities import HEADER_BAND
from utilities import PANEL_GAP
from utilities import PANEL_MARGIN
from utilities import PANEL_PAD
from utilities import PANEL_RADIUS
from utilities import ROUND_SIZE
from utilities import Canvas
from utilities import apply_clip_siblings
from utilities import draw_chevron
from utilities import draw_frame
from utilities import draw_text_in
from utilities import fill_rect
from utilities import get_font
from utilities import get_ink
from utilities import get_text_top
from utilities import get_text_width
from utilities import mix
from utilities import shade


class Pressable(Canvas):
    '''캔버스 단추들이 공유하는 hover / press. 반응하는 것은 get_hit() 자리뿐이다 — 줄의 글씨
    위에서 단추가 밝아지거나 눌리면 안 된다(사용자). 누르면 마우스를 잡고, 그 자리 안에서
    놓아야 눌린 것이다. 밖으로 끌고 나가면 눌린 모양이 풀리고, 놓으면 아무 일도 없다.
    빨리 두 번 누르면 wx 는 둘째를 두 번 누름으로 보낸다 — 그것도 누름이다(on_dclick).'''

    def __init__(self, parent, theme, on_click):
        super().__init__(parent, theme)
        self.on_click = on_click
        self.hovered = False
        self.pressed = False
        self.holding = False
        self.up_position = wx.Point(-1, -1)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_down)
        self.Bind(wx.EVT_LEFT_DCLICK, self.on_dclick)
        self.Bind(wx.EVT_LEFT_UP, self.on_up)
        self.Bind(wx.EVT_MOTION, self.on_track)
        self.Bind(wx.EVT_ENTER_WINDOW, self.on_enter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self.on_leave)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self.on_lost)

    def get_hit(self):
        '''누를 수 있는 자리. None 이면 창 전체.'''
        return None

    def hits(self, position):
        rect = self.get_hit()
        return rect is None or rect.Contains(position)

    def set_hovered(self, hovered):
        if hovered != self.hovered:
            self.hovered = hovered
            self.update_cursor()
            self.Refresh()

    def update_cursor(self):
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND if self.hovered else wx.CURSOR_ARROW))

    def on_track(self, event):
        inside = self.hits(event.GetPosition())
        self.set_hovered(inside)
        if self.holding and inside != self.pressed:
            self.pressed = inside
            self.Refresh()
        event.Skip()

    def on_down(self, event):
        if not self.hits(event.GetPosition()):
            event.Skip()
            return
        self.holding = True
        self.pressed = True
        if not self.HasCapture():
            self.CaptureMouse()
        self.Refresh()

    def on_dclick(self, event):
        self.on_down(event)

    def on_up(self, event):
        if self.HasCapture():
            self.ReleaseMouse()
        # 누른 일이 어느 칸인지(고르기·보이스 칸)는 놓은 자리로 정한다. 전역 커서 자리를 다시
        # 읽으면 이벤트와 어긋날 수 있다.
        self.up_position = event.GetPosition()
        clicked = self.holding and self.hits(self.up_position)
        self.holding = False
        self.pressed = False
        self.Refresh()
        if clicked and self.on_click:
            self.on_click()

    def on_lost(self, event):
        self.holding = False
        self.pressed = False
        self.Refresh()

    def on_enter(self, event):
        self.set_hovered(self.hits(event.GetPosition()))

    def on_leave(self, event):
        # 잡고 있는 동안은 밖으로 나가도 놓을 때까지 기다린다. 눌린 모양만 풀린다.
        if self.holding:
            if self.pressed:
                self.pressed = False
                self.Refresh()
            self.set_hovered(False)
            return
        self.set_hovered(False)


class RoundButton(Pressable):
    '''Windows 시계와 같은 원형 아이콘 버튼. 글자 대신 아이콘을 그린다.
    tone 은 원의 채움색과 아이콘 색을 고르는 이름이다. 지도처럼 그림 위에 얹히는
    자리에는 평소엔 아이콘만 두고 호버 때만 회색이 비치는 ghost 를 쓴다.'''

    TONES = {
        'plain': ('control', 'text'),
        'primary': ('accent', '#ffffff'),
        'ghost': (None, 'dim'),
    }

    # 모서리를 굴린 네모로 그리고 싶을 때 쓰는 반지름. None 이면 동그라미다.
    CORNER = 9

    def __init__(self, parent, theme, icon, on_click, tone='plain', size=ROUND_SIZE,
                 square=False, backdrop=None):
        super().__init__(parent, theme, on_click)
        self.icon = icon
        self.tone = tone
        self.square = square
        # 뒤가 한 색으로 덮인 판 위라면 그 색만 깔면 된다. 부모 그림을 다시
        # 부르는 draw_backdrop 은 그리기 상태가 얽혀 화면이 깨지기 쉽다.
        self.backdrop = backdrop
        self.SetMinSize(wx.Size(size, size))

    def set_backdrop(self, colour):
        self.backdrop = colour
        self.Refresh()

    def set_icon(self, icon):
        if icon != self.icon:
            self.icon = icon
            self.Refresh()

    def set_tone(self, tone):
        if tone != self.tone:
            self.tone = tone
            self.Refresh()

    def draw(self, gc, width, height):
        theme = self.theme
        radius = min(width, height) / 2 - 1
        cx, cy = width / 2, height / 2

        key, mark = self.TONES[self.tone]
        # 채운 톤이라도 굴린 모서리 바깥은 비어 있다. 그 자리를 채워 두지 않으면
        # 페이지 배경색이 그대로 드러나 네모난 검은 자국이 남는다.
        if self.backdrop is not None:
            gc.SetPen(wx.TRANSPARENT_PEN)
            gc.SetBrush(wx.Brush(wx.Colour(self.backdrop)))
            gc.DrawRectangle(0, 0, width, height)
        else:
            self.draw_backdrop(gc)
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(self.get_fill(key)))
        if self.square:
            gc.DrawRoundedRectangle(cx - radius, cy - radius,
                                    radius * 2, radius * 2, self.CORNER)
        else:
            gc.DrawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

        # 아이콘 색은 테마의 이름일 수도, 테마를 타지 않는 색 자체일 수도 있다.
        self.draw_icon(gc, cx, cy, radius, wx.Colour(theme.get(mark, mark)))

    def get_fill(self, key):
        if key is None:
            # 채움색이 없으면 평소엔 비워 두고 호버·눌림에만 회색을 비친다.
            grey = wx.Colour(self.theme['tick'])
            alpha = 96 if self.pressed else 64 if self.hovered else 0
            return wx.Colour(grey.Red(), grey.Green(), grey.Blue(), alpha)

        fill = self.theme[key]
        if self.pressed:
            fill = shade(fill, 0.85)
        elif self.hovered:
            fill = shade(fill, 1.16)
        return wx.Colour(fill)

    def draw_icon(self, gc, cx, cy, radius, colour):
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(colour))

        if self.icon == 'play':
            path = gc.CreatePath()
            # 삼각형은 무게 중심이 왼쪽으로 쏠려 보여 조금 오른쪽으로 민다.
            path.MoveToPoint(cx - radius * 0.19, cy - radius * 0.40)
            path.AddLineToPoint(cx + radius * 0.44, cy)
            path.AddLineToPoint(cx - radius * 0.19, cy + radius * 0.40)
            path.CloseSubpath()
            gc.FillPath(path)

        elif self.icon == 'pause':
            for sign in (-1, 1):
                gc.DrawRectangle(cx + sign * radius * 0.24 - radius * 0.08,
                                 cy - radius * 0.38, radius * 0.16, radius * 0.76)

        elif self.icon == 'flag':
            gc.SetPen(wx.Pen(colour, max(2, int(radius * 0.11))))
            gc.StrokeLine(cx - radius * 0.28, cy - radius * 0.44,
                          cx - radius * 0.28, cy + radius * 0.46)
            gc.SetPen(wx.TRANSPARENT_PEN)
            path = gc.CreatePath()
            path.MoveToPoint(cx - radius * 0.28, cy - radius * 0.40)
            path.AddLineToPoint(cx + radius * 0.40, cy - radius * 0.14)
            path.AddLineToPoint(cx - radius * 0.28, cy + radius * 0.12)
            path.CloseSubpath()
            gc.FillPath(path)

        elif self.icon in ('plus', 'minus'):
            # 가로획이 상자 한가운데를 지나면 아래로 처져 보인다. 한 픽셀 올린다.
            cy -= 1
            arm = radius * 0.44
            gc.SetPen(wx.Pen(colour, max(1, round(radius * 0.13))))
            gc.StrokeLine(cx - arm, cy, cx + arm, cy)
            if self.icon == 'plus':
                gc.StrokeLine(cx, cy - arm, cx, cy + arm)
            gc.SetPen(wx.TRANSPARENT_PEN)

        elif self.icon == 'pencil':
            # 왼쪽 아래 촉에서 오른쪽 위 꼭지까지 기울어진 몸통 하나로 그린다.
            length = radius * 0.60
            half = radius * 0.15
            neck = radius * 0.26
            dx, dy = math.cos(math.radians(-45)), math.sin(math.radians(-45))
            px, py = -dy, dx
            tip = (cx - dx * length, cy - dy * length)
            end = (cx + dx * length, cy + dy * length)

            path = gc.CreatePath()
            path.MoveToPoint(tip[0], tip[1])
            path.AddLineToPoint(tip[0] + dx * neck + px * half,
                                tip[1] + dy * neck + py * half)
            path.AddLineToPoint(end[0] + px * half, end[1] + py * half)
            path.AddLineToPoint(end[0] - px * half, end[1] - py * half)
            path.AddLineToPoint(tip[0] + dx * neck - px * half,
                                tip[1] + dy * neck - py * half)
            path.CloseSubpath()
            gc.FillPath(path)

        elif self.icon == 'back':
            gc.SetPen(wx.Pen(colour, max(2, int(radius * 0.12))))
            gc.StrokeLine(cx - radius * 0.36, cy, cx + radius * 0.38, cy)
            gc.SetPen(wx.TRANSPARENT_PEN)
            path = gc.CreatePath()
            path.MoveToPoint(cx - radius * 0.44, cy)
            path.AddLineToPoint(cx - radius * 0.06, cy - radius * 0.28)
            path.AddLineToPoint(cx - radius * 0.06, cy + radius * 0.28)
            path.CloseSubpath()
            gc.FillPath(path)

        elif self.icon == 'reset':
            self.draw_reset(gc, cx, cy, radius, colour)

    def draw_reset(self, gc, cx, cy, radius, colour):
        ring = radius * 0.40
        # 위쪽을 터놓은 원호에 반시계 방향 화살촉을 붙인다.
        path = gc.CreatePath()
        path.AddArc(cx, cy, ring, math.radians(300), math.radians(240), True)
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        gc.SetPen(wx.Pen(colour, max(2, int(radius * 0.12))))
        gc.StrokePath(path)

        angle = math.radians(300)
        x, y = cx + ring * math.cos(angle), cy + ring * math.sin(angle)
        dx, dy = math.sin(angle), -math.cos(angle)
        size = radius * 0.24
        path = gc.CreatePath()
        path.MoveToPoint(x + dx * size, y + dy * size)
        path.AddLineToPoint(x - dy * size * 0.8, y + dx * size * 0.8)
        path.AddLineToPoint(x + dy * size * 0.8, y - dx * size * 0.8)
        path.CloseSubpath()
        gc.SetBrush(wx.Brush(colour))
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.FillPath(path)


def get_pen(gc, colour, width=1):
    '''반 칸 굵기도 받는 그래픽 펜. wx.Pen 은 정수 굵기만 받는다.'''
    return gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(colour)).Width(width))


def get_button_width(text):
    return get_text_width(get_font(BUTTON_FONT), text) + BUTTON_PAD * 2


def draw_button(gc, theme, rect, text, state='plain', tone=None):
    '''누르는 것은 모두 이 모양 하나 (PyWinAudio 의 Button·Segment·Switch). state 는
    'lit'(고른 것·켜진 것: 강조색으로 채움)·'down'·'hover'·'plain'. 글씨 굵기는 상태와 상관없이
    같다 — 굵어지면 폭이 변해 옆 칸이 밀린다. tone='warn' 이면 한 번 더 누르면 되돌릴 수 없는 일.'''
    if state == 'lit':
        fill, edge, colour = theme['accent'], theme['accent'], theme['on_accent']
    else:
        fill = {'down': theme['control_down'], 'hover': theme['control_hover']}.get(
            state, theme['control'])
        edge, colour = theme['edge'], theme['text']
        if tone == 'warn':
            edge = colour = theme['warn']
    gc.SetPen(get_pen(gc, edge))
    gc.SetBrush(wx.Brush(wx.Colour(fill)))
    gc.DrawRoundedRectangle(rect.x + 0.5, rect.y + 0.5, rect.width - 1, rect.height - 1,
                            PANEL_RADIUS)
    draw_text_in(gc, text, rect, get_font(BUTTON_FONT), colour, back=fill)


def draw_row_face(gc, theme, width, height, first, last):
    '''판 본체의 한 줄. 판 안의 줄은 사이 틈 없이 붙고, 둘째 줄부터 위에 안쪽으로 들인
    1 px 금을 긋는다. 판의 마지막 줄만 아래 모서리를 굴린다.'''
    fill = theme['face']
    if last:
        fill_rect(gc, fill, 0, 0, width, height, PANEL_RADIUS)
        fill_rect(gc, fill, 0, 0, width, PANEL_RADIUS)
    else:
        fill_rect(gc, fill, 0, 0, width, height)
    if not first:
        fill_rect(gc, theme['rim'], PANEL_PAD, 0, max(0, width - PANEL_PAD * 2), 1)


class PanelHeader(Pressable):
    '''판의 이름 띠 (PyWinAudio 랙 장치의 머리 띠와 같은 모양). 왼쪽 끝에 강조색 줄, 그 옆에
    꺾쇠+대문자 제목이 한 단추로 서고 그 단추만 접고 편다. 부제는 단추 밖에 흐리게.'''

    TITLE_SIZE = 9
    CHEVRON = 10
    # 단추 안: 왼쪽 여백, 꺾쇠, 꺾쇠와 제목 사이, 제목 뒤 여백.
    LEFT = 6
    SPACE = 6
    RIGHT = 8
    SUB_GAP = 8

    def __init__(self, parent, theme, title, subtitle, on_toggle):
        super().__init__(parent, theme, on_toggle)
        self.title = title.upper()
        self.subtitle = subtitle
        self.folded = False
        self.SetToolTip('Fold')
        self.update_height()

    def set_folded(self, folded):
        self.folded = folded
        self.SetToolTip('Unfold' if folded else 'Fold')
        self.update_height()
        self.Refresh()

    def set_subtitle(self, subtitle):
        if subtitle != self.subtitle:
            self.subtitle = subtitle
            self.Refresh()

    def update_height(self):
        # 펼친 판은 띠 아래 1 px 금까지가 머리다.
        self.SetMinSize(wx.Size(-1, HEADER_BAND + (0 if self.folded else 1)))

    def get_title_left(self):
        return BAND_INSET + self.LEFT + self.CHEVRON + self.SPACE

    def get_hit(self):
        width = self.GetClientSize()[0]
        right = self.get_title_left() + get_text_width(get_font(self.TITLE_SIZE, True),
                                                       self.title) + self.RIGHT
        return wx.Rect(BAND_INSET, BAND_INSET, max(0, min(right, width - BAND_INSET) - BAND_INSET),
                       BUTTON_HEIGHT)

    def draw(self, gc, width, height):
        theme = self.theme
        fill_rect(gc, theme['band'], 0, 0, width, HEADER_BAND, PANEL_RADIUS)
        if not self.folded:
            fill_rect(gc, theme['band'], 0, HEADER_BAND - PANEL_RADIUS, width, PANEL_RADIUS)
            fill_rect(gc, theme['rim'], 0, HEADER_BAND, width, 1)
        fill_rect(gc, theme['accent'], 0, 6, 2, HEADER_BAND - 12, 1)

        hit = self.get_hit()
        if self.pressed:
            fill_rect(gc, theme['control_down'], hit.x, hit.y, hit.width, hit.height, PANEL_RADIUS)
        elif self.hovered:
            fill_rect(gc, theme['control_hover'], hit.x, hit.y, hit.width, hit.height, PANEL_RADIUS)
        middle = HEADER_BAND / 2
        draw_chevron(gc, 'right' if self.folded else 'down',
                     BAND_INSET + self.LEFT + self.CHEVRON / 2, middle, self.CHEVRON,
                     theme['text'] if self.hovered else theme['dim'])

        font = get_font(self.TITLE_SIZE, True)
        left = self.get_title_left()
        limit = max(0, width - left - PANEL_PAD)
        gc.SetFont(font, wx.Colour(theme['text']))
        title = self.fit_text(gc, self.title, limit)
        title_top = get_text_top(font, 0, HEADER_BAND)
        gc.DrawText(title, left, title_top)
        if self.subtitle:
            sub_font = get_font(8)
            sub_left = hit.x + hit.width + self.SUB_GAP
            room = width - sub_left - PANEL_PAD
            if room > 12:
                gc.SetFont(sub_font, wx.Colour(theme['dim']))
                # 부제는 제목과 기준선을 맞춘다. 글씨 크기가 달라 가운데로 맞추면 들떠 보인다.
                baseline = title_top + get_ink(font)[1]
                gc.DrawText(self.fit_text(gc, self.subtitle, room), sub_left,
                            baseline - get_ink(sub_font)[1])


class Panel:
    '''이름 띠 하나와 그 아래 줄들을 한 판으로 묶는다. 위젯이 아니라 세로 사이저 하나다 —
    페이지가 그 사이저를 단에 담는다. 접힘은 folds(접힌 판 키의 모음, 앱이 저장한다)에
    적고 on_fold 로 알린다.

    body 는 줄(창) 또는 줄을 담은 사이저의 나열이다. 판 모양(첫 줄 금·마지막 줄 모서리)을
    정하는 것은 rows — 화면에 놓인 차례대로의 줄 창들이다.'''

    def __init__(self, parent, theme, key, title, body, folds, on_fold, subtitle='', rows=None):
        self.key = key
        self.folds = folds
        self.on_fold = on_fold
        self.header = PanelHeader(parent, theme, title, subtitle, self.toggle)
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.header, 0, wx.EXPAND)
        for item in body:
            self.sizer.Add(item, 0, wx.EXPAND)
        self.sizer.AddSpacer(PANEL_GAP)
        self.set_rows(rows if rows is not None else body)
        self.apply_fold()

    @property
    def folded(self):
        return self.key in self.folds

    def set_rows(self, rows):
        rows = list(rows)
        for index, row in enumerate(rows):
            first, last = index == 0, index == len(rows) - 1
            if getattr(row, 'first', None) != first or getattr(row, 'last', None) != last:
                row.first, row.last = first, last
                row.Refresh()

    def toggle(self):
        if self.folded:
            self.folds.discard(self.key)
        else:
            self.folds.add(self.key)
        self.apply_fold()
        if self.on_fold:
            self.on_fold()

    def apply_fold(self):
        folded = self.folded
        self.header.set_folded(folded)
        # 맨 앞은 머리, 맨 뒤는 판 사이 틈이다. wx 의 항목 목록은 잘라 쓸 수 없어 list 로.
        for item in list(self.sizer.GetChildren())[1:-1]:
            item.Show(not folded)


class CardBase(Pressable):
    '''판 본체의 한 줄. 왼쪽에 제목·설명, 오른쪽 끝에 조작부. 반응하는 것은 조작부뿐이다
    (get_control_rect). 조작부가 자리를 먼저 잡고 남는 왼쪽을 글자가 쓴다.'''

    PADDING = PANEL_PAD
    # 제목이 조작부에 닿지 않게 두는 자리.
    LABEL_GAP = 12
    # 제목 기준선에서 설명 대문자 윗줄까지.
    LINE_GAP = 6
    # 판 안에서의 자리. Panel.set_rows 가 정한다.
    first = True
    last = True

    def __init__(self, parent, theme, label, description, on_change=None):
        super().__init__(parent, theme, self.activate)
        self.label = label
        self.description = description
        self.on_change = on_change
        self.SetMinSize(wx.Size(-1, CARD_HEIGHT))

    def activate(self):
        '''조작부를 눌렀을 때 하는 일.'''

    def notify(self):
        self.Refresh()
        if self.on_change:
            self.on_change()

    def get_control_rect(self, width, height):
        '''누를 자리. 기본은 없다.'''
        return wx.Rect()

    def get_button_rect(self, width, height, button_width):
        '''오른쪽 끝, 세로 가운데의 단추 한 칸.'''
        return wx.Rect(width - self.PADDING - button_width, (height - BUTTON_HEIGHT) // 2,
                       button_width, BUTTON_HEIGHT)

    def get_hit(self):
        width, height = self.GetClientSize()
        return self.get_control_rect(width, height)

    def draw(self, gc, width, height):
        theme = self.theme
        draw_row_face(gc, theme, width, height, self.first, self.last)
        label_right = self.draw_control(gc, width, height) - self.LABEL_GAP
        self.draw_label(gc, height, max(0, label_right - self.PADDING))

    def draw_label(self, gc, height, limit):
        '''제목과 설명 두 줄을 대문자 잉크로 재서 줄의 세로 가운데에 놓는다.'''
        theme = self.theme
        title_font, note_font = get_font(10), get_font(8)
        title_ink, note_ink = get_ink(title_font), get_ink(note_font)
        title_height = title_ink[1] - title_ink[0] + 1
        note_height = note_ink[1] - note_ink[0] + 1
        if self.description:
            block = title_height + self.LINE_GAP + note_height
        else:
            block = title_height
        top = (height - block) // 2
        gc.SetFont(title_font, wx.Colour(theme['text']))
        gc.DrawText(self.fit_text(gc, self.label, limit), self.PADDING, top - title_ink[0])
        if self.description:
            gc.SetFont(note_font, wx.Colour(theme['dim']))
            gc.DrawText(self.fit_text(gc, self.description, limit), self.PADDING,
                        top + title_height + self.LINE_GAP - note_ink[0])

    def get_state(self):
        if self.pressed:
            return 'down'
        return 'hover' if self.hovered else 'plain'

    def draw_control(self, gc, width, height):
        '''오른쪽 끝에서부터 조작부를 그리고 그 왼쪽 끝 x 를 돌려준다.'''
        return width - self.PADDING


class SettingCard(CardBase):
    '''오른쪽 끝에 ON/OFF 글씨 단추를 둔 줄 (PyWinAudio 의 Switch). 켜지면 강조색으로 채운다.'''

    SWITCH_WIDTH = 48

    value = False

    def GetValue(self):
        return self.value

    def SetValue(self, value):
        self.value = bool(value)
        self.Refresh()

    def activate(self):
        self.value = not self.value
        self.notify()

    def get_control_rect(self, width, height):
        return self.get_button_rect(width, height, self.SWITCH_WIDTH)

    def draw_control(self, gc, width, height):
        rect = self.get_control_rect(width, height)
        state = 'lit' if self.value else self.get_state()
        if self.value and self.pressed:
            state = 'down'
        draw_button(gc, self.theme, rect, 'ON' if self.value else 'OFF', state)
        return rect.x


class LayoutCard(SettingCard):
    '''끌어서 차례를 바꾸는 토글 줄 (사용량 페이지의 묶음 차례·숨김). 줄 어디서든 눌러
    몇 픽셀 움직이면 끌기가 되고, 토글은 ON/OFF 단추로만 한다. 끄는 동안의 자리 계산과
    애니메이션은 부모가 한다 (`on_drag(card, phase, screen_y)`, phase 는 'start'·'move'·'drop').'''

    GRIP = 14
    # 이만큼 움직여야 끌기로 본다. 손이 떨려 누른 것이 끌기가 되면 토글이 안 먹는다.
    DRAG_SLOP = 4

    def __init__(self, parent, theme, label, description, on_change=None, on_drag=None):
        super().__init__(parent, theme, label, description, on_change)
        self.on_drag = on_drag
        self.press_y = None
        self.dragging = False
        self.Bind(wx.EVT_MOTION, self.on_motion)
        self.update_cursor()

    def update_cursor(self):
        # 단추 위는 누르는 손, 나머지는 위아래로 끄는 손.
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND if self.hovered and not self.dragging
                                 else wx.CURSOR_SIZENS))

    def get_screen_y(self, event):
        return self.ClientToScreen(event.GetPosition()).y

    def on_down(self, event):
        self.press_y = self.get_screen_y(event)
        super().on_down(event)
        if not self.HasCapture():
            self.CaptureMouse()

    def on_motion(self, event):
        if self.press_y is not None and event.LeftIsDown():
            y = self.get_screen_y(event)
            if not self.dragging and abs(y - self.press_y) >= self.DRAG_SLOP:
                self.dragging = True
                # 끌기가 되면 단추 누름은 없던 일이다.
                self.holding = False
                self.pressed = False
                self.update_cursor()
                self.Refresh()
                if self.on_drag:
                    self.on_drag(self, 'start', self.press_y)
            if self.dragging:
                if self.on_drag:
                    self.on_drag(self, 'move', y)
                return
        event.Skip()

    def on_up(self, event):
        self.press_y = None
        if self.dragging:
            if self.HasCapture():
                self.ReleaseMouse()
            self.finish_drag(self.get_screen_y(event))
            return
        super().on_up(event)

    def on_lost(self, event):
        self.press_y = None
        super().on_lost(event)
        if self.dragging:
            self.finish_drag(wx.GetMousePosition().y)

    def finish_drag(self, y):
        self.dragging = False
        self.pressed = False
        self.update_cursor()
        self.Refresh()
        if self.on_drag:
            self.on_drag(self, 'drop', y)

    def draw(self, gc, width, height):
        super().draw(gc, width, height)
        if self.dragging:
            # 들려 있는 줄은 강조색 1 px 테두리로 다른 줄과 갈라 보이게 한다.
            draw_frame(gc, self.theme['accent'], 0, 0, width, height)

    def draw_control(self, gc, width, height):
        theme = self.theme
        left = super().draw_control(gc, width, height)
        # 끌 수 있다는 표시: 점 두 줄 세 칸. 단추와의 사이는 단추끼리의 사이를 세 번.
        grip_left = left - BUTTON_GAP * 3 - self.GRIP
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(wx.Colour(theme['dim'])))
        cy = height // 2
        for column in (0, 6):
            for row in (-5, 0, 5):
                gc.DrawEllipse(grip_left + 4 + column - 1.25, cy + row - 1.25, 2.5, 2.5)
        return grip_left


class ChoiceCard(CardBase):
    '''고를 것이 몇 되지 않으면 칸을 나란히 붙인다 (PyWinAudio 의 Segment). 칸 폭은 모두
    같고 고른 칸만 강조색으로 채운다. 누른 칸에서 놓아야 고른다.'''

    marked = -1
    down_index = -1

    def __init__(self, parent, theme, label, description, options, on_change=None):
        super().__init__(parent, theme, label, description, on_change)
        # (저장할 값, 보일 이름) 의 나열.
        self.options = options
        self.value = options[0][0]
        self.segment = max(get_button_width(name) for _, name in options)

    def GetValue(self):
        return self.value

    def SetValue(self, value):
        if value in [option[0] for option in self.options]:
            self.value = value
            self.Refresh()

    def get_cell(self, index, width, height):
        count = len(self.options)
        left = width - self.PADDING - self.segment * count - BUTTON_GAP * (count - 1)
        return wx.Rect(left + (self.segment + BUTTON_GAP) * index, (height - BUTTON_HEIGHT) // 2,
                       self.segment, BUTTON_HEIGHT)

    def get_index(self, position):
        width, height = self.GetClientSize()
        for index in range(len(self.options)):
            if self.get_cell(index, width, height).Contains(position):
                return index
        # 칸 사이 빈자리는 어느 쪽도 아니다. 넘겨짚어 고르면 눌린 적 없는 값이 선다.
        return -1

    def hits(self, position):
        return self.get_index(position) >= 0

    def on_track(self, event):
        index = self.get_index(event.GetPosition())
        if index != self.marked:
            self.marked = index
            self.Refresh()
        super().on_track(event)

    def on_down(self, event):
        self.down_index = self.get_index(event.GetPosition())
        super().on_down(event)

    def on_leave(self, event):
        if self.marked != -1:
            self.marked = -1
            self.Refresh()
        super().on_leave(event)

    def activate(self):
        index = self.get_index(self.up_position)
        if index < 0 or index != self.down_index or self.options[index][0] == self.value:
            return
        self.value = self.options[index][0]
        self.notify()

    def draw_control(self, gc, width, height):
        for index, (value, name) in enumerate(self.options):
            if value == self.value:
                state = 'lit'
            elif self.pressed and index == self.down_index and index == self.marked:
                state = 'down'
            elif index == self.marked:
                state = 'hover'
            else:
                state = 'plain'
            draw_button(gc, self.theme, self.get_cell(index, width, height), name, state)
        return self.get_cell(0, width, height).x


class SliderCard(CardBase):
    '''오른쪽 끝에 track 과 값을 둔 줄. 손잡이는 PyWinAudio 그래픽 EQ 페이더의 납작한
    손잡이를 눕힌 것이다. track 을 누르면 그 자리로, 손잡이를 잡으면 잡은 자리 그대로 따라온다.
    Shift 를 누른 채 끌면 열 배 곱게, 두 번 누르면 기본값.

    track 의 자리와 폭은 모든 줄이 같다 — 값 칸을 줄마다 재면 자릿수에 따라 track 이
    들쭉날쭉해진다(사용자). 다섯 자리 숫자 폭으로 모두 맞춘다.'''

    TRACK_WIDTH = 116
    TRACK_HEIGHT = 2
    THUMB = (8, 14)
    VALUE_SIZE = 9
    # ★손잡이는 끝값에서 track 밖으로 반 폭만큼 더 나간다. 값 칸과의 사이가 그보다 넉넉해야 한다.
    VALUE_GAP = 14
    FINE = 10.0

    def __init__(self, parent, theme, label, description, bounds, on_change=None, default=None):
        super().__init__(parent, theme, label, description, on_change)
        self.low, self.high, self.step, self.digits = bounds
        self.default = default
        self.value = self.low
        self.dragging = False
        self.grab = None
        self.value_width = get_text_width(get_font(self.VALUE_SIZE), '00000')

    def format(self, value):
        if self.digits == 0:
            return str(int(round(value)))
        return ('%%.%df' % self.digits) % value

    def GetValue(self):
        if self.digits == 0:
            return int(round(self.value))
        return round(self.value, self.digits)

    def SetValue(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return
        self.value = min(self.high, max(self.low, value))
        self.Refresh()

    def get_track_left(self, width):
        return width - self.PADDING - self.value_width - self.VALUE_GAP - self.TRACK_WIDTH

    def get_knob_x(self, width):
        span = (self.value - self.low) / float(self.high - self.low)
        return self.get_track_left(width) + self.TRACK_WIDTH * span

    def get_control_rect(self, width, height):
        thumb = self.THUMB[0]
        return wx.Rect(self.get_track_left(width) - thumb, (height - BUTTON_HEIGHT) // 2,
                       self.TRACK_WIDTH + thumb * 2, BUTTON_HEIGHT)

    def update_cursor(self):
        self.SetCursor(wx.Cursor(wx.CURSOR_SIZEWE if self.hovered or self.dragging
                                 else wx.CURSOR_ARROW))

    def put(self, value):
        stepped = self.low + round((value - self.low) / self.step) * self.step
        value = min(self.high, max(self.low, stepped))
        if self.digits:
            value = round(value, self.digits)
        if value != self.value:
            self.value = value
            self.notify()
        else:
            self.Refresh()

    def on_down(self, event):
        position = event.GetPosition()
        if not self.hits(position):
            event.Skip()
            return
        width = self.GetClientSize()[0]
        knob = self.get_knob_x(width)
        if abs(position.x - knob) > self.THUMB[0] / 2 + 2:
            # track 을 누르면 손잡이가 그 자리로 온다. 그다음부터는 끌기다.
            ratio = (position.x - self.get_track_left(width)) / float(self.TRACK_WIDTH)
            self.put(self.low + min(1.0, max(0.0, ratio)) * (self.high - self.low))
        self.grab = (position.x, self.value, event.ShiftDown())
        self.dragging = True
        self.pressed = True
        if not self.HasCapture():
            self.CaptureMouse()
        self.update_cursor()
        self.Refresh()

    def on_track(self, event):
        if self.dragging and self.grab:
            x, value, fine = self.grab
            shift = event.ShiftDown()
            if shift != fine:
                # 곱게 끌기를 켜고 끌 때 손잡이가 튀지 않게 그 자리에서 다시 잡는다.
                self.grab = (event.GetPosition().x, self.value, shift)
                return
            per_pixel = (self.high - self.low) / float(self.TRACK_WIDTH)
            if shift:
                per_pixel /= self.FINE
            self.put(value + (event.GetPosition().x - x) * per_pixel)
            return
        super().on_track(event)

    def on_up(self, event):
        self.release()
        self.set_hovered(self.hits(event.GetPosition()))

    def on_dclick(self, event):
        if not self.hits(event.GetPosition()):
            event.Skip()
            return
        self.release()
        if self.default is not None:
            self.put(self.default)

    def on_lost(self, event):
        self.dragging = False
        self.pressed = False
        self.grab = None
        self.update_cursor()
        self.Refresh()

    def on_leave(self, event):
        # 끄는 중이라면 캡처가 살아 있어 손을 놓을 때까지 그대로 둔다.
        if not self.dragging:
            super().on_leave(event)

    def release(self):
        if self.HasCapture():
            self.ReleaseMouse()
        self.dragging = False
        self.pressed = False
        self.grab = None
        self.update_cursor()
        self.Refresh()

    def draw_control(self, gc, width, height):
        theme = self.theme
        left = self.get_track_left(width)
        middle = height // 2
        knob_x = round(self.get_knob_x(width))

        value_rect = wx.Rect(width - self.PADDING - self.value_width, 0, self.value_width, height)
        draw_text_in(gc, self.format(self.value), value_rect, get_font(self.VALUE_SIZE),
                     theme['text'], align='right')

        top = middle - self.TRACK_HEIGHT // 2
        fill_rect(gc, theme['track'], left, top, self.TRACK_WIDTH, self.TRACK_HEIGHT, 1)
        if knob_x > left:
            fill_rect(gc, theme['accent'], left, top, knob_x - left, self.TRACK_HEIGHT, 1)

        thumb_width, thumb_height = self.THUMB
        lit = self.hovered or self.dragging
        fill_rect(gc, theme['thumb_hover'] if lit else theme['thumb'],
                  knob_x - thumb_width // 2, middle - thumb_height // 2,
                  thumb_width, thumb_height, 1.5)
        fill_rect(gc, theme['thumb_line'], knob_x, middle - thumb_height // 2 + 2,
                  1, thumb_height - 4)
        return left - thumb_width // 2


class ChipGrid(Pressable):
    '''고를 것이 스무 남짓이라 한 줄에 칸을 늘어세울 수 없다. 줄을 접어 격자로 늘어놓고
    하나만 고른다. 칸은 다른 단추와 같은 모양·크기이고, 판 본체의 한 줄로 놓인다.

    높이가 폭에서 나오므로 접히는 줄 수가 바뀔 때만 최소 크기를 다시 준다 —
    줄 수는 띄엄띄엄한 값이라 되먹임이 생기지 않는다.'''

    PADDING = PANEL_PAD

    marked = -1
    down_index = -1
    first = True
    last = True

    def __init__(self, parent, theme, options, on_change=None, on_layout=None):
        super().__init__(parent, theme, self.choose)
        self.on_change = on_change
        # 줄 수가 바뀌면 담고 있는 쪽의 높이도 달라진다. 굴리는 자리에 담겼다면
        # 그쪽이 자기 크기를 다시 잡아야 한다.
        self.on_layout = on_layout
        self.value = ''
        self.chip = 44
        self.set_options(options)
        self.Bind(wx.EVT_SIZE, self.on_size)

    def set_options(self, options):
        self.options = list(options)
        self.chip = max([get_button_width(name) for name in self.options] or [44])
        self.relayout()

    def GetValue(self):
        return self.value

    def SetValue(self, value):
        self.value = value
        self.Refresh()

    def get_columns(self, width):
        usable = width - self.PADDING * 2 + BUTTON_GAP
        return max(1, int(usable // (self.chip + BUTTON_GAP)))

    def get_rows(self, width):
        columns = self.get_columns(width)
        return max(1, (len(self.options) + columns - 1) // columns)

    def get_height(self, width):
        rows = self.get_rows(width)
        return self.PADDING * 2 + rows * BUTTON_HEIGHT + (rows - 1) * BUTTON_GAP

    def relayout(self):
        width = self.GetClientSize()[0]
        if width <= 0:
            return
        height = self.get_height(width)
        if height != self.GetMinSize()[1]:
            self.SetMinSize(wx.Size(-1, height))
            self.GetParent().Layout()
            if self.on_layout:
                self.on_layout()
        self.Refresh()

    def on_size(self, event):
        self.relayout()
        event.Skip()

    def get_chip_rect(self, index, width):
        columns = self.get_columns(width)
        row, column = divmod(index, columns)
        return wx.Rect(self.PADDING + column * (self.chip + BUTTON_GAP),
                       self.PADDING + row * (BUTTON_HEIGHT + BUTTON_GAP),
                       self.chip, BUTTON_HEIGHT)

    def hit_test(self, position):
        width = self.GetClientSize()[0]
        for index in range(len(self.options)):
            if self.get_chip_rect(index, width).Contains(position):
                return index
        return -1

    def hits(self, position):
        return self.hit_test(position) >= 0

    def on_track(self, event):
        index = self.hit_test(event.GetPosition())
        if index != self.marked:
            self.marked = index
            self.Refresh()
        super().on_track(event)

    def on_down(self, event):
        self.down_index = self.hit_test(event.GetPosition())
        super().on_down(event)

    def on_leave(self, event):
        if self.marked != -1:
            self.marked = -1
            self.Refresh()
        super().on_leave(event)

    def choose(self):
        index = self.hit_test(self.up_position)
        if index < 0 or index != self.down_index or self.options[index] == self.value:
            return
        self.value = self.options[index]
        self.Refresh()
        if self.on_change:
            self.on_change()

    def draw(self, gc, width, height):
        draw_row_face(gc, self.theme, width, height, self.first, self.last)
        for index, name in enumerate(self.options):
            if name == self.value:
                state = 'lit'
            elif self.pressed and index == self.down_index and index == self.marked:
                state = 'down'
            elif index == self.marked:
                state = 'hover'
            else:
                state = 'plain'
            draw_button(gc, self.theme, self.get_chip_rect(index, width), name, state)


class ActionCard(CardBase):
    '''오른쪽 끝에 글자 단추 하나를 둔 줄. 값이 아니라 일을 시킨다. 한 번 더 누르면 되돌릴 수
    없는 일이 나는 동안(warn)은 테두리와 글씨가 주황이다.'''

    tone = 'plain'

    def __init__(self, parent, theme, label, description, caption, on_click=None):
        super().__init__(parent, theme, label, description)
        self.action = on_click
        self.caption = None
        self.captions = [caption]
        self.set_caption(caption)

    def set_caption(self, caption):
        '''글씨가 바뀌어도(Reset index → Confirm) 단추 폭은 그대로다. 지금까지 쓴 글씨 가운데
        가장 긴 것에 맞춘다 — 누를 때마다 단추가 줄었다 늘었다 하면 손이 놓친다.'''
        if caption not in self.captions:
            self.captions.append(caption)
        self.button = max(get_button_width(text) for text in self.captions)
        if caption != self.caption:
            self.caption = caption
            self.Refresh()

    def set_captions(self, *captions):
        '''미리 쓸 글씨를 모두 알려 둔다. 처음부터 그 폭으로 선다.'''
        for caption in captions:
            if caption not in self.captions:
                self.captions.append(caption)
        self.set_caption(self.caption)

    def set_description(self, description):
        if description != self.description:
            self.description = description
            self.Refresh()

    def set_tone(self, tone):
        if tone != self.tone:
            self.tone = tone
            self.Refresh()

    def activate(self):
        if self.action:
            self.action()

    def get_control_rect(self, width, height):
        return self.get_button_rect(width, height, self.button)

    def draw_control(self, gc, width, height):
        rect = self.get_control_rect(width, height)
        draw_button(gc, self.theme, rect, self.caption, self.get_state(),
                    'warn' if self.tone == 'warn' else None)
        return rect.x


class ScrollBar(Canvas):
    '''실제로 움직일 때만 잠깐 뜨는 가는 막대. 판 바깥 여백 위에 얹히므로
    바탕은 페이지 색 그대로 칠하면 된다.'''

    WIDTH = 4
    # 막대 자리(WIDTH + INSET * 2)는 판 페이지의 오른쪽 여백(PANEL_MARGIN) 안에 든다.
    # 바탕을 칠하는 창이라 이보다 넓으면 판 오른쪽 끝을 덮는다.
    INSET = 2
    RADIUS = 2
    HOLD = 700
    # 사라지는 데 걸리는 시간. 프레임 수가 아니라 시각으로 잰다 — 타이머가 밀려도
    # 같은 빠르기로 지고, 16ms 마다 다시 칠해 계단이 안 보인다.
    FADE_MS = 400
    STEP = 16

    def __init__(self, parent, theme):
        super().__init__(parent, theme)
        self.fade = 0.0
        self.span = 0.0
        self.ratio = 1.0
        self.shown_at = 0.0
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_fade)

    def set_span(self, ratio, span):
        '''ratio 는 보이는 만큼의 비율, span 은 굴린 자리의 비율이다.'''
        self.ratio = min(1.0, max(0.0, ratio))
        self.span = min(1.0, max(0.0, span))
        self.Refresh()

    def show(self):
        self.fade = 1.0
        self.shown_at = time.monotonic()
        if not self.timer.IsRunning():
            self.timer.Start(self.STEP)
        self.Refresh()

    def on_fade(self, event):
        elapsed = (time.monotonic() - self.shown_at) * 1000 - self.HOLD
        if elapsed <= 0:
            return
        progress = min(1.0, elapsed / self.FADE_MS)
        # 처음엔 빠르게 옅어지다 끝에서 늦춘다 (ease-out). 직선으로 빼면 끝이 툭 끊긴다.
        self.fade = (1.0 - progress) ** 2
        if progress >= 1.0:
            self.fade = 0.0
            self.timer.Stop()
        self.Refresh()

    def draw(self, gc, width, height):
        if self.fade <= 0 or self.ratio >= 1.0:
            return
        colour = wx.Colour(self.theme['rim'])
        colour = wx.Colour(colour.Red(), colour.Green(), colour.Blue(),
                           int(255 * self.fade))
        thumb = max(24, height * self.ratio)
        top = (height - thumb) * self.span
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(colour))
        gc.DrawRoundedRectangle(self.INSET, top, self.WIDTH, thumb, self.RADIUS)


class ScrollArea(wx.Panel):
    '''세로로 굴리는 자리. wx.ScrolledWindow 를 쓰지 않는다 — 네이티브 막대는
    다크 테마에서 혼자 하얗게 남고 wx 로는 색을 못 준다. 대신 내용판을 통째로
    위아래로 옮기고 막대는 우리가 그린다.

    바퀴 이벤트는 wx 에서 부모로 올라가지 않으므로, 내용판에 담긴 자식마다
    따로 걸어 주어야 카드 위에서도 굴러간다 (`bind_wheel`).'''

    LINE = 42

    def __init__(self, parent, theme):
        super().__init__(parent)
        self.theme = theme
        self.offset = 0
        self.content = wx.Panel(self)
        self.content.SetDoubleBuffered(True)
        self.bar = ScrollBar(self, theme)
        # 내용판이 다시 칠할 때 위에 얹힌 막대를 지우지 않게 한다.
        apply_clip_siblings(self.content)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.bind_wheel(self)

    def set_theme(self, theme):
        self.theme = theme
        self.SetBackgroundColour(wx.Colour(theme['bg']))
        self.content.SetBackgroundColour(wx.Colour(theme['bg']))
        self.bar.set_theme(theme)

    def bind_wheel(self, window):
        window.Bind(wx.EVT_MOUSEWHEEL, self.on_wheel)

    def bind_children(self):
        '''내용판을 다 채운 뒤 한 번 부른다.'''
        def walk(window):
            for child in window.GetChildren():
                if child is not self.bar:
                    self.bind_wheel(child)
                    walk(child)
        walk(self.content)

    # 넓은 창에서 묶음을 여러 단으로 펴는 기준 폭 (사용량 페이지와 같다).
    TWO_COLUMNS = 820
    THREE_COLUMNS = 1240

    groups = None
    columns = 0
    # 단과 단 사이. 판을 쌓는 페이지(set_panels)만 둔다. 옛 카드 페이지는 카드가 제 여백을 가진다.
    column_gap = 0
    # ★페이지가 'wide' 라는 이름을 따로 쓸 수 있다 (설정의 Wide layout 카드). 겹치지 않게.
    wide_columns = True

    def set_groups(self, top, groups, side=0, bottom=0):
        '''묶음(세로 사이저)들을 넘긴다. 폭에 따라 단에 나눠 담는다. side 는 창 가장자리와
        단 사이 여백, bottom 은 마지막 묶음 아래에 더 둘 자리다.'''
        self.groups = list(groups)
        self.root = wx.BoxSizer(wx.VERTICAL)
        self.root.AddSpacer(top)
        self.row = wx.BoxSizer(wx.HORIZONTAL)
        self.root.Add(self.row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, side)
        if bottom:
            self.root.AddSpacer(bottom)
        self.content.SetSizer(self.root)
        self.columns = 0
        self.arrange()

    def set_panels(self, panels):
        '''PyWinAudio 랙처럼 판을 쌓는다. 창 가장자리와 단 사이는 PANEL_MARGIN, 판과 판
        사이와 단과 단 사이는 PANEL_GAP. 판 사이 틈은 판이 제 아래에 둔다.'''
        self.column_gap = PANEL_GAP
        self.set_groups(PANEL_MARGIN, [panel.sizer for panel in panels], PANEL_MARGIN,
                        PANEL_MARGIN - PANEL_GAP)

    def relayout_panels(self):
        '''판을 접고 펴면 묶음 키가 바뀐다. 단 나누기부터 다시 한다.'''
        self.content.Layout()
        self.arrange(force=True)

    def set_wide(self, wide):
        if wide != self.wide_columns:
            self.wide_columns = wide
            self.arrange()

    def get_column_count(self):
        width = self.GetClientSize()[0]
        if not self.wide_columns or width < self.TWO_COLUMNS:
            return 1
        return 3 if width >= self.THREE_COLUMNS else 2

    @staticmethod
    def split_columns(heights, count):
        '''차례를 지킨 채 count 개의 단으로 끊는다. 가장 높은 단이 가장 낮아지는 자리를
        다 따져 고른다 (묶음이 열 개 안쪽이라 순식간이다). 단마다 첫 묶음의 자리를 준다.'''
        prefix = [0]
        for height in heights:
            prefix.append(prefix[-1] + height)
        n = len(heights)
        best = {1: prefix[:]}
        cut = {1: [0] * (n + 1)}
        for c in range(2, count + 1):
            best[c], cut[c] = [], []
            for i in range(n + 1):
                # 같으면 뒤쪽에서 끊는다. 묶음이 단보다 적을 때 빈 단이 앞이 아니라 끝에 남게.
                choice = min(range(i, -1, -1), key=lambda j: max(best[c - 1][j], prefix[i] - prefix[j]))
                best[c].append(max(best[c - 1][choice], prefix[i] - prefix[choice]))
                cut[c].append(choice)
        starts, end = [], n
        for c in range(count, 0, -1):
            starts.insert(0, cut[c][end])
            end = cut[c][end]
        return starts

    def arrange(self, force=False):
        '''문서의 단처럼. 첫 단을 위에서 아래로 채우고 다음 단으로 넘어간다. 차례는
        그대로, 끊는 자리는 단 높이가 가장 고르게 되는 곳.'''
        if not self.groups:
            return
        count = self.get_column_count()
        if count == self.columns and not force:
            return
        self.columns = count
        # 옮기고 다시 재는 동안의 중간 모습이 칠해지면 번쩍인다. 다 끝난 뒤 한 번만 칠한다.
        self.Freeze()
        try:
            self.arrange_columns(count)
        finally:
            self.Thaw()
        self.Refresh()

    def arrange_columns(self, count):
        # 키는 단 폭에서 재야 맞다. 보이스 격자처럼 폭 따라 줄이 바뀌는 묶음은 담기 전과
        # 담은 뒤의 키가 다르다. 한 번 담아 펼친 뒤 다시 재서, 끊는 자리가 바뀌면 다시 담는다.
        starts = None
        for _ in range(3):
            heights = [group.CalcMin()[1] for group in self.groups]
            fresh = self.split_columns(heights, count)
            if fresh == starts:
                break
            starts = fresh
            self.fill_columns(starts, count)
            self.content.SetSize(self.GetClientSize()[0], self.content.GetSize()[1])
            self.content.Layout()
        self.fit()

    def fill_columns(self, starts, count):
        # 단을 지우기 전에 묶음부터 떼어 낸다. Clear 는 담긴 사이저까지 지운다.
        for item in list(self.row.GetChildren()):
            column = item.GetSizer()
            if column:
                for group in self.groups:
                    column.Detach(group)
        self.row.Clear(delete_windows=False)
        columns = []
        for index in range(count):
            if index and self.column_gap:
                self.row.AddSpacer(self.column_gap)
            column = wx.BoxSizer(wx.VERTICAL)
            self.row.Add(column, 1, wx.EXPAND)
            columns.append(column)
        for index, group in enumerate(self.groups):
            column = max(c for c, start in enumerate(starts) if index >= start)
            columns[column].Add(group, 0, wx.EXPAND)

    def get_extent(self):
        sizer = self.content.GetSizer()
        return sizer.GetMinSize()[1] if sizer else 0

    def get_limit(self):
        return max(0, self.get_extent() - self.GetClientSize()[1])

    def scroll_to(self, offset):
        offset = min(self.get_limit(), max(0, offset))
        if offset == self.offset:
            return False
        self.offset = offset
        self.content.SetPosition(wx.Point(0, -offset))
        return True

    def on_wheel(self, event):
        limit = self.get_limit()
        if limit <= 0:
            return
        lines = event.GetWheelRotation() / float(event.GetWheelDelta())
        self.scroll_to(self.offset - int(round(lines)) * self.LINE)
        self.update_bar()
        self.bar.show()

    def update_bar(self):
        extent, height = self.get_extent(), self.GetClientSize()[1]
        limit = self.get_limit()
        self.bar.set_span(height / float(extent) if extent else 1.0,
                          self.offset / float(limit) if limit else 0.0)

    def fit(self):
        '''내용의 높이가 달라졌을 때 다시 잡는다.'''
        width, height = self.GetClientSize()
        self.content.SetSize(0, -self.offset, width, max(height, self.get_extent()))
        # 창이 커져 아래가 비면 끌어올린다.
        self.scroll_to(self.offset)
        self.update_bar()

    def on_size(self, event):
        width, height = self.GetClientSize()
        bar_width = ScrollBar.WIDTH + ScrollBar.INSET * 2
        self.arrange()
        self.fit()
        self.bar.SetSize(width - bar_width, 0, bar_width, height)
        self.bar.Raise()
        event.Skip()
