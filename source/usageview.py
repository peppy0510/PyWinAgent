# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

사용량 페이지의 웹뷰 판. 같은 값을 `usagebox` 는 캔버스에 손으로 그리고 여기는
HTML 에 맡긴다. mainapp 의 import 한 줄로 갈아 끼운다 (honeypot 의
wxmain/wvmain/wemain 과 같은 짜임새).

Edge(Chromium) 백엔드를 쓴다. honeypot 의 `wxmain.py` 는 IE 에뮬레이션을 켜지만
이 PC 에는 WebView2 런타임이 있어 그럴 이유가 없다.

값은 `usageindex` 가 색인한 기록에서 `dashboard` 가 뽑는다. 모으는 일은 두
번에 나눈다 — 색인과 저장해 둔 git 통계로 먼저 그리고, git 을 다시 센 뒤에
한 번 더 그린다. git 은 저장소마다 몇 초씩 걸린다.
'''


import base64
import json
import os
import threading
import time
import traceback
import wx
import wx.html2

import claudelogin
import dashboard
import usageindex
import utilities

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


PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'usage.htm')
BRAND_ICONS = ('claude', 'codex-dark', 'codex-light')

# 페이지가 CSS 변수로 받는 색. 테마가 바뀌면 이만큼만 다시 넘긴다.
TINTS = ('bg', 'face', 'rim', 'text', 'dim', 'accent', 'mint', 'grid', 'warn', 'close')

# 페이지가 보이는 동안 이 간격으로 다시 읽는다. 색인 덕에 새 줄만 읽는다.
AUTO_REFRESH = 60
# git 은 비싸다. 이보다 자주 다시 세지 않는다 (Reload 를 누르면 바로 센다).
GIT_REFRESH = 10 * 60


def get_backend():
    edge = getattr(wx.html2, 'WebViewBackendEdge', None)
    if edge and wx.html2.WebView.IsBackendAvailable(edge):
        return edge
    return wx.html2.WebViewBackendDefault


def get_brand_sources():
    '''묶음 머리에 쓰는 도구 아이콘. 각 앱 설치 패키지의 Square44x44Logo(64px) 를 옮겨 둔 것.'''
    sources = {}
    for name in BRAND_ICONS:
        try:
            with open(utilities.get_asset_path('brand', name + '.png'), 'rb') as file:
                sources[name] = 'data:image/png;base64,' + base64.b64encode(file.read()).decode('ascii')
        except OSError:
            pass
    return sources


class UsageView(wx.Panel):

    def __init__(self, parent, theme, settings=None, on_options=None):
        super().__init__(parent, style=wx.BORDER_NONE)
        settings = settings or {}
        self.theme = theme
        self.loading = False
        self.pending = False
        self.ready = False
        self.refreshing = False
        self.last_refresh_try = 0
        self.last_expiry_check = 0
        self.last_run = 0
        self.last_git = 0
        self.on_options = on_options
        # 모을 때마다 같은 값을 받는 쪽 (트레이·위젯·알림). mainapp 이 건다.
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
        self.SetBackgroundColour(wx.Colour(theme['bg']))

        # ★테두리를 끄지 않으면 컨트롤 둘레에 회색+흰색 1px 이 둘러 나온다.
        # 캔버스 페이지엔 없는 자국이라 창이 유리에 끼운 것처럼 보인다.
        self.view = wx.html2.WebView.New(self, backend=get_backend(),
                                         style=wx.BORDER_NONE)
        self.view.EnableContextMenu(False)
        # ★핸들러는 SetPage 보다 먼저 걸어야 한다. 나중에 걸면 페이지가 뜨면서
        # 보내는 첫 메시지를 통째로 놓친다.
        self.view.AddScriptMessageHandler('bridge')
        self.view.Bind(wx.html2.EVT_WEBVIEW_SCRIPT_MESSAGE_RECEIVED, self.on_message)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.load_page()

    def load_page(self):
        try:
            with open(PAGE, encoding='utf-8') as file:
                page = file.read()
            # SetPage 로 띄운 페이지는 기준 경로가 없어 상대 경로 그림을 못 읽는다. 바로 싣는다.
            page = page.replace('var BRAND_SRC = {};', 'var BRAND_SRC = %s;' % json.dumps(get_brand_sources()), 1)
            self.view.SetPage(page, '')
        except OSError:
            self.view.SetPage('<body>usage.htm is missing</body>', '')

    def on_size(self, event):
        self.view.SetSize(0, 0, *self.GetClientSize())
        event.Skip()

    def call(self, name, value):
        self.view.RunScriptAsync('%s(%s)' % (name, json.dumps(value)))

    def apply_theme(self, theme):
        self.theme = theme
        self.SetBackgroundColour(wx.Colour(theme['bg']))
        if self.ready:
            self.push_theme()

    def push_theme(self):
        tints = {key: self.theme[key] for key in TINTS}
        tints['dark'] = self.theme['titlebar_dark']
        self.call('setTheme', tints)

    def set_options(self, **options):
        '''설정 페이지에서 오는 값(도구·통화·묶음 순서). 바뀌었을 때만 다시 모은다.'''
        if 'agents' in options:
            enabled = options['agents']
            options['agents'] = tuple(name for name in usageindex.AGENTS if enabled.get(name))
        changed = any(self.options.get(key) != value for key, value in options.items())
        self.options.update(options)
        if changed and self.ready:
            self.reload(force=True)

    def get_options(self):
        return {'hidden_projects': self.options['hidden'],
                'excluded_projects': self.options['excluded']}

    def on_message(self, event):
        message = event.GetString()
        command, _, argument = message.partition(':')
        if message == 'ready':
            self.ready = True
            self.push_theme()
            self.reload(git=True)
        elif message == 'reload':
            self.reload(force=True, git=True)
        elif command in ('hide', 'unhide', 'exclude') and argument:
            self.toggle_project(command, argument)
        elif command == 'claude-login':
            self.sign_in()

    def sign_in(self):
        '''Claude 토큰 갱신. 조용한 갱신이 길면 수십 초라 실에서 돌린다.'''
        self.call('setLoginState', 'working')
        self.refreshing = True

        def run():
            result = claudelogin.sign_in()
            wx.CallAfter(self.after_sign_in, result)
        threading.Thread(target=run, daemon=True).start()

    def after_sign_in(self, result):
        self.refreshing = False
        self.call('setLoginState', result)
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
            self.call('setLoginState', 'refreshed')
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
            self.index.update(lambda value: wx.CallAfter(self.call, 'setProgress', value))
            wx.CallAfter(self.call, 'setProgress', None)
            data = dashboard.build(self.index, options, fresh_limits=force)
            wx.CallAfter(self.deliver, data)
            if git:
                data = dashboard.build(self.index, options, refresh_git=True)
                wx.CallAfter(self.deliver, data)
        except Exception:
            traceback.print_exc()
        # 페이지를 건드리는 것은 주 실에서만.
        wx.CallAfter(self.settle)

    def deliver(self, data):
        self.call('render', data)
        if self.on_data:
            self.on_data(data)

    def count_orphans(self, callback):
        '''지워진 기록 파일에서 와서 이제 색인에만 남은 요청 수와 금액. UNC 경로의
        존재 확인이 느려 실에서 센다.'''
        def run():
            requests, cost = 0, 0.0
            try:
                rows = self.index.query('SELECT file, COUNT(*), SUM(cost) FROM entries GROUP BY file')
                for path, count, total in rows:
                    if not os.path.exists(path):
                        requests += count
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
        # 미뤄 둔 것은 force 로 부른 것뿐이다. 그대로 force 로 돌려야 한도를 다시 묻는다 —
        # 안 그러면 로그인 직후의 새 토큰이 5 분 캐시(CLAUDE_LIMITS_TTL) 뒤에 묻힌다.
        if self.pending:
            self.reload(force=True)

    def tick(self):
        # 안 보여도 다시 읽는다. 트레이·위젯·알림이 이 값을 쓴다.
        if self.ready and time.time() - self.last_run > AUTO_REFRESH:
            self.reload()
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
