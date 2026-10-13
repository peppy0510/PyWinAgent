# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import math
import os

from PIL import Image
from PIL import ImageDraw


SPARK = (24, 30, 64, 255)
TILE_STOPS = ((70, 150, 255), (120, 90, 240), (250, 150, 80))

SPARK_RADIUS = 0.4
SPARK_POWER = 3.4
SIMPLIFY_BELOW = 32
SMALL_SPARK_POWER = 2.6

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

SCALE = 8


def blend(stops, t):
    t = max(0.0, min(1.0, t))
    index = min(len(stops) - 2, int(t * (len(stops) - 1)))
    local = t * (len(stops) - 1) - index
    a, b = stops[index], stops[index + 1]
    return tuple(int(a[i] + (b[i] - a[i]) * local) for i in range(3)) + (255,)


def draw_gradient(canvas):
    image = Image.new('RGBA', (canvas, canvas))
    pixels = image.load()
    for y in range(canvas):
        for x in range(canvas):
            pixels[x, y] = blend(TILE_STOPS, (x * 0.55 + y * 0.45) / canvas)
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

    inset = canvas * 0.03
    mask = Image.new('L', (canvas, canvas), 0)
    ImageDraw.Draw(mask).rounded_rectangle((inset, inset, canvas - inset - 1, canvas - inset - 1),
                                           radius=canvas * 0.23, fill=255)
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
    frames[-1].save(os.path.join(path, 'icon.ico'), format='ICO',
                    sizes=[(size, size) for size in SIZES],
                    append_images=frames[:-1])
    print('[ ICON CREATED ] [ {} ]'.format(os.path.join(path, 'icon.ico')))


if __name__ == '__main__':
    main()
