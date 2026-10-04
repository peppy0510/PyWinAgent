# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

사용량 페이지 한 장에 들어갈 값을 색인에서 뽑는다. 꼴은 WhereMyTokens 대시보드의
여섯 묶음(Plan Usage·Code Output·Trend·Sessions·Activity·Model Usage)과 머리판을
따른다.

날짜와 시는 모두 이 곳 시간이다. 묶는 일은 SQLite 에 맡기고 파이썬은 모양만
잡는다 — 색인 6 만 줄에서 전부 합쳐 0.1 초 안쪽이다.
'''


import time

import gitstats
import usagedata
import usageindex


SESSION_ACTIVE = 2 * 60
SESSION_WAITING = 15 * 60
SESSION_DAYS = 7
TREND_DAYS = 400
HEAT_DAYS = 7
CALENDAR_WEEKS = 22
HOURLY_DAYS = 30
TOP_MODELS = 4

LOCAL_DAY = "date(ts / 1000, 'unixepoch', 'localtime')"
LOCAL_HOUR = "CAST(strftime('%H', ts / 1000, 'unixepoch', 'localtime') AS INTEGER)"
TOKENS = 'input + output + cache_write + cache_read'

AGENT_NAMES = {'claude': 'Claude', 'codex': 'Codex', 'antigravity': 'Antigravity'}

# Claude 한도는 서버에 물어야 한다. 페이지가 1 분마다 다시 읽으므로 묻는 것은
# 5 분에 한 번만 (WhereMyTokens 의 쿼터 조회 간격과 같다).
CLAUDE_LIMITS_TTL = 5 * 60
claude_limits = {'at': 0, 'value': None}


def get_claude_limits(index, fresh):
    '''(한도들, 상태). 물어서 받으면 색인에 남겨 두고, 못 받으면 남겨 둔 것을 '지난 값'으로
    내준다 (WhereMyTokens 와 같다 — 토큰이 만료돼도 한도 막대가 통째로 사라지지 않게).
    상태는 못 받았을 때만 {'error': 'expired'|'offline', 'age': 남겨 둔 값의 나이(초)}.'''
    now = time.time()
    if fresh or now - claude_limits['at'] > CLAUDE_LIMITS_TTL:
        claude_limits['value'] = usagedata.get_limits()
        claude_limits['error'] = usagedata.last_error
        claude_limits['at'] = now
        if claude_limits['value'] is not None:
            index.set_meta('claude_limits', {'at': now, 'limits': [
                dict(limit, resets_at=None if limit['remains'] is None else now + limit['remains'])
                for limit in claude_limits['value']]})
    if claude_limits['value'] is not None:
        # 남은 시간은 물은 때 기준이다. 그 뒤 흐른 만큼 뺀다.
        spent = now - claude_limits['at']
        return [dict(limit, remains=None if limit['remains'] is None else
                     max(0, limit['remains'] - spent)) for limit in claude_limits['value']], None

    status = {'error': claude_limits.get('error') or 'offline', 'age': None}
    stored = index.get_meta('claude_limits')
    if not stored:
        return None, status
    status['age'] = now - stored['at']
    limits = []
    for limit in stored['limits']:
        limit = dict(limit, stale=True)
        resets_at = limit.pop('resets_at', None)
        if resets_at is None:
            limit['remains'] = None
        elif resets_at <= now:
            # 그 사이 창이 새로 열렸다. 지금 몇 % 인지는 모른다.
            limit.update(percent=0, remains=None, idle='window reset · waiting for fresh data')
        else:
            limit['remains'] = resets_at - now
        limits.append(limit)
    return limits, status


# Codex 초기화 이용권도 서버에 물어야 한다. 간격은 Claude 한도와 같다.
codex_resets = {'at': 0, 'value': None}


def get_codex_resets(index, options, fresh):
    '''{'credits': [...], 'stale': 지난 값인지} 또는 None. 못 받으면 남겨 둔 것에서
    그 사이 만료된 이용권만 빼고 내준다 (쓴 것은 알 수 없으니 'stale' 로 표시).'''
    if 'codex' not in options['agents']:
        return None
    now = time.time()
    if fresh or now - codex_resets['at'] > CLAUDE_LIMITS_TTL:
        codex_resets['value'] = usagedata.get_codex_resets()
        codex_resets['at'] = now
        if codex_resets['value'] is not None:
            index.set_meta('codex_resets', {'at': now, 'credits': codex_resets['value']})
    credits = codex_resets['value']
    stale = credits is None
    if stale:
        credits = (index.get_meta('codex_resets') or {}).get('credits')
        if credits is None:
            return None
    credits = [credit for credit in credits if not credit['expires'] or credit['expires'] > now]
    return {'credits': credits, 'stale': stale}


def get_day(offset=0):
    return time.strftime('%Y-%m-%d', time.localtime(time.time() - offset * 86400))


def get_filter(options, column_prefix=''):
    '''켜 둔 도구와 빼 둔 프로젝트로 거르는 WHERE 조각과 인자.'''
    agents = [name for name in options['agents'] if name != 'antigravity']
    if not agents:
        return '0', []
    sql = '%sprovider IN (%s)' % (column_prefix, ','.join('?' * len(agents)))
    args = list(agents)
    excluded = options.get('excluded') or []
    if excluded:
        sql += ' AND %sproject NOT IN (%s)' % (column_prefix, ','.join('?' * len(excluded)))
        args += excluded
    return sql, args


def get_state(last_ms):
    age = time.time() - last_ms / 1000.0
    if age < SESSION_ACTIVE:
        return 'active'
    if age < SESSION_WAITING:
        return 'waiting'
    return 'idle'


def get_cache_ratio(rows):
    '''도구마다 캐시 적중의 분모가 다르다. Claude 는 (읽기+쓰기), 나머지는 입력 전체.'''
    hit = 0
    base = 0
    for provider, fresh, written, read in rows:
        hit += read or 0
        if provider == 'claude':
            base += (read or 0) + (written or 0)
        else:
            base += (fresh or 0) + (written or 0) + (read or 0)
    return hit / float(base) if base else 0.0


def get_totals(index, where, args, since_day=None):
    extra = ''
    extra_args = []
    if since_day:
        extra = ' AND %s >= ?' % LOCAL_DAY
        extra_args = [since_day]
    row = index.query('SELECT COALESCE(SUM(cost), 0), COALESCE(SUM(saved), 0), COUNT(*), '
                      'COUNT(DISTINCT session) FROM entries WHERE %s%s' % (where, extra),
                      args + extra_args)[0]
    ratio_rows = index.query('SELECT provider, SUM(input), SUM(cache_write), SUM(cache_read) '
                             'FROM entries WHERE %s%s GROUP BY provider' % (where, extra),
                             args + extra_args)
    return {'cost': row[0], 'saved': row[1], 'calls': row[2], 'sessions': row[3],
            'ratio': get_cache_ratio(ratio_rows)}


def get_limits(index, options, fresh=False):
    '''(한도들, Claude 상태). 한도들이 None 이면 보일 것이 하나도 없다.'''
    limits = []
    failed = False
    claude_status = None
    if 'claude' in options['agents']:
        claude, claude_status = get_claude_limits(index, fresh)
        if claude is None:
            failed = True
        else:
            limits.extend(dict(limit, provider='claude') for limit in claude)
    if 'codex' in options['agents']:
        stored = index.get_meta('codex_limits') or {}
        rates = stored.get('limits') or {}
        defaults = ({'window_minutes': 300}, {'window_minutes': 10080})
        for window, default in zip((rates.get('primary'), rates.get('secondary')), defaults):
            window = window or default
            minutes = window.get('window_minutes') or default['window_minutes']
            remains = (window.get('resets_at') or 0) - time.time()
            name = 'Codex · ' + usagedata.get_window_name(minutes)
            # 초기화 시각이 지났으면 그 뒤로 Codex 를 안 쓴 것이다. 창이 아직 안 열렸으니
            # 0% 로 두되 줄은 남긴다 (WhereMyTokens 와 같이 늘 보인다).
            if remains <= 0:
                limits.append({'name': name, 'percent': 0, 'severity': 'normal',
                               'remains': None, 'window': minutes * 60, 'provider': 'codex',
                               'idle': 'starts with the next request'})
                continue
            limits.append({'name': name, 'percent': int(round(window.get('used_percent', 0))),
                           'severity': 'normal', 'remains': remains, 'window': minutes * 60,
                           'provider': 'codex'})
    now = time.time()
    for limit in limits:
        limit['when'] = limit.pop('idle', None) or usagedata.format_remaining(limit['remains'])
        # 다 쓴 칸은 풀리는 시각을 크게 보인다. 남은 시간은 페이지가 이 시각에서 센다 —
        # 1 분마다 새로 모으기 전에도 줄어들어야 하므로 남은 초가 아니라 절대 시각을 넘긴다.
        limit['reached'] = limit['percent'] >= 100 and limit['remains'] is not None
        limit['until'] = now + limit['remains'] if limit['reached'] else None
        window = limit.get('window')
        limit['elapsed'] = None if not window or limit['remains'] is None else \
            max(0, min(100, int(round((1 - limit['remains'] / float(window)) * 100))))
    if failed and not limits:
        return None, claude_status
    return limits, claude_status


def get_tool_filter(options):
    '''tools 표에는 project 칸이 없다. 빼 둔 프로젝트는 세션을 거쳐 거른다.'''
    where, args = get_filter(dict(options, excluded=[]))
    excluded = options.get('excluded') or []
    if excluded and args:
        where += (' AND session NOT IN (SELECT DISTINCT session FROM entries '
                  'WHERE project IN (%s))' % ','.join('?' * len(excluded)))
        args = args + list(excluded)
    return where, args


def get_plans(index, options):
    '''지금 쓰는 플랜. Claude 는 로그인 파일에서, Codex 는 기록에 실려 온 한도
    정보의 plan_type 에서 읽는다.'''
    plans = []
    if 'claude' in options['agents']:
        name = usagedata.get_plan_name()
        if name:
            plans.append({'provider': 'claude', 'name': name})
    if 'codex' in options['agents']:
        stored = index.get_meta('codex_limits') or {}
        kind = (stored.get('limits') or {}).get('plan_type')
        if kind:
            plans.append({'provider': 'codex', 'name': kind.replace('_', ' ').title()})
    return plans


def get_daily(index, options, where, args):
    since = get_day(TREND_DAYS)
    rows = index.query(
        'SELECT %s AS day, SUM(cost), SUM(%s), COUNT(*), SUM(input), SUM(output), '
        'SUM(cache_read), SUM(cache_write), SUM(reasoning) FROM entries '
        'WHERE %s AND %s >= ? GROUP BY day ORDER BY day' % (LOCAL_DAY, TOKENS, where, LOCAL_DAY),
        args + [since])
    tool_where, tool_args = get_tool_filter(options)
    tools = index.query(
        'SELECT %s AS day, category, COUNT(*), SUM(tokens) FROM tools '
        'WHERE %s AND %s >= ? GROUP BY day, category' % (LOCAL_DAY, tool_where, LOCAL_DAY),
        tool_args + [since])
    daily = {}
    for day, cost, tokens, calls, fresh, output, read, written, thinking in rows:
        daily[day] = {'cost': cost, 'tokens': tokens, 'calls': calls,
                      'panorama': [fresh, output, read, written, thinking or 0],
                      'tools': {}}
    for day, category, count, tokens in tools:
        slot = daily.setdefault(day, {'cost': 0, 'tokens': 0, 'calls': 0,
                                      'panorama': [0, 0, 0, 0, 0], 'tools': {}})
        slot['tools'][category] = [count, tokens or 0]
    return daily


def get_activity(index, where, args):
    today = get_day()
    hours = index.query(
        'SELECT %s AS day, %s AS hour, SUM(%s), SUM(cost), COUNT(*) FROM entries '
        'WHERE %s AND %s >= ? GROUP BY day, hour' % (LOCAL_DAY, LOCAL_HOUR, TOKENS, where,
                                                     LOCAL_DAY),
        args + [get_day(max(HOURLY_DAYS, HEAT_DAYS) - 1)])
    days = [get_day(index) for index in range(HEAT_DAYS - 1, -1, -1)]
    heat = {day: [0] * 24 for day in days}
    hourly = [[0, 0.0, 0] for _ in range(24)]
    for day, hour, tokens, cost, calls in hours:
        if day in heat:
            heat[day][hour] += tokens
        hourly[hour][0] += tokens
        hourly[hour][1] += cost
        hourly[hour][2] += calls

    # 달력은 일요일에서 시작하는 주로 22 주를 채운다. 오늘이 마지막 칸이다.
    weekday = int(time.strftime('%w'))
    span = CALENDAR_WEEKS * 7 - (6 - weekday)
    calendar_rows = index.query(
        'SELECT %s AS day, SUM(%s) FROM entries WHERE %s AND %s >= ? GROUP BY day'
        % (LOCAL_DAY, TOKENS, where, LOCAL_DAY), args + [get_day(span - 1)])
    calendar = dict(calendar_rows)
    calendar_days = [[get_day(offset), calendar.get(get_day(offset), 0)]
                     for offset in range(span - 1, -1, -1)]

    weeks = []
    for week in range(3, -1, -1):
        start, end = get_day(week * 7 + 6), get_day(week * 7)
        row = index.query('SELECT COALESCE(SUM(%s), 0), COALESCE(SUM(cost), 0), COUNT(*) '
                          'FROM entries WHERE %s AND %s BETWEEN ? AND ?'
                          % (TOKENS, where, LOCAL_DAY), args + [start, end])[0]
        weeks.append({'from': start, 'to': end, 'tokens': row[0], 'cost': row[1],
                      'calls': row[2]})

    return {'days': days, 'heat': [heat[day] for day in days], 'today': today,
            'calendar': calendar_days, 'hourly': hourly, 'weeks': weeks}


def get_models(index, where, args):
    rows = index.query('SELECT model, provider, SUM(cost), SUM(%s), COUNT(*) FROM entries '
                       "WHERE %s AND model != '<synthetic>' GROUP BY model, provider "
                       'ORDER BY SUM(cost) DESC' % (TOKENS, where), args)
    top = [{'model': model, 'provider': provider, 'cost': cost, 'tokens': tokens,
            'calls': calls} for model, provider, cost, tokens, calls in rows[:TOP_MODELS]]
    rest = rows[TOP_MODELS:]
    if rest:
        top.append({'model': 'Other', 'provider': '', 'cost': sum(row[2] for row in rest),
                    'tokens': sum(row[3] for row in rest), 'calls': sum(row[4] for row in rest)})
    return top


def get_sessions(index, where, args, options):
    since = (time.time() - SESSION_DAYS * 86400) * 1000
    rows = index.query(
        'SELECT s.provider, s.session, s.cwd, s.project, s.model, s.source, s.last, '
        's.context, s.context_max, s.file FROM sessions s WHERE s.last >= ? '
        'ORDER BY s.last DESC', (since,))
    agents = options['agents']
    excluded = set(options.get('excluded') or [])
    sessions = []
    seen = set()
    for provider, session, cwd, project, model, source, last, context, context_max, path in rows:
        if provider not in agents or project in excluded or (provider, session) in seen:
            continue
        seen.add((provider, session))
        sessions.append({'provider': provider, 'session': session, 'cwd': cwd,
                         'project': project, 'model': model, 'source': source,
                         'last': last, 'state': get_state(last),
                         'context': context, 'contextMax': context_max})
    if sessions:
        keys = [item['session'] for item in sessions]
        marks = ','.join('?' * len(keys))
        totals = {row[0]: row[1:] for row in index.query(
            'SELECT session, SUM(cost), SUM(%s), COUNT(*) FROM entries WHERE session IN (%s) '
            'GROUP BY session' % (TOKENS, marks), keys)}
        tools = {}
        for session, category, count in index.query(
                'SELECT session, category, COUNT(*) FROM tools WHERE session IN (%s) '
                'GROUP BY session, category' % marks, keys):
            tools.setdefault(session, {})[category] = count
        for item in sessions:
            cost, tokens, calls = totals.get(item['session'], (0, 0, 0))
            item.update({'cost': cost or 0, 'tokens': tokens or 0, 'calls': calls,
                         'tools': tools.get(item['session'], {})})

    if 'antigravity' in agents:
        for conversation, last, steps, workspaces in usageindex.read_antigravity():
            if last < since:
                continue
            folder = workspaces.split(',')[0].strip().strip('[]"')
            project = usageindex.get_project(folder.replace('file:///', ''))
            if project in excluded:
                continue
            sessions.append({'provider': 'antigravity', 'session': conversation,
                             'cwd': folder, 'project': project, 'model': '', 'source': '',
                             'last': last, 'state': get_state(last), 'context': 0,
                             'contextMax': 0, 'cost': 0, 'tokens': 0, 'calls': steps,
                             'tools': {}})
        sessions.sort(key=lambda item: -item['last'])
    return sessions


def get_code(index, options, refresh_git):
    '''(저장소 통계를 합친 날짜표, 저장소 수). refresh_git 이 거짓이면 저장해 둔 것만.'''
    folders = [row[0] for row in index.query('SELECT DISTINCT cwd FROM sessions WHERE provider IN '
                                             "('claude', 'codex')")]
    excluded = set(options.get('excluded') or [])
    folders = [folder for folder in folders if usageindex.get_project(folder) not in excluded]
    if refresh_git:
        repos = gitstats.collect(folders)
    else:
        cache = gitstats.load_cache()
        tops = {cache['folders'].get(folder) for folder in folders}
        repos = {top: cache['repos'][top]['days'] for top in tops
                 if top and top in cache['repos']}
    days = {}
    for repo in repos.values():
        for day, stats in repo.items():
            slot = days.setdefault(day, {'commits': 0, 'added': 0, 'removed': 0, 'paths': {}})
            slot['commits'] += stats['commits']
            slot['added'] += stats['added']
            slot['removed'] += stats['removed']
            for name, (added, removed) in stats['paths'].items():
                pair = slot['paths'].setdefault(name, [0, 0])
                pair[0] += added
                pair[1] += removed
    return days, len(repos)


def build(index, options, refresh_git=False, fresh_limits=False):
    where, args = get_filter(options)
    today = get_day()
    code, repos = get_code(index, options, refresh_git)
    limits, claude_status = get_limits(index, options, fresh_limits)
    return {
        'agents': list(options['agents']),
        'claude': 'claude' in options['agents'],
        'today': get_totals(index, where, args, today),
        'all': get_totals(index, where, args),
        'limits': limits,
        'claude_status': claude_status,
        'codex_resets': get_codex_resets(index, options, fresh_limits),
        'plans': get_plans(index, options),
        'daily': get_daily(index, options, where, args),
        'code': code,
        'repos': repos,
        'activity': get_activity(index, where, args),
        'models': get_models(index, where, args),
        'sessions': get_sessions(index, where, args, options),
        'hidden': list(options.get('hidden') or []),
        'currency': options.get('currency', 'USD'),
        'rate': options.get('rate', 1.0),
        'sections': options.get('sections'),
        'wide': options.get('wide', True),
        'updated': time.time(),
    }
