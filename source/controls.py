# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
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
from utilities import shade


class Pressable(Canvas):

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

    # wx turns a quick second press into a double click
    def on_dclick(self, event):
        self.on_down(event)

    def on_up(self, event):
        if self.HasCapture():
            self.ReleaseMouse()
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
        if self.holding:
            if self.pressed:
                self.pressed = False
                self.Refresh()
            self.set_hovered(False)
            return
        self.set_hovered(False)


class RoundButton(Pressable):

    TONES = {
        'plain': ('control', 'text'),
        'primary': ('accent', '#ffffff'),
        'ghost': (None, 'dim'),
    }

    CORNER = 9

    def __init__(self, parent, theme, icon, on_click, tone='plain', size=ROUND_SIZE,
                 square=False, backdrop=None):
        super().__init__(parent, theme, on_click)
        self.icon = icon
        self.tone = tone
        self.square = square
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

        self.draw_icon(gc, cx, cy, radius, wx.Colour(theme.get(mark, mark)))

    def get_fill(self, key):
        if key is None:
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
            cy -= 1
            arm = radius * 0.44
            gc.SetPen(wx.Pen(colour, max(1, round(radius * 0.13))))
            gc.StrokeLine(cx - arm, cy, cx + arm, cy)
            if self.icon == 'plus':
                gc.StrokeLine(cx, cy - arm, cx, cy + arm)
            gc.SetPen(wx.TRANSPARENT_PEN)

        elif self.icon == 'pencil':
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
    return gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(colour)).Width(width))


def get_button_width(text):
    return get_text_width(get_font(BUTTON_FONT), text) + BUTTON_PAD * 2


def draw_button(gc, theme, rect, text, state='plain', tone=None):
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
    fill = theme['face']
    if last:
        fill_rect(gc, fill, 0, 0, width, height, PANEL_RADIUS)
        fill_rect(gc, fill, 0, 0, width, PANEL_RADIUS)
    else:
        fill_rect(gc, fill, 0, 0, width, height)
    if not first:
        fill_rect(gc, theme['rim'], PANEL_PAD, 0, max(0, width - PANEL_PAD * 2), 1)


class PanelHeader(Pressable):

    TITLE_SIZE = 9
    CHEVRON = 10
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
                baseline = title_top + get_ink(font)[1]
                gc.DrawText(self.fit_text(gc, self.subtitle, room), sub_left,
                            baseline - get_ink(sub_font)[1])


class Panel:

    def __init__(self, parent, theme, key, title, body, folds, on_fold, subtitle='', rows=None,
                 header=None):
        self.key = key
        self.folds = folds
        self.on_fold = on_fold
        if header is None:
            header = PanelHeader(parent, theme, title, subtitle, self.toggle)
        else:
            header.on_toggle = self.toggle
        self.header = header
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
        # wx.SizerItemList cannot be sliced
        for item in list(self.sizer.GetChildren())[1:-1]:
            item.Show(not folded)


class CardBase(Pressable):

    PADDING = PANEL_PAD
    LABEL_GAP = 12
    LINE_GAP = 6
    first = True
    last = True

    def __init__(self, parent, theme, label, description, on_change=None):
        super().__init__(parent, theme, self.activate)
        self.label = label
        self.description = description
        self.on_change = on_change
        self.SetMinSize(wx.Size(-1, CARD_HEIGHT))

    def activate(self):
        pass

    def notify(self):
        self.Refresh()
        if self.on_change:
            self.on_change()

    def get_control_rect(self, width, height):
        return wx.Rect()

    def get_button_rect(self, width, height, button_width):
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
        return width - self.PADDING


class SettingCard(CardBase):

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

    GRIP = 14
    DRAG_SLOP = 4

    def __init__(self, parent, theme, label, description, on_change=None, on_drag=None):
        super().__init__(parent, theme, label, description, on_change)
        self.on_drag = on_drag
        self.press_y = None
        self.dragging = False
        self.Bind(wx.EVT_MOTION, self.on_motion)
        self.update_cursor()

    def update_cursor(self):
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
            draw_frame(gc, self.theme['accent'], 0, 0, width, height)

    def draw_control(self, gc, width, height):
        theme = self.theme
        left = super().draw_control(gc, width, height)
        grip_left = left - BUTTON_GAP * 3 - self.GRIP
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(wx.Colour(theme['dim'])))
        cy = height // 2
        for column in (0, 6):
            for row in (-5, 0, 5):
                gc.DrawEllipse(grip_left + 4 + column - 1.25, cy + row - 1.25, 2.5, 2.5)
        return grip_left


class ChoiceCard(CardBase):

    marked = -1
    down_index = -1

    def __init__(self, parent, theme, label, description, options, on_change=None):
        super().__init__(parent, theme, label, description, on_change)
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

    TRACK_WIDTH = 116
    TRACK_HEIGHT = 2
    THUMB = (8, 14)
    VALUE_SIZE = 9
    # the thumb overhangs the track ends by half its width
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

    PADDING = PANEL_PAD

    marked = -1
    down_index = -1
    first = True
    last = True

    def __init__(self, parent, theme, options, on_change=None, on_layout=None):
        super().__init__(parent, theme, self.choose)
        self.on_change = on_change
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

    tone = 'plain'

    def __init__(self, parent, theme, label, description, caption, on_click=None):
        super().__init__(parent, theme, label, description)
        self.action = on_click
        self.caption = None
        self.captions = [caption]
        self.set_caption(caption)

    def set_caption(self, caption):
        if caption not in self.captions:
            self.captions.append(caption)
        self.button = max(get_button_width(text) for text in self.captions)
        if caption != self.caption:
            self.caption = caption
            self.Refresh()

    def set_captions(self, *captions):
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

    WIDTH = 4
    INSET = 2
    RADIUS = 2
    HOLD = 700
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

    LINE = 42

    def __init__(self, parent, theme):
        super().__init__(parent)
        self.theme = theme
        self.offset = 0
        # not wx.ScrolledWindow: its native bar stays white in the dark theme
        self.content = wx.Panel(self)
        self.content.SetDoubleBuffered(True)
        self.bar = ScrollBar(self, theme)
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

    # wheel events do not bubble up to the parent in wx
    def bind_children(self):
        def walk(window):
            for child in window.GetChildren():
                if child is not self.bar:
                    self.bind_wheel(child)
                    walk(child)
        walk(self.content)

    TWO_COLUMNS = 820
    THREE_COLUMNS = 1240

    groups = None
    columns = 0
    column_gap = 0
    wide_columns = True

    def set_groups(self, top, groups, side=0, bottom=0):
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
        self.column_gap = PANEL_GAP
        self.set_groups(PANEL_MARGIN, [panel.sizer for panel in panels], PANEL_MARGIN,
                        PANEL_MARGIN - PANEL_GAP)

    def relayout_panels(self):
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
        prefix = [0]
        for height in heights:
            prefix.append(prefix[-1] + height)
        n = len(heights)
        best = {1: prefix[:]}
        cut = {1: [0] * (n + 1)}
        for c in range(2, count + 1):
            best[c], cut[c] = [], []
            for i in range(n + 1):
                choice = min(range(i, -1, -1), key=lambda j: max(best[c - 1][j], prefix[i] - prefix[j]))
                best[c].append(max(best[c - 1][choice], prefix[i] - prefix[choice]))
                cut[c].append(choice)
        starts, end = [], n
        for c in range(count, 0, -1):
            starts.insert(0, cut[c][end])
            end = cut[c][end]
        return starts

    def arrange(self, force=False):
        if not self.groups:
            return
        count = self.get_column_count()
        if count == self.columns and not force:
            return
        self.columns = count
        self.Freeze()
        try:
            self.arrange_columns(count)
        finally:
            self.Thaw()
        self.Refresh()

    def arrange_columns(self, count):
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
        width, height = self.GetClientSize()
        self.content.SetSize(0, -self.offset, width, max(height, self.get_extent()))
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
