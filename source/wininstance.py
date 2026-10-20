# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import os
import psutil
import sys

from pathlib import Path


def has_process_authority(p):
    try:
        p.cwd()
        p.name()
    except Exception:
        return False
    return True


def get_current_process():
    pid = int(os.getpid())
    for p in psutil.process_iter():
        if p.pid == pid and has_process_authority(p):
            return p


def get_source_path():
    return str(Path(__file__).resolve().parent)


def has_running_instance():
    pid = int(os.getpid())
    source = get_source_path()
    # a venv launches through Scripts\python.exe, which shares our name and cwd
    ancestors = {p.pid for p in psutil.Process(pid).parents()}

    for p in psutil.process_iter():
        if p.pid == pid or p.pid in ancestors or not has_process_authority(p):
            continue

        if hasattr(sys, '_MEIPASS'):
            cp = get_current_process()
            if cp is not None and cp.name() == p.name():
                return True
            continue

        if p.name().lower() not in ('python.exe', 'pythonw.exe',):
            continue

        try:
            cmdline = p.cmdline()
        except Exception:
            continue

        if [True for v in cmdline if v.startswith(source)]:
            return True

    return False


def show_running_window(title):
    # the running copy may sit hidden in the tray; bring it back instead of doing nothing
    import win32con
    import win32gui
    hwnd = win32gui.FindWindow('wxWindowNR', title)
    if not hwnd:
        return
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE if win32gui.IsIconic(hwnd)
                        else win32con.SW_SHOW)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
