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

from utilities import CARD_HEIGHT
from utilities import CARD_RADIUS
from utilities import ROUND_SIZE
from utilities import Canvas
from utilities import apply_clip_siblings
from utilities import draw_card_rim
from utilities import get_font
from utilities import mix
from utilities import shade


class Pressable(Canvas):
    '''캔버스 버튼들이 공유하는 hover / press 상태.'''

    def __init__(self, parent, theme, on_click):
        super().__init__(parent, theme)
        self.on_click = on_click
        self.hovered = False
        self.pressed = False
        self.Bind(wx.EVT_LEFT_DOWN, self.on_down)
        self.Bind(wx.EVT_LEFT_UP, self.on_up)
        self.Bind(wx.EVT_ENTER_WINDOW, self.on_enter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self.on_leave)

    def on_down(self, event):
        self.pressed = True
        self.Refresh()

    def on_up(self, event):
        was_pressed = self.pressed
        self.pressed = False
        self.Refresh()
        if was_pressed and self.hovered and self.on_click:
            self.on_click()

    def on_enter(self, event):
        self.hovered = True
        self.Refresh()

    def on_leave(self, event):
        self.hovered = False
        self.pressed = False
        self.Refresh()


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


class CardBase(Pressable):
    '''Windows 11 설정과 같은 카드 한 줄. 바탕과 제목·설명은 여기서 그리고,
    오른쪽 끝의 조작부만 자식이 채운다. 조작부가 자리를 먼저 잡고 남는 왼쪽을
    글자가 쓰므로, 제목은 조작부가 넓어지는 만큼 말없이 잘린다.'''

    PADDING = 14
    # 제목이 조작부에 닿지 않게 두는 자리.
    LABEL_GAP = 12

    def __init__(self, parent, theme, label, description, on_change=None):
        super().__init__(parent, theme, self.activate)
        self.label = label
        self.description = description
        self.on_change = on_change
        self.SetMinSize(wx.Size(-1, CARD_HEIGHT))

    def activate(self):
        '''카드를 눌렀을 때 값을 바꾸는 자리.'''

    def notify(self):
        self.Refresh()
        if self.on_change:
            self.on_change()

    def draw(self, gc, width, height):
        theme = self.theme
        fill = theme['face']
        if self.pressed:
            fill = shade(fill, 0.94)
        elif self.hovered:
            fill = shade(fill, 1.12)

        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(wx.Colour(fill)))
        gc.DrawRoundedRectangle(0, 0, width, height, CARD_RADIUS)
        draw_card_rim(gc, theme['rim'], 0, 0, width, height)

        label_right = self.draw_control(gc, width, height) - self.LABEL_GAP
        gc.SetFont(get_font(10), wx.Colour(theme['text']))
        title_height = gc.GetTextExtent(self.label)[1]
        top = (height - title_height - 15) / 2
        gc.Clip(self.PADDING, 0, max(0, label_right - self.PADDING), height)
        gc.DrawText(self.label, self.PADDING, top)
        gc.SetFont(get_font(8), wx.Colour(theme['dim']))
        gc.DrawText(self.description, self.PADDING, top + title_height + 1)
        gc.ResetClip()

    def draw_control(self, gc, width, height):
        '''오른쪽 끝에서부터 조작부를 그리고 그 왼쪽 끝 x 를 돌려준다.'''
        return width - self.PADDING


class SettingCard(CardBase):
    '''오른쪽 끝에 On/Off 토글을 둔 카드. 카드 어디를 눌러도 토글된다.'''

    TRACK_WIDTH = 38
    TRACK_HEIGHT = 20

    value = False

    def GetValue(self):
        return self.value

    def SetValue(self, value):
        self.value = bool(value)
        self.Refresh()

    def activate(self):
        self.value = not self.value
        self.notify()

    def draw_control(self, gc, width, height):
        theme = self.theme
        switch_left = width - self.PADDING - self.TRACK_WIDTH
        state = 'On' if self.value else 'Off'
        gc.SetFont(get_font(9), wx.Colour(theme['dim']))
        state_width, state_height = gc.GetTextExtent(state)[:2]
        gc.DrawText(state, switch_left - state_width - 8, (height - state_height) / 2)
        # 세로 자리는 반 칸 없이 딱 떨어져야 알약 위아래가 흐려지지 않는다.
        self.draw_switch(gc, switch_left, round((height - self.TRACK_HEIGHT) / 2))
        return switch_left - state_width - 8

    def draw_switch(self, gc, left, top):
        theme = self.theme
        radius = self.TRACK_HEIGHT / 2
        gc.SetPen(wx.TRANSPARENT_PEN)

        # 선을 두르면 1px 획이 화소 경계에 반씩 걸려 아래쪽 곡선이 각져 보이고
        # 핸들과도 반 칸 어긋난다. 채운 알약 위에 한 칸 작은 알약을 겹쳐 테를 만든다.
        if self.value:
            gc.SetBrush(wx.Brush(wx.Colour(theme['accent'])))
            gc.FillPath(self.get_track(gc, left, top, 0))
        else:
            gc.SetBrush(wx.Brush(wx.Colour(theme['dim'])))
            gc.FillPath(self.get_track(gc, left, top, 0))
            gc.SetBrush(wx.Brush(wx.Colour(theme['bg'])))
            gc.FillPath(self.get_track(gc, left, top, 1))

        knob = radius - 4
        x = left + (self.TRACK_WIDTH - radius if self.value else radius)
        gc.SetBrush(wx.Brush(wx.Colour('#ffffff' if self.value else theme['text'])))
        gc.DrawEllipse(x - knob, top + radius - knob, knob * 2, knob * 2)

    def get_track(self, gc, left, top, inset):
        '''반원 둘을 직선으로 이은 알약. 둥근 사각형은 반지름이 높이의 절반일 때
        호와 직선이 만나는 자리가 각져 보인다.

        밑동 좌우가 위보다 살짝 각져 보이는 것은 이 경로 탓이 아니다. 원 둘 +
        네모로 다시 그려 봐도 화소가 한 점 다르지 않았다 — GDI+ 가 맨 윗줄과
        맨 아랫줄의 안티에일리어싱을 다르게 얹는다(실측: 꽉 찬 구간이 위 18px,
        아래 22px, 윤곽선 자체는 대칭). 모양을 바꿔서는 못 없앤다.'''
        left, top = left + inset, top + inset
        width, height = self.TRACK_WIDTH - inset * 2, self.TRACK_HEIGHT - inset * 2
        radius = height / 2

        path = gc.CreatePath()
        path.MoveToPoint(left + radius, top)
        path.AddLineToPoint(left + width - radius, top)
        path.AddArc(left + width - radius, top + radius, radius,
                    -math.pi / 2, math.pi / 2, True)
        path.AddLineToPoint(left + radius, top + height)
        path.AddArc(left + radius, top + radius, radius, math.pi / 2, -math.pi / 2, True)
        path.CloseSubpath()
        return path


class LayoutCard(SettingCard):
    '''끌어서 차례를 바꾸는 토글 카드 (사용량 페이지의 묶음 차례·숨김). 누르기만
    하면 토글되고, 눌린 채로 몇 픽셀 움직이면 끌기가 된다. 끄는 동안의 자리
    계산과 애니메이션은 부모가 한다 (`on_drag(card, phase, screen_y)`, phase 는
    'start'·'move'·'drop').'''

    GRIP = 14
    # 이만큼 움직여야 끌기로 본다. 손이 떨려 누른 것이 끌기가 되면 토글이 안 먹는다.
    DRAG_SLOP = 4

    def __init__(self, parent, theme, label, description, on_change=None, on_drag=None):
        super().__init__(parent, theme, label, description, on_change)
        self.on_drag = on_drag
        self.press_y = None
        self.dragging = False
        self.Bind(wx.EVT_MOTION, self.on_motion)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self.on_capture_lost)
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))

    def on_down(self, event):
        self.press_y = wx.GetMousePosition().y
        if not self.HasCapture():
            self.CaptureMouse()
        super().on_down(event)

    def on_motion(self, event):
        if self.press_y is None or not event.LeftIsDown():
            event.Skip()
            return
        y = wx.GetMousePosition().y
        if not self.dragging and abs(y - self.press_y) >= self.DRAG_SLOP:
            self.dragging = True
            self.pressed = False
            self.SetCursor(wx.Cursor(wx.CURSOR_SIZENS))
            if self.on_drag:
                self.on_drag(self, 'start', self.press_y)
        if self.dragging and self.on_drag:
            self.on_drag(self, 'move', y)

    def on_up(self, event):
        if self.HasCapture():
            self.ReleaseMouse()
        self.press_y = None
        if self.dragging:
            self.finish_drag()
            return
        super().on_up(event)

    def on_capture_lost(self, event):
        self.press_y = None
        if self.dragging:
            self.finish_drag()

    def finish_drag(self):
        self.dragging = False
        self.pressed = False
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        self.Refresh()
        if self.on_drag:
            self.on_drag(self, 'drop', wx.GetMousePosition().y)

    def on_leave(self, event):
        # 끄는 동안에는 카드가 마우스 밑에서 빠져나가도 눌린 상태를 지우지 않는다.
        if self.dragging:
            return
        super().on_leave(event)

    def draw(self, gc, width, height):
        super().draw(gc, width, height)
        if self.dragging:
            # 들려 있는 카드는 테두리를 강조색으로 둘러 다른 카드와 갈라 보이게 한다.
            draw_card_rim(gc, self.theme['accent'], 0, 0, width, height)

    def draw_control(self, gc, width, height):
        theme = self.theme
        left = super().draw_control(gc, width, height)
        # 손잡이: 점 두 줄 세 칸. 끌 수 있다는 표시일 뿐 누를 자리가 따로 있지는 않다.
        grip_left = left - 12 - self.GRIP
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(wx.Colour(theme['dim'])))
        cy = height / 2
        for column in (0, 6):
            for row in (-5, 0, 5):
                gc.DrawEllipse(grip_left + 4 + column - 1.25, cy + row - 1.25, 2.5, 2.5)
        return grip_left


class ChoiceCard(CardBase):
    '''고를 것이 몇 되지 않으면 목록을 펼칠 것 없이 칸을 나란히 붙인다. 토글과
    달리 카드 바탕을 눌러서는 값이 바뀌지 않는다 — 어느 칸을 고르는지 눌러서
    알릴 길이 없기 때문이다.'''

    SEGMENT_HEIGHT = 26
    SEGMENT_PADDING = 14
    SEGMENT_RADIUS = 5
    # 칸끼리 붙여 두면 어디까지가 한 칸인지 눈에 안 들어온다. 사이를 띄운다.
    SEGMENT_GAP = 6

    # 마우스가 얹힌 칸. 카드 밖으로 나가면 지운다.
    marked = -1

    def __init__(self, parent, theme, label, description, options, on_change=None):
        super().__init__(parent, theme, label, description, on_change)
        # (저장할 값, 보일 이름) 의 나열.
        self.options = options
        self.value = options[0][0]
        # 칸 폭은 글꼴이 정하니 한 번만 재 둔다. 누른 자리를 따지는 데도 쓴다.
        dc = wx.MemoryDC(wx.Bitmap(1, 1))
        dc.SetFont(get_font(9))
        self.segment = (max(dc.GetTextExtent(name)[0] for _, name in options) +
                        self.SEGMENT_PADDING * 2)
        self.Bind(wx.EVT_MOTION, self.on_motion)

    def GetValue(self):
        return self.value

    def SetValue(self, value):
        if value in [option[0] for option in self.options]:
            self.value = value
            self.Refresh()

    def get_stride(self):
        return self.segment + self.SEGMENT_GAP

    def get_left(self, width):
        return (width - self.PADDING - self.get_stride() * len(self.options) +
                self.SEGMENT_GAP)

    def get_index(self, position):
        width, height = self.GetClientSize()
        left = self.get_left(width)
        top = (height - self.SEGMENT_HEIGHT) / 2
        if not top <= position.y < top + self.SEGMENT_HEIGHT:
            return -1
        if not left <= position.x < width - self.PADDING:
            return -1
        # 칸 사이 빈자리는 어느 쪽도 아니다. 넘겨짚어 고르면 눌린 적 없는 값이 선다.
        index, offset = divmod(int(position.x - left), self.get_stride())
        return index if offset < self.segment else -1

    def on_motion(self, event):
        self.mark(self.get_index(event.GetPosition()))
        event.Skip()

    def on_leave(self, event):
        self.mark(-1)
        super().on_leave(event)

    def mark(self, index):
        if index != self.marked:
            self.marked = index
            self.Refresh()

    def activate(self):
        index = self.get_index(self.ScreenToClient(wx.GetMousePosition()))
        if index < 0 or self.options[index][0] == self.value:
            return
        self.value = self.options[index][0]
        self.notify()

    def draw_control(self, gc, width, height):
        theme = self.theme
        left = self.get_left(width)
        top = round((height - self.SEGMENT_HEIGHT) / 2)
        gc.SetPen(wx.TRANSPARENT_PEN)

        for index, (value, name) in enumerate(self.options):
            x = left + self.get_stride() * index
            chosen = value == self.value
            if chosen:
                fill = wx.Colour(theme['accent'])
            elif index == self.marked:
                fill = mix(theme['control'], theme['text'], 0.14)
            else:
                fill = wx.Colour(theme['control'])
            gc.SetBrush(wx.Brush(fill))
            gc.DrawRoundedRectangle(x, top, self.segment, self.SEGMENT_HEIGHT,
                                    self.SEGMENT_RADIUS)
            gc.SetFont(get_font(9), wx.Colour('#ffffff' if chosen else theme['dim']))
            text_width, text_height = gc.GetTextExtent(name)[:2]
            gc.DrawText(name, x + (self.segment - text_width) / 2,
                        top + (self.SEGMENT_HEIGHT - text_height) / 2)
        return left


class SliderCard(CardBase):
    '''오른쪽 끝에 값과 track 을 둔 카드. 눌러서 끌면 값이 따라온다.

    토글과 달리 카드 바탕을 눌러서는 값이 바뀌지 않는다 — 어디를 눌렀는지가
    곧 값이라, 글자 자리를 눌렀다고 값을 옮기면 넘겨짚는 셈이 된다.'''

    TRACK_WIDTH = 116
    TRACK_HEIGHT = 4
    KNOB = 7
    # 값이 흔들려도 track 이 밀리지 않도록 가장 넓은 글자만큼 미리 떼어 둔다.
    # ★손잡이는 끝값에서 track 밖으로 KNOB 만큼 더 나간다. 그만큼을 빼고 남는
    # 자리가 글자와의 사이가 되므로, 이 값이 KNOB 보다 넉넉히 커야 안 닿는다.
    VALUE_GAP = 18

    def __init__(self, parent, theme, label, description, bounds, on_change=None):
        super().__init__(parent, theme, label, description, on_change)
        self.low, self.high, self.step, self.digits = bounds
        self.value = self.low
        self.dragging = False
        # 값 칸의 폭은 가장 긴 표기가 정한다. 끝값 둘만 재면 충분하다.
        dc = wx.MemoryDC(wx.Bitmap(1, 1))
        dc.SetFont(get_font(9))
        self.value_width = max(dc.GetTextExtent(self.format(bound))[0]
                               for bound in (self.low, self.high))
        self.Bind(wx.EVT_MOTION, self.on_motion)
        # 잡은 마우스를 놓친 채로 창이 사라지면 소멸자에서 assertion 이 뜬다.
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self.on_capture_lost)

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

    def set_from_x(self, x, width):
        ratio = min(1.0, max(0.0, (x - self.get_track_left(width)) / self.TRACK_WIDTH))
        # 눈금에 맞춰 떨어뜨린다. 끌면서 나오는 값이 저장될 값과 같아야 한다.
        stepped = self.low + round(ratio * (self.high - self.low) / self.step) * self.step
        value = min(self.high, max(self.low, stepped))
        if value != self.value:
            self.value = value
            self.notify()
        else:
            self.Refresh()

    def on_down(self, event):
        width = self.GetClientSize()[0]
        position = event.GetPosition()
        # track 에서 한참 벗어난 자리는 값을 옮기려던 손이 아니다.
        if position.x < self.get_track_left(width) - self.KNOB:
            return
        self.dragging = True
        self.pressed = True
        self.CaptureMouse()
        self.set_from_x(position.x, width)

    def on_motion(self, event):
        if self.dragging:
            self.set_from_x(event.GetPosition().x, self.GetClientSize()[0])
        event.Skip()

    def on_up(self, event):
        self.release()

    def on_leave(self, event):
        # 끄는 중이라면 캡처가 살아 있어 여기 오지 않는다. 그냥 hover 만 지운다.
        if not self.dragging:
            super().on_leave(event)

    def on_capture_lost(self, event):
        self.dragging = False
        self.pressed = False
        self.Refresh()

    def release(self):
        if not self.dragging:
            return
        self.dragging = False
        self.pressed = False
        if self.HasCapture():
            self.ReleaseMouse()
        self.Refresh()

    def draw_control(self, gc, width, height):
        theme = self.theme
        left = self.get_track_left(width)
        middle = round(height / 2)
        span = (self.value - self.low) / float(self.high - self.low)
        knob_x = left + self.TRACK_WIDTH * span

        gc.SetFont(get_font(9), wx.Colour(theme['text']))
        text = self.format(self.value)
        text_width, text_height = gc.GetTextExtent(text)[:2]
        # 값은 오른쪽 맞춤이다. 자릿수가 바뀌어도 track 이 안 흔들린다.
        gc.DrawText(text, width - self.PADDING - text_width, (height - text_height) / 2)

        gc.SetPen(wx.TRANSPARENT_PEN)
        top = middle - self.TRACK_HEIGHT / 2
        gc.SetBrush(wx.Brush(wx.Colour(theme['control'])))
        gc.DrawRoundedRectangle(left, top, self.TRACK_WIDTH, self.TRACK_HEIGHT,
                                self.TRACK_HEIGHT / 2)
        if span > 0:
            gc.SetBrush(wx.Brush(wx.Colour(theme['accent'])))
            gc.DrawRoundedRectangle(left, top, max(self.TRACK_HEIGHT, knob_x - left),
                                    self.TRACK_HEIGHT, self.TRACK_HEIGHT / 2)

        knob = self.KNOB + (1 if self.hovered or self.dragging else 0)
        gc.SetBrush(wx.Brush(wx.Colour(theme['accent'])))
        gc.DrawEllipse(knob_x - knob, middle - knob, knob * 2, knob * 2)
        gc.SetBrush(wx.Brush(wx.Colour(theme['face'])))
        gc.DrawEllipse(knob_x - knob + 2, middle - knob + 2,
                       (knob - 2) * 2, (knob - 2) * 2)
        return left


class ChipGrid(Canvas):
    '''고를 것이 스무 남짓이라 카드 한 줄에 칸을 늘어세울 수 없다. 줄을 접어
    격자로 늘어놓고 하나만 고른다.

    높이가 폭에서 나오므로 접히는 줄 수가 바뀔 때만 최소 크기를 다시 준다 —
    줄 수는 띄엄띄엄한 값이라 되먹임이 생기지 않는다.'''

    CHIP_HEIGHT = 26
    CHIP_GAP = 6
    RADIUS = 5
    PADDING = 12

    marked = -1

    def __init__(self, parent, theme, options, on_change=None, on_layout=None):
        super().__init__(parent, theme)
        self.on_change = on_change
        # 줄 수가 바뀌면 담고 있는 쪽의 높이도 달라진다. 굴리는 자리에 담겼다면
        # 그쪽이 자기 크기를 다시 잡아야 한다.
        self.on_layout = on_layout
        self.value = ''
        self.chip = 44
        self.set_options(options)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_down)
        self.Bind(wx.EVT_MOTION, self.on_motion)
        self.Bind(wx.EVT_LEAVE_WINDOW, self.on_leave)
        self.Bind(wx.EVT_SIZE, self.on_size)

    def set_options(self, options):
        self.options = list(options)
        dc = wx.MemoryDC(wx.Bitmap(1, 1))
        dc.SetFont(get_font(9))
        widest = max([dc.GetTextExtent(name)[0] for name in self.options] or [0])
        self.chip = widest + self.PADDING * 2
        self.relayout()

    def GetValue(self):
        return self.value

    def SetValue(self, value):
        self.value = value
        self.Refresh()

    def get_columns(self, width):
        usable = width - self.PADDING * 2 + self.CHIP_GAP
        return max(1, int(usable // (self.chip + self.CHIP_GAP)))

    def get_rows(self, width):
        columns = self.get_columns(width)
        return max(1, (len(self.options) + columns - 1) // columns)

    def get_height(self, width):
        rows = self.get_rows(width)
        return (self.PADDING * 2 + rows * self.CHIP_HEIGHT +
                (rows - 1) * self.CHIP_GAP)

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
        return wx.Rect(self.PADDING + column * (self.chip + self.CHIP_GAP),
                       self.PADDING + row * (self.CHIP_HEIGHT + self.CHIP_GAP),
                       self.chip, self.CHIP_HEIGHT)

    def hit_test(self, position):
        width = self.GetClientSize()[0]
        for index in range(len(self.options)):
            if self.get_chip_rect(index, width).Contains(position):
                return index
        return -1

    def on_down(self, event):
        index = self.hit_test(event.GetPosition())
        if index < 0 or self.options[index] == self.value:
            return
        self.value = self.options[index]
        self.Refresh()
        if self.on_change:
            self.on_change()

    def on_motion(self, event):
        index = self.hit_test(event.GetPosition())
        if index != self.marked:
            self.marked = index
            self.Refresh()
        event.Skip()

    def on_leave(self, event):
        if self.marked != -1:
            self.marked = -1
            self.Refresh()

    def draw(self, gc, width, height):
        theme = self.theme
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(wx.Colour(theme['face'])))
        gc.DrawRoundedRectangle(0, 0, width, height, CARD_RADIUS)
        draw_card_rim(gc, theme['rim'], 0, 0, width, height)

        for index, name in enumerate(self.options):
            rect = self.get_chip_rect(index, width)
            chosen = name == self.value
            if chosen:
                fill = wx.Colour(theme['accent'])
            elif index == self.marked:
                fill = mix(theme['control'], theme['text'], 0.14)
            else:
                fill = wx.Colour(theme['control'])
            gc.SetPen(wx.TRANSPARENT_PEN)
            gc.SetBrush(wx.Brush(fill))
            gc.DrawRoundedRectangle(rect.x, rect.y, rect.width, rect.height,
                                    self.RADIUS)
            gc.SetFont(get_font(9), wx.Colour('#ffffff' if chosen else theme['dim']))
            text_width, text_height = gc.GetTextExtent(name)[:2]
            gc.DrawText(name, rect.x + (rect.width - text_width) / 2,
                        rect.y + (rect.height - text_height) / 2)


class ActionCard(CardBase):
    '''오른쪽 끝에 누름 단추 하나를 둔 카드. 값이 아니라 일을 시킨다.'''

    BUTTON_HEIGHT = 26
    BUTTON_PADDING = 16
    RADIUS = 5

    # 'warn' 이면 단추를 주황으로 칠한다. 한 번 더 누르면 되돌릴 수 없는 일이 난다는 표시.
    tone = 'plain'

    def __init__(self, parent, theme, label, description, caption, on_click=None):
        super().__init__(parent, theme, label, description)
        self.action = on_click
        self.caption = None
        self.set_caption(caption)

    def set_caption(self, caption):
        if caption != self.caption:
            self.caption = caption
            dc = wx.MemoryDC(wx.Bitmap(1, 1))
            dc.SetFont(get_font(9))
            self.button = dc.GetTextExtent(caption)[0] + self.BUTTON_PADDING * 2
            self.Refresh()

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

    def draw_control(self, gc, width, height):
        theme = self.theme
        left = width - self.PADDING - self.button
        top = round((height - self.BUTTON_HEIGHT) / 2)

        fill = theme['warn'] if self.tone == 'warn' else theme['accent']
        if self.pressed:
            fill = shade(fill, 0.85)
        elif self.hovered:
            fill = shade(fill, 1.16)

        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(wx.Colour(fill)))
        gc.DrawRoundedRectangle(left, top, self.button, self.BUTTON_HEIGHT, self.RADIUS)
        gc.SetFont(get_font(9), wx.Colour('#ffffff'))
        text_width, text_height = gc.GetTextExtent(self.caption)[:2]
        gc.DrawText(self.caption, left + (self.button - text_width) / 2,
                    top + (self.BUTTON_HEIGHT - text_height) / 2)
        return left


class ScrollBar(Canvas):
    '''실제로 움직일 때만 잠깐 뜨는 가는 막대. 카드 바깥 여백 위에 얹히므로
    바탕은 페이지 색 그대로 칠하면 된다.'''

    WIDTH = 4
    INSET = 3
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
    # ★페이지가 'wide' 라는 이름을 따로 쓸 수 있다 (설정의 Wide layout 카드). 겹치지 않게.
    wide_columns = True

    def set_groups(self, top, groups):
        '''묶음(제목+카드를 담은 세로 사이저)들을 넘긴다. 폭에 따라 단에 나눠 담는다.'''
        self.groups = list(groups)
        self.root = wx.BoxSizer(wx.VERTICAL)
        self.root.AddSpacer(top)
        self.row = wx.BoxSizer(wx.HORIZONTAL)
        self.root.Add(self.row, 0, wx.EXPAND)
        self.content.SetSizer(self.root)
        self.columns = 0
        self.arrange()

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
        for _ in range(count):
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
