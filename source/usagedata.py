# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import base64
import json
import os
import re
import time
import urllib.error
import urllib.request

from datetime import datetime


USAGE_URL = 'https://api.anthropic.com/api/oauth/usage'

CLAUDE_PROFILE = os.path.join(os.path.expanduser('~'), '.claude.json')

CREDENTIALS = (
    os.path.join(os.path.expanduser('~'), '.claude', '.credentials.json'),
    r'\\wsl.localhost\ubuntu-26.04\root\.claude\.credentials.json',
)

CODEX_RESETS_URL = 'https://chatgpt.com/backend-api/wham/rate-limit-reset-credits'

CODEX_AUTHS = (
    os.path.join(os.path.expanduser('~'), '.codex', 'auth.json'),
    r'\\wsl.localhost\ubuntu-26.04\root\.codex\auth.json',
)

LIMIT_NAMES = {'session': '5-hour', 'weekly_all': 'Weekly'}

SESSION_WINDOW = 5 * 3600
WEEKLY_WINDOW = 7 * 86400


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


def get_claude_account():
    try:
        with open(CLAUDE_PROFILE, encoding='utf-8') as file:
            account = json.load(file).get('oauthAccount') or {}
    except Exception:
        return None, None
    return account.get('displayName') or None, account.get('emailAddress') or None


def get_codex_account():
    for path in CODEX_AUTHS:
        try:
            with open(path, encoding='utf-8') as file:
                payload = json.load(file)['tokens']['id_token'].split('.')[1]
            claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        except Exception:
            continue
        if claims.get('name') or claims.get('email'):
            return claims.get('name') or None, claims.get('email') or None
    return None, None


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


def get_window_name(minutes):
    if minutes and minutes % 1440 == 0:
        return 'Weekly' if minutes == 10080 else '%d-day' % (minutes // 1440)
    return '%d-hour' % round((minutes or 0) / 60.0)
