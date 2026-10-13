# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
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
ANTIGRAVITY_DBS = tuple(
    os.path.join(os.path.expanduser('~'), '.gemini', name, 'conversation_summaries.db')
    for name in ('antigravity', 'antigravity-cli'))

AGENTS = ('claude', 'codex', 'antigravity')

USAGE_URL = 'https://api.anthropic.com/api/oauth/usage'

CREDENTIALS = (
    os.path.join(os.path.expanduser('~'), '.claude', '.credentials.json'),
    r'\\wsl.localhost\ubuntu-24.04\root\.claude\.credentials.json',
)

CODEX_RESETS_URL = 'https://chatgpt.com/backend-api/wham/rate-limit-reset-credits'

CODEX_AUTHS = (
    os.path.join(os.path.expanduser('~'), '.codex', 'auth.json'),
    r'\\wsl.localhost\ubuntu-24.04\root\.codex\auth.json',
)

LIMIT_NAMES = {'session': '5-hour', 'weekly_all': 'Weekly'}

SESSION_WINDOW = 5 * 3600
WEEKLY_WINDOW = 7 * 86400

TREND_DAYS = 60
HEATMAP_DAYS = 7

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


last_error = None


def read_token(path):
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
    # never refresh the token here: refresh tokens rotate and would sign Claude Code out
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


codex_resets_error = None


def ask_codex_resets(path):
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
    key = local.get(stamp)
    if key is None:
        moment = time.localtime(timegm((
            int(stamp[0]), int(stamp[1]), int(stamp[2]),
            int(stamp[3]), 0, 0, 0, 0, 0)))
        key = (time.strftime('%Y-%m-%d', moment), moment.tm_hour)
        local[stamp] = key
    return key


def scan_records(root=PROJECTS, request=REQUEST, days=HEATMAP_DAYS, on_line=None):
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
    today = get_day_key()
    since = get_day_key(days - 1)
    hours = {}
    local = {}
    sessions = 0
    for path in ANTIGRAVITY_DBS:
        if not os.path.exists(path):
            continue
        try:
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
