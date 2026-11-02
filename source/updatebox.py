# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import wx

from controls import Pressable
from controls import draw_button
from controls import get_button_width
from utilities import APP_NAME
from utilities import APP_VERSION
from utilities import BUTTON_GAP
from utilities import BUTTON_HEIGHT
from utilities import PANEL_MARGIN
from utilities import PANEL_PAD
from utilities import PANEL_RADIUS
from utilities import fill_rect
from utilities import get_font
from utilities import get_text_top
from utilities import get_text_width


# the page below starts with its own margin
TOP_GAP = PANEL_MARGIN
PADDING = PANEL_PAD
TITLE_ROW = 20
NOTE_ROW = 16
LINE_ROW = 18
NOTES_GAP = 8
NOTES_LINES = 6
BUTTONS_GAP = 12
PROGRESS_HEIGHT = 2
SCROLL_WIDTH = 2

CAPTIONS = {'skip': 'Skip this version', 'later': 'Later', 'cancel': 'Cancel'}
UPDATE_CAPTIONS = {'installer': 'Update now', 'git': 'Update now', 'page': 'Release page'}


def wrap_text(font, text, width):
    # a word wider than the line keeps a line of its own and is cut when drawn
    lines = []
    for paragraph in text.split('\n'):
        line = ''
        for word in paragraph.split(' '):
            trial = f'{line} {word}' if line else word
            if not line or get_text_width(font, trial) <= width:
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


class UpdateBox(Pressable):
    '''a newer release under the title bar, its notes and the choices about it'''

    marked = -1
    down_index = -1

    def __init__(self, parent, theme, on_action):
        super().__init__(parent, theme, self.choose)
        self.on_action = on_action
        self.release = None
        # 'found', then 'busy' while updating and 'failed' with a message after an error
        self.state = 'found'
        self.message = ''
        self.progress = None
        self.lines = []
        self.top_line = 0
        self.wrapped_width = 0
        self.Bind(wx.EVT_MOUSEWHEEL, self.on_wheel)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Hide()

    def show_release(self, release):
        self.release = release
        self.state = 'found'
        self.message = ''
        self.progress = None
        self.top_line = 0
        self.wrapped_width = 0
        self.relayout()

    def set_busy(self, message, progress=None):
        self.state = 'busy'
        self.message = message
        self.progress = progress
        self.relayout()

    def set_failed(self, message):
        self.state = 'failed'
        self.message = message
        self.progress = None
        self.relayout()

    def get_buttons(self):
        if self.state == 'busy':
            # a pull cannot stop halfway
            return [('cancel', CAPTIONS['cancel'])] if self.progress is not None else []
        update = 'Retry' if self.state == 'failed' else UPDATE_CAPTIONS[self.release['kind']]
        return [('skip', CAPTIONS['skip']), ('later', CAPTIONS['later']), ('update', update)]

    def get_card(self, width, height):
        return wx.Rect(PANEL_MARGIN, TOP_GAP, max(0, width - PANEL_MARGIN * 2), height - TOP_GAP)

    def get_text_width(self, width):
        return self.get_card(width, 0).width - PADDING * 2 - SCROLL_WIDTH * 3

    def wrap(self, width):
        text_width = self.get_text_width(width)
        if text_width != self.wrapped_width:
            self.wrapped_width = text_width
            notes = self.release['notes'] if self.release else ''
            self.lines = wrap_text(get_font(9), notes, text_width) if notes else []
            self.top_line = min(self.top_line, self.get_scroll_limit())

    def get_visible_lines(self):
        return min(len(self.lines), NOTES_LINES)

    def get_scroll_limit(self):
        return max(0, len(self.lines) - NOTES_LINES)

    def get_height(self, width):
        self.wrap(width)
        height = TOP_GAP + PADDING + TITLE_ROW + NOTE_ROW
        if self.lines:
            height += NOTES_GAP + LINE_ROW * self.get_visible_lines()
        if self.get_buttons() or self.progress is not None:
            height += BUTTONS_GAP + BUTTON_HEIGHT
        return height + PADDING

    def relayout(self):
        width = self.GetParent().GetClientSize()[0]
        height = self.get_height(width)
        if height != self.GetMinSize()[1]:
            self.SetMinSize(wx.Size(-1, height))
            self.GetParent().Layout()
        self.Refresh()

    def on_size(self, event):
        width = self.GetClientSize()[0]
        if self.release and self.get_text_width(width) != self.wrapped_width:
            # the parent lays out again after this size settles
            wx.CallAfter(self.relayout)
        event.Skip()

    def get_button_rects(self, width, height):
        card = self.get_card(width, height)
        right = card.x + card.width - PADDING
        top = card.y + card.height - PADDING - BUTTON_HEIGHT
        rects = []
        for key, caption in reversed(self.get_buttons()):
            button = get_button_width(caption)
            right -= button
            rects.insert(0, (key, caption, wx.Rect(right, top, button, BUTTON_HEIGHT)))
            right -= BUTTON_GAP
        return rects

    def get_index(self, position):
        width, height = self.GetClientSize()
        for index, (key, caption, rect) in enumerate(self.get_button_rects(width, height)):
            if rect.Contains(position):
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

    def choose(self):
        index = self.get_index(self.up_position)
        buttons = self.get_buttons()
        if 0 <= index < len(buttons) and index == self.down_index:
            self.on_action(buttons[index][0])

    def on_wheel(self, event):
        limit = self.get_scroll_limit()
        if not limit:
            return
        lines = int(round(event.GetWheelRotation() / float(event.GetWheelDelta())))
        top_line = min(limit, max(0, self.top_line - lines))
        if top_line != self.top_line:
            self.top_line = top_line
            self.Refresh()

    def draw(self, gc, width, height):
        if not self.release:
            return
        theme = self.theme
        card = self.get_card(width, height)
        # a face with the accent mark, as the indexing banner on the usage page
        fill_rect(gc, theme['face'], card.x, card.y, card.width, card.height, PANEL_RADIUS)
        fill_rect(gc, theme['accent'], card.x, card.y + 6, 2, card.height - 12, 1)
        left = card.x + PADDING
        limit = card.width - PADDING * 2
        top = card.y + PADDING

        title = get_font(10, True)
        gc.SetFont(title, wx.Colour(theme['text']))
        gc.DrawText(self.fit_text(gc, f'{APP_NAME} {self.release["version"]} is available', limit),
                    left, get_text_top(title, top, TITLE_ROW))
        top += TITLE_ROW

        note = get_font(8)
        colour = theme['warn'] if self.state == 'failed' else theme['dim']
        message = self.message or f'You have {APP_VERSION}'
        gc.SetFont(note, wx.Colour(colour))
        gc.DrawText(self.fit_text(gc, message, limit), left, get_text_top(note, top, NOTE_ROW))
        top += NOTE_ROW

        if self.lines:
            top += NOTES_GAP
            self.draw_notes(gc, left, top, limit)
            top += LINE_ROW * self.get_visible_lines()

        rects = self.get_button_rects(width, height)
        if self.progress is not None:
            self.draw_progress(gc, left, card.y + card.height - PADDING - BUTTON_HEIGHT,
                               (rects[0][2].x - BUTTONS_GAP if rects else left + limit) - left)
        for index, (key, caption, rect) in enumerate(rects):
            if self.pressed and index == self.down_index and index == self.marked:
                state = 'down'
            elif key == 'update':
                state = 'lit'
            elif index == self.marked:
                state = 'hover'
            else:
                state = 'plain'
            draw_button(gc, theme, rect, caption, state)

    def draw_notes(self, gc, left, top, limit):
        theme = self.theme
        font = get_font(9)
        gc.SetFont(font, wx.Colour(theme['text']))
        text_limit = limit - SCROLL_WIDTH * 3
        shown = self.lines[self.top_line:self.top_line + NOTES_LINES]
        for index, line in enumerate(shown):
            gc.DrawText(self.fit_text(gc, line, text_limit), left,
                        get_text_top(font, top + LINE_ROW * index, LINE_ROW))
        scroll = self.get_scroll_limit()
        if scroll:
            track = LINE_ROW * len(shown)
            thumb = max(12, round(track * NOTES_LINES / len(self.lines)))
            fill_rect(gc, theme['rim'], left + limit - SCROLL_WIDTH,
                      top + round((track - thumb) * self.top_line / scroll), SCROLL_WIDTH, thumb, 1)

    def draw_progress(self, gc, left, top, width):
        theme = self.theme
        y = top + (BUTTON_HEIGHT - PROGRESS_HEIGHT) // 2
        # the indexing banner's track
        fill_rect(gc, theme['grid'], left, y, width, PROGRESS_HEIGHT, 1)
        done = round(width * min(1.0, max(0.0, self.progress)))
        if done:
            fill_rect(gc, theme['accent'], left, y, done, PROGRESS_HEIGHT, 1)
