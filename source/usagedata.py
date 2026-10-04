# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

사용량 숫자를 모은다. 돈과 토큰은 ccusage 에 맡기고, ccusage 가 내주지 않는
것(시간대별 활동, 오늘의 호출 수, 세션 수)만 기록 파일에서 직접 센다.

기록은 `~/.claude/projects/**/*.jsonl` 이다. Codex 는 `~/.codex/sessions` 의 같은 꼴
jsonl 을 같은 정규식으로 훑고, Antigravity 는 토큰 기록을 남기지 않아 대화 목록
DB 에서 대화 수와 마지막 시각만 읽는다. 통째로 파싱하지 않고 줄마다
정규식 하나만 걸어 훑는다 — 이 PC 에서 7 일치 370MB 가 1 초 안쪽이라 인덱스를
따로 둘 이유가 없었다.
'''


import glob
import json
import os
import re
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request

from calendar import timegm
from datetime import datetime


CCUSAGE = os.environ.get('PYWINAGENT_CCUSAGE', 'ccusage@latest')
PROJECTS = os.path.join(os.path.expanduser('~'), '.claude', 'projects')
CODEX_SESSIONS = os.path.join(os.path.expanduser('~'), '.codex', 'sessions')
# IDE 와 CLI 가 저마다 대화 목록을 따로 둔다.
ANTIGRAVITY_DBS = tuple(
    os.path.join(os.path.expanduser('~'), '.gemini', name, 'conversation_summaries.db')
    for name in ('antigravity', 'antigravity-cli'))

AGENTS = ('claude', 'codex', 'antigravity')

USAGE_URL = 'https://api.anthropic.com/api/oauth/usage'

# 남은 한도는 기록에 없고 이 곳에서만 나온다. 로그인한 자격으로 물어야 하는데
# 살아 있는 건 Windows 쪽 토큰이다(수명 8시간, Windows 의 claude 가 돌 때만 갱신된다).
# WSL 쪽 파일은 데스크톱 앱이 인증을 넣어 주는 탓에 비어 있는 일이 많다. 그래도
# 둘 다 대 보고 먼저 대답하는 쪽을 쓴다. ★토큰은 쓰고 버린다 — 찍지도, 남기지도 않는다.
CREDENTIALS = (
    os.path.join(os.path.expanduser('~'), '.claude', '.credentials.json'),
    r'\\wsl.localhost\ubuntu-24.04\root\.claude\.credentials.json',
)

CODEX_RESETS_URL = 'https://chatgpt.com/backend-api/wham/rate-limit-reset-credits'

# Codex 강제 초기화 이용권은 기록에 없고 이 곳에서만 나온다. Codex 가 로그인해 둔 파일의
# 토큰으로 묻는다. Claude 와 같이 Windows 쪽을 먼저, 대답이 없으면 WSL 쪽을 댄다.
CODEX_AUTHS = (
    os.path.join(os.path.expanduser('~'), '.codex', 'auth.json'),
    r'\\wsl.localhost\ubuntu-24.04\root\.codex\auth.json',
)

LIMIT_NAMES = {'session': '5-hour', 'weekly_all': 'Weekly'}

# 창 길이는 응답에 없다. 지나간 시간을 그리려고 종류로 정한다 — 5시간 창 하나 말고는
# 모두 주간이다.
SESSION_WINDOW = 5 * 3600
WEEKLY_WINDOW = 7 * 86400

TREND_DAYS = 60
HEATMAP_DAYS = 7

# 백만 토큰당 (입력, 출력, 캐시 쓰기, 캐시 읽기).
PRICES = {
    'claude-opus-5': (5.0, 25.0, 6.25, 0.50),
    'claude-opus-4-8': (15.0, 75.0, 18.75, 1.50),
    'claude-fable-5': (10.0, 50.0, 12.5, 1.0),
    'claude-mythos-5': (10.0, 50.0, 12.5, 1.0),
    'claude-sonnet-5': (3.0, 15.0, 3.75, 0.30),
    'claude-sonnet-4-6': (3.0, 15.0, 3.75, 0.30),
    'claude-haiku-4-5': (1.0, 5.0, 1.25, 0.10),
}
DEFAULT_PRICE = (3.0, 15.0, 3.75, 0.30)

TIMESTAMP = re.compile(rb'"timestamp":"(\d{4})-(\d{2})-(\d{2})T(\d{2})')
REQUEST = re.compile(rb'"requestId":"([^"]+)"')
CODEX_REQUEST = re.compile(rb'"type":"token_usage_record".*?"response_id":"([^"]+)"')


def get_npx():
    '''★Windows 쪽 npx 라야 한다. WSL 의 홈에는 .claude 기록이 없다.'''
    path = os.path.join(os.path.expanduser('~'), '.nvm4w', 'nodejs', 'npx.cmd')
    return path if os.path.exists(path) else 'npx.cmd'


def run_ccusage(*args):
    command = [get_npx(), CCUSAGE] + list(args) + ['--json']
    try:
        done = subprocess.run(command, capture_output=True, timeout=180,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:
        return None
    text = done.stdout.decode('utf-8', 'replace')
    # npm notice 같은 잡소리가 앞에 붙는다. 첫 중괄호부터가 우리 것이다.
    start = text.find('{')
    if start < 0:
        return None
    try:
        return json.loads(text[start:])
    except ValueError:
        return None


def get_price(model):
    for name, price in PRICES.items():
        if model and name in model:
            return price
    return DEFAULT_PRICE


def get_cache_stats(row):
    '''(캐시 적중률, 캐시로 아낀 돈). 아낀 돈은 캐시로 읽은 토큰을 그냥 입력으로
    넣었다면 더 냈을 차액이다.'''
    read = row.get('cacheReadTokens', 0)
    written = row.get('cacheCreationTokens', 0)
    fresh = row.get('inputTokens', 0)
    total = read + written + fresh
    ratio = (read / float(total)) if total else 0.0

    saved = 0.0
    breakdowns = row.get('modelBreakdowns') or [row]
    for item in breakdowns:
        price = get_price(item.get('modelName'))
        saved += item.get('cacheReadTokens', 0) * (price[0] - price[3]) / 1e6
    return ratio, saved


# 마지막으로 한도를 못 물은 까닭. 'expired' 는 로그인 토큰이 다 만료된 것,
# 'offline' 은 묻기는 했는데 대답을 못 받은 것. 물어서 받았으면 None.
last_error = None


def read_token(path):
    '''(토큰, 만료됐는지). 만료 시각이 지난 토큰은 서버에 보내 봐야 401 이라 보내지 않는다.'''
    try:
        with open(path, encoding='utf-8') as file:
            oauth = json.load(file)['claudeAiOauth']
    except Exception:
        return None, False
    expires = oauth.get('expiresAt') or 0
    if expires and expires / 1000.0 < time.time():
        return None, True
    return oauth.get('accessToken'), False


def read_plan():
    '''로그인 파일의 구독 종류. (subscriptionType, rateLimitTier). 토큰은 읽지 않는다.'''
    for path in CREDENTIALS:
        try:
            with open(path, encoding='utf-8') as file:
                oauth = json.load(file)['claudeAiOauth']
        except Exception:
            continue
        if oauth.get('subscriptionType') or oauth.get('rateLimitTier'):
            return oauth.get('subscriptionType') or '', oauth.get('rateLimitTier') or ''
    return None


def get_plan_name():
    '''Max 20x 같은 이름. 배수는 subscriptionType 에 없고 rateLimitTier 에만 있다
    (`default_claude_max_20x`).'''
    plan = read_plan()
    if not plan:
        return None
    kind, tier = plan
    name = (kind or 'claude').replace('_', ' ').title()
    found = re.search(r'(\d+)x', tier)
    if found and kind == 'max':
        name += ' %sx' % found.group(1)
    return name


def ask_limits(token):
    request = urllib.request.Request(USAGE_URL, headers={
        'Authorization': 'Bearer ' + token,
        'anthropic-beta': 'oauth-2025-04-20',
        'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode('utf-8')), None
    except urllib.error.HTTPError as error:
        return None, 'expired' if error.code in (401, 403) else 'offline'
    except Exception:
        return None, 'offline'


def get_reset_seconds(stamp):
    if not stamp:
        return None
    try:
        moment = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return max(0, moment.timestamp() - time.time())


def get_limits():
    '''클로드 클라이언트가 보여 주는 5시간·주간 한도. 못 물으면 None 이다 —
    토큰이 만료되면 401 이 오는데 우리는 갱신할 방법이 없다(그건 로그인 흐름이다).
    Windows 에서 claude 를 한 번 돌리면(Sign in 단추가 하는 일) 토큰이 갱신되어 다시 열린다.

    ★토큰을 우리가 갱신하지는 않는다. refresh token 은 쓰면 바뀌어서 Claude Code 가
    쥔 것이 무효가 되고, 그쪽 로그인이 풀린다.'''
    global last_error
    body = None
    error = None
    expired = 0
    for path in CREDENTIALS:
        token, stale = read_token(path)
        expired += stale
        if token:
            body, error = ask_limits(token)
        if body:
            break
    if not body:
        last_error = error or ('expired' if expired else 'offline')
        return None
    last_error = None

    limits = []
    for item in body.get('limits', []):
        percent = item.get('percent', 0)
        resets = item.get('resets_at')
        # 쓰지도 않고 초기화도 없는 칸은 이 화면에서 알릴 것이 없다.
        if not resets and not percent:
            continue
        name = LIMIT_NAMES.get(item.get('kind'))
        if name is None:
            scope = (item.get('scope') or {}).get('model') or {}
            name = 'Weekly · %s' % (scope.get('display_name') or 'scoped')
        window = SESSION_WINDOW if item.get('kind') == 'session' else WEEKLY_WINDOW
        limits.append({'name': name, 'percent': percent,
                       'severity': item.get('severity', 'normal'),
                       'remains': get_reset_seconds(resets), 'window': window})
    return limits


# 마지막으로 초기화 이용권을 못 물은 까닭. 뜻은 last_error 와 같다.
codex_resets_error = None


def ask_codex_resets(path):
    '''(응답, 까닭). ★토큰은 쓰고 버린다 — 찍지도, 남기지도 않는다.'''
    try:
        with open(path, encoding='utf-8') as file:
            tokens = json.load(file)['tokens']
    except Exception:
        return None, None
    if not tokens.get('access_token'):
        return None, None
    headers = {'Authorization': 'Bearer ' + tokens['access_token'],
               'Accept': 'application/json', 'User-Agent': 'codex-cli'}
    if tokens.get('account_id'):
        headers['ChatGPT-Account-Id'] = tokens['account_id']
    request = urllib.request.Request(CODEX_RESETS_URL, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode('utf-8')), None
    except urllib.error.HTTPError as error:
        return None, 'expired' if error.code in (401, 403) else 'offline'
    except Exception:
        return None, 'offline'


def get_codex_resets():
    '''쓸 수 있는 Codex 강제 초기화(5시간+주간 한도를 한 번에 비운다) 이용권들.
    [{'expires': 만료 시각(epoch 초) 또는 None, 'title': ...}] 를 만료가 이른 차례로.
    못 물으면 None 이다. 이용권마다 받은 날부터 30 일 뒤에 사라진다.'''
    global codex_resets_error
    body = None
    error = None
    for path in CODEX_AUTHS:
        body, error = ask_codex_resets(path)
        if body:
            break
    if not body or not isinstance(body.get('credits'), list):
        codex_resets_error = error or 'offline'
        return None
    codex_resets_error = None

    credits = []
    for item in body['credits']:
        if not isinstance(item, dict) or item.get('status') != 'available':
            continue
        try:
            expires = datetime.fromisoformat(item['expires_at'].replace('Z', '+00:00')).timestamp()
        except (KeyError, AttributeError, ValueError):
            expires = None
        credits.append({'expires': expires, 'title': item.get('title') or ''})
    credits.sort(key=lambda credit: credit['expires'] or float('inf'))
    return credits


def format_remaining(seconds):
    if seconds is None:
        return ''
    hours, rest = divmod(int(seconds), 3600)
    if hours >= 24:
        return 'resets in %dd %dh' % divmod(hours, 24)
    if hours:
        return 'resets in %dh %dm' % (hours, rest // 60)
    return 'resets in %dm' % max(1, rest // 60)


def get_day_key(offset_days=0):
    return time.strftime('%Y-%m-%d', time.localtime(time.time() - offset_days * 86400))


def get_local_key(stamp, local):
    '''UTC (년, 월, 일, 시) 를 이 곳의 (날짜, 시) 로. 조합마다 한 번만 옮기고 외워 둔다.'''
    key = local.get(stamp)
    if key is None:
        moment = time.localtime(timegm((
            int(stamp[0]), int(stamp[1]), int(stamp[2]),
            int(stamp[3]), 0, 0, 0, 0, 0)))
        key = (time.strftime('%Y-%m-%d', moment), moment.tm_hour)
        local[stamp] = key
    return key


def scan_records(root=PROJECTS, request=REQUEST, days=HEATMAP_DAYS, on_line=None):
    '''시간대별 활동 수, 오늘의 고유 요청 수, 오늘 손댄 세션 파일 수.

    기록의 시각은 UTC 라 화면에 쓰려면 이 곳 시간으로 옮겨야 한다. 줄마다
    옮기면 느리니 (날짜, 시) 조합마다 한 번만 옮기고 외워 둔다 — 7 일이면
    조합이 168 개뿐이다.'''
    since = time.time() - days * 86400
    midnight = time.mktime(time.strptime(get_day_key(), '%Y-%m-%d'))
    today = get_day_key()

    files = glob.glob(os.path.join(root, '**', '*.jsonl'), recursive=True)
    recent = [path for path in files if os.path.getmtime(path) >= since]
    sessions = sum(1 for path in recent if os.path.getmtime(path) >= midnight)

    hours = {}
    calls = set()
    local = {}

    for path in recent:
        try:
            handle = open(path, 'rb')
        except OSError:
            continue
        with handle:
            for line in handle:
                found = TIMESTAMP.search(line)
                if not found:
                    continue
                key = get_local_key(found.groups(), local)
                hours[key] = hours.get(key, 0) + 1
                if key[0] == today:
                    called = request.search(line)
                    if called:
                        calls.add(called.group(1))
                if on_line is not None:
                    on_line(line)

    return {'hours': hours, 'calls': len(calls), 'sessions': sessions,
            'days': [get_day_key(index) for index in range(days - 1, -1, -1)]}


def get_window_name(minutes):
    if minutes and minutes % 1440 == 0:
        return 'Weekly' if minutes == 10080 else '%d-day' % (minutes // 1440)
    return '%d-hour' % round((minutes or 0) / 60.0)


def scan_codex():
    '''Codex 기록. 한도는 서버에 묻지 않는다 — 응답마다 `token_count` 이벤트에
    그때의 한도가 실려 오므로 가장 늦은 것을 쓴다. 초기화 시각이 이미 지났으면
    그 창은 새로 열렸다는 뜻이라 알릴 것이 없다.'''
    latest = {'stamp': b'', 'line': None}

    def on_line(line):
        if b'"rate_limits"' not in line:
            return
        stamp = TIMESTAMP.search(line).group(0)
        if stamp >= latest['stamp']:
            latest['stamp'] = stamp
            latest['line'] = line

    scanned = scan_records(CODEX_SESSIONS, CODEX_REQUEST, on_line=on_line)

    limits = []
    try:
        rates = json.loads(latest['line'])['payload']['rate_limits'] if latest['line'] else {}
    except (ValueError, KeyError, TypeError):
        rates = {}
    for window in (rates.get('primary'), rates.get('secondary')):
        if not window or not window.get('resets_at'):
            continue
        remains = window['resets_at'] - time.time()
        if remains <= 0:
            continue
        limits.append({'name': 'Codex · ' + get_window_name(window.get('window_minutes')),
                       'percent': int(round(window.get('used_percent', 0))),
                       'severity': 'normal', 'remains': remains,
                       'window': (window.get('window_minutes') or 0) * 60})
    scanned['limits'] = limits
    return scanned


def scan_antigravity(days=HEATMAP_DAYS):
    '''Antigravity 는 토큰도 호출도 남기지 않는다. 대화마다 마지막으로 손댄 시각
    한 줄뿐이라 활동 표에는 대화 하나가 그 시각에 한 칸씩만 찍힌다.'''
    today = get_day_key()
    since = get_day_key(days - 1)
    hours = {}
    local = {}
    sessions = 0
    for path in ANTIGRAVITY_DBS:
        if not os.path.exists(path):
            continue
        try:
            # ★읽기 전용으로 연다. 앱이 쓰는 중인 DB 에 잠금을 걸지 않는다.
            connection = sqlite3.connect('file:%s?mode=ro' % path, uri=True, timeout=2)
            try:
                rows = connection.execute(
                    'SELECT last_modified_time FROM conversation_summaries').fetchall()
            finally:
                connection.close()
        except sqlite3.Error:
            continue
        for (stamp,) in rows:
            found = re.match(r'(\d{4})-(\d{2})-(\d{2})[ T](\d{2})', str(stamp))
            if not found:
                continue
            key = get_local_key(found.groups(), local)
            if key[0] < since:
                continue
            hours[key] = hours.get(key, 0) + 1
            if key[0] == today:
                sessions += 1
    return {'hours': hours, 'calls': 0, 'sessions': sessions}


def collect(agents=('claude',)):
    '''화면 한 장에 필요한 것을 모두 모은다. ccusage 호출과 기록 훑기가 각각
    1 초 안쪽이라 한 번에 해도 된다. 부르는 쪽이 스레드로 돌릴 것.

    돈·캐시·추세는 ccusage 가 내주는 Claude 것뿐이다. 호출·세션·활동·한도는
    켜 둔 도구를 모두 더한다.'''
    rows = []
    report = None
    limits = []
    claude_limits = None
    scans = []

    if 'claude' in agents:
        since = time.strftime('%Y%m%d', time.localtime(time.time() - TREND_DAYS * 86400))
        report = run_ccusage('daily', '--since', since)
        rows = (report or {}).get('daily', [])
        claude_limits = get_limits()
        limits.extend(claude_limits or [])
        scans.append(scan_records())
    if 'codex' in agents:
        codex = scan_codex()
        limits.extend(codex['limits'])
        scans.append(codex)
    if 'antigravity' in agents:
        scans.append(scan_antigravity())

    today = get_day_key()
    current = next((row for row in rows if row.get('period') == today), None)
    ratio, saved = get_cache_stats(current) if current else (0.0, 0.0)

    hours = {}
    for scanned in scans:
        for key, value in scanned['hours'].items():
            hours[key] = hours.get(key, 0) + value

    # Claude 한도를 못 물었는데 다른 한도도 없으면 다시 로그인하라고 알린다.
    if 'claude' in agents and claude_limits is None and not limits:
        limits = None

    return {
        'ok': report is not None,
        'claude': 'claude' in agents,
        'limits': limits,
        'cost': (current or {}).get('totalCost', 0.0),
        'ratio': ratio,
        'saved': saved,
        'trend': [(row.get('period'), row.get('totalCost', 0.0)) for row in rows],
        'calls': sum(scanned['calls'] for scanned in scans),
        'sessions': sum(scanned['sessions'] for scanned in scans),
        'hours': hours,
        'days': [get_day_key(index) for index in range(HEATMAP_DAYS - 1, -1, -1)],
    }


def format_count(value):
    if value >= 1000:
        return '%.1fK' % (value / 1000.0)
    return str(value)


def format_money(value, digits=0):
    return '$%s' % format(round(value, digits), ',.%df' % digits)
