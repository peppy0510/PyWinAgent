# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import hashlib
import json
import os
import re
import subprocess
import threading

from usageindex import HOME


CACHE_PATH = os.path.join(os.environ.get('APPDATA', HOME), 'PyWinAgent', 'git-stats.json')
MARKER = '@@'
GIT_JOBS = 6

PATH_RULES = (
    ('vendor', (r'(^|/)(node_modules|vendor|third[_-]?party|\.yarn|bower_components)/',)),
    ('test_code', (r'(\.|^)(test|spec)\.[a-z0-9]+$', r'(^|/)(tests?|__tests__)/')),
    ('schema_migration', (r'(^|/)(migrations?)/', r'\.(sql|prisma|proto)$',
                          r'schema\.(graphql|prisma|sql)$')),
    ('docs_spec', (r'\.(md|mdx|markdown|rst|adoc|txt)$',
                   r'(^|/)(license|licence|copying|notice|authors)$', r'(^|/)(docs?|spec|specs)/')),
    ('config_build', (r'\.(json|ya?ml|toml|ini|cfg|conf|lock|dockerfile|gradle)$',
                      r'(^|/)(dockerfile|makefile|\.gitignore)$', r'(^|/)\.github/',
                      r'\.(config|rc)\.[a-z0-9]+$')),
    ('asset', (r'\.(png|jpe?g|gif|svg|ico|webp|woff2?|ttf|otf|eot|mp4|mp3|wav|pdf)$',
               r'(^|/)(assets?|public|static|images?|fonts?)/')),
)
PATH_PATTERNS = tuple((name, tuple(re.compile(rule) for rule in rules))
                      for name, rules in PATH_RULES)


def classify_path(path):
    lower = path.replace('\\', '/').lower()
    for name, patterns in PATH_PATTERNS:
        if any(pattern.search(lower) for pattern in patterns):
            return name
    return 'product_code'


def run_git(cwd, *args, timeout=60):
    if cwd.startswith('/') and os.name == 'nt':
        # git over \\wsl.localhost is tens of times slower than git inside WSL; the default
        # distro, whose home the sessions come from
        command = ['wsl.exe', '-e', 'git', '-C', cwd] + list(args)
    else:
        command = ['git', '-C', cwd] + list(args)
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    try:
        done = subprocess.run(command, capture_output=True, timeout=timeout,
                              creationflags=flags)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.decode('utf-8', 'replace')


def run_parallel(function, items):
    # threads, not asyncio or concurrent.futures: those imports cost 4-7 MB here (measured)
    results = [None] * len(items)
    jobs = threading.Semaphore(GIT_JOBS)

    def work(index, item):
        with jobs:
            results[index] = function(item)

    threads = [threading.Thread(target=work, args=(index, item), daemon=True)
               for index, item in enumerate(items)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def find_repo(cwd):
    output = run_git(cwd, 'rev-parse', '--show-toplevel', timeout=15)
    if not output:
        return None
    top = output.strip()
    return top


def get_heads(top):
    output = run_git(top, 'for-each-ref', '--format=%(objectname)', 'refs/heads', timeout=15)
    if output is None:
        return None
    return hashlib.sha1(output.encode()).hexdigest()


def read_log(top):
    email = (run_git(top, 'config', 'user.email', timeout=15) or '').strip()
    args = ['log', '--branches', '--no-merges', '--date=short',
            '--format=' + MARKER + '%ad', '--numstat']
    if email:
        args.append('--author=' + email)
    output = run_git(top, *args, timeout=120)
    if output is None:
        return None
    days = {}
    day = None
    for line in output.splitlines():
        if line.startswith(MARKER):
            day = days.setdefault(line[len(MARKER):].strip(),
                                  {'commits': 0, 'added': 0, 'removed': 0, 'paths': {}})
            day['commits'] += 1
            continue
        parts = line.split('\t')
        if day is None or len(parts) != 3:
            continue
        if not parts[0].isdigit() or not parts[1].isdigit():
            continue
        added, removed = int(parts[0]), int(parts[1])
        day['added'] += added
        day['removed'] += removed
        slot = day['paths'].setdefault(classify_path(parts[2]), [0, 0])
        slot[0] += added
        slot[1] += removed
    return days


def load_cache():
    try:
        with open(CACHE_PATH, encoding='utf-8') as file:
            return json.load(file)
    except Exception:
        return {'repos': {}, 'folders': {}}


def save_cache(cache):
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, 'w', encoding='utf-8') as file:
            json.dump(cache, file)
    except OSError:
        pass


def collect(folders):
    cache = load_cache()
    folders = [folder for folder in folders if folder]
    unknown = list(dict.fromkeys(folder for folder in folders
                                 if cache['folders'].get(folder) is None))
    for folder, top in zip(unknown, run_parallel(find_repo, unknown)):
        if top:
            cache['folders'][folder] = top
    repos = list(dict.fromkeys(cache['folders'][folder] for folder in folders
                               if cache['folders'].get(folder)))

    heads = run_parallel(get_heads, repos)
    stale = [(top, head) for top, head in zip(repos, heads) if head is not None and
             (cache['repos'].get(top) or {}).get('heads') != head]
    for (top, head), days in zip(stale, run_parallel(read_log, [top for top, _ in stale])):
        if days is not None:
            cache['repos'][top] = {'heads': head, 'days': days}

    result = {}
    for top, head in zip(repos, heads):
        stored = cache['repos'].get(top)
        if head is not None and stored and stored.get('heads') == head:
            result[top] = stored['days']
    save_cache(cache)
    return result
