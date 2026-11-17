# title_ru.py — генератор русского титула "ЦЕНТУРИОН" в стиле MINIT_TITLE.png
# Грань — золото, боковина — 3D-экструзия вниз-вправо с дизерингованным градиентом
# (2x2 Bayer), как текстурированная тень оригинала. Фон оливковый.
# Результат: decoded/cbm/MINIT_TITLE_RU.png (313x51, как оригинал).
# Шрифт/текст: python title_ru.py [fontfile] [text]
import os, sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
OUT = os.path.join(ROOT, 'decoded', 'cbm', 'MINIT_TITLE_RU.png')

W, H = 313, 51
BG = (113, 116, 93)
FACE = (192, 141, 82)
SHADES = [(63, 36, 23)]                               # однотонная короткая тень
DEPTH = 5
BAYER = ((0, 2), (3, 1))                              # 2x2 дизеринг

TEXT = sys.argv[2] if len(sys.argv) > 2 else 'ЦЕНТУРИОН'
FONT = sys.argv[1] if len(sys.argv) > 1 else r'C:\Windows\Fonts\times.ttf'

def render_mask(text, fontpath):
    """Маска букв 0/255, вписанная в ширину W-DEPTH и высоту H-DEPTH."""
    box_w, box_h = W - DEPTH, H - DEPTH
    size = box_h
    while size > 6:
        f = ImageFont.truetype(fontpath, size)
        m = Image.new('L', (W * 2, H * 2), 0)
        d = ImageDraw.Draw(m)
        d.text((W // 2, H // 2), text, font=f, fill=255, anchor='mm')
        bb = m.getbbox()
        if bb:
            w, h = bb[2] - bb[0], bb[3] - bb[1]
            if w <= box_w and h <= box_h:
                return m.crop(bb)
        size -= 1
    raise SystemExit('не влезает')

def main():
    mask = render_mask(TEXT, FONT)
    mw, mh = mask.size
    ox = (W - mw - DEPTH) // 2
    oy = (H - mh - DEPTH) // 2
    mpx = mask.load()
    im = Image.new('RGB', (W, H), BG)
    px = im.load()
    last = len(SHADES) - 1
    for y in range(H):
        for x in range(W):
            # глубина экструзии: самый дальний сдвиг, накрывающий пиксель
            depth = -1
            for s in range(1, DEPTH + 1):
                mx, my = x - ox - s, y - oy - s
                if 0 <= mx < mw and 0 <= my < mh and mpx[mx, my]:
                    depth = s
                    break
            if depth < 0:
                continue
            t = (depth - 1) / (DEPTH - 1) * last       # 0..last
            i = int(t)
            frac = t - i
            j = min(i + 1, last)
            # Bayer: порог решает, брать ли следующий оттенок
            if frac * 4 > BAYER[y & 1][x & 1]:
                i = j
            px[x, y] = SHADES[i]
    # грань поверх
    for y in range(H):
        for x in range(W):
            mx, my = x - ox, y - oy
            if 0 <= mx < mw and 0 <= my < mh and mpx[mx, my]:
                px[x, y] = FACE
    im.save(OUT)
    print('OK -> %s (%dx%d)' % (OUT, W, H))

if __name__ == '__main__':
    main()
