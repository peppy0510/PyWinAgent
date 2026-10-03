# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

assets/icon 의 icon.ico 와 icon.png 를 만든다.

마크는 남색 타일 위의 구슬과 그 안의 흰 반짝이다. 반짝이는 흔히 AI 도우미를 가리키는
기호이고, 구슬의 파랑→보라→주황은 앱이 다루는 Claude(파랑)·Codex(주황)의 계열색을 잇는다.

반짝이는 초타원(|x|^(2/p) + |y|^(2/p) = 1)의 네 끝이다. p 가 클수록 날이 가늘다.
작은 치수는 날을 굵게 그린다 — 가는 날을 그대로 16px 로 줄이면 흰 점 하나로 뭉갠다.
'''


import math
import os

from PIL import Image
from PIL import ImageDraw


TILE = (24, 30, 64, 255)
SPARK = (255, 255, 255, 255)
ORB_STOPS = ((70, 150, 255), (120, 90, 240), (250, 150, 80))

ORB = (0.16, 0.84)
SPARK_RADIUS = 0.22
SPARK_POWER = 3.4
# 이보다 작으면 반짝이 날을 굵게 그린다.
SIMPLIFY_BELOW = 32
SMALL_SPARK_POWER = 2.6

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

# 계단을 없애려고 이 배율로 그린 뒤 줄인다.
SCALE = 8


def blend(stops, t):
    t = max(0.0, min(1.0, t))
    index = min(len(stops) - 2, int(t * (len(stops) - 1)))
    local = t * (len(stops) - 1) - index
    a, b = stops[index], stops[index + 1]
    return tuple(int(a[i] + (b[i] - a[i]) * local) for i in range(3)) + (255,)


def draw_gradient(canvas):
    '''왼쪽 위에서 오른쪽 아래로 흐르는 구슬 색. 가로를 조금 더 탄다.'''
    image = Image.new('RGBA', (canvas, canvas))
    pixels = image.load()
    for y in range(canvas):
        for x in range(canvas):
            pixels[x, y] = blend(ORB_STOPS, (x * 0.55 + y * 0.45) / canvas)
    return image


def get_sparkle(canvas, radius, power):
    middle = canvas / 2
    points = []
    for step in range(400):
        angle = 2 * math.pi * step / 400
        cos, sin = math.cos(angle), math.sin(angle)
        points.append((middle + radius * math.copysign(abs(cos) ** power, cos),
                       middle + radius * math.copysign(abs(sin) ** power, sin)))
    return points


def draw_mark(size):
    canvas = size * SCALE
    image = Image.new('RGBA', (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    inset = canvas * 0.03
    draw.rounded_rectangle((inset, inset, canvas - inset - 1, canvas - inset - 1),
                           radius=canvas * 0.23, fill=TILE)

    mask = Image.new('L', (canvas, canvas), 0)
    ImageDraw.Draw(mask).ellipse([canvas * edge for edge in (ORB[0], ORB[0], ORB[1], ORB[1])], fill=255)
    image.paste(draw_gradient(canvas), (0, 0), mask)

    power = SMALL_SPARK_POWER if size < SIMPLIFY_BELOW else SPARK_POWER
    ImageDraw.Draw(image).polygon(get_sparkle(canvas, canvas * SPARK_RADIUS, power), fill=SPARK)

    return image.resize((size, size), Image.LANCZOS)


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, 'assets', 'icon')
    os.makedirs(path, exist_ok=True)

    frames = [draw_mark(size) for size in SIZES]
    frames[-1].save(os.path.join(path, 'icon.png'))
    # ico 는 치수마다 따로 그린 그림을 담는다. Pillow 가 알아서 깎게 두면
    # 16px 이 뭉개진다.
    frames[-1].save(os.path.join(path, 'icon.ico'), format='ICO',
                    sizes=[(size, size) for size in SIZES],
                    append_images=frames[:-1])
    print('[ ICON CREATED ] [ {} ]'.format(os.path.join(path, 'icon.ico')))


if __name__ == '__main__':
    main()
