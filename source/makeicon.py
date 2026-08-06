# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

assets/icon 의 icon.ico 와 icon.png 를 만든다.

마크는 둥근 사각형 안의 세로 막대다. 소리의 파형으로도, 사용량 그래프로도
읽혀 이 앱이 다루는 두 가지를 한 그림이 덮는다.

PyWinClock 의 makeicon 은 문자판을 그대로 쓰려고 wx 로 그리지만, 여기는 다시
쓸 그림이 없고 모서리 바깥을 비워야 해서 알파를 곧바로 다루는 쪽을 골랐다.
작은 치수는 줄여 그린다 — 256 을 깎아 내리면 막대가 회색 죽으로 뭉갠다.
'''


import os

from PIL import Image
from PIL import ImageDraw


BADGE = (47, 127, 230, 255)
BAR = (255, 255, 255, 255)

# 이보다 작으면 막대를 셋으로 줄이고 굵게 그린다.
SIMPLIFY_BELOW = 32

TALL = (0.42, 0.68, 1.00, 0.62, 0.34)
SHORT = (0.55, 1.00, 0.44)

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

# 계단을 없애려고 이 배율로 그린 뒤 줄인다.
SCALE = 8


def draw_mark(size):
    canvas = size * SCALE
    image = Image.new('RGBA', (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    inset = canvas * 0.02
    draw.rounded_rectangle((inset, inset, canvas - inset - 1, canvas - inset - 1),
                           radius=canvas * 0.22, fill=BADGE)

    if size < SIMPLIFY_BELOW:
        heights, width, gap = SHORT, 0.17, 0.105
    else:
        heights, width, gap = TALL, 0.10, 0.065

    bar = canvas * width
    step = bar + canvas * gap
    span = step * len(heights) - canvas * gap
    left = (canvas - span) / 2
    middle = canvas / 2
    # 가장 긴 막대가 배지 안에서 숨 쉴 만큼만 자란다.
    reach = canvas * 0.29

    for index, height in enumerate(heights):
        x = left + step * index
        half = reach * height
        draw.rounded_rectangle((x, middle - half, x + bar - 1, middle + half),
                               radius=bar / 2, fill=BAR)

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
