# title_ru.py — генератор русского титула "ЦЕНТУРИОН" в стиле MINIT_TITLE.png
# Грань — золото, боковина — 3D-экструзия вниз-вправо тремя тёмными оттенками, фон оливковый.
# Результат: decoded/cbm/MINIT_TITLE_RU.png (313x51, как оригинал).
# Шрифт можно заменить параметром: python title_ru.py [fontfile] [text]
import os, sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
OUT = os.path.join(ROOT, 'decoded', 'cbm', 'MINIT_TITLE_RU.png')

W, H = 313, 51
BG = (113, 116, 93)
FACE = (192, 141, 82)
SHADES = [(67, 40, 36)]                               # однотонная боковина
DEPTH = 7                                               # глубина экструзии, px
MARGIN = 1

TEXT = sys.argv[2] if len(sys.argv) > 2 else 'ЦЕНТУРИОН'
FONT = sys.argv[1] if len(sys.argv) > 1 else r'C:\Windows\Fonts\timesbd.ttf'

def render_mask(text, fontpath):
    """Маска букв 0/255, подогнанная под (W-2*MARGIN) x (H-DEPTH-2*MARGIN)."""
    box_w, box_h = W - 2 * MARGIN, H - DEPTH - 2 * MARGIN
    size = box_h
    while size > 6:
        f = ImageFont.truetype(fontpath, size)
        m = Image.new('L', (W * 2, H * 2), 0)
        d = ImageDraw.Draw(m)
        d.text((W // 2, H // 2), text, font=f, fill=255, anchor='mm')
        bb = m.getbbox()
        if not bb:
            size -= 1
            continue
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        if w <= box_w and h <= box_h:
            m = m.crop(bb)
            return m.resize((min(w, box_w), min(h, box_h)), Image.LANCZOS) if (w > box_w or h > box_h) else m
        size -= 1
    raise SystemExit('не влезает')

def main():
    mask = render_mask(TEXT, FONT)
    mw, mh = mask.size
    ox = (W - mw - DEPTH) // 2          # лицевая грань; экструзия уйдёт вниз-вправо
    oy = (H - mh - DEPTH) // 2
    im = Image.new('RGB', (W, H), BG)
    # экструзия: от дальнего слоя к ближнему
    for s in range(DEPTH, 0, -1):
        sh = SHADES[min((s - 1) * len(SHADES) // DEPTH, len(SHADES) - 1)]
        im.paste(Image.new("RGB", (mw, mh), sh), (ox + s, oy + s), mask)
    im.paste(Image.new("RGB", (mw, mh), FACE), (ox, oy), mask)
    im.save(OUT)
    print('OK -> %s (%dx%d)' % (OUT, W, H))

if __name__ == '__main__':
    main()
