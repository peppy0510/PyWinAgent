# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

description:
Installs the read-aloud hooks into Claude Code, on Windows and for every WSL user
who has run it, and takes the read-aloud hotkey
over from the agent toolkit. Whatever the toolkit had registered is kept aside
and put back when the feature is turned off.
'''


import json
import os
import shlex
import shutil
import subprocess
import sys
import winreg

import psutil

import ttsconfig


CLAUDE_SETTINGS = os.path.join(os.path.expanduser('~'), '.claude', 'settings.json')
LXSS_KEY = r'Software\Microsoft\Windows\CurrentVersion\Lxss'
BACKUP_DIR = os.path.join(ttsconfig.APPDATA, 'PyWinAgent', 'legacy')
HOOK_BACKUP = os.path.join(BACKUP_DIR, 'claude-hooks.json')
HOOK_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ttshook.py')
HOOK_FLAG = '--hook'
HOOK_EXE = 'PyWinAgent.exe'

HOOK_EVENTS = {'UserPromptSubmit': 'prompt', 'Stop': 'stop'}
HOOK_TIMEOUT = 30
TOOLKIT_HOOK = 'agent-toolkit\\tts\\hook.ps1'

STARTUP_DIR = os.path.join(ttsconfig.APPDATA, 'Microsoft', 'Windows', 'Start Menu',
                           'Programs', 'Startup')
LISTENER_NAME = 'readaloud-hotkey.vbs'
LISTENER_SCRIPT = 'readaloud-hotkey.ps1'


def get_python():
    path = os.path.join(os.path.dirname(sys.executable), 'python.exe')
    return path if os.path.exists(path) else sys.executable


def get_command(argument):
    # the packaged exe runs the hook itself; its scripts sit in a folder gone after it exits
    if hasattr(sys, 'frozen'):
        return f'& "{sys.executable}" {HOOK_FLAG} {argument}'
    return f'& "{get_python()}" "{HOOK_SCRIPT}" {argument}'


def get_wsl_command(argument):
    # sh runs the hook; the distro name lets the hook reach the transcript from Windows
    if hasattr(sys, 'frozen'):
        program, script = shlex.quote(sys.executable), HOOK_FLAG
    else:
        program, script = shlex.quote(get_python()), shlex.quote(HOOK_SCRIPT)
    return (f'WSLENV=WSL_DISTRO_NAME:$WSLENV "$(wslpath -u {program})" '
            f'{script} {argument}')


def get_hook(path, argument):
    if path == CLAUDE_SETTINGS:
        return {'type': 'command', 'shell': 'powershell', 'async': True,
                'timeout': HOOK_TIMEOUT, 'command': get_command(argument)}
    return {'type': 'command', 'async': True,
            'timeout': HOOK_TIMEOUT, 'command': get_wsl_command(argument)}


def get_running_distros():
    try:
        result = subprocess.run(['wsl.exe', '--list', '--running', '--quiet'],
                                capture_output=True, timeout=5,
                                creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return set()
    if result.returncode:
        return set()
    # UTF-16 unless WSL_UTF8 is set
    output = result.stdout
    text = output.decode('utf-16-le' if b'\0' in output else 'utf-8', 'replace')
    return {line.strip().lower() for line in text.splitlines() if line.strip()}


def list_distros(every):
    # reaching a stopped distro boots it, so only installing visits every one; a stopped
    # distro is not running Claude Code, so checking the running ones is enough
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, LXSS_KEY) as key:
            names = []
            for index in range(winreg.QueryInfoKey(key)[0]):
                with winreg.OpenKey(key, winreg.EnumKey(key, index)) as distro:
                    names.append(winreg.QueryValueEx(distro, 'DistributionName')[0])
    except OSError:
        return []
    if every:
        return names
    running = get_running_distros()
    return [name for name in names if name.lower() in running]


def get_homes(distro):
    root = rf'\\wsl.localhost\{distro}'
    homes = [os.path.join(root, 'root')]
    try:
        homes += [os.path.join(root, 'home', name)
                  for name in os.listdir(os.path.join(root, 'home'))]
    except OSError:
        pass
    return homes


def get_targets(every=False):
    # only where Claude Code has been run, so WSL without it is left alone
    targets = [CLAUDE_SETTINGS]
    for distro in list_distros(every):
        for home in get_homes(distro):
            if os.path.isdir(os.path.join(home, '.claude')):
                targets.append(os.path.join(home, '.claude', 'settings.json'))
    return targets


def read_settings(path=CLAUDE_SETTINGS):
    try:
        with open(path, encoding='utf-8') as file:
            settings = json.load(file)
    except FileNotFoundError:
        return {}
    return settings if isinstance(settings, dict) else {}


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + '.tmp'
    with open(temporary, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write('\n')
    os.replace(temporary, path)


def is_ours(hook):
    command = hook.get('command') or ''
    return 'ttshook.py' in command or (HOOK_EXE in command and f' {HOOK_FLAG} ' in command)


def is_toolkit(hook, argument):
    command = (hook.get('command') or '').replace('/', '\\')
    return TOOLKIT_HOOK in command and command.rstrip().endswith('-Event ' + argument)


def take_hooks(groups, keep):
    # drops the matching hooks and any group they leave empty
    taken = []
    result = []
    for group in groups:
        hooks = group.get('hooks') or []
        left = [hook for hook in hooks if keep(hook)]
        taken += [hook for hook in hooks if not keep(hook)]
        if left or not hooks:
            result.append(dict(group, hooks=left) if len(left) != len(hooks) else group)
    return result, taken


def has_ours(path):
    # None for a file this user cannot read, which no install could change either
    try:
        hooks = read_settings(path).get('hooks') or {}
    except (OSError, ValueError):
        return None
    return any(is_ours(hook) for groups in hooks.values()
               for group in groups for hook in group.get('hooks') or [])


def get_hook_state():
    installed = [found for found in map(has_ours, get_targets()) if found is not None]
    if all(installed):
        return 'installed'
    if any(installed):
        return 'partial'
    hooks = read_settings().get('hooks') or {}
    toolkit = any(is_toolkit(hook, argument) for event, argument in HOOK_EVENTS.items()
                  for group in hooks.get(event) or [] for hook in group.get('hooks') or [])
    return 'toolkit' if toolkit else 'missing'


def install_into(path):
    settings = read_settings(path)
    hooks = settings.setdefault('hooks', {})
    backup = {}
    for event, argument in HOOK_EVENTS.items():
        groups = hooks.get(event) or []
        groups, _ = take_hooks(groups, lambda hook: not is_ours(hook))
        if path == CLAUDE_SETTINGS:
            groups, taken = take_hooks(groups, lambda hook: not is_toolkit(hook, argument))
            if taken:
                backup[event] = taken
        groups.append({'matcher': '', 'hooks': [get_hook(path, argument)]})
        hooks[event] = groups
    if backup and not os.path.exists(HOOK_BACKUP):
        write_json(HOOK_BACKUP, backup)
    write_json(path, settings)


def remove_from(path):
    if not os.path.exists(path):
        return
    settings = read_settings(path)
    hooks = settings.get('hooks') or {}
    for event in list(hooks):
        groups, _ = take_hooks(hooks[event], lambda hook: not is_ours(hook))
        if groups:
            hooks[event] = groups
        else:
            del hooks[event]
    if path == CLAUDE_SETTINGS:
        try:
            with open(HOOK_BACKUP, encoding='utf-8') as file:
                backup = json.load(file)
        except (OSError, ValueError):
            backup = {}
        for event, taken in backup.items():
            hooks.setdefault(event, []).append({'matcher': '', 'hooks': taken})
    write_json(path, settings)
    if path == CLAUDE_SETTINGS and os.path.exists(HOOK_BACKUP):
        os.remove(HOOK_BACKUP)


def apply_everywhere(action):
    # one unwritable home must not keep the others from changing
    failed = []
    for path in get_targets(every=True):
        try:
            action(path)
        except (OSError, ValueError):
            failed.append(path)
    if failed:
        raise OSError('not written: ' + ', '.join(failed))


def install_hooks():
    apply_everywhere(install_into)


def remove_hooks():
    apply_everywhere(remove_from)


def find_listeners():
    found = []
    for process in psutil.process_iter(['name', 'cmdline']):
        try:
            if LISTENER_SCRIPT in ' '.join(process.info['cmdline'] or []):
                found.append(process)
        except (psutil.Error, TypeError):
            continue
    return found


def take_listener():
    # the toolkit polls the same keys, so both would read the selection at once
    source = os.path.join(STARTUP_DIR, LISTENER_NAME)
    if os.path.exists(source):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.move(source, os.path.join(BACKUP_DIR, LISTENER_NAME))
    for process in find_listeners():
        try:
            process.kill()
        except psutil.Error:
            pass


def restore_listener():
    saved = os.path.join(BACKUP_DIR, LISTENER_NAME)
    if not os.path.exists(saved):
        return
    target = os.path.join(STARTUP_DIR, LISTENER_NAME)
    shutil.move(saved, target)
    if not find_listeners():
        subprocess.Popen(['wscript.exe', target], creationflags=subprocess.CREATE_NO_WINDOW)
