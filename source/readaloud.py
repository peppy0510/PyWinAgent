# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

description:
Global read-aloud hotkey: copies the selection in any app and reads it aloud.
'''


import subprocess
import threading
import time

import win32api
import win32clipboard
import win32con
import wx

import ttsconfig


HOTKEY_ID = 0x5241
DEFAULT_HOTKEY = 'Ctrl+Alt+Shift+9'

MODIFIERS = (
    ('Ctrl', wx.MOD_CONTROL, win32con.VK_CONTROL),
    ('Alt', wx.MOD_ALT, win32con.VK_MENU),
    ('Shift', wx.MOD_SHIFT, win32con.VK_SHIFT),
    ('Win', wx.MOD_WIN, win32con.VK_LWIN),
)

KEYS = {chr(code): code for code in range(ord('A'), ord('Z') + 1)}
KEYS.update({chr(code): code for code in range(ord('0'), ord('9') + 1)})
KEYS.update({f'F{number}': 0x6F + number for number in range(1, 25)})
KEYS.update({f'Num{number}': 0x60 + number for number in range(10)})
KEYS.update({'Space': 0x20, 'PageUp': 0x21, 'PageDown': 0x22, 'End': 0x23, 'Home': 0x24,
             'Insert': 0x2D, 'Delete': 0x2E, 'Pause': 0x13})
KEY_NAMES = {code: name for name, code in KEYS.items()}
FUNCTION_KEYS = set(range(0x70, 0x88))

RELEASE_TIMEOUT = 1.8
CAPTURE_TIMEOUT = 15.0


def is_down(code):
    return bool(win32api.GetAsyncKeyState(code) & 0x8000)


def is_win_down():
    return is_down(win32con.VK_LWIN) or is_down(win32con.VK_RWIN)


def parse(text):
    # 'Ctrl+Alt+Shift+9' -> (wx modifiers, virtual key, keys to wait on)
    modifiers = 0
    held = []
    key = None
    for part in (text or '').split('+'):
        part = part.strip()
        modifier = next((item for item in MODIFIERS if item[0].lower() == part.lower()), None)
        if modifier:
            modifiers |= modifier[1]
            held.append(modifier[2])
            continue
        key = next((code for name, code in KEYS.items() if name.lower() == part.lower()), None)
    if key is None or not (modifiers or key in FUNCTION_KEYS):
        return None
    return modifiers, key, tuple(held) + (key,)


def capture():
    # waits for a combination, returns its text, or None on Esc or timeout
    deadline = time.monotonic() + CAPTURE_TIMEOUT
    while any(is_down(code) for code in KEY_NAMES) and time.monotonic() < deadline:
        time.sleep(0.015)
    while time.monotonic() < deadline:
        time.sleep(0.015)
        if is_down(win32con.VK_ESCAPE):
            return None
        key = next((code for code in KEY_NAMES if is_down(code)), None)
        if key is None:
            continue
        names = [name for name, _, code in MODIFIERS
                 if (is_win_down() if code == win32con.VK_LWIN else is_down(code))]
        if not names and key not in FUNCTION_KEYS:
            continue
        while is_down(key):
            time.sleep(0.015)
        return '+'.join(names + [KEY_NAMES[key]])
    return None


def send_copy():
    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    win32api.keybd_event(ord('C'), 0, 0, 0)
    win32api.keybd_event(ord('C'), 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)


def read_clipboard():
    # the source app may still be writing, so try a few times
    for _ in range(8):
        try:
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                    text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                    if text:
                        return text
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            pass
        time.sleep(0.06)
    return ''


def read_selection(held):
    # held modifiers would turn the synthetic Ctrl+C into Ctrl+Alt+C
    deadline = time.monotonic() + RELEASE_TIMEOUT
    while time.monotonic() < deadline and (
            any(is_down(code) for code in held) or is_win_down()):
        time.sleep(0.015)
    time.sleep(0.04)
    send_copy()
    time.sleep(0.12)
    text = read_clipboard()
    if text.strip():
        command = [ttsconfig.get_pythonw(), ttsconfig.SPEAK_SCRIPT, '--interrupt', '--text', text]
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=subprocess.CREATE_NO_WINDOW)


class Hotkey:

    def __init__(self, window, text=DEFAULT_HOTKEY):
        self.window = window
        self.active = False
        self.text = text
        self.held = ()
        window.Bind(wx.EVT_HOTKEY, self.on_hotkey, id=HOTKEY_ID)

    def register(self):
        parsed = parse(self.text)
        if not parsed:
            return False
        modifiers, key, self.held = parsed
        return bool(self.window.RegisterHotKey(HOTKEY_ID, modifiers, key))

    def set_active(self, active):
        if active == self.active:
            return self.active
        if active:
            self.active = self.register()
        else:
            self.window.UnregisterHotKey(HOTKEY_ID)
            self.active = False
        return self.active

    def set_text(self, text):
        # keeps the old combination when the new one is taken
        if not parse(text):
            return False
        was_active = self.active
        self.set_active(False)
        old = self.text
        self.text = text
        if was_active and not self.set_active(True):
            self.text = old
            self.set_active(True)
            return False
        return True

    def on_hotkey(self, event):
        threading.Thread(target=read_selection, args=(self.held,), daemon=True).start()
