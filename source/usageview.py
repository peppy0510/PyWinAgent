# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

사용량 페이지의 웹뷰 판. 같은 값을 `usagebox` 는 캔버스에 손으로 그리고 여기는
HTML 에 맡긴다. mainapp 의 import 한 줄로 갈아 끼운다 (honeypot 의
wxmain/wvmain/wemain 과 같은 짜임새).

Edge(Chromium) 백엔드를 쓴다. honeypot 의 `wxmain.py` 는 IE 에뮬레이션을 켜지만
이 PC 에는 WebView2 런타임이 있어 그럴 이유가 없다.
'''


import json
import os
import threading
import wx
import wx.html2

import usagedata


PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'usage.htm')

# 페이지가 CSS 변수로 받는 색. 테마가 바뀌면 이만큼만 다시 넘긴다.
TINTS = ('bg', 'face', 'rim', 'text', 'dim', 'accent', 'mint', 'grid', 'warn', 'close')


def get_backend():
    edge = getattr(wx.html2, 'WebViewBackendEdge', None)
    if edge and wx.html2.WebView.IsBackendAvailable(edge):
        return edge
    return wx.html2.WebViewBackendDefault


def build_payload(data):
    '''파이썬 쪽 자료를 그대로 넘길 수 없다 — 활동 표의 키가 (날짜, 시) 짝이라
    JSON 이 되지 않는다. 날짜마다 24 칸짜리 줄로 편다.'''
    days = data['days']
    hours = [[data['hours'].get((day, hour), 0) for hour in range(24)]
             for day in days]

    limits = data['limits']
    if limits is not None:
        limits = [{'name': limit['name'], 'percent': limit['percent'],
                   'severity': limit['severity'],
                   'when': usagedata.format_remaining(limit['remains'])}
                  for limit in limits]

    return {'cost': data['cost'], 'ratio': data['ratio'], 'saved': data['saved'],
            'calls': data['calls'], 'sessions': data['sessions'],
            'trend': data['trend'], 'days': days, 'hours': hours, 'limits': limits}


class UsageView(wx.Panel):

    def __init__(self, parent, theme):
        super().__init__(parent)
        self.theme = theme
        self.loading = False
        self.ready = False

        self.view = wx.html2.WebView.New(self, backend=get_backend())
        self.view.EnableContextMenu(False)
        # ★핸들러는 SetPage 보다 먼저 걸어야 한다. 나중에 걸면 페이지가 뜨면서
        # 보내는 첫 메시지를 통째로 놓친다.
        self.view.AddScriptMessageHandler('bridge')
        self.view.Bind(wx.html2.EVT_WEBVIEW_SCRIPT_MESSAGE_RECEIVED, self.on_message)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.load_page()

    def load_page(self):
        try:
            with open(PAGE, encoding='utf-8') as file:
                self.view.SetPage(file.read(), '')
        except OSError:
            self.view.SetPage('<body>usage.htm is missing</body>', '')

    def on_size(self, event):
        self.view.SetSize(0, 0, *self.GetClientSize())
        event.Skip()

    def call(self, name, value):
        self.view.RunScriptAsync('%s(%s)' % (name, json.dumps(value)))

    def apply_theme(self, theme):
        self.theme = theme
        self.SetBackgroundColour(wx.Colour(theme['bg']))
        if self.ready:
            self.push_theme()

    def push_theme(self):
        tints = {key: self.theme[key] for key in TINTS}
        tints['dark'] = self.theme['titlebar_dark']
        self.call('setTheme', tints)

    def on_message(self, event):
        message = event.GetString()
        if message == 'ready':
            self.ready = True
            self.push_theme()
            self.reload()
        elif message == 'reload':
            self.reload()

    def reload(self):
        if self.loading:
            return
        self.loading = True
        threading.Thread(target=self.gather, daemon=True).start()

    def gather(self):
        try:
            data = usagedata.collect()
        except Exception:
            data = None
        # 페이지를 건드리는 것은 주 실에서만.
        wx.CallAfter(self.settle, data)

    def settle(self, data):
        self.loading = False
        if data is None:
            return
        self.call('render', build_payload(data))

    def tick(self):
        pass
