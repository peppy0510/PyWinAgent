# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

사용량 숫자를 모은다. 돈과 토큰은 ccusage 에 맡기고, ccusage 가 내주지 않는
것(시간대별 활동, 오늘의 호출 수, 세션 수)만 기록 파일에서 직접 센다.

기록은 `~/.claude/projects/**/*.jsonl` 이다. 통째로 파싱하지 않고 줄마다
정규식 하나만 걸어 훑는다 — 이 PC 에서 7 일치 370MB 가 1 초 안쪽이라 인덱스를
따로 둘 이유가 없었다.
'''


import glob
import json
import os
import re
import subprocess
import time
import urllib.request

from calendar import timegm
from datetime import datetime


CCUSAGE = os.environ.get('PYWINAGENT_CCUSAGE', 'ccusage@latest')
PROJECTS = os.path.join(os.path.expanduser('~'), '.claude', 'projects')

USAGE_URL = 'https://api.anthropic.com/api/oauth/usage'

# 남은 한도는 기록에 없고 이 곳에서만 나온다. 로그인한 자격으로 물어야 하는데
# 이 PC 는 Windows 쪽 토큰이 폐기돼 있고 WSL 쪽이 살아 있다. 둘 다 대 보고 먼저
# 대답하는 쪽을 쓴다. ★토큰은 쓰고 버린다 — 찍지도, 남기지도 않는다.
CREDENTIALS = (
    os.path.join(os.path.expanduser('~'), '.claude', '.credentials.json'),
    r'\\wsl.localhost\ubuntu-24.04\root\.claude\.credentials.json',
)

LIMIT_NAMES = {'session': '5-hour', 'weekly_all': 'Weekly'}

TREND_DAYS = 17
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


def read_token(path):
    try:
        with open(path, encoding='utf-8') as file:
            return json.load(file)['claudeAiOauth']['accessToken']
    except Exception:
        return None


def ask_limits(token):
    request = urllib.request.Request(USAGE_URL, headers={
        'Authorization': 'Bearer ' + token,
        'anthropic-beta': 'oauth-2025-04-20',
        'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception:
        return None


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
    WSL 에서 claude 를 쓰면 그쪽 토큰이 갱신되어 다시 열린다.'''
    body = None
    for path in CREDENTIALS:
        token = read_token(path)
        if token:
            body = ask_limits(token)
        if body:
            break
    if not body:
        return None

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
        limits.append({'name': name, 'percent': percent,
                       'severity': item.get('severity', 'normal'),
                       'remains': get_reset_seconds(resets)})
    return limits


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


def scan_records(days=HEATMAP_DAYS):
    '''시간대별 활동 수, 오늘의 고유 요청 수, 오늘 손댄 세션 파일 수.

    기록의 시각은 UTC 라 화면에 쓰려면 이 곳 시간으로 옮겨야 한다. 줄마다
    옮기면 느리니 (날짜, 시) 조합마다 한 번만 옮기고 외워 둔다 — 7 일이면
    조합이 168 개뿐이다.'''
    since = time.time() - days * 86400
    midnight = time.mktime(time.strptime(get_day_key(), '%Y-%m-%d'))
    today = get_day_key()

    files = glob.glob(os.path.join(PROJECTS, '**', '*.jsonl'), recursive=True)
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
                stamp = found.groups()
                key = local.get(stamp)
                if key is None:
                    moment = time.localtime(timegm((
                        int(stamp[0]), int(stamp[1]), int(stamp[2]),
                        int(stamp[3]), 0, 0, 0, 0, 0)))
                    key = (time.strftime('%Y-%m-%d', moment), moment.tm_hour)
                    local[stamp] = key
                hours[key] = hours.get(key, 0) + 1
                if key[0] == today:
                    request = REQUEST.search(line)
                    if request:
                        calls.add(request.group(1))

    return {'hours': hours, 'calls': len(calls), 'sessions': sessions,
            'days': [get_day_key(index) for index in range(days - 1, -1, -1)]}


def collect():
    '''화면 한 장에 필요한 것을 모두 모은다. ccusage 호출과 기록 훑기가 각각
    1 초 안쪽이라 한 번에 해도 된다. 부르는 쪽이 스레드로 돌릴 것.'''
    since = time.strftime('%Y%m%d', time.localtime(time.time() - TREND_DAYS * 86400))
    report = run_ccusage('daily', '--since', since)
    rows = (report or {}).get('daily', [])

    today = get_day_key()
    current = next((row for row in rows if row.get('period') == today), None)
    ratio, saved = get_cache_stats(current) if current else (0.0, 0.0)

    scanned = scan_records()
    return {
        'ok': report is not None,
        'limits': get_limits(),
        'cost': (current or {}).get('totalCost', 0.0),
        'ratio': ratio,
        'saved': saved,
        'trend': [(row.get('period'), row.get('totalCost', 0.0)) for row in rows],
        'calls': scanned['calls'],
        'sessions': scanned['sessions'],
        'hours': scanned['hours'],
        'days': scanned['days'],
    }


def format_count(value):
    if value >= 1000:
        return '%.1fK' % (value / 1000.0)
    return str(value)


def format_money(value, digits=0):
    return '$%s' % format(round(value, digits), ',.%df' % digits)
