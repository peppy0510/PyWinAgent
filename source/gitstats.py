# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

에이전트가 일한 저장소의 커밋 통계 (사용량 페이지의 Code Output).

저장소는 세션 기록의 작업 폴더에서 찾는다. 각 저장소의 `user.email` 로 쓴
커밋만 센다. WSL 쪽 폴더(`/` 로 시작)는 `\\\\wsl.localhost` 로 건너가 Windows
git 을 돌리면 수십 배 느려서 `wsl.exe` 안의 git 을 부른다.

결과는 브랜치 끝 해시들을 열쇠로 저장해 두고, 바뀐 저장소만 다시 센다.
'''


import hashlib
import json
import os
import re
import subprocess

from usageindex import HOME


CACHE_PATH = os.path.join(os.environ.get('APPDATA', HOME), 'PyWinAgent', 'git-stats.json')
WSL_DISTRO = 'Ubuntu-24.04'
MARKER = '@@'

# WhereMyTokens 의 pathClassifier 를 옮겼다. 위에서부터 먼저 맞는 것.
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
        command = ['wsl.exe', '-d', WSL_DISTRO, '-e', 'git', '-C', cwd] + list(args)
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


def find_repo(cwd):
    '''(최상위 폴더, 저장소 열쇠). 저장소가 아니면 None.'''
    output = run_git(cwd, 'rev-parse', '--show-toplevel', timeout=15)
    if not output:
        return None
    top = output.strip()
    # WSL git 은 리눅스 경로, Windows git 은 C:/... 로 돌려준다. 그대로 쓴다.
    return top


def get_heads(top):
    output = run_git(top, 'for-each-ref', '--format=%(objectname)', 'refs/heads', timeout=15)
    if output is None:
        return None
    return hashlib.sha1(output.encode()).hexdigest()


def read_log(top):
    '''날짜마다 {commits, added, removed, paths: {분류: [added, removed]}}.'''
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
        # 바이너리 파일은 줄 수 자리에 '-' 가 온다.
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
    '''작업 폴더들 → 저장소별 날짜 통계. 바뀌지 않은 저장소는 저장해 둔 것을 쓴다.'''
    cache = load_cache()
    repos = {}
    for folder in folders:
        if not folder:
            continue
        top = cache['folders'].get(folder)
        if top is None:
            # 저장소가 아닌 폴더는 외우지 않는다. WSL 이 잠깐 꺼져 있던 것일 수 있다.
            top = find_repo(folder)
            if top:
                cache['folders'][folder] = top
        if top:
            repos[top] = True

    result = {}
    for top in repos:
        heads = get_heads(top)
        if heads is None:
            continue
        stored = cache['repos'].get(top)
        if not stored or stored.get('heads') != heads:
            days = read_log(top)
            if days is None:
                continue
            stored = {'heads': heads, 'days': days}
            cache['repos'][top] = stored
        result[top] = stored['days']
    save_cache(cache)
    return result
