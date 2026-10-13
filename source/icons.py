# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import math
import wx


def get_pen(gc, colour, width):
    return gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(colour)).Width(width)
                        .Cap(wx.CAP_ROUND).Join(wx.JOIN_ROUND))


def draw_glyph(gc, name, cx, cy, size, colour, width=None):
    handler = HANDLERS.get(name)
    if handler is None:
        return
    width = width or max(1.0, size * 0.085)
    gc.SetPen(get_pen(gc, colour, width))
    gc.SetBrush(wx.TRANSPARENT_BRUSH)
    handler(gc, cx, cy, size, wx.Colour(colour), width)


def draw_sound(gc, cx, cy, size, colour, width):
    left = cx - size * 0.42
    neck = cx - size * 0.16
    body = size * 0.15
    cone = size * 0.34

    path = gc.CreatePath()
    path.MoveToPoint(left, cy - body)
    path.AddLineToPoint(neck, cy - body)
    path.AddLineToPoint(cx + size * 0.02, cy - cone)
    path.AddLineToPoint(cx + size * 0.02, cy + cone)
    path.AddLineToPoint(neck, cy + body)
    path.AddLineToPoint(left, cy + body)
    path.CloseSubpath()
    gc.SetPen(wx.TRANSPARENT_PEN)
    gc.SetBrush(wx.Brush(colour))
    gc.FillPath(path)

    gc.SetPen(get_pen(gc, colour, width))
    gc.SetBrush(wx.TRANSPARENT_BRUSH)
    for index, radius in enumerate((size * 0.20, size * 0.34)):
        path = gc.CreatePath()
        path.AddArc(cx + size * 0.08, cy, radius,
                    math.radians(-52), math.radians(52), True)
        gc.StrokePath(path)


def draw_chart(gc, cx, cy, size, colour, width):
    base = cy + size * 0.38
    gc.StrokeLine(cx - size * 0.42, base, cx + size * 0.42, base)

    bar = size * 0.17
    gc.SetPen(wx.TRANSPARENT_PEN)
    gc.SetBrush(wx.Brush(colour))
    for offset, height in ((-size * 0.28, 0.30), (0.0, 0.54), (size * 0.28, 0.42)):
        top = base - size * height
        gc.DrawRectangle(cx + offset - bar / 2, top, bar, base - top - width / 2)


def draw_settings(gc, cx, cy, size, colour, width):
    outer, inner, hub = size * 0.48, size * 0.33, size * 0.15
    steps = 16

    path = gc.CreatePath()
    for step in range(steps):
        angle = math.radians(step * 360.0 / steps)
        radius = outer if step % 2 == 0 else inner
        x, y = cx + radius * math.cos(angle), cy + radius * math.sin(angle)
        if step:
            path.AddLineToPoint(x, y)
        else:
            path.MoveToPoint(x, y)
    path.CloseSubpath()
    gc.StrokePath(path)
    gc.DrawEllipse(cx - hub, cy - hub, hub * 2, hub * 2)


def draw_menu(gc, cx, cy, size, colour, width):
    half = size * 0.42
    for offset in (-size * 0.30, 0.0, size * 0.30):
        gc.StrokeLine(cx - half, cy + offset, cx + half, cy + offset)


def draw_minimize(gc, cx, cy, size, colour, width):
    gc.StrokeLine(cx - size * 0.40, cy, cx + size * 0.40, cy)


def draw_maximize(gc, cx, cy, size, colour, width):
    span = size * 0.72
    gc.DrawRectangle(cx - span / 2, cy - span / 2, span, span)


def draw_restore(gc, cx, cy, size, colour, width):
    gc.DrawRectangle(cx - size * 0.38, cy - size * 0.22, size * 0.60, size * 0.60)
    path = gc.CreatePath()
    path.MoveToPoint(cx - size * 0.22, cy - size * 0.22)
    path.AddLineToPoint(cx - size * 0.22, cy - size * 0.38)
    path.AddLineToPoint(cx + size * 0.38, cy - size * 0.38)
    path.AddLineToPoint(cx + size * 0.38, cy + size * 0.22)
    path.AddLineToPoint(cx + size * 0.22, cy + size * 0.22)
    gc.StrokePath(path)


def draw_close(gc, cx, cy, size, colour, width):
    arm = size * 0.36
    gc.StrokeLine(cx - arm, cy - arm, cx + arm, cy + arm)
    gc.StrokeLine(cx - arm, cy + arm, cx + arm, cy - arm)


HANDLERS = {
    'sound': draw_sound,
    'chart': draw_chart,
    'settings': draw_settings,
    'menu': draw_menu,
    'minimize': draw_minimize,
    'maximize': draw_maximize,
    'restore': draw_restore,
    'close': draw_close,
}
