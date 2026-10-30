# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import winreg

from datetime import datetime
from datetime import timezone


AGENTS = ('claude', 'codex', 'antigravity')

# the banner would flash and push the page down on every small append
PROGRESS_MIN_BYTES = 8 * 1024 * 1024
# WSL listings lag the file by seconds (up to 8 s measured) and local NTFS listings stay
# stale while a writer holds the file, so only idle WSL files skip the stat
REMOTE_IDLE = 10 * 60

LXSS_KEY = r'Software\Microsoft\Windows\CurrentVersion\Lxss'


def get_wsl_home():
    # the default distro's login home as Windows reaches it, whatever the distro is named;
    # None without WSL
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, LXSS_KEY) as key:
            default = winreg.QueryValueEx(key, 'DefaultDistribution')[0]
            with winreg.OpenKey(key, default) as distro:
                name = winreg.QueryValueEx(distro, 'DistributionName')[0]
                try:
                    uid = winreg.QueryValueEx(distro, 'DefaultUid')[0]
                except OSError:
                    uid = 0
    except OSError:
        return None
    # lower, as the index's file and session keys were written; another case is new paths
    root = rf'\\wsl.localhost\{name.lower()}'
    if uid == 0:
        return root + r'\root'
    try:
        with open(root + r'\etc\passwd', encoding='utf-8') as file:
            for line in file:
                fields = line.split(':')
                if len(fields) > 5 and fields[2] == str(uid):
                    return root + fields[5].replace('/', '\\')
    except OSError:
        pass
    return None


def in_wsl(*parts):
    return (os.path.join(WSL_HOME, *parts),) if WSL_HOME else ()


HOME = os.path.expanduser('~')
WSL_HOME = get_wsl_home()

ROOTS = {
    'claude': (os.path.join(HOME, '.claude', 'projects'), *in_wsl('.claude', 'projects')),
    'codex': (os.path.join(HOME, '.codex', 'sessions'),
              os.path.join(HOME, '.codex', 'archived_sessions'),
              *in_wsl('.codex', 'sessions'), *in_wsl('.codex', 'archived_sessions')),
}

ANTIGRAVITY_DBS = tuple(os.path.join(HOME, '.gemini', name, 'conversation_summaries.db')
                        for name in ('antigravity', 'antigravity-cli'))

INDEX_PATH = os.path.join(os.environ.get('APPDATA', HOME), 'PyWinAgent', 'usage-index.sqlite')

SCHEMA_VERSION = 1

LIMIT_KEEP = 35 * 86400

PER_MILLION = 1e6
LONG_CONTEXT_THRESHOLD = 272000
GPT_56_PRICE_CUT = datetime(2026, 7, 30, tzinfo=timezone.utc).timestamp() * 1000
SONNET_5_STANDARD = datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp() * 1000
GPT_6_ASTRA_START = datetime(2026, 9, 3, tzinfo=timezone.utc).timestamp() * 1000

RATE = {
    'gpt6Astra': (10, 50, 12.5, 1),
    'gpt56Sol': (5, 30, 6.25, 0.5),
    'gpt56Terra': (2, 12, 2.5, 0.2),
    'gpt56TerraLaunch': (2.5, 15, 3.125, 0.25),
    'gpt56Luna': (0.2, 1.2, 0.25, 0.02),
    'gpt56LunaLaunch': (1, 6, 1.25, 0.1),
    'gpt54Mini': (0.75, 4.5, 0.75, 0.075),
    'gpt54Nano': (0.2, 1.25, 0.2, 0.02),
    'gpt54': (2.5, 15, 2.5, 0.25),
    'gpt53Codex': (1.75, 14, 1.75, 0.175),
    'gpt51CodexMini': (0.25, 2, 0.25, 0.025),
    'gpt51Codex': (1.25, 10, 1.25, 0.125),
    'codexMiniLatest': (1.5, 6, 1.5, 0.375),
    'claudeFable5': (10, 50, 12.5, 1),
    'claudeOpusCurrent': (5, 25, 6.25, 0.5),
    'claudeOpusLegacy': (15, 75, 18.75, 1.5),
    'claudeSonnet5Promo': (2, 10, 2.5, 0.2),
    'claudeSonnet': (3, 15, 3.75, 0.3),
    'claudeHaiku4': (1, 5, 1.25, 0.1),
    'claudeHaikuLegacy': (0.8, 4, 1, 0.08),
    'gpt4o': (2.5, 10, 0, 1.25),
    'gpt4': (2, 8, 0, 0.5),
    'fallback': (3, 15, 3.75, 0.3),
}

CURRENT_OPUS_4 = re.compile(r'claude-opus-4-(?:5|6|7|8)(?:\b|-)')

BUILD_COMMAND = re.compile(
    r'\b(npm|yarn|pnpm|bun|tsc|tsx|ts-node|cargo|python|pytest|jest|vitest|make|cmake|'
    r'gradle|mvn|dotnet|go\s+build|go\s+test)\b')

TOOL_CATEGORIES = ('read', 'editWrite', 'search', 'git', 'buildTest', 'terminal',
                   'subagents', 'web')

CLAUDE_CONTEXT = 200000
LONG_CONTEXT = 1000000


def resolve_price(model, stamp):
    lower = (model or '').strip().lower()
    early = 0 < stamp < GPT_56_PRICE_CUT
    if lower == 'gpt-6-astra' and stamp >= GPT_6_ASTRA_START:
        return RATE['gpt6Astra'], True
    if 'gpt-5.6-luna' in lower:
        return RATE['gpt56LunaLaunch' if early else 'gpt56Luna'], True
    if 'gpt-5.6-terra' in lower:
        return RATE['gpt56TerraLaunch' if early else 'gpt56Terra'], True
    if 'gpt-5.6-sol' in lower or lower == 'gpt-5.6':
        return RATE['gpt56Sol'], True
    for needle, name in (('gpt-5.4-mini', 'gpt54Mini'), ('gpt-5.4-nano', 'gpt54Nano'),
                         ('gpt-5.4', 'gpt54'), ('gpt-5.3-codex', 'gpt53Codex'),
                         ('gpt-5.2-codex', 'gpt53Codex'), ('gpt-5.1-codex-mini', 'gpt51CodexMini'),
                         ('gpt-5.1-codex', 'gpt51Codex'), ('gpt-5-codex', 'gpt51Codex'),
                         ('codex-mini-latest', 'codexMiniLatest'),
                         ('claude-fable-5', 'claudeFable5')):
        if needle in lower:
            return RATE[name], False
    if 'claude-opus-5' in lower or CURRENT_OPUS_4.search(lower):
        return RATE['claudeOpusCurrent'], False
    if 'claude-opus' in lower:
        return RATE['claudeOpusLegacy'], False
    if 'claude-sonnet-5' in lower:
        promo = 0 < stamp < SONNET_5_STANDARD
        return RATE['claudeSonnet5Promo' if promo else 'claudeSonnet'], False
    if 'claude-sonnet' in lower:
        return RATE['claudeSonnet'], False
    if 'claude-haiku-4' in lower:
        return RATE['claudeHaiku4'], False
    if 'claude-haiku' in lower:
        return RATE['claudeHaikuLegacy'], False
    if 'gpt-4o' in lower:
        return RATE['gpt4o'], False
    if 'gpt-4' in lower:
        return RATE['gpt4'], False
    if lower.startswith('gpt') or lower == 'codex':
        return RATE['gpt54'], False
    if lower.startswith('claude'):
        return RATE['claudeSonnet'], False
    return RATE['fallback'], False


def estimate_cost(model, stamp, fresh, output, written, read, written_long=0):
    rates, long_context = resolve_price(model, stamp)
    prompt = fresh + written + read
    boost = long_context and prompt > LONG_CONTEXT_THRESHOLD
    input_rate = rates[0] * (2 if boost else 1)
    write_rate = rates[2] * (2 if boost else 1)
    read_rate = rates[3] * (2 if boost else 1)
    output_rate = rates[1] * (1.5 if boost else 1)
    written_long = min(written, max(0, written_long))
    cost = (fresh * input_rate + output * output_rate +
            (written - written_long) * write_rate + written_long * input_rate * 2 +
            read * read_rate) / PER_MILLION
    saved = max(0, input_rate - read_rate) * read / PER_MILLION
    return cost, saved


def classify_command(command):
    command = (command or '').lstrip()
    if re.match(r'git\b', command):
        return 'git'
    if BUILD_COMMAND.search(command):
        return 'buildTest'
    return 'terminal'


def classify_tool(name, arguments):
    if name == 'Read':
        return 'read'
    if name in ('Edit', 'Write', 'MultiEdit', 'NotebookEdit', 'apply_patch'):
        return 'editWrite'
    if name in ('Grep', 'Glob', 'LS', 'TodoRead', 'TodoWrite'):
        return 'search'
    if name in ('Agent', 'Task'):
        return 'subagents'
    if name in ('WebFetch', 'WebSearch'):
        return 'web'
    if name in ('Bash', 'shell_command', 'shell', 'exec_command', 'PowerShell'):
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except ValueError:
                return classify_command(arguments)
        if isinstance(arguments, dict):
            command = arguments.get('command') or arguments.get('cmd') or ''
            if isinstance(command, list):
                command = ' '.join(str(part) for part in command)
            return classify_command(command)
        return 'terminal'
    return None


def parse_stamp(text):
    if not isinstance(text, str):
        return 0
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')).timestamp() * 1000
    except ValueError:
        return 0


def to_number(value):
    return value if isinstance(value, (int, float)) and value > 0 else 0


def get_project(cwd):
    if not cwd:
        return ''
    return re.split(r'[\\/]', cwd.rstrip('\\/'))[-1] or cwd


SCHEMA = '''
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY, provider TEXT, size INTEGER, mtime REAL,
    offset INTEGER, state TEXT);
CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY, file TEXT, provider TEXT, ts INTEGER, model TEXT,
    session TEXT, project TEXT, input INTEGER, output INTEGER,
    cache_write INTEGER, cache_read INTEGER, reasoning INTEGER,
    cost REAL, saved REAL);
CREATE INDEX IF NOT EXISTS entries_ts ON entries (ts);
CREATE INDEX IF NOT EXISTS entries_file ON entries (file);
CREATE INDEX IF NOT EXISTS entries_session ON entries (session);
CREATE TABLE IF NOT EXISTS tools (
    id TEXT PRIMARY KEY, file TEXT, provider TEXT, ts INTEGER, session TEXT,
    category TEXT, tokens REAL);
CREATE INDEX IF NOT EXISTS tools_ts ON tools (ts);
CREATE INDEX IF NOT EXISTS tools_file ON tools (file);
CREATE INDEX IF NOT EXISTS tools_session ON tools (session);
CREATE TABLE IF NOT EXISTS sessions (
    key TEXT PRIMARY KEY, provider TEXT, file TEXT, session TEXT, cwd TEXT,
    project TEXT, model TEXT, source TEXT, started INTEGER, last INTEGER,
    context INTEGER, context_max INTEGER);
CREATE TABLE IF NOT EXISTS limits (
    provider TEXT, name TEXT, ts INTEGER, percent REAL, resets_at INTEGER,
    PRIMARY KEY (provider, name, ts));
'''

UPSERT_ENTRY = '''
INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (id) DO UPDATE SET
    input = excluded.input, output = excluded.output,
    cache_write = excluded.cache_write, cache_read = excluded.cache_read,
    reasoning = excluded.reasoning, cost = excluded.cost, saved = excluded.saved
WHERE excluded.input + excluded.output + excluded.cache_write + excluded.cache_read
    > entries.input + entries.output + entries.cache_write + entries.cache_read
'''


class Indexer:

    def __init__(self, db, path, provider, state):
        self.db = db
        self.path = path
        self.provider = provider
        self.state = state
        self.entries = []
        self.tools = []
        self.limits = []

    def add_entry(self, key, stamp, model, session, project, fresh, output,
                  written, read, reasoning=0, written_long=0):
        if fresh + output + written + read <= 0:
            return
        cost, saved = estimate_cost(model, stamp, fresh, output, written, read, written_long)
        self.entries.append((key, self.path, self.provider, int(stamp), model, session,
                             project, fresh, output, written, read, reasoning, cost, saved))

    def add_tool(self, key, stamp, session, category, tokens):
        self.tools.append((key, self.path, self.provider, int(stamp), session, category, tokens))

    def add_limits(self, stamp, rates):
        for name in ('primary', 'secondary'):
            window = rates.get(name) or {}
            if window.get('resets_at'):
                self.limits.append((self.provider, name, int(stamp),
                                    window.get('used_percent') or 0, int(window['resets_at'])))

    def flush(self):
        if self.entries:
            self.db.executemany(UPSERT_ENTRY, self.entries)
        if self.tools:
            self.db.executemany('INSERT OR IGNORE INTO tools VALUES (?, ?, ?, ?, ?, ?, ?)',
                                self.tools)
        if self.limits:
            self.db.executemany('INSERT OR IGNORE INTO limits VALUES (?, ?, ?, ?, ?)', self.limits)
        self.entries = []
        self.tools = []
        self.limits = []


def read_claude_line(indexer, line):
    state = indexer.state
    if b'"assistant"' not in line or b'"usage"' not in line:
        if b'"cwd"' in line and not state.get('cwd'):
            try:
                record = json.loads(line)
            except ValueError:
                return
            state['cwd'] = record.get('cwd') or ''
        return
    try:
        record = json.loads(line)
    except ValueError:
        return
    if record.get('type') != 'assistant':
        return
    message = record.get('message') or {}
    usage = message.get('usage') or record.get('usage')
    key = message.get('id') or record.get('requestId')
    if not usage or not key:
        return

    stamp = parse_stamp(record.get('timestamp'))
    model = message.get('model') or record.get('model') or 'claude'
    session = record.get('sessionId') or state.get('session') or ''
    state['session'] = session
    state['cwd'] = record.get('cwd') or state.get('cwd', '')
    state['source'] = record.get('entrypoint') or state.get('source', '')
    project = get_project(state['cwd'])

    fresh = to_number(usage.get('input_tokens'))
    output = to_number(usage.get('output_tokens'))
    written = to_number(usage.get('cache_creation_input_tokens'))
    written_long = to_number((usage.get('cache_creation') or {}).get('ephemeral_1h_input_tokens'))
    read = to_number(usage.get('cache_read_input_tokens'))
    thinking = to_number((usage.get('output_tokens_details') or {}).get('thinking_tokens'))
    indexer.add_entry('claude:' + key, stamp, model, session, project, fresh, output,
                      written, read, thinking, written_long)

    if model != '<synthetic>' and fresh + written + read > 0:
        state['model'] = model
        state['context'] = fresh + written + read
    state['last'] = max(state.get('last', 0), stamp)
    state['started'] = state.get('started') or stamp

    blocks = [block for block in (message.get('content') or [])
              if isinstance(block, dict) and block.get('type') == 'tool_use']
    for block in blocks:
        category = classify_tool(block.get('name'), block.get('input'))
        if category and block.get('id'):
            indexer.add_tool('claude:' + block['id'], stamp, session, category,
                             output / float(len(blocks)))


def read_codex_line(indexer, line):
    state = indexer.state
    interesting = (b'"session_meta"', b'"turn_context"', b'"token_usage_record"',
                   b'"token_count"', b'"function_call"', b'"custom_tool_call"')
    if not any(token in line for token in interesting):
        return
    try:
        record = json.loads(line)
    except ValueError:
        return
    kind = record.get('type')
    payload = record.get('payload') or {}
    stamp = parse_stamp(record.get('timestamp'))
    session = state.get('session', '')

    if kind == 'session_meta':
        if not state.get('session'):
            state['session'] = payload.get('id') or payload.get('session_id') or ''
            state['cwd'] = payload.get('cwd') or ''
            state['source'] = payload.get('originator') or payload.get('source') or ''
            state['created'] = parse_stamp(payload.get('timestamp'))
            # a fork repeats its parent's lines from before its own creation
            state['forked'] = bool(payload.get('forked_from_id'))
        return
    if kind == 'turn_context':
        state['model'] = payload.get('model') or state.get('model', '')
        return
    if state.get('forked') and stamp < state.get('created', 0):
        return

    model = state.get('model') or 'codex'
    project = get_project(state.get('cwd', ''))

    if kind == 'response_item' and payload.get('type') in ('function_call', 'custom_tool_call'):
        category = classify_tool(payload.get('name'),
                                 payload.get('arguments') or payload.get('input'))
        if category:
            key = payload.get('call_id') or payload.get('id') or hashlib.sha1(line).hexdigest()
            indexer.add_tool('codex:' + key, stamp, session, category, 0)
        return

    if kind == 'token_usage_record':
        usage = payload.get('usage') or {}
        response = payload.get('response_id')
        key = 'codex:response:' + response if response else \
            'codex:line:' + hashlib.sha1(line).hexdigest()
        state['structured'] = True
    elif kind == 'event_msg' and payload.get('type') == 'token_count':
        info = payload.get('info') or {}
        state['context_max'] = to_number(info.get('model_context_window')) or \
            state.get('context_max', 0)
        if payload.get('rate_limits'):
            state['rate_limits'] = payload['rate_limits']
            state['rate_stamp'] = stamp
            indexer.add_limits(stamp, payload['rate_limits'])
        # token_count repeats the token_usage_record newer logs write per response
        if state.get('structured'):
            return
        usage = info.get('last_token_usage') or {}
        total = info.get('total_token_usage') or {}
        key = 'codex:observation:' + hashlib.sha1(json.dumps(
            [session, record.get('timestamp'), total], sort_keys=True).encode()).hexdigest()
    else:
        return

    raw = to_number(usage.get('input_tokens'))
    read = min(raw, to_number(usage.get('cached_input_tokens')))
    output = to_number(usage.get('output_tokens'))
    reasoning = to_number(usage.get('reasoning_output_tokens'))
    indexer.add_entry(key, stamp, model, session, project, raw - read, output, 0, read, reasoning)
    if raw:
        state['context'] = raw
    state['last'] = max(state.get('last', 0), stamp)
    state['started'] = state.get('started') or stamp


READERS = {'claude': read_claude_line, 'codex': read_codex_line}


class UsageIndex:

    def __init__(self, path=INDEX_PATH):
        self.path = path
        self.lock = threading.Lock()
        self.progress = None

    def connect(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        db = sqlite3.connect(self.path, timeout=30)
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA synchronous=NORMAL')
        db.executescript(SCHEMA)
        row = db.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone()
        if row is None or row[0] != str(SCHEMA_VERSION):
            for table in ('files', 'entries', 'tools', 'sessions'):
                db.execute(f'DELETE FROM {table}')
            db.execute("INSERT OR REPLACE INTO meta VALUES ('schema', ?)", (str(SCHEMA_VERSION),))
            db.commit()
        if db.execute("SELECT 1 FROM meta WHERE key = 'limit_history'").fetchone() is None:
            # every Codex reply logs the limits, so reading them once more fills the history
            db.execute("DELETE FROM files WHERE provider = 'codex'")
            db.execute("INSERT INTO meta VALUES ('limit_history', '1')")
            db.commit()
        return db

    def list_files(self, provider):
        found = []

        def walk(folder, remote):
            try:
                entries = list(os.scandir(folder))
            except OSError:
                return
            for entry in entries:
                if entry.name.startswith('.'):
                    continue
                if entry.is_dir():
                    walk(entry.path, remote)
                elif entry.name.lower().endswith('.jsonl'):
                    found.append((entry.path, entry.stat() if remote else None))

        for root in ROOTS[provider]:
            walk(root, root.startswith('\\\\'))
        return found

    def update(self, on_progress=None):
        with self.lock:
            db = self.connect()
            try:
                self.update_locked(db, on_progress)
            finally:
                db.close()

    def update_locked(self, db, on_progress):
        known = {row[0]: row[1:] for row in
                 db.execute('SELECT path, size, mtime, offset, state FROM files')}
        work = []
        now = time.time()
        for provider in READERS:
            for path, listed in self.list_files(provider):
                previous = known.get(path)
                if previous and listed and previous[0] == listed.st_size and \
                        previous[1] == listed.st_mtime and now - listed.st_mtime > REMOTE_IDLE:
                    continue
                try:
                    stat = os.stat(path)
                except OSError:
                    continue
                if previous and previous[0] == stat.st_size and previous[1] == stat.st_mtime:
                    continue
                work.append((provider, path, stat, previous))

        total = sum(stat.st_size - (previous[2] if previous and previous[2] <= stat.st_size else 0)
                    for provider, path, stat, previous in work) or 1
        if total < PROGRESS_MIN_BYTES:
            on_progress = None
        done = 0
        for provider, path, stat, previous in work:
            offset = previous[2] if previous else 0
            state = json.loads(previous[3]) if previous and previous[3] else {}
            if offset > stat.st_size:
                for table in ('entries', 'tools'):
                    db.execute(f'DELETE FROM {table} WHERE file = ?', (path,))
                offset = 0
                state = {}
            done += self.read_file(db, provider, path, offset, state, stat)
            if on_progress:
                on_progress(min(1.0, done / float(total)))

    def read_file(self, db, provider, path, offset, state, stat):
        indexer = Indexer(db, path, provider, state)
        reader = READERS[provider]
        consumed = 0
        try:
            with open(path, 'rb') as handle:
                handle.seek(offset)
                for line in handle:
                    # an unfinished last line is read again next time
                    if not line.endswith(b'\n'):
                        break
                    consumed += len(line)
                    reader(indexer, line)
                    if len(indexer.entries) >= 2000:
                        indexer.flush()
        except OSError:
            return 0
        indexer.flush()

        if state.get('session'):
            context_max = state.get('context_max') or (
                LONG_CONTEXT if '1m' in (state.get('model') or '').lower() or
                state.get('context', 0) > CLAUDE_CONTEXT else CLAUDE_CONTEXT)
            db.execute('INSERT OR REPLACE INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                       (provider + ':' + path, provider, path, state['session'],
                        state.get('cwd', ''), get_project(state.get('cwd', '')),
                        state.get('model', ''), state.get('source', ''),
                        int(state.get('started', 0)), int(state.get('last', 0)),
                        int(state.get('context', 0)), int(context_max)))
        if state.get('rate_limits'):
            row = db.execute("SELECT value FROM meta WHERE key = 'codex_limits'").fetchone()
            latest = json.loads(row[0]) if row else {}
            if state.get('rate_stamp', 0) >= latest.get('stamp', 0):
                db.execute("INSERT OR REPLACE INTO meta VALUES ('codex_limits', ?)",
                           (json.dumps({'stamp': state['rate_stamp'],
                                        'limits': state['rate_limits']}),))
        db.execute('INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?, ?, ?)',
                   (path, provider, stat.st_size, stat.st_mtime, offset + consumed,
                    json.dumps(state)))
        db.commit()
        return consumed

    def query(self, sql, args=()):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            return db.execute(sql, args).fetchall()
        finally:
            db.close()

    def add_limits(self, provider, stamp, rows):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.executescript(SCHEMA)
            db.executemany('INSERT OR IGNORE INTO limits VALUES (?, ?, ?, ?, ?)',
                           [(provider, name, int(stamp * 1000), percent, int(resets_at))
                            for name, percent, resets_at in rows])
            db.execute('DELETE FROM limits WHERE ts < ?', (int((stamp - LIMIT_KEEP) * 1000),))
            db.commit()
        finally:
            db.close()

    def get_meta(self, key):
        rows = self.query('SELECT value FROM meta WHERE key = ?', (key,))
        return json.loads(rows[0][0]) if rows else None

    def set_meta(self, key, value):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.execute('INSERT OR REPLACE INTO meta VALUES (?, ?)', (key, json.dumps(value)))
            db.commit()
        finally:
            db.close()


def read_antigravity():
    rows = []
    for path in ANTIGRAVITY_DBS:
        if not os.path.exists(path):
            continue
        try:
            # read-only so the app's live database is never locked
            connection = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=2)
            try:
                found = connection.execute(
                    'SELECT conversation_id, last_modified_time, step_count, workspace_uris '
                    'FROM conversation_summaries').fetchall()
            finally:
                connection.close()
        except sqlite3.Error:
            continue
        for conversation, stamp, steps, workspaces in found:
            moment = parse_stamp(str(stamp).replace(' ', 'T', 1))
            rows.append((conversation, moment, steps or 0, workspaces or ''))
    return rows
