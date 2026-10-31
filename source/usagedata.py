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

from usageindex import as_dict
from usageindex import as_epoch
from usageindex import as_float
from usageindex import as_list
from usageindex import as_text
from usageindex import in_wsl


USAGE_URL = 'https://api.anthropic.com/api/oauth/usage'

CLAUDE_PROFILE = os.path.join(os.path.expanduser('~'), '.claude.json')

CREDENTIALS = (os.path.join(os.path.expanduser('~'), '.claude', '.credentials.json'),
               *in_wsl('.claude', '.credentials.json'))

CODEX_RESETS_URL = 'https://chatgpt.com/backend-api/wham/rate-limit-reset-credits'

CODEX_AUTHS = (os.path.join(os.path.expanduser('~'), '.codex', 'auth.json'),
               *in_wsl('.codex', 'auth.json'))

LIMIT_NAMES = {'session': '5-hour', 'weekly_all': 'Weekly'}

# the older per-window fields, read when the limits list is missing
LEGACY_LIMITS = (('five_hour', 'session'), ('seven_day', 'weekly_all'))

# 2026-10-30: Max 5x became Max and Max 20x Ultra; the tokens still carry the old tier names
PLAN_NAMES = {('max', '5'): 'Max', ('max', '20'): 'Ultra'}

SESSION_WINDOW = 5 * 3600
WEEKLY_WINDOW = 7 * 86400


last_error = None


def read_token(path):
    try:
        with open(path, encoding='utf-8') as file:
            oauth = json.load(file)['claudeAiOauth']
    except Exception:
        return None, False
    expires = as_epoch(oauth.get('expiresAt'))
    if expires and expires < time.time():
        return None, True
    return as_text(oauth.get('accessToken')) or None, False


def read_plan():
    for path in CREDENTIALS:
        try:
            with open(path, encoding='utf-8') as file:
                oauth = json.load(file)['claudeAiOauth']
        except Exception:
            continue
        kind, tier = as_text(oauth.get('subscriptionType')), as_text(oauth.get('rateLimitTier'))
        if kind or tier:
            return kind, tier
    return None


def get_plan_name():
    plan = read_plan()
    if not plan:
        return None
    kind, tier = plan
    found = re.search(r'(\d+)x', tier)
    if found and (kind, found.group(1)) in PLAN_NAMES:
        return PLAN_NAMES[kind, found.group(1)]
    name = (kind or 'claude').replace('_', ' ').title()
    if found and kind == 'max':
        name += f' {found.group(1)}x'
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
    moment = as_epoch(stamp)
    if moment is None:
        return None
    return max(0, moment - time.time())


def get_limit_items(body):
    # numbered as the API lists them: weekly_scoped_shares points by that index
    if isinstance(body.get('limits'), list):
        return [(order, item) for order, item in enumerate(body['limits'])
                if isinstance(item, dict)]
    items = []
    for key, kind in LEGACY_LIMITS:
        window = as_dict(body.get(key))
        if window:
            items.append((None, {'kind': kind, 'percent': window.get('utilization'),
                                 'resets_at': window.get('resets_at'), 'is_active': True}))
    return items


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
    if not isinstance(body, dict):
        last_error = error or ('expired' if expired else 'offline')
        return None
    last_error = None

    # a model-scoped weekly limit may only take its share of the weekly one
    shares = {}
    for share in as_list(body.get('weekly_scoped_shares')):
        share = as_dict(share)
        if isinstance(share.get('limit_index'), int):
            shares[share['limit_index']] = share
    # verified Ultra accounts have no 5-hour limit, though the API still reports an idle one
    ultra = get_plan_name() == 'Ultra'
    limits = []
    for order, item in get_limit_items(body):
        kind = as_text(item.get('kind'))
        percent = as_float(item.get('percent')) or 0
        remains = get_reset_seconds(item.get('resets_at'))
        if remains is None and not percent:
            continue
        if ultra and kind == 'session' and not item.get('is_active'):
            continue
        name = LIMIT_NAMES.get(kind)
        if name is None:
            model = as_dict(as_dict(item.get('scope')).get('model'))
            name = f'Weekly · {as_text(model.get("display_name")) or kind or "scoped"}'
        window = SESSION_WINDOW if kind == 'session' else WEEKLY_WINDOW
        limit = {'name': name, 'percent': percent,
                 'severity': as_text(item.get('severity')) or 'normal',
                 'remains': remains, 'window': window}
        cap = as_float(shares.get(order, {}).get('allowance_percent_of_weekly'))
        if cap is not None:
            limit['cap'] = cap
            limit['of_weekly'] = as_float(shares[order].get('used_percent_of_weekly')) or 0
        limits.append(limit)
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
    if not isinstance(body, dict) or not isinstance(body.get('credits'), list):
        codex_resets_error = error or 'offline'
        return None
    codex_resets_error = None

    credits = []
    for item in body['credits']:
        if not isinstance(item, dict) or item.get('status') != 'available':
            continue
        credits.append({'expires': as_epoch(item.get('expires_at')),
                        'title': as_text(item.get('title'))})
    credits.sort(key=lambda credit: credit['expires'] or float('inf'))
    return credits


def format_remaining(seconds):
    if seconds is None:
        return ''
    hours, rest = divmod(int(seconds), 3600)
    if hours >= 24:
        days, hours = divmod(hours, 24)
        return f'resets in {days}d {hours}h'
    if hours:
        return f'resets in {hours}h {rest // 60}m'
    return f'resets in {max(1, rest // 60)}m'


def get_window_name(minutes):
    minutes = as_float(minutes) or 0
    if minutes and minutes % 1440 == 0:
        return 'Weekly' if minutes == 10080 else f'{int(minutes // 1440)}-day'
    return f'{round((minutes or 0) / 60.0)}-hour'
