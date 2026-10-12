# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

사용량 페이지. TTS·설정 페이지와 같은 랙 판(`controls.Panel`)을 쌓고 본체는 캔버스에 직접
그린다. 웹뷰(usage.htm) 판을 옮겨 왔다 — 다른 PyWin 앱과 같이 런타임이 하나뿐이다.

값은 `usageindex` 가 색인한 기록에서 `dashboard` 가 뽑는다. 모으는 일은 두
번에 나눈다 — 색인과 저장해 둔 git 통계로 먼저 그리고, git 을 다시 센 뒤에
한 번 더 그린다. git 은 저장소마다 몇 초씩 걸린다.

판 본체(`Body`)는 키가 폭에서 나온다. 그리는 함수를 빈 바탕에 한 번 돌려 잰다 —
같은 함수가 재고 그리니 둘이 어긋나지 않는다. 누를 자리와 툴팁 자리는 그리면서 적는다.
'''


import datetime
import math
import os
import threading
import time
import traceback
import wx

import claudelogin
import dashboard
import usageindex

from controls import PanelHeader
from controls import Panel
from controls import ScrollArea
from controls import draw_button
from controls import draw_row_face
from controls import get_button_width
from utilities import BAND_INSET
from utilities import BUTTON_GAP
from utilities import BUTTON_HEIGHT
from utilities import HEADER_BAND
from utilities import PANEL_GAP
from utilities import PANEL_MARGIN
from utilities import PANEL_PAD
from utilities import PANEL_RADIUS
from utilities import Canvas
from utilities import draw_card_rim
from utilities import draw_chevron
from utilities import fill_rect
from utilities import get_asset_path
from utilities import get_font
from utilities import get_ink
from utilities import get_text_top
from utilities import mix
from utilities import shade

# 로그인 창을 띄운 뒤 새 토큰이 생겼는지 이 간격으로, 이만큼 동안 살핀다.
LOGIN_POLL_MS = 5000
LOGIN_POLL_LIMIT = 10 * 60
# 토큰이 만료되기 직전(claudelogin.REFRESH_SKEW)이면 Sign in 단추와 같은 조용한 갱신을 스스로 돌린다.
# 실패하면(refresh token 까지 만료 등) 이만큼 기다렸다 다시 해 본다 — 매 tick 마다 claude 를 띄우지 않게.
AUTO_REFRESH_RETRY = 30 * 60
# 만료 시각은 파일에서 읽는다. 이보다 자주 읽지 않는다.
EXPIRY_CHECK = 30
# 폭주 막이. 정상이면 하루 3 번(8 시간마다)이다. 24 시간 안에 이만큼 넘게는 스스로 돌리지 않는다.
# 시도 시각은 색인 meta 에 남겨 앱을 다시 띄워도 이어 센다. 넘으면 Sign in 단추만 남는다.
AUTO_REFRESH_DAILY_CAP = 6
AUTO_REFRESH_KEY = 'claude_auto_refresh'

# 페이지가 보이는 동안 이 간격으로 다시 읽는다. 색인 덕에 새 줄만 읽는다.
AUTO_REFRESH = 60
# git 은 비싸다. 이보다 자주 다시 세지 않는다 (Reload 를 누르면 바로 센다).
GIT_REFRESH = 10 * 60
# 남은 시간(한도·이용권)과 'last run' 글씨를 이 간격으로 다시 쓴다.
CLOCK_REFRESH = 15

# 묶음 머리의 도구 아이콘. 각 앱 설치 패키지의 Square44x44Logo(64px) 를 옮겨 둔 것.
BRAND_ICONS = ('claude', 'codex-dark', 'codex-light')
BRAND_SIZE = 14

# 글씨 크기(pt)와 그 글씨의 줄 키(px). 웹판의 px 글씨를 0.75 배로 옮겼고, 줄 키는 Segoe UI 의
# 기본 줄 높이(글씨의 약 1.33 배)다.
TINY = 7        # 9px  — 이름표·축·눈금
SMALL = 7.5     # 10px — 그림 머리·도구 이름표·상태 칩
NOTE = 8        # 11px — 흐린 설명
BODY = 9        # 12px — 줄 이름
MAIN = 10       # 13px — 본문
VALUE = 11      # 15px — 큰 숫자
HUGE = 16.5     # 22px — 한도가 풀리기까지
LINE = {TINY: 12, SMALL: 13, NOTE: 15, BODY: 16, MAIN: 17, VALUE: 20, HUGE: 24}

PAD = PANEL_PAD
# 그림은 넓은 창에서 부풀지 않는다 — 칸이 커지면 뚱뚱해 보인다(사용자). 활동 모자이크
# 폭(칸 12px)에서 멈추고 판 가운데에 선다. 좁으면 그만큼 줄어든다.
CHART_MAX = 368
CHART_HEIGHT = 64
SMALL_CHART = 34
SLOT_GAP = 2
# 진행 막대는 모두 이 굵기·둥글기 하나로 (한도·세션 문맥·모델·주별·내역·색인 띠).
BAR_HEIGHT = 6
BAR_RADIUS = 1
CELL_MAX = 12
CELL_GAP = 2
LEVELS = 4
SESSION_LIMIT = 5
GRAIN_COUNT = {'day': 30, 'week': 12, 'month': 12}
RESET_SOON = 24 * 3600

VIEW_DEFAULTS = {
    'headerPeriod': 'today', 'codePeriod': 'today', 'metric': 'cost', 'grain': 'day',
    'sessionFilter': 'all', 'activity': 'week',
}
CHOICES = {
    'headerPeriod': (('today', 'Today'), ('all', 'All')),
    'codePeriod': (('today', 'Today'), ('all', 'All')),
    'metric': (('cost', 'Cost'), ('tokens', 'Tokens')),
    'grain': (('day', 'Day'), ('week', 'Week'), ('month', 'Month')),
    'sessionFilter': (('all', 'All'), ('active', 'Active')),
    'activity': (('week', '7d'), ('calendar', '5mo'), ('hourly', 'Hourly'), ('weekly', 'Weekly'),
                 ('tod', 'Time of day')),
}
TOOL_NAMES = {
    'read': 'Read', 'editWrite': 'Edit / Write', 'search': 'Search', 'git': 'Git',
    'buildTest': 'Build / Test', 'terminal': 'Terminal', 'subagents': 'Subagents', 'web': 'Web',
}
PATH_NAMES = {
    'product_code': 'Product code', 'test_code': 'Tests', 'docs_spec': 'Docs / Spec',
    'config_build': 'Config / Build', 'schema_migration': 'Schema / Migration',
    'vendor': 'Vendor', 'asset': 'Assets',
}
AGENT_NAMES = {'claude': 'Claude', 'codex': 'Codex', 'antigravity': 'Antigravity'}
LOGIN_TEXT = {
    'working': 'Signing in…',
    'refreshed': 'Signed in. Reading plan limits…',
    'login': 'Finish signing in in the terminal window. Limits come back by themselves.',
    'missing': 'Claude Code was not found on this PC.',
    'failed': 'Could not open the sign-in window.',
}
WEEKDAYS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')

# 설정에서 오는 값 가운데 다시 모아야 하는 것. 묶음 차례·단 나누기는 그리기만 바뀐다.
DATA_OPTIONS = ('agents', 'hidden', 'excluded', 'currency', 'rate')


def get_palette(theme):
    '''테마에 그림용 색을 더한다. 계열색 1 = 파랑(accent), 2 = 주황. 상태색(warn·close)과 따로
    둔다. 어두운 판의 2 번은 판 밝기에 맞춰 낮췄다 (파랑↔주황 색약 ΔE 27.7 / 정상 29.6).'''
    palette = dict(theme)
    palette['series1'] = theme['accent']
    palette['series2'] = '#c98430' if theme['titlebar_dark'] else theme['warn']
    palette['sunken'] = mix(theme['face'], theme['grid'], 0.3).GetAsString(wx.C2S_HTML_SYNTAX)
    palette['soft'] = mix(theme['grid'], theme['accent'], 0.45).GetAsString(wx.C2S_HTML_SYNTAX)
    return palette


def js_round(value):
    '''JS 의 Math.round 와 같이 .5 는 위로. 파이썬 round 는 짝수 쪽으로 간다.'''
    return int(math.floor(value + 0.5))


def count(value):
    value = value or 0
    size = abs(value)
    if size >= 1e9:
        return '%.1fB' % (value / 1e9)
    if size >= 1e6:
        return '%.1fM' % (value / 1e6)
    if size >= 1e3:
        return '%.1fK' % (value / 1e3)
    return str(js_round(value))


def signed(value):
    return ('+' if value > 0 else '−' if value < 0 else '') + count(abs(value))


def ago(ms):
    seconds = max(0, time.time() - ms / 1000.0)
    if seconds < 60:
        return 'just now'
    if seconds < 3600:
        return '%dm ago' % (seconds // 60)
    if seconds < 86400:
        return '%dh ago' % (seconds // 3600)
    return '%dd ago' % (seconds // 86400)


def countdown(until):
    '''남은 시간을 짧게. 한도가 풀리기까지의 큰 글자에 쓴다.'''
    seconds = max(0, js_round(until - time.time()))
    days, hours, minutes = seconds // 86400, seconds % 86400 // 3600, seconds % 3600 // 60
    if days:
        return '%dd %dh' % (days, hours)
    if hours:
        return '%dh %dm' % (hours, minutes)
    return '%dm' % max(1, minutes)


def clock(at):
    '''풀리는 시각을 이 곳 시간으로. 물은 때와 받은 때의 몇 초 어긋남에 분이 흔들리지 않게 반올림한다.'''
    moment = time.localtime(js_round(at / 60.0) * 60)
    return '%d/%d %s %02d:%02d' % (moment.tm_mon, moment.tm_mday, WEEKDAYS[moment.tm_wday],
                                   moment.tm_hour, moment.tm_min)


def short_day(day):
    return day[5:].replace('-', '/', 1)


def to_date(day):
    return datetime.date(int(day[:4]), int(day[5:7]), int(day[8:10]))


def bucket_of(day, grain):
    '''묶는 단위의 열쇠. 주는 월요일에서 시작한다.'''
    if grain == 'day':
        return day
    if grain == 'month':
        return day[:7]
    date = to_date(day)
    return (date - datetime.timedelta(days=date.weekday())).isoformat()


def bucket_label(key, grain):
    if grain == 'month':
        return key[5:] + '/' + key[2:4]
    return short_day(key)


def get_level(value, peak):
    '''칸 하나가 유난히 바쁘면 나머지가 다 같은 색이 된다. 제곱근으로 눌러 편다.'''
    if not value:
        return 0
    return max(1, min(LEVELS, js_round(math.sqrt(value / float(peak)) * LEVELS)))


def sum_code(code, days):
    total = {'commits': 0, 'added': 0, 'removed': 0, 'paths': {}}
    for day in days:
        item = code.get(day)
        if not item:
            continue
        total['commits'] += item['commits']
        total['added'] += item['added']
        total['removed'] += item['removed']
        for name, (added, removed) in item['paths'].items():
            slot = total['paths'].setdefault(name, [0, 0])
            slot[0] += added
            slot[1] += removed
    return total


def flow(items, x, y, width, gap, row_gap, height, center=True):
    '''items = [(폭, 그리기(x, y))]. 자리가 모자라면 줄을 넘긴다 (웹판의 flex-wrap). 줄마다
    가운데에 두고, 다 쓴 아래 끝 y 를 돌려준다.'''
    rows, row, used = [], [], 0
    for item in items:
        wanted = item[0] if not row else used + gap + item[0]
        if row and wanted > width:
            rows.append((row, used))
            row, used = [item], item[0]
        else:
            row.append(item)
            used = wanted
    if row:
        rows.append((row, used))
    for index, (row, used) in enumerate(rows):
        left = x + (width - used) / 2.0 if center else x
        top = y + index * (height + row_gap)
        for item_width, draw in row:
            draw(int(round(left)), top)
            left += item_width + gap
    return y + len(rows) * height + max(0, len(rows) - 1) * row_gap


def round_corners(image, radius):
    '''Claude 아이콘은 모서리를 3px 굴린다 (웹판의 border-radius). 모서리 밖은 알파로 지운다.'''
    if not image.HasAlpha():
        image.InitAlpha()
    width, height = image.GetWidth(), image.GetHeight()
    for y in range(height):
        for x in range(width):
            cx = radius if x < radius else width - radius if x >= width - radius else None
            cy = radius if y < radius else height - radius if y >= height - radius else None
            if cx is None or cy is None:
                continue
            distance = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
            cover = max(0.0, min(1.0, radius + 0.5 - distance))
            image.SetAlpha(x, y, int(image.GetAlpha(x, y) * cover))


def load_brands():
    brands = {}
    for name in BRAND_ICONS:
        path = get_asset_path('brand', name + '.png')
        if not os.path.exists(path):
            continue
        image = wx.Image(path)
        if not image.IsOk():
            continue
        image = image.Scale(BRAND_SIZE, BRAND_SIZE, wx.IMAGE_QUALITY_HIGH)
        if name == 'claude':
            round_corners(image, 3)
        brands[name] = wx.Bitmap(image)
    return brands


def get_spaced_width(gc, font, text, spacing):
    gc.SetFont(font, wx.BLACK)
    return sum(gc.GetTextExtent(letter)[0] for letter in text) + spacing * len(text)


def draw_spaced(gc, font, colour, text, x, y, spacing):
    '''자간을 벌린 글씨. 한 글자씩 놓는다 (웹판의 letter-spacing).'''
    gc.SetFont(font, colour)
    for letter in text:
        gc.DrawText(letter, x, y)
        x += gc.GetTextExtent(letter)[0] + spacing


class Zone:
    '''누르거나 툴팁을 띄울 자리. lit 이면 손을 얹었을 때 모양이 바뀌어 다시 그린다.'''

    __slots__ = ('rect', 'key', 'action', 'tip', 'lit')

    def __init__(self, rect, key, action, tip, lit):
        self.rect = rect
        self.key = key
        self.action = action
        self.tip = tip
        self.lit = lit


class Painter:
    '''판 본체를 그리는 손. 글씨·막대·단추를 테마 색으로 그리고, 누를 자리와 툴팁 자리를
    적어 둔다. fade 를 주면 모든 색을 판 바탕 쪽으로 그만큼 옅게 한다 (지난 값).'''

    def __init__(self, gc, theme, body):
        self.gc = gc
        self.theme = theme
        self.body = body
        self.zones = []
        self.fade = 0.0

    def colour(self, name):
        # 테마 이름·'#rrggbb'·wx.Colour 모두 받는다. wx.Colour 는 사전 열쇠가 못 된다.
        colour = wx.Colour(self.theme.get(name, name) if isinstance(name, str) else name)
        if self.fade:
            colour = mix(colour, self.theme['face'], self.fade)
        return colour

    def width(self, text, size, bold=False):
        self.gc.SetFont(get_font(size, bold), wx.BLACK)
        return self.gc.GetTextExtent(text)[0]

    def fit(self, text, size, bold, limit):
        '''주어진 폭을 넘으면 말줄임으로 자른다.'''
        if self.width(text, size, bold) <= limit:
            return text
        while text and self.width(text + '…', size, bold) > limit:
            text = text[:-1]
        return text + '…' if text else ''

    def text(self, text, x, top, size, colour='text', bold=False, align='left', limit=None,
             line=None):
        '''줄 칸(top..top+line) 의 세로 가운데에 대문자 잉크가 오게 쓴다. 쓴 폭을 돌려준다.'''
        font = get_font(size, bold)
        return self.draw_at(text, x, get_text_top(font, top, line or LINE[size]), font,
                            size, colour, bold, align, limit)

    def baseline(self, size, top, line=None, bold=False):
        '''줄 칸에 쓴 글씨의 기준선. 크기가 다른 글씨를 한 줄에 둘 때 이 선에 맞춘다.'''
        font = get_font(size, bold)
        return get_text_top(font, top, line or LINE[size]) + get_ink(font)[1]

    def text_on(self, text, x, baseline, size, colour='text', bold=False, align='left',
                limit=None):
        font = get_font(size, bold)
        return self.draw_at(text, x, baseline - get_ink(font)[1], font, size, colour, bold,
                            align, limit)

    def draw_at(self, text, x, y, font, size, colour, bold, align, limit):
        if limit is not None:
            text = self.fit(text, size, bold, max(0, limit))
        if not text:
            return 0
        width = self.width(text, size, bold)
        if align == 'right':
            x -= width
        elif align == 'center':
            x -= width / 2.0
        self.gc.SetFont(font, self.colour(colour))
        self.gc.DrawText(text, int(round(x)), y)
        return width

    def rich(self, parts, x, top, size, align='left', limit=None):
        '''굵기·색이 섞인 한 줄. parts = [(글씨, 색, 굵게)].'''
        total = sum(self.width(text, size, bold) for text, _, bold in parts)
        if align == 'right':
            x -= total
        # 넘치면 자리가 다하는 조각에서 말줄임으로 끊는다.
        room = total if limit is None else limit
        for text, colour, bold in parts:
            if room <= 0:
                break
            used = self.text(text, x, top, size, colour, bold, limit=room)
            x += used
            room -= used
        return total

    def spaced_width(self, text, size, bold, spacing):
        return get_spaced_width(self.gc, get_font(size, bold), text, spacing)

    def spaced(self, text, x, top, size, colour='dim', bold=True, spacing=1.4, align='left',
               line=None):
        font = get_font(size, bold)
        width = self.spaced_width(text, size, bold, spacing)
        if align == 'right':
            x -= width
        elif align == 'center':
            x -= width / 2.0
        draw_spaced(self.gc, font, self.colour(colour), text, int(round(x)),
                    get_text_top(font, top, line or LINE[size]), spacing)
        return width

    def caption(self, text, x, top, align='left'):
        '''작은 대문자 이름표. 자간을 벌려야 제목처럼 읽힌다.'''
        return self.spaced(text.upper(), x, top, TINY, 'dim', True, 1.4, align)

    def fill(self, colour, x, y, width, height, radius=0):
        fill_rect(self.gc, self.colour(colour), x, y, width, height, radius)

    def rim(self, colour, x, y, width, height, radius=PANEL_RADIUS):
        draw_card_rim(self.gc, self.colour(colour), x, y, width, height, radius)

    def track(self, x, y, width, ratio, colour='accent', back='grid'):
        '''진행 막대. 바탕 막대 위에 몫만큼 채운다.'''
        self.fill(back, x, y, width, BAR_HEIGHT, BAR_RADIUS)
        filled = width * max(0.0, min(1.0, ratio))
        if filled > 0:
            self.fill(colour, x, y, filled, BAR_HEIGHT, BAR_RADIUS)

    def wrap(self, text, size, limit, bold=False):
        '''낱말 단위로 줄을 나눈다.'''
        lines, line = [], ''
        for word in text.split(' '):
            candidate = word if not line else line + ' ' + word
            if line and self.width(candidate, size, bold) > limit:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
        return lines

    def zone(self, x, y, width, height, key, action=None, tip=None, lit=None):
        self.zones.append(Zone(wx.Rect(int(x), int(y), int(math.ceil(width)), int(height)), key,
                               action, tip, action is not None if lit is None else lit))

    def state(self, key):
        body = self.body
        if body.down == key and body.hover == key:
            return 'down'
        return 'hover' if body.hover == key else 'plain'

    def button(self, x, y, label, key, action, lit=False):
        width = get_button_width(label)
        rect = wx.Rect(int(x), int(y), width, BUTTON_HEIGHT)
        state = 'lit' if lit else self.state(key)
        draw_button(self.gc, self.theme, rect, label, state)
        self.zone(rect.x, rect.y, rect.width, rect.height, key, None if lit else action)
        return width

    def link(self, text, x, top, key, action, size=NOTE):
        '''글자 단추. 손을 얹으면 밑줄. 반응하는 것은 글씨 자리뿐이다.'''
        width = self.text(text, x, top, size, 'accent')
        if self.body.hover == key:
            base = self.baseline(size, top)
            self.fill('accent', int(round(x)), base + 1, width, 1)
        self.zone(x, top, width, LINE[size], key, action)
        return width

    def dot(self, x, baseline, colour):
        '''도구 표시의 동그라미. 아랫변을 글씨 기준선에 둔다 (웹판의 vertical-align: 0).'''
        self.gc.SetPen(wx.TRANSPARENT_PEN)
        self.gc.SetBrush(wx.Brush(self.colour(colour)))
        self.gc.DrawEllipse(x, baseline - 7, 7, 7)

    def provider(self, provider, x, baseline, upper=True):
        '''도구 표시: 계열색 동그라미 + 흐린 이름. 쓴 폭을 돌려준다.'''
        colour = {'claude': 'series1', 'codex': 'series2'}.get(provider, 'dim')
        name = AGENT_NAMES.get(provider, provider)
        name = name.upper() if upper else name
        self.dot(x, baseline, colour)
        font = get_font(SMALL, True)
        width = self.spaced_width(name, SMALL, True, 0.4)
        draw_spaced(self.gc, font, self.colour('dim'), name, int(x + 11),
                    baseline - get_ink(font)[1], 0.4)
        return 11 + width


class Body(Canvas):
    '''판 본체 한 장. 그리는 일은 render(painter, width) → 다 쓴 높이 가 한다. 키는 폭에서
    나오므로 폭이 바뀌거나 값이 바뀌면 다시 재고, 키가 달라졌을 때만 최소 크기를 준다 —
    키가 폭만 보고 정해져 되먹임이 생기지 않는다.'''

    first = True
    last = True

    def __init__(self, parent, theme, render, on_layout):
        super().__init__(parent, theme)
        self.render = render
        self.on_layout = on_layout
        self.zones = []
        self.hover = None
        self.hover_lit = False
        self.down = None
        self.tip = None
        self.SetMinSize(wx.Size(-1, PAD * 2))
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_MOTION, self.on_motion)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_down)
        self.Bind(wx.EVT_LEFT_DCLICK, self.on_down)
        self.Bind(wx.EVT_LEFT_UP, self.on_up)
        self.Bind(wx.EVT_LEAVE_WINDOW, self.on_leave)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self.on_lost)

    def run(self, gc, width):
        painter = Painter(gc, self.theme, self)
        try:
            height = self.render(painter, width)
        except Exception:
            # 한 판이 깨져도 나머지는 그린다.
            traceback.print_exc()
            height = self.GetMinSize()[1]
        self.zones = painter.zones
        return int(math.ceil(height))

    def measure(self):
        '''지금 폭에서 키를 다시 잰다. 달라졌으면 최소 크기를 주고 참.'''
        width = self.GetClientSize()[0]
        if width <= 0:
            return False
        dc = wx.MemoryDC(wx.Bitmap(1, 1))
        gc = wx.GraphicsContext.Create(dc)
        height = self.run(gc, width)
        del gc
        dc.SelectObject(wx.NullBitmap)
        if height == self.GetMinSize()[1]:
            return False
        self.SetMinSize(wx.Size(-1, height))
        return True

    def on_size(self, event):
        if self.measure() and self.on_layout:
            self.on_layout()
        self.Refresh()
        event.Skip()

    def draw(self, gc, width, height):
        draw_row_face(gc, self.theme, width, height, self.first, self.last)
        self.run(gc, width)

    def find(self, position):
        for zone in reversed(self.zones):
            if zone.rect.Contains(position):
                return zone
        return None

    def set_hover(self, zone):
        key = zone.key if zone else None
        if key == self.hover:
            return
        lit = bool(zone and zone.lit)
        repaint = lit or self.hover_lit
        self.hover, self.hover_lit = key, lit
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND if zone and zone.action else wx.CURSOR_ARROW))
        tip = zone.tip if zone else None
        if tip != self.tip:
            self.tip = tip
            if tip:
                self.SetToolTip(tip)
            else:
                self.UnsetToolTip()
        if repaint:
            self.Refresh()

    def on_motion(self, event):
        self.set_hover(self.find(event.GetPosition()))
        event.Skip()

    def on_down(self, event):
        zone = self.find(event.GetPosition())
        if not zone or not zone.action:
            event.Skip()
            return
        self.down = zone.key
        if not self.HasCapture():
            self.CaptureMouse()
        self.Refresh()

    def on_up(self, event):
        if self.HasCapture():
            self.ReleaseMouse()
        zone = self.find(event.GetPosition())
        down, self.down = self.down, None
        self.Refresh()
        # 누른 자리에서 놓아야 누른 것이다. 끌고 나가 놓으면 아무 일도 없다.
        if down and zone and zone.key == down and zone.action:
            zone.action()

    def on_leave(self, event):
        if not self.HasCapture():
            self.set_hover(None)

    def on_lost(self, event):
        self.down = None
        self.Refresh()


class BandHeader(PanelHeader):
    '''판의 이름 띠에 오른쪽 끝 단추를 더한 것. 고르기 칸 묶음(Today·All) 또는 글자 단추 하나
    (Reload). 꺾쇠+제목 단추와 오른쪽 단추가 따로 반응한다 — 띠의 다른 단추에 손을 얹었을 때
    꺾쇠가 함께 밝아지면 안 된다(사용자). solo 면 본체 없는 띠 한 줄이라 접지 않는다 (Refresh).
    부제 자리에는 글씨 대신 플랜 이름표를 둘 수 있다 (Overview).'''

    TAIL_GAP = 8

    solo = False

    def __init__(self, parent, theme, title, subtitle='', choices=None, value=None, on_pick=None,
                 button=None, on_button=None, solo=False):
        super().__init__(parent, theme, title, subtitle, self.dispatch)
        self.solo = solo
        self.on_toggle = None
        self.choices = list(choices or ())
        self.value = value
        self.on_pick = on_pick
        self.button = button
        self.on_button = on_button
        self.enabled = True
        self.plans = []
        self.marked = None
        self.down_zone = None
        # 툴팁은 꺾쇠+제목 위에서만 (on_track). 띠 전체에 걸면 오른쪽 단추 위에서도 Fold 가 뜬다.
        self.UnsetToolTip()
        self.update_height()

    def update_height(self):
        if self.solo:
            self.SetMinSize(wx.Size(-1, HEADER_BAND))
            return
        super().update_height()

    def set_folded(self, folded):
        self.folded = folded
        self.update_height()
        self.Refresh()

    def set_value(self, value):
        if value != self.value:
            self.value = value
            self.Refresh()

    def set_plans(self, plans):
        plans = [(plan['provider'], plan['name']) for plan in plans or ()]
        if plans != self.plans:
            self.plans = plans
            self.Refresh()

    def set_enabled(self, enabled):
        if enabled != self.enabled:
            self.enabled = enabled
            self.Refresh()

    def get_tail(self):
        '''오른쪽 끝 단추들의 (열쇠, 글씨, 자리). 오른쪽 끝에서부터 쌓는다.'''
        if self.button:
            items = [('button', self.button)]
        else:
            items = [(index, name) for index, (_, name) in enumerate(self.choices)]
        right = self.GetClientSize()[0] - BAND_INSET
        cells = []
        for key, label in reversed(items):
            width = get_button_width(label)
            right -= width
            cells.insert(0, (key, label, wx.Rect(right, BAND_INSET, width, BUTTON_HEIGHT)))
            right -= BUTTON_GAP
        return cells

    def get_zone(self, position):
        if not self.solo and self.get_hit().Contains(position):
            return 'fold'
        for key, _, rect in self.get_tail():
            if rect.Contains(position) and (key != 'button' or self.enabled):
                return key
        return None

    def hits(self, position):
        return self.get_zone(position) is not None

    def on_track(self, event):
        zone = self.get_zone(event.GetPosition())
        if zone != self.marked:
            self.marked = zone
            if zone == 'fold':
                self.SetToolTip('Unfold' if self.folded else 'Fold')
            else:
                self.UnsetToolTip()
            self.Refresh()
        super().on_track(event)

    def on_down(self, event):
        self.down_zone = self.get_zone(event.GetPosition())
        super().on_down(event)

    def on_leave(self, event):
        if self.marked is not None:
            self.marked = None
            self.Refresh()
        super().on_leave(event)

    def dispatch(self):
        zone = self.get_zone(self.up_position)
        if zone is None or zone != self.down_zone:
            return
        if zone == 'fold':
            if self.on_toggle:
                self.on_toggle()
        elif zone == 'button':
            if self.on_button:
                self.on_button()
        else:
            value = self.choices[zone][0]
            if value != self.value:
                self.value = value
                self.Refresh()
                if self.on_pick:
                    self.on_pick(value)

    def get_state(self, key):
        if self.pressed and self.down_zone == key and self.marked == key:
            return 'down'
        return 'hover' if self.marked == key else 'plain'

    def draw(self, gc, width, height):
        theme = self.theme
        folded = self.folded or self.solo
        fill_rect(gc, theme['band'], 0, 0, width, HEADER_BAND, PANEL_RADIUS)
        if not folded:
            fill_rect(gc, theme['band'], 0, HEADER_BAND - PANEL_RADIUS, width, PANEL_RADIUS)
            fill_rect(gc, theme['rim'], 0, HEADER_BAND, width, 1)
        fill_rect(gc, theme['accent'], 0, 6, 2, HEADER_BAND - 12, 1)

        hit = self.get_hit()
        if not self.solo:
            state = self.get_state('fold')
            if state != 'plain':
                fill_rect(gc, theme['control_down' if state == 'down' else 'control_hover'],
                          hit.x, hit.y, hit.width, hit.height, PANEL_RADIUS)
            draw_chevron(gc, 'right' if self.folded else 'down',
                         BAND_INSET + self.LEFT + self.CHEVRON / 2, HEADER_BAND / 2, self.CHEVRON,
                         theme['text'] if self.marked == 'fold' else theme['dim'])

        tail = self.get_tail()
        right = (tail[0][2].x - self.TAIL_GAP) if tail else width - PANEL_PAD
        for key, label, rect in tail:
            if key == 'button':
                # 읽는 동안은 누를 수 없다. 글씨만 흐리게 — 폭이 변하면 띠가 밀린다.
                face = theme if self.enabled else dict(theme, text=theme['faint'])
                draw_button(gc, face, rect, label, self.get_state(key) if self.enabled else 'plain')
            else:
                lit = self.choices[key][0] == self.value
                draw_button(gc, theme, rect, label, 'lit' if lit else self.get_state(key))

        font = get_font(self.TITLE_SIZE, True)
        left = self.get_title_left()
        gc.SetFont(font, wx.Colour(theme['text']))
        title = self.fit_text(gc, self.title, max(0, right - left))
        title_top = get_text_top(font, 0, HEADER_BAND)
        gc.DrawText(title, left, title_top)
        # 부제는 제목과 기준선을 맞춘다. 글씨 크기가 달라 가운데로 맞추면 들떠 보인다.
        baseline = title_top + get_ink(font)[1]
        if self.solo:
            sub_left = left + gc.GetTextExtent(title)[0] + self.SUB_GAP
        else:
            sub_left = hit.x + hit.width + self.SUB_GAP
        if self.plans:
            self.draw_plans(gc, sub_left, right, baseline)
        elif self.subtitle and right - sub_left > 12:
            sub_font = get_font(8)
            gc.SetFont(sub_font, wx.Colour(theme['dim']))
            gc.DrawText(self.fit_text(gc, self.subtitle, right - sub_left), sub_left,
                        baseline - get_ink(sub_font)[1])

    def draw_plans(self, gc, left, right, baseline):
        '''지금 쓰는 플랜. 좁으면 줄을 바꾸지 않고 들어가는 데까지만 쓴다. 눌리지 않는 글씨라
        테두리를 두르지 않는다 — 단추처럼 보이면 안 된다.'''
        theme = self.theme
        tag_font, name_font = get_font(SMALL, True), get_font(8)
        x = left
        for provider, name in self.plans:
            label = AGENT_NAMES.get(provider, provider).upper()
            tag = get_spaced_width(gc, tag_font, label, 0.4)
            gc.SetFont(name_font, wx.BLACK)
            name_width = gc.GetTextExtent(name)[0]
            total = 11 + tag + 4 + name_width
            if x + total > right:
                break
            colour = {'claude': 'series1', 'codex': 'series2'}.get(provider, 'dim')
            gc.SetPen(wx.TRANSPARENT_PEN)
            gc.SetBrush(wx.Brush(wx.Colour(theme.get(colour, theme['dim']))))
            gc.DrawEllipse(x, baseline - 7, 7, 7)
            draw_spaced(gc, tag_font, wx.Colour(theme['dim']), label, x + 11,
                        baseline - get_ink(tag_font)[1], 0.4)
            gc.SetFont(name_font, wx.Colour(theme['dim']))
            gc.DrawText(name, x + 11 + tag + 4, baseline - get_ink(name_font)[1])
            x += total + 10


class Banner(Canvas):
    '''색인을 처음 만드는 동안 판들 위에 뜨는 띠. 아래 판 사이 틈까지가 제 키다.'''

    HEIGHT = 8 + LINE[BODY] + 6 + BAR_HEIGHT + 8

    def __init__(self, parent, theme):
        super().__init__(parent, theme)
        self.value = 0.0
        self.SetMinSize(wx.Size(-1, self.HEIGHT + PANEL_GAP))

    def set_value(self, value):
        self.value = value
        self.Refresh()

    def draw(self, gc, width, height):
        theme = self.theme
        fill_rect(gc, theme['face'], 0, 0, width, self.HEIGHT, PANEL_RADIUS)
        fill_rect(gc, theme['accent'], 0, 6, 2, self.HEIGHT - 12, 1)
        font = get_font(BODY)
        gc.SetFont(font, wx.Colour(theme['text']))
        gc.DrawText('Indexing usage history… %d%%' % js_round(self.value * 100), PAD,
                    get_text_top(font, 8, LINE[BODY]))
        top = 8 + LINE[BODY] + 6
        span = width - PAD * 2
        fill_rect(gc, theme['grid'], PAD, top, span, BAR_HEIGHT, BAR_RADIUS)
        if self.value > 0:
            fill_rect(gc, theme['accent'], PAD, top, span * min(1.0, self.value), BAR_HEIGHT,
                      BAR_RADIUS)


class UsageBox(ScrollArea):

    def __init__(self, parent, theme, settings=None, on_options=None):
        super().__init__(parent, theme)
        settings = settings or {}
        self.theme = theme
        self.palette = get_palette(theme)
        self.loading = False
        self.pending = False
        self.ready = False
        self.refreshing = False
        self.last_refresh_try = 0
        self.last_expiry_check = 0
        self.last_run = 0
        self.last_git = 0
        self.last_clock = 0
        self.on_options = on_options
        # 모을 때마다 같은 값을 받는 쪽 (떠 있는 위젯). mainapp 이 건다.
        self.on_data = None
        self.index = usageindex.UsageIndex()
        self.options = {
            'agents': ('claude',),
            'hidden': list(settings.get('hidden_projects', [])),
            'excluded': list(settings.get('excluded_projects', [])),
            'currency': 'USD',
            'rate': 1.0,
            'sections': None,
            'wide': True,
        }
        self.data = None
        # 첫 값으로 그린 뒤에야 참이다. 그 전의 단 나누기는 뼈대 키로 한 것이라 한 번 다시 나눈다.
        self.drawn = False
        self.login_state = None
        # 고른 칸 (metric·grain·...). 설정에 남겨 다음에도 같은 모습으로 연다.
        stored = settings.get('usage_view') or {}
        self.view = {key: stored.get(key, value) if stored.get(key) in
                     [choice[0] for choice in CHOICES[key]] else value
                     for key, value in VIEW_DEFAULTS.items()}
        self.view.update(picked=None, showAll=False, showIdle=False, showHidden=False,
                         openSession=None)
        # 접어 둔 판. 접고 펼 때마다 앱이 저장한다.
        self.folded = set(settings.get('usage_folded_sections') or [])
        self.brands = load_brands()

        self.build()
        self.bind_children()
        self.apply_theme(theme)
        # 처음 모으기는 앱이 설정(켠 도구·통화)을 건넨 뒤에 한다. 그 전 값으로 모으면 버린다.
        wx.CallAfter(self.start)

    def start(self):
        self.ready = True
        self.reload(git=True)

    # 판 ---------------------------------------------------------------

    def build(self):
        board = self.content
        self.banner = Banner(board, self.palette)
        self.bodies = {}
        self.headers = {}
        self.panels = {}
        for key, title, render, name, subtitle in (
                ('header', 'Overview', self.draw_header, 'headerPeriod', ''),
                ('planUsage', 'Plan Usage', self.draw_limits, None, ''),
                ('codeOutput', 'Code Output', self.draw_code, 'codePeriod', ''),
                ('trend', 'Trend', self.draw_trend, None, ''),
                ('sessions', 'Sessions', self.draw_sessions, 'sessionFilter', ''),
                ('activity', 'Activity', self.draw_activity, None, ''),
                ('modelUsage', 'Model Usage', self.draw_models, None, 'Top 4 · all time')):
            header = BandHeader(board, self.palette, title, subtitle,
                                choices=CHOICES[name] if name else None,
                                value=self.view.get(name),
                                on_pick=(lambda value, name=name: self.set_view(name, value))
                                if name else None)
            body = Body(board, self.palette, render, self.relayout_soon)
            self.headers[key] = header
            self.bodies[key] = body
            self.panels[key] = Panel(board, self.palette, key, title, [body], self.folded,
                                     self.on_fold, header=header)
        self.refresh_band = BandHeader(board, self.palette, 'Refresh', 'Re-read the agent records',
                                       button='Reload', on_button=self.on_reload, solo=True)
        self.headers['refresh'] = self.refresh_band
        self.panels['refresh'] = Panel(board, self.palette, 'refresh', 'Refresh', [], self.folded,
                                       None, header=self.refresh_band)

        # ScrollArea.set_panels 와 같은 짜임에 색인 띠를 판들 위에 한 줄 더한다.
        self.column_gap = PANEL_GAP
        self.root = wx.BoxSizer(wx.VERTICAL)
        self.root.AddSpacer(PANEL_MARGIN)
        self.root.Add(self.banner, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, PANEL_MARGIN)
        self.row = wx.BoxSizer(wx.HORIZONTAL)
        self.root.Add(self.row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, PANEL_MARGIN)
        self.root.AddSpacer(PANEL_MARGIN - PANEL_GAP)
        self.content.SetSizer(self.root)
        self.root.Show(self.banner, False)
        self.groups = []
        self.apply_sections()

    def apply_sections(self):
        '''묶음 차례·숨김은 설정에서 온다. 머리판이 맨 앞, Refresh 가 맨 끝, 그 사이는 설정의 차례.'''
        sections = self.options.get('sections')
        middle = [key for key in self.panels if key not in ('header', 'refresh')]
        hidden = set()
        if sections:
            known = [item['id'] for item in sections if item['id'] in self.panels]
            middle = known + [key for key in middle if key not in known]
            hidden = {item['id'] for item in sections if item.get('hidden')}
        order = [key for key in ['header'] + middle + ['refresh'] if key not in hidden]

        # 단을 다시 짜기 전에 판을 모두 떼어 낸다. 숨길 판이 단에 남은 채 단이 지워지면
        # 그 판의 사이저까지 함께 지워진다.
        for item in list(self.row.GetChildren()):
            column = item.GetSizer()
            if column:
                for panel in self.panels.values():
                    column.Detach(panel.sizer)
        for key, panel in self.panels.items():
            if key in hidden:
                for item in panel.sizer.GetChildren():
                    if item.IsWindow():
                        item.GetWindow().Hide()
            else:
                panel.header.Show()
                panel.apply_fold()
        self.groups = [self.panels[key].sizer for key in order]
        self.Freeze()
        try:
            self.columns = 0
            self.arrange(force=True)
        finally:
            self.Thaw()

    def on_fold(self):
        self.relayout_panels()
        if self.on_options:
            self.on_options()

    def relayout(self):
        '''판 키가 바뀌었을 때. 단 나누기는 그대로 둔다 — 1 분마다 새로 그릴 때마다 다시
        나누면 판이 단 사이를 오가며 튄다(사용자).'''
        self.relayout_pending = False
        self.content.Layout()
        self.fit()

    relayout_pending = False

    def relayout_soon(self):
        '''판이 제 크기 이벤트 안에서 키를 바꿨을 때. ★그 자리에서 다시 배치하면 바깥에서 돌던
        배치가 옛 키로 덮어쓴다(실측: 키 191 인 판이 295 로 남았다). 다음 차례로 미루고,
        여러 판이 한꺼번에 불러도 한 번만 한다.'''
        if not self.relayout_pending:
            self.relayout_pending = True
            wx.CallAfter(self.relayout)

    def refresh_bodies(self, keys=None):
        changed = False
        for key, body in self.bodies.items():
            if keys is None or key in keys:
                changed = body.measure() or changed
                body.Refresh()
        if changed:
            self.relayout()

    def set_view(self, name, value):
        self.view[name] = value
        if name == 'grain':
            self.view['picked'] = None
        if name in ('headerPeriod', 'codePeriod', 'sessionFilter'):
            key = {'headerPeriod': 'header', 'codePeriod': 'codeOutput',
                   'sessionFilter': 'sessions'}[name]
            self.headers[key].set_value(value)
        self.refresh_bodies()
        if name in VIEW_DEFAULTS and self.on_options:
            self.on_options()

    def apply_theme(self, theme):
        self.theme = theme
        self.palette = get_palette(theme)
        self.set_theme(theme)
        for child in self.content.GetChildren():
            if hasattr(child, 'set_theme'):
                child.set_theme(self.palette)
        self.Refresh()

    # 값 --------------------------------------------------------------

    def money(self, value, digits=0):
        data = self.data or {}
        currency = data.get('currency') or 'USD'
        rate = 1 if currency == 'USD' else (data.get('rate') or 1)
        symbol = {'USD': '$', 'KRW': '₩'}.get(currency, '$')
        if currency == 'KRW':
            digits = 0
        return symbol + format((value or 0) * rate, ',.%df' % digits)

    def set_progress(self, value):
        shown = value is not None and value < 1
        if shown:
            self.banner.set_value(value)
        if shown != self.banner.IsShown():
            self.root.Show(self.banner, shown)
            self.relayout()

    def set_login_state(self, state):
        self.login_state = state
        self.refresh_bodies(('planUsage',))

    def deliver(self, data):
        self.data = data
        if not data.get('claude_status'):
            self.login_state = None
        self.headers['header'].set_plans(data.get('plans'))
        self.refresh_band.set_enabled(True)
        self.refresh_band.set_subtitle('last run · ' + ago(data['updated'] * 1000))
        self.refresh_bodies()
        if not self.drawn:
            self.drawn = True
            self.relayout_panels()
        if self.on_data:
            self.on_data(data)

    def on_reload(self):
        # 단추 글씨는 그대로 둔다(폭이 변하면 띠가 밀린다). 읽는 중이라는 것은 부제가 말한다.
        self.refresh_band.set_enabled(False)
        self.refresh_band.set_subtitle('reading…')
        self.reload(force=True, git=True)

    # 머리판 -------------------------------------------------------------

    def draw_header(self, p, width):
        data = self.data
        all_time = self.view['headerPeriod'] == 'all'
        left, right = PAD, width - PAD
        half = (right - left - 12) / 2.0
        if data:
            totals = data['all'] if all_time else data['today']
            values = (self.money(totals['cost']), '%d%%' % js_round(totals['ratio'] * 100))
            notes = ('%s calls  /  %d sessions' % (count(totals['calls']), totals['sessions']),
                     '+ %s%s' % (self.money(totals['saved']),
                                 ' saved total' if all_time else ' saved today'))
        else:
            values, notes = ('—', '—'), ('', '')
        y = PAD
        p.caption('All-time cost' if all_time else 'Today cost', left, y)
        p.caption('Avg cache efficiency' if all_time else 'Cache efficiency', right, y, 'right')
        y += LINE[TINY] + 2
        p.text(values[0], left, y, VALUE, bold=True, limit=half)
        p.text(values[1], right, y, VALUE, bold=True, align='right', limit=half)
        y += LINE[VALUE] + 2
        p.text(notes[0], left, y, NOTE, 'dim', limit=half)
        p.text(notes[1], right, y, NOTE, 'dim', align='right', limit=half)
        return y + LINE[NOTE] + PAD

    # 한도 ---------------------------------------------------------------

    def draw_empty(self, p, text, x, y, width):
        p.text(text, x + width / 2.0, y + 6, BODY, 'dim', align='center', limit=width)
        return y + 6 + LINE[BODY] + 6

    def draw_skeleton_rows(self, p, x, y, width, rows, left, right, gap):
        '''한도·모델 뼈대: 이름 줄(왼쪽·오른쪽 토막) + 막대를 rows 번.'''
        for index in range(rows):
            if index:
                y += gap
            p.fill('grid', x, y + 4, width * left, 9, PANEL_RADIUS)
            p.fill('grid', x + width * (1 - right), y + 4, width * right, 9, PANEL_RADIUS)
            y += 17 + 6
            p.fill('grid', x, y, width, BAR_HEIGHT, PANEL_RADIUS)
            y += BAR_HEIGHT
        return y

    def draw_limits(self, p, width):
        data = self.data
        x, span, y = PAD, width - PAD * 2, PAD
        if data is None:
            return self.draw_skeleton_rows(p, x, y, span, 5, 0.38, 0.12, 14) + PAD
        limits, status = data['limits'], data.get('claude_status')
        if limits is None:
            if status:
                return self.draw_limit_note(p, x, y, span, status) + PAD
            return self.draw_empty(p, 'plan limits unavailable', x, y, span) + PAD
        if not limits:
            return self.draw_empty(p, 'nothing running against a limit', x, y, span) + PAD
        if status:
            y = self.draw_limit_note(p, x, y, span, status)

        # 도구마다 묶는다. 묶음 머리에 아이콘·이름·플랜을 두므로 줄 이름의 "Codex · " 는 뗀다.
        plans = {plan['provider']: plan['name'] for plan in data.get('plans') or ()}
        groups = []
        for limit in limits:
            provider = limit.get('provider') or 'claude'
            if not groups or groups[-1][0] != provider:
                groups.append((provider, []))
            groups[-1][1].append(limit)
        for index, (provider, rows) in enumerate(groups):
            if index:
                y += PAD
                p.fill('rim', x, y, span, 1)
                y += 1 + PAD
            y = self.draw_brand(p, provider, plans.get(provider, ''), x, y, span)
            for order, limit in enumerate(rows):
                if order:
                    y += PAD
                y = self.draw_limit(p, limit, x, y, span)
            if provider == 'codex':
                y = self.draw_resets(p, data.get('codex_resets'), x, y, span)
        return y + PAD

    def draw_limit_note(self, p, x, y, width, status):
        '''서버에 못 물어 지난 값을 보일 때. 까닭을 위에 두고, 만료일 때만 Sign in 을 둔다 —
        연결이 안 되는 것은 다시 로그인해도 풀리지 않는다.'''
        reason = ('Claude sign-in token expired.' if status.get('error') == 'expired'
                  else 'Could not reach Claude for plan limits.')
        if status.get('age') is None:
            shown = ' No earlier snapshot to show.'
        else:
            shown = ' Showing the last snapshot from %s.' % ago((time.time() - status['age']) * 1000)
        lines = p.wrap(reason + shown, NOTE, width - 16)
        action = None
        if self.login_state:
            action = LOGIN_TEXT.get(self.login_state, '')
        elif status.get('error') == 'expired':
            action = 'link'
        height = 6 + len(lines) * LINE[NOTE] + (4 + LINE[NOTE] if action else 0) + 6
        p.fill('sunken', x, y, width, height, PANEL_RADIUS)
        top = y + 6
        for line in lines:
            p.text(line, x + 8, top, NOTE, 'dim')
            top += LINE[NOTE]
        if action == 'link':
            p.link('Sign in', x + 8, top + 4, 'claude-login', self.sign_in)
        elif action:
            p.text(action, x + 8, top + 4, NOTE, 'dim', limit=width - 16)
        return y + height + PAD

    def draw_brand(self, p, provider, plan, x, y, width):
        '''묶음 머리. Codex 아이콘은 바탕에 따라 흰·검정 두 벌을 갈아 쓴다.'''
        name = provider
        if provider == 'codex':
            name = 'codex-dark' if self.theme['titlebar_dark'] else 'codex-light'
        bitmap = self.brands.get(name)
        left = x
        if bitmap:
            p.gc.DrawBitmap(bitmap, x, y + 1, BRAND_SIZE, BRAND_SIZE)
            left += BRAND_SIZE + 7
        base = p.baseline(BODY, y, LINE[BODY], True)
        left += p.text_on(AGENT_NAMES.get(provider, provider), left, base, BODY, bold=True) + 7
        p.text_on(plan, left, base, NOTE, 'dim', limit=x + width - left)
        return y + LINE[BODY] + 10

    def get_tint(self, limit):
        if limit['severity'] == 'critical' or limit.get('reached'):
            return 'close'
        return 'warn' if limit['severity'] == 'warning' else 'accent'

    def draw_limit(self, p, limit, x, y, width):
        '''한 칸에 둘을 겹친다. 뒤의 옅은 막대가 창 전체 가운데 지나간 시간, 앞의 색 막대가
        쓴 몫이다. 색 막대가 옅은 막대를 앞지르면 이대로는 창이 끝나기 전에 한도에 닿는다.'''
        tint = self.get_tint(limit)
        stale = limit.get('stale')
        p.fade = 0.45 if stale else 0.0
        name = limit['name']
        if name.startswith('Codex · '):
            name = name[len('Codex · '):]
        base = p.baseline(MAIN, y, LINE[MAIN], True)
        right = x + width
        right -= p.text_on('%d%%' % limit['percent'], right, base, MAIN, tint, True, 'right')
        if limit.get('elapsed') is not None:
            right -= 8 + p.text_on('%d%% elapsed' % limit['elapsed'], right - 8, base, NOTE, 'dim',
                                   align='right')
        name_width = p.text_on(name, x, base, BODY)
        when = (limit.get('when') or '') + (' · ' + clock(limit['reset_at'])
                                            if limit.get('reset_at') else '')
        if stale:
            when += ' · cached'
        p.text_on(when, x + name_width + 8, base, NOTE, 'dim', limit=right - 8 - (x + name_width + 8))
        y += LINE[MAIN] + 5
        p.fill('grid', x, y, width, BAR_HEIGHT, BAR_RADIUS)
        if limit.get('elapsed') is not None:
            p.fill(mix(self.palette['grid'], self.palette['dim'], 0.45), x, y,
                   width * limit['elapsed'] / 100.0, BAR_HEIGHT, BAR_RADIUS)
        used = width * min(100, max(0, limit['percent'])) / 100.0
        if used > 0:
            p.fill(tint, x, y, used, BAR_HEIGHT, BAR_RADIUS)
        y += BAR_HEIGHT
        if limit.get('reached') and limit.get('until'):
            # 다 쓴 칸. 언제 다시 쓸 수 있는지가 이 줄에서 가장 궁금한 값이라 크게 둔다.
            y += 8
            base = p.baseline(HUGE, y, LINE[HUGE], True)
            left = x + p.text_on(countdown(limit['until']), x, base, HUGE, tint, True) + 8
            p.text_on('until this limit lifts · ' + clock(limit['until']), left, base, NOTE, 'dim',
                      limit=x + width - left)
            y += LINE[HUGE]
        p.fade = 0.0
        return y

    def draw_resets(self, p, resets, x, y, width):
        '''Codex 강제 초기화 이용권. 이용권마다 만료가 따로라 한 장씩 남은 시간을 둔다. 하루 안에
        사라질 것은 주황 테두리에 '곧' 표시를 붙인다 (색만으로 가르지 않는다).'''
        if not resets:
            return y
        now = time.time()
        # 1 분마다 다시 모으기 전에 만료된 것은 여기서 뺀다.
        credits = [credit for credit in resets['credits']
                   if not credit.get('expires') or credit['expires'] > now]
        p.fade = 0.45 if resets.get('stale') else 0.0
        y += PAD
        base = p.baseline(MAIN, y, LINE[MAIN], True)
        right = x + width - p.text_on('%d available' % len(credits), x + width, base, MAIN,
                                      'accent', True, 'right')
        name_width = p.text_on('Force resets', x, base, BODY)
        nxt = credits[0].get('expires') if credits else None
        when = ('next expires in ' + countdown(nxt) if nxt else '') + \
            (' · cached' if resets.get('stale') else '')
        p.text_on(when, x + name_width + 8, base, NOTE, 'dim', limit=right - 8 - (x + name_width + 8))
        y += LINE[MAIN]
        if credits:
            y += 6
            items = []
            for order, credit in enumerate(credits):
                expires = credit.get('expires')
                soon = bool(expires) and expires - now < RESET_SOON
                parts = [('#%d ' % (order + 1), 'dim', False),
                         (countdown(expires) if expires else 'no expiry',
                          'warn' if soon else 'text', True)]
                if soon:
                    parts.append((' · soon', 'dim', False))
                chip = sum(p.width(text, NOTE, bold) for text, _, bold in parts) + 16
                items.append((chip, lambda left, top, parts=parts, chip=chip, soon=soon, credit=credit:
                              self.draw_chip(p, parts, left, top, chip, soon, credit)))
            # 웹판처럼 왼쪽부터 채운다 (가운데 맞춤 아님).
            y = flow(items, x, y, width, 6, 6, LINE[NOTE] + 4, center=False)
        p.fade = 0.0
        return y

    def draw_chip(self, p, parts, left, top, width, soon, credit):
        height = LINE[NOTE] + 4
        p.rim('warn' if soon else 'edge', left, top, width, height)
        p.rich(parts, left + 8, top + 2, NOTE)
        p.zone(left, top, width, height, 'credit:%s' % credit.get('title'), tip=credit.get('title'))

    # 막대 그림 ----------------------------------------------------------

    def draw_chart(self, p, x, y, width, head_left, head_right, points, small=False, axis=None,
                   slotted=False):
        '''머리 한 줄 + 막대 + 축. 축 라벨이 막대마다 하나면(slotted) 그 막대 가운데에 둔다.'''
        right_width = p.rich(head_right, x + width, y, SMALL, 'right') if head_right else 0
        p.rich(head_left, x, y, SMALL, limit=width - right_width - 8)
        y += LINE[SMALL] + 4
        y = self.draw_bars(p, x, y, width, points, SMALL_CHART if small else CHART_HEIGHT)
        if axis:
            y += 4
            self.draw_axis(p, x, y, width, axis, slotted)
            y += LINE[TINY]
        return y

    def get_slot(self, x, width, count, index):
        stride = (width + SLOT_GAP) / float(count)
        left = int(round(x + stride * index))
        return left, int(round(x + stride * index + stride - SLOT_GAP)) - left

    def draw_bars(self, p, x, y, width, points, height):
        '''막대 그림 한 장. points = [{value, title, key, now, picked, action}]. 0 에서 자라고,
        음수가 있으면 0 선을 올려 그 아래로 주황. 축은 언제나 0 에서 시작한다 (막대 길이가 곧 값이다).'''
        values = [point['value'] for point in points]
        high, low = max([0] + values), min([0] + values)
        span = float(high - low) or 1.0
        signed_chart = low < 0
        area = height if signed_chart else height - 1
        zero = y + area - round(-low / span * area)
        if signed_chart:
            p.fill('rim', x, zero - 1, width, 1)
        else:
            p.fill('rim', x, y + height - 1, width, 1)
        palette = self.palette
        for index, point in enumerate(points):
            left, slot = self.get_slot(x, width, len(points), index)
            key = point.get('zone') or 'bar:%d' % index
            value = point['value']
            if value:
                size = max(1, round(abs(value) / span * area))
                strong = point.get('now') or point.get('picked')
                if value > 0:
                    colour = palette['series1'] if strong else mix(palette['face'], palette['series1'], 0.55)
                    top = zero - size
                else:
                    colour = palette['series2'] if strong else mix(palette['face'], palette['series2'], 0.70)
                    top = zero
                if p.body.hover == key:
                    colour = shade(colour, 1.2)
                # 끝만 둥글다. 둥근 네모 위에 바닥 쪽을 네모로 덮는다.
                radius = min(2, size / 2.0)
                p.fill(colour, left, top, slot, size, radius)
                if size > radius:
                    if value > 0:
                        p.fill(colour, left, top + radius, slot, size - radius)
                    else:
                        p.fill(colour, left, top, slot, size - radius)
            p.zone(left, y, slot, height, key, point.get('action'), point.get('title'), lit=True)
        return y + height

    def draw_axis(self, p, x, y, width, labels, slotted):
        if slotted:
            for index, label in enumerate(labels):
                if label:
                    left, slot = self.get_slot(x, width, len(labels), index)
                    p.text(label, left + slot / 2.0, y, TINY, 'dim', align='center')
            return
        # 양 끝에 붙이고 사이는 고르게 (웹판의 space-between).
        widths = [p.width(label, TINY) for label in labels]
        gap = (width - sum(widths)) / float(max(1, len(labels) - 1))
        left = x
        for label, label_width in zip(labels, widths):
            p.text(label, left, y, TINY, 'dim')
            left += label_width + gap

    def get_chart_area(self, width):
        inner = width - PAD * 2
        area = min(inner, CHART_MAX)
        return PAD + (inner - area) / 2.0, area

    # 코드 산출 ----------------------------------------------------------

    def draw_code(self, p, width):
        data = self.data
        x, area = self.get_chart_area(width)
        y = PAD
        code = (data or {}).get('code') or {}
        days = sorted(code)
        if not days:
            # 처음 git 을 세는 몇 초 동안은 뼈대를 그대로 둔다. 다 세고도 없을 때만 알린다.
            if data and data.get('repos'):
                return self.draw_empty(p, 'no commits yet', PAD, y, width - PAD * 2) + PAD
            return self.draw_code_skeleton(p, x, y, area) + PAD
        today = data['activity']['today']
        all_time = self.view['codePeriod'] == 'all'
        total = sum_code(code, days if all_time else [today])
        everything = sum_code(code, days)
        net = total['added'] - total['removed']
        cost = data['all']['cost'] if all_time else data['today']['cost']
        per100 = cost / total['added'] * 100 if total['added'] else 0
        average = data['all']['cost'] / everything['added'] * 100 if everything['added'] else 0
        kpis = (('Commits', str(total['commits']),
                 'all time' if all_time else '%d total' % everything['commits']),
                ('Net lines', signed(net), count(total['added'] + total['removed']) + ' lines'),
                ('$/100 added', self.money(per100, 2) if total['added'] else '—',
                 'avg ' + self.money(average, 2)))
        y = self.draw_kpis(p, kpis, x, y, area)

        # 지난 7 일의 하루 순증. 늘면 위로(파랑), 줄면 아래로(주황).
        base = to_date(today)
        week = [(base - datetime.timedelta(days=offset)).isoformat() for offset in range(6, -1, -1)]
        points = []
        for day in week:
            item = code.get(day)
            gain = item['added'] - item['removed'] if item else 0
            points.append({'value': gain, 'now': day == today,
                           'title': '%s  %s net lines' % (short_day(day), signed(gain))})
        week_net = sum(point['value'] for point in points)
        total_net = everything['added'] - everything['removed']
        y += PAD
        y = self.draw_chart(p, x, y, area, [('Net lines · last 7 days', 'dim', False)],
                            [(signed(week_net), 'text', True),
                             (' this week · %s all time' % signed(total_net), 'dim', False)],
                            points, axis=[short_day(day) for day in week], slotted=True)
        y += 6
        p.text('%d repos' % data['repos'], width / 2.0, y, NOTE, 'dim', align='center')
        return y + LINE[NOTE] + PAD

    def draw_kpis(self, p, kpis, x, y, area):
        '''세 칸. 아래 그림과 같은 폭에서 멈추고 가운데에 선다 — 넓은 창에서 셋이 양끝으로
        흩어지지 않게.'''
        column = (area - 16) / 3.0
        for index, (caption, value, note) in enumerate(kpis):
            centre = x + index * (column + 8) + column / 2.0
            p.spaced(caption.upper(), centre, y, TINY, 'dim', True, 1.4, 'center')
            p.text(value, centre, y + LINE[TINY] + 2, VALUE, bold=True, align='center',
                   limit=column)
            p.text(note, centre, y + LINE[TINY] + 2 + LINE[VALUE] + 2, NOTE, 'dim',
                   align='center', limit=column)
        return y + LINE[TINY] + 2 + LINE[VALUE] + 2 + LINE[NOTE]

    def draw_code_skeleton(self, p, x, y, area):
        column = (area - 16) / 3.0
        for index in range(3):
            centre = x + index * (column + 8) + column / 2.0
            for top, ratio, height in ((0, 0.6, 9), (15, 0.4, 16), (37, 0.5, 9)):
                p.fill('grid', centre - column * ratio / 2, y + top, column * ratio, height,
                       PANEL_RADIUS)
        y += 51 + PAD
        p.fill('grid', x, y, area * 0.35, 9, PANEL_RADIUS)
        p.fill('grid', x + area * 0.7, y, area * 0.3, 9, PANEL_RADIUS)
        y += 15
        p.fill('grid', x, y, area, CHART_HEIGHT, PANEL_RADIUS)
        return y + CHART_HEIGHT + 37

    # 추세 ---------------------------------------------------------------

    def seg_items(self, p, name, split=False):
        '''고르기 칸 묶음. split 이면 칸마다 따로 줄을 넘길 수 있게 하나씩 내준다.'''
        cells = []
        for value, label in CHOICES[name]:
            def draw(left, top, value=value, label=label):
                p.button(left, top, label, 'seg:%s:%s' % (name, value),
                         lambda: self.set_view(name, value), lit=self.view[name] == value)
            cells.append((get_button_width(label), draw))
        if split:
            return cells
        total = sum(cell[0] for cell in cells) + BUTTON_GAP * (len(cells) - 1)

        def draw_all(left, top):
            for cell_width, draw in cells:
                draw(left, top)
                left += cell_width + BUTTON_GAP
        return [(total, draw_all)]

    def label_item(self, p, text):
        text = text.upper()
        width = int(math.ceil(p.spaced_width(text, TINY, False, 1)))
        return [(width, lambda left, top: p.spaced(text, left, top, TINY, 'dim', False, 1,
                                                   line=BUTTON_HEIGHT))]

    def get_buckets(self, data):
        grain = self.view['grain']
        buckets = {}

        def slot(key):
            return buckets.setdefault(key, {'key': key, 'cost': 0, 'tokens': 0, 'calls': 0,
                                            'net': 0, 'days': []})
        for day, item in data['daily'].items():
            bucket = slot(bucket_of(day, grain))
            bucket['cost'] += item['cost'] or 0
            bucket['tokens'] += item['tokens'] or 0
            bucket['calls'] += item['calls'] or 0
            bucket['days'].append(day)
        first = min(buckets) if buckets else None
        for day, item in (data.get('code') or {}).items():
            key = bucket_of(day, grain)
            # 쓰기 전의 옛 커밋까지 그리면 그림이 좌우로 갈라진다. 사용 기록이 시작된 뒤만.
            if first and key < first:
                continue
            bucket = slot(key)
            bucket['net'] += item['added'] - item['removed']
            if day not in bucket['days']:
                bucket['days'].append(day)
        return [buckets[key] for key in sorted(buckets)[-GRAIN_COUNT[grain]:]]

    def pick(self, key):
        self.view['picked'] = None if self.view['picked'] == key else key
        self.refresh_bodies(('trend',))

    def draw_trend(self, p, width):
        data = self.data
        inner = width - PAD * 2
        y = PAD
        items = (self.label_item(p, 'Metric') + self.seg_items(p, 'metric') +
                 self.label_item(p, 'Range') + self.seg_items(p, 'grain'))
        y = flow(items, PAD, y, inner, 8, BUTTON_GAP, BUTTON_HEIGHT) + PAD
        x, area = self.get_chart_area(width)
        if data is None:
            p.fill('grid', x, y, area * 0.4, 9, PANEL_RADIUS)
            y += 14
            p.fill('grid', x, y, area, CHART_HEIGHT, PANEL_RADIUS)
            y += CHART_HEIGHT + PAD
            p.fill('grid', x, y, area * 0.35, 9, PANEL_RADIUS)
            y += 14
            p.fill('grid', x, y, area, SMALL_CHART, PANEL_RADIUS)
            return y + SMALL_CHART + 24 + PAD
        points = self.get_buckets(data)
        if not points:
            return self.draw_empty(p, 'No trend data yet', PAD, y, inner) + PAD
        metric = self.view['metric']
        grain = self.view['grain']

        def fmt(value, digits=0):
            return self.money(value, digits) if metric == 'cost' else count(value)
        last = points[-1]
        current = bucket_of(data['activity']['today'], grain)
        peak = max(point[metric] for point in points)

        def slots(name, value):
            return [{'value': value(point), 'now': point['key'] == current,
                     'picked': point['key'] == self.view['picked'],
                     'zone': '%s:%s' % (name, point['key']),
                     'action': lambda key=point['key']: self.pick(key),
                     'title': '%s  %s  %d requests  %s net lines' % (
                         bucket_label(point['key'], grain), fmt(point[metric], 2), point['calls'],
                         signed(point['net']))} for point in points]
        # 돈(또는 토큰)과 순증 줄은 단위가 달라 한 축에 겹치지 않는다. 날짜 축을 맞춘 두 장.
        y = self.draw_chart(p, x, y, area,
                            [('%s · peak %s' % ('Cost' if metric == 'cost' else 'Tokens',
                                                fmt(peak)), 'dim', False)],
                            [('now ', 'dim', False), (fmt(last[metric]), 'text', True)],
                            slots('metric', lambda point: point[metric]))
        y += PAD
        y = self.draw_chart(p, x, y, area, [('Net lines committed', 'dim', False)],
                            [('now ', 'dim', False), (signed(last['net']), 'text', True)],
                            slots('net', lambda point: point['net']), small=True,
                            axis=[bucket_label(points[0]['key'], grain),
                                  bucket_label(last['key'], grain)])
        bucket = next((point for point in points if point['key'] == self.view['picked']), None)
        if bucket:
            y = self.draw_breakdown(p, data, bucket, PAD, y, inner)
        return y + PAD

    def draw_heading(self, p, left, right, x, y, width, first=False):
        '''내역의 소제목 한 줄. 오른쪽은 흐린 설명.'''
        if not first:
            y += 10
        right_width = p.text(right, x + width, y, NOTE, 'dim', align='right')
        p.text(left, x, y, NOTE, bold=True, limit=width - right_width - 8)
        return y + LINE[NOTE] + 6

    def draw_meters(self, p, rows, top, formatter, x, y, width):
        '''이름 92px | 막대 | 값. 줄마다 값 폭만큼 막대가 줄어든다 (웹판의 grid auto 칸).'''
        for row in rows:
            y += 4
            value = formatter(row)
            value_width = p.text(value, x + width, y, NOTE, 'dim', align='right')
            p.text(row[0], x, y, NOTE, limit=92)
            left = x + 92 + 8
            p.track(left, y + (LINE[NOTE] - BAR_HEIGHT) // 2,
                    max(0, x + width - value_width - 8 - left), row[1] / float(top) if top else 0)
            y += LINE[NOTE]
        return y

    def draw_breakdown(self, p, data, bucket, x, y, width):
        '''고른 칸의 내역.'''
        panorama = [0, 0, 0, 0, 0]
        tools = {}
        for day in bucket['days']:
            item = data['daily'].get(day)
            if not item:
                continue
            for index, value in enumerate(item['panorama']):
                panorama[index] += value or 0
            for name, (calls, tokens) in item['tools'].items():
                slot = tools.setdefault(name, [0, 0])
                slot[0] += calls
                slot[1] += tokens
        code = sum_code(data.get('code') or {}, bucket['days'])
        token_rows = [('Input', panorama[0]), ('Output', panorama[1]), ('Cache read', panorama[2]),
                      ('Cache write', panorama[3]), ('Thinking', panorama[4])]
        tool_rows = sorted(([TOOL_NAMES.get(name, name), value[0], value[1]]
                            for name, value in tools.items()), key=lambda row: -row[1])
        path_rows = sorted(([PATH_NAMES.get(name, name), added - removed]
                            for name, (added, removed) in code['paths'].items()),
                           key=lambda row: -abs(row[1]))

        y += PAD
        p.fill('rim', x, y, width, 1)
        y += 1 + PAD
        grain = self.view['grain']
        y = self.draw_heading(p, ('Week ' if grain == 'week' else '') + bucket_label(bucket['key'], grain),
                              '%s · %d requests' % (self.money(bucket['cost'], 2), bucket['calls']),
                              x, y, width, first=True)
        y = self.draw_heading(p, 'Token panorama', 'input + output · cache', x, y, width)
        y = self.draw_meters(p, token_rows, max(row[1] for row in token_rows),
                             lambda row: count(row[1]), x, y, width)
        y = self.draw_heading(p, 'Tool usage', 'calls · ≈tok', x, y, width)
        if tool_rows:
            y = self.draw_meters(p, tool_rows, tool_rows[0][1],
                                 lambda row: '%d · ≈%s' % (row[1], count(row[2])), x, y, width)
        else:
            y = self.draw_empty(p, 'No tool data', x, y, width)
        y = self.draw_heading(p, 'Net lines committed', '%s added / %s removed' % (
            count(code['added']), count(code['removed'])), x, y, width)
        if path_rows:
            top = max(abs(row[1]) for row in path_rows)
            y = self.draw_meters(p, [(row[0], abs(row[1]), row[1]) for row in path_rows], top,
                                 lambda row: signed(row[2]), x, y, width)
        else:
            y = self.draw_empty(p, 'No commits for this period', x, y, width)
        return y

    # 세션 ---------------------------------------------------------------

    def draw_sessions(self, p, width):
        data = self.data
        x, inner, y = PAD, width - PAD * 2, PAD
        if data is None:
            p.fill('grid', x, y + 4, inner * 0.45, 9, PANEL_RADIUS)
            p.fill('grid', x + inner * 0.85, y + 4, inner * 0.15, 9, PANEL_RADIUS)
            y += 17 + 6
            for ratio, height in ((0.7, 9), (1.0, BAR_HEIGHT), (0.4, 9)):
                p.fill('grid', x, y, inner * ratio, height, PANEL_RADIUS)
                y += height + 6
            y += 42
            p.fill('grid', x, y, inner * 0.35, 9, PANEL_RADIUS)
            return y + 9 + PAD
        view = self.view
        hidden = data.get('hidden') or []
        rows = [item for item in data['sessions'] if view['showHidden'] or item['project'] not in hidden]
        live = [item for item in rows if item['state'] != 'idle']
        idle = len(rows) - len(live)
        if view['sessionFilter'] == 'active':
            rows = live
        elif not view['showIdle']:
            # 일 없는 세션은 접어 둔다. 살아 있는 것이 하나도 없으면 최근 것을 보인다.
            rows = live or rows
        shown = rows if view['showAll'] else rows[:SESSION_LIMIT]
        if not shown:
            y = self.draw_empty(p, 'No active sessions', x, y, inner)
        for index, item in enumerate(shown):
            if index:
                p.fill('grid', x, y, inner, 1)
                y += 1 + 8
            y = self.draw_session(p, item, hidden, x, y, inner) + 8

        foot = []
        if len(rows) > SESSION_LIMIT:
            foot.append(('more', 'Show less' if view['showAll'] else
                         'Show %d more' % (len(rows) - SESSION_LIMIT),
                         lambda: self.toggle_flag('showAll')))
        if view['sessionFilter'] == 'all' and idle and live:
            foot.append(('idle', '%s %d idle session%s' % ('Hide' if view['showIdle'] else 'Show',
                                                          idle, '' if idle == 1 else 's'),
                         lambda: self.toggle_flag('showIdle')))
        if hidden:
            foot.append(('hidden', '%d hidden project%s · %s' % (
                len(hidden), '' if len(hidden) == 1 else 's',
                'hide' if view['showHidden'] else 'show'), lambda: self.toggle_flag('showHidden')))
        if foot:
            items = [(p.width(text, NOTE), lambda left, top, key=key, text=text, action=action:
                      p.link(text, left, top, 'foot:' + key, action)) for key, text, action in foot]
            y = flow(items, x, y + 8, inner, 14, 4, LINE[NOTE], center=False)
        return y + PAD

    def toggle_flag(self, name):
        self.view[name] = not self.view[name]
        self.refresh_bodies(('sessions',))

    def toggle_session(self, key):
        self.view['openSession'] = None if self.view['openSession'] == key else key
        self.refresh_bodies(('sessions',))

    def draw_session(self, p, item, hidden, x, y, width):
        context_max = item.get('contextMax') or 0
        pct = min(100.0, item['context'] / float(context_max) * 100) if context_max else 0
        key = '%s:%s' % (item['provider'], item['session'])
        is_open = self.view['openSession'] == key

        # 머리 줄: 도구 · 프로젝트 · 상태 · 지난 시각
        base = p.baseline(MAIN, y, LINE[MAIN], True)
        right = x + width - p.text_on(ago(item['last']), x + width, base, NOTE, 'dim', align='right') - 6
        left = x + p.provider(item['provider'], x, base) + 6
        state = item['state']
        # 테두리 1 + 옆 여백 6 (웹판의 .chip).
        chip_width = p.width(state, SMALL, state == 'active') + 14
        chip_height = LINE[SMALL] + 4
        project = p.fit(item['project'] or '(no folder)', MAIN, True, max(0, right - left - 6 - chip_width))
        left += p.text_on(project, left, base, MAIN, bold=True) + 6
        # 상태는 색만으로 말하지 않는다. 글자와 테두리 굵기도 다르다.
        tone = {'active': 'accent', 'waiting': 'warn'}.get(state, 'edge')
        chip_top = y + (LINE[MAIN] - chip_height) // 2
        p.rim(tone, left, chip_top, chip_width, chip_height)
        p.text(state, left + 7, chip_top + 2, SMALL, tone if state != 'idle' else 'dim',
               state == 'active')
        y += LINE[MAIN]

        meta = [item.get('model'), item.get('source'),
                count(item['tokens']) + ' tok' if item.get('tokens') else None,
                self.money(item['cost'], 2) if item.get('cost') else None,
                '%d %s' % (item['calls'], 'steps' if item['provider'] == 'antigravity' else 'calls')]
        items = [(p.width(text, NOTE), lambda left, top, text=text: p.text(text, left, top, NOTE, 'dim'))
                 for text in meta if text]
        y = flow(items, x, y + 3, width, 10, 2, LINE[NOTE], center=False)

        if context_max:
            y += 5
            near = 'at limit' if pct >= 95 else 'compact soon' if pct >= 85 else \
                'near limit' if pct >= 70 else ''
            text = 'Context %d%% · %s' % (js_round(pct), near or
                                          count(context_max - item['context']) + ' left')
            text_width = p.text(text, x + width, y, NOTE, 'dim', align='right')
            colour = 'close' if pct >= 95 else 'warn' if pct >= 70 else 'accent'
            p.track(x, y + (LINE[NOTE] - BAR_HEIGHT) // 2, max(0, width - text_width - 8),
                    pct / 100.0, colour)
            y += LINE[NOTE]

        if is_open:
            y += 6
            p.fill('rim', x, y, width, 1)
            y += 1 + 6
            tools = sorted(([TOOL_NAMES.get(name, name), value]
                            for name, value in (item.get('tools') or {}).items()),
                           key=lambda row: -row[1])
            total = sum(row[1] for row in tools)
            if tools:
                y = self.draw_meters(p, tools, tools[0][1],
                                     lambda row: '%d%%' % js_round(row[1] / float(total) * 100),
                                     x, y, width)
            else:
                y = self.draw_empty(p, 'No tool data', x, y, width)

        y += 4
        left = x
        if item['provider'] != 'antigravity':
            left += p.link('Hide breakdown' if is_open else 'Show breakdown', left, y,
                           'open:' + key, lambda: self.toggle_session(key)) + 10
        project = item.get('project')
        if project:
            command = 'unhide' if project in hidden else 'hide'
            left += p.link(command.capitalize(), left, y, '%s:%s' % (command, key),
                           lambda: self.toggle_project(command, project)) + 10
            p.link('Exclude', left, y, 'exclude:' + key,
                   lambda: self.toggle_project('exclude', project))
        return y + LINE[NOTE]

    # 활동 ---------------------------------------------------------------

    def draw_activity(self, p, width):
        data = self.data
        y = flow(self.seg_items(p, 'activity', split=True), PAD, PAD, width - PAD * 2,
                 BUTTON_GAP, BUTTON_GAP, BUTTON_HEIGHT) + PAD
        x, area = self.get_chart_area(width)
        if data is None:
            p.fill('grid', x, y, area, 110, PANEL_RADIUS)
            y += 110 + 8
            p.fill('grid', x + area * 0.7, y, area * 0.3, 9, PANEL_RADIUS)
            return y + 9 + PAD
        draw = {'week': self.draw_week_heat, 'calendar': self.draw_calendar,
                'hourly': self.draw_hourly, 'weekly': self.draw_weekly,
                'tod': self.draw_time_of_day}.get(self.view['activity'], self.draw_week_heat)
        return draw(p, data['activity'], x, y, area) + PAD

    def get_shade(self, level):
        palette = self.palette
        if not level:
            return mix(palette['face'], palette['grid'], 0.3)
        return mix(palette['grid'], palette['accent'], level / float(LEVELS))

    def draw_legend(self, p, right, y):
        less, more = p.width('less', TINY), p.width('more', TINY)
        total = less + 6 + (LEVELS + 1) * 8 + LEVELS * 3 + 6 + more
        left = right - total
        p.text('less', left, y, TINY, 'dim')
        left += less + 6
        for level in range(LEVELS + 1):
            p.fill(self.get_shade(level), left, y + (LINE[TINY] - 8) // 2, 8, 8, 1.5)
            left += 8 + 3
        p.text('more', left - 3 + 6, y, TINY, 'dim')
        return y + LINE[TINY]

    def draw_cell(self, p, colour, left, top, size, key, tip):
        x0, y0 = int(round(left)), int(round(top))
        cell = int(round(left + size)) - x0
        p.fill(colour, x0, y0, cell, int(round(top + size)) - y0, 1.5)
        p.zone(x0, y0, cell, cell, key, tip=tip)

    def draw_week_heat(self, p, activity, x, y, area):
        '''날짜 × 시각. 칸은 12px 에서 멈추고 자리가 모자라면 그만큼 줄어든다.'''
        peak = max([1] + [value for row in activity['heat'] for value in row])
        label = max(p.width(short_day(day), TINY) for day in activity['days'])
        cells = min(area - label - 6, 24 * CELL_MAX + 23 * CELL_GAP)
        size = (cells - 23 * CELL_GAP) / 24.0
        box = label + 6 + cells
        left = x + (area - box) / 2.0
        grid = left + label + 6
        for hour in range(0, 24, 6):
            p.text(str(hour), grid + hour * (size + CELL_GAP), y, TINY, 'dim', line=9)
        y += 9 + CELL_GAP
        for row, day in enumerate(activity['days']):
            p.text(short_day(day), left, y, TINY, 'dim', line=size)
            for hour, value in enumerate(activity['heat'][row]):
                self.draw_cell(p, self.get_shade(get_level(value, peak)),
                               grid + hour * (size + CELL_GAP), y, size, 'heat:%d:%d' % (row, hour),
                               '%s %d:00  %s tok' % (short_day(day), hour, count(value)))
            y += size + CELL_GAP
        return self.draw_legend(p, left + box, y - CELL_GAP + 8)

    def draw_calendar(self, p, activity, x, y, area):
        days = activity['calendar']
        peak = max([1] + [value for _, value in days])
        # 일요일에서 시작하는 주. 첫 날 앞은 비워 둔다.
        first = (to_date(days[0][0]).weekday() + 1) % 7
        columns = int(math.ceil((first + len(days)) / 7.0))
        size = min(CELL_MAX, (area - CELL_GAP * (columns - 1)) / float(columns))
        box = columns * size + (columns - 1) * CELL_GAP
        left = x + (area - box) / 2.0
        for index, (day, value) in enumerate(days):
            column, row = divmod(first + index, 7)
            self.draw_cell(p, self.get_shade(get_level(value, peak)),
                           left + column * (size + CELL_GAP), y + row * (size + CELL_GAP), size,
                           'day:' + day, '%s  %s tok' % (day, count(value)))
        y += 7 * size + 6 * CELL_GAP
        y = self.draw_legend(p, left + box, y + 8)
        return self.draw_caption_row(p, '5mo activity', count(sum(value for _, value in days)) +
                                     ' tok', left, y, box)

    def draw_caption_row(self, p, left_text, right_text, x, y, width):
        y += 8
        right_width = p.text(right_text, x + width, y, NOTE, 'dim', align='right')
        p.text(left_text, x, y, NOTE, 'dim', limit=width - right_width - 8)
        return y + LINE[NOTE]

    def draw_hourly(self, p, activity, x, y, area):
        values = [hour[0] for hour in activity['hourly']]
        peak = max(values)
        peak_hour = values.index(peak)
        points = [{'value': value, 'now': hour == peak_hour,
                   'title': '%d:00  %s tok  %s' % (hour, count(value),
                                                   self.money(activity['hourly'][hour][1], 2))}
                  for hour, value in enumerate(values)]
        return self.draw_chart(p, x, y, area, [('Hourly · last 30 days', 'dim', False)],
                               [('peak ', 'dim', False), ('%d:00' % peak_hour, 'text', True)],
                               points, axis=[str(hour) if hour in (0, 6, 12, 18, 23) else ''
                                             for hour in range(24)], slotted=True)

    def draw_weekly(self, p, activity, x, y, area):
        weeks = activity['weeks']
        peak = max(week['tokens'] for week in weeks) or 1
        for index, week in enumerate(weeks):
            current = index == len(weeks) - 1
            y += 6
            p.text('current' if current else '%dw ago' % (len(weeks) - 1 - index), x, y, NOTE,
                   'dim', limit=70)
            p.text('%s · %s' % (count(week['tokens']), self.money(week['cost'])), x + area, y,
                   NOTE, align='right', limit=90)
            p.track(x + 78, y + (LINE[NOTE] - BAR_HEIGHT) // 2, max(0, area - 78 - 98),
                    week['tokens'] / float(peak), 'accent' if current else 'soft')
            y += LINE[NOTE]
        return self.draw_caption_row(p, '4-week total', count(sum(week['tokens'] for week in weeks))
                                     + ' tok', x, y, area)

    def draw_time_of_day(self, p, activity, x, y, area):
        parts = (('Night', 0, 6), ('Morning', 6, 12), ('Afternoon', 12, 18), ('Evening', 18, 24))
        rows = []
        for name, start, end in parts:
            total = [0, 0.0, 0]
            for hour in range(start, end):
                for index in range(3):
                    total[index] += activity['hourly'][hour][index]
            rows.append(('%s (%d–%d)' % (name, start, end), total))
        total_cost = sum(row[1][1] for row in rows)
        peak = max(rows, key=lambda row: row[1][0])
        cells = [[count(row[1][0]), self.money(row[1][1]), count(row[1][2]),
                  '%d%%' % (js_round(row[1][1] / total_cost * 100) if total_cost else 0)]
                 for row in rows]
        heads = ('Tokens', 'Cost', 'Requests', '%')
        # 이름 칸이 남는 폭을 다 쓰고, 숫자 네 칸은 가장 긴 값만큼씩 오른쪽 맞춤으로.
        widths = [max([p.width(heads[index], SMALL)] + [p.width(row[index], NOTE) for row in cells])
                  for index in range(4)]
        gap = max(8, (area - max(p.width(row[0], NOTE, True) for row in rows) - sum(widths)) / 4.0)
        rights, right = [], x + area
        for width in reversed(widths):
            rights.insert(0, right)
            right -= width + gap
        y += 3
        for index, head in enumerate(heads):
            p.text(head, rights[index], y, SMALL, 'dim', align='right')
        y += LINE[SMALL] + 3
        for row, values in zip(rows, cells):
            p.fill('grid', x, y, area, 1)
            y += 1 + 4
            is_peak = row is peak
            p.text(row[0], x, y, NOTE, 'accent' if is_peak else 'text', is_peak,
                   limit=rights[0] - widths[0] - gap - x)
            for index, value in enumerate(values):
                p.text(value, rights[index], y, NOTE, align='right')
            y += LINE[NOTE] + 4
        return self.draw_caption_row(p, 'Peak: ' + peak[0], '30d · %s total' % self.money(total_cost),
                                     x, y, area)

    # 모델 ---------------------------------------------------------------

    def draw_models(self, p, width):
        data = self.data
        x, inner, y = PAD, width - PAD * 2, PAD
        if data is None:
            return self.draw_skeleton_rows(p, x, y, inner, 5, 0.4, 0.28, 12) + PAD
        models = data['models']
        if not models:
            return self.draw_empty(p, 'No data', x, y, inner) + PAD
        total = sum(model['cost'] for model in models) or 1
        for index, model in enumerate(models):
            if index:
                y += 8
            base = p.baseline(BODY, y, LINE[BODY])
            note = ' %d%% · %s tok' % (js_round(model['cost'] / total * 100), count(model['tokens']))
            right = x + inner - p.text_on(note, x + inner, base, NOTE, 'dim', align='right')
            right -= p.text_on(self.money(model['cost']), right, base, BODY, align='right')
            tag = 0
            if model.get('provider'):
                tag = 4 + 11 + p.spaced_width(AGENT_NAMES.get(model['provider'], model['provider']),
                                             SMALL, True, 0.4)
            name_width = p.text_on(model['model'], x, base, BODY,
                                   limit=right - 8 - x - tag)
            if model.get('provider'):
                p.provider(model['provider'], x + name_width + 4, base, upper=False)
            y += LINE[BODY] + 2
            p.track(x, y, inner, model['cost'] / total)
            y += BAR_HEIGHT
        return y + PAD

    # 모으기 -------------------------------------------------------------

    def set_options(self, **options):
        '''설정 페이지에서 오는 값(도구·통화·묶음 순서). 값이 바뀌는 것만 다시 모은다.'''
        if 'agents' in options:
            enabled = options['agents']
            options['agents'] = tuple(name for name in usageindex.AGENTS if enabled.get(name))
        changed = any(key in DATA_OPTIONS and self.options.get(key) != value
                      for key, value in options.items())
        layout = any(key in ('sections', 'wide') and self.options.get(key) != value
                     for key, value in options.items())
        self.options.update(options)
        if layout:
            self.wide_columns = self.options['wide'] is not False
            self.apply_sections()
        if changed and self.ready:
            self.reload(force=True)

    def get_options(self):
        return {'hidden_projects': self.options['hidden'],
                'excluded_projects': self.options['excluded'],
                'usage_folded_sections': sorted(self.folded),
                'usage_view': {key: self.view[key] for key in VIEW_DEFAULTS}}

    def sign_in(self):
        '''Claude 토큰 갱신. 조용한 갱신이 길면 수십 초라 실에서 돌린다.'''
        self.set_login_state('working')
        self.refreshing = True

        def run():
            result = claudelogin.sign_in()
            wx.CallAfter(self.after_sign_in, result)
        threading.Thread(target=run, daemon=True).start()

    def after_sign_in(self, result):
        self.refreshing = False
        self.set_login_state(result)
        if result == 'refreshed':
            self.reload(force=True)
        elif result == 'login':
            # 사람이 터미널에서 로그인을 마칠 때까지 기다린다. 새 토큰이 보이면 바로 다시 묻는다.
            # 서버가 401 로 거절한 토큰은 만료 시각이 아직 남아 있을 수 있다. 시각이 바뀐 것만 새 토큰이다.
            self.login_since = time.time()
            self.login_before = claudelogin.read_expiry()
            self.login_timer = wx.CallLater(LOGIN_POLL_MS, self.watch_login)

    def watch_login(self):
        expiry = claudelogin.read_expiry()
        if expiry and expiry != self.login_before and expiry > time.time():
            self.set_login_state('refreshed')
            self.reload(force=True)
            return
        if time.time() - self.login_since < LOGIN_POLL_LIMIT:
            self.login_timer = wx.CallLater(LOGIN_POLL_MS, self.watch_login)

    def toggle_project(self, command, project):
        '''Hide 는 세션 목록에서만 감추고, Exclude 는 모든 숫자에서 뺀다.'''
        key = 'excluded' if command == 'exclude' else 'hidden'
        values = [value for value in self.options[key] if value != project]
        if command != 'unhide':
            values.append(project)
        self.set_project_list(key, values)

    def set_project_list(self, key, values):
        self.options[key] = list(values)
        if self.on_options:
            self.on_options()
        self.reload(force=True)

    def reload(self, force=False, git=False):
        if self.loading:
            # 모으는 중에 무언가 바뀌면 끝난 뒤 한 번 더 모은다.
            self.pending = self.pending or force
            return
        self.loading = True
        self.pending = False
        self.last_run = time.time()
        git = git or time.time() - self.last_git > GIT_REFRESH
        if git:
            self.last_git = time.time()
        options = dict(self.options)
        threading.Thread(target=self.gather, args=(options, git, force), daemon=True).start()

    def gather(self, options, git, force):
        try:
            self.index.update(lambda value: wx.CallAfter(self.set_progress, value))
            wx.CallAfter(self.set_progress, None)
            data = dashboard.build(self.index, options, fresh_limits=force)
            wx.CallAfter(self.deliver, data)
            if git:
                data = dashboard.build(self.index, options, refresh_git=True)
                wx.CallAfter(self.deliver, data)
        except Exception:
            traceback.print_exc()
        # 화면을 건드리는 것은 주 실에서만.
        wx.CallAfter(self.settle)

    def count_orphans(self, callback):
        '''지워진 기록 파일에서 와서 이제 색인에만 남은 요청 수와 금액. UNC 경로의
        존재 확인이 느려 실에서 센다.'''
        def run():
            requests, cost = 0, 0.0
            try:
                rows = self.index.query('SELECT file, COUNT(*), SUM(cost) FROM entries GROUP BY file')
                for path, number, total in rows:
                    if not os.path.exists(path):
                        requests += number
                        cost += total or 0
            except Exception:
                traceback.print_exc()
            wx.CallAfter(callback, requests, cost)
        threading.Thread(target=run, daemon=True).start()

    def reset_index(self):
        '''색인을 지우고 처음부터 다시 만든다. 모으는 중이면 끝난 뒤에.'''
        def run():
            with self.index.lock:
                for suffix in ('', '-wal', '-shm'):
                    try:
                        os.remove(self.index.path + suffix)
                    except OSError:
                        pass
            wx.CallAfter(self.reload, True, True)
        threading.Thread(target=run, daemon=True).start()

    def settle(self):
        self.loading = False
        # 읽다 실패해 값이 안 왔어도 단추는 다시 누를 수 있어야 한다.
        self.refresh_band.set_enabled(True)
        # 미뤄 둔 것은 force 로 부른 것뿐이다. 그대로 force 로 돌려야 한도를 다시 묻는다 —
        # 안 그러면 로그인 직후의 새 토큰이 5 분 캐시(CLAUDE_LIMITS_TTL) 뒤에 묻힌다.
        if self.pending:
            self.reload(force=True)

    def tick(self):
        # 안 보여도 다시 읽는다. 떠 있는 위젯이 이 값을 쓴다.
        if self.ready and time.time() - self.last_run > AUTO_REFRESH:
            self.reload()
        if self.data and time.time() - self.last_clock > CLOCK_REFRESH:
            self.last_clock = time.time()
            if self.refresh_band.enabled:
                self.refresh_band.set_subtitle('last run · ' + ago(self.data['updated'] * 1000))
            self.refresh_bodies(('planUsage',))
        self.keep_signed_in()

    def keep_signed_in(self):
        '''Claude 토큰(수명 8 시간)이 곧 만료되면 조용히 갱신한다. 터미널 로그인은 띄우지 않는다 —
        그건 사람이 Sign in 을 눌렀을 때만. 갱신 한 번마다 아주 작은 요청 하나가 사용량에 잡힌다.'''
        now = time.time()
        if not self.ready or self.refreshing or 'claude' not in self.options['agents']:
            return
        if now - self.last_expiry_check < EXPIRY_CHECK:
            return
        self.last_expiry_check = now
        expiry = claudelogin.read_expiry()
        if expiry is None or expiry > now + claudelogin.REFRESH_SKEW:
            return
        if now - self.last_refresh_try < AUTO_REFRESH_RETRY:
            return
        self.refreshing = True
        self.last_refresh_try = now

        def run():
            refreshed = False
            try:
                if self.take_refresh_slot(now):
                    claude = claudelogin.find_claude()
                    refreshed = bool(claude) and claudelogin.refresh(claude)
            except Exception:
                traceback.print_exc()
            wx.CallAfter(self.after_auto_refresh, refreshed)
        threading.Thread(target=run, daemon=True).start()

    def take_refresh_slot(self, now):
        '''24 시간 상한 안이면 이번 시도를 적고 참. 실에서 부른다(색인 쓰기가 기다릴 수 있다).'''
        recent = [stamp for stamp in (self.index.get_meta(AUTO_REFRESH_KEY) or [])
                  if now - stamp < 86400]
        if len(recent) >= AUTO_REFRESH_DAILY_CAP:
            return False
        self.index.set_meta(AUTO_REFRESH_KEY, recent + [now])
        return True

    def after_auto_refresh(self, refreshed):
        self.refreshing = False
        if refreshed:
            self.reload(force=True)
