# cbm_encode.py — сборка PNG обратно в CBM-ресурс игры (замена картинки).
# Режим по умолчанию: decoded/cbm/MINIT_TITLE_RU.png -> TITLE.CBM в MINIT.DAT.
#   python cbm_encode.py                — собрать титул в MINIT.DAT
#   python cbm_encode.py --check        — только проверить round-trip, не писать в игру
# PNG квантуется в 16 цветов палитры TITLE (palettes_learned.json), пакуется в 4bpp,
# жмётся игровым LZSS (textool.lzss_encode), заголовок CBM берётся от оригинала.
# Чтобы подменить картинку своей — перерисуй decoded/cbm/MINIT_TITLE_RU.png
# (строго 313x51) и запусти скрипт снова.
import os, struct, sys
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textool import read_archive_from, write_archive, pristine_path, backup, lzss_encode
import json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
MOD, ENTRY = 'MINIT', 'TITLE.CBM'
PNG = os.path.join(ROOT, 'decoded', 'cbm', 'MINIT_TITLE_RU.png')

def get_palette():
    d = json.load(open(os.path.join(HERE, 'palettes_learned.json')))
    return {int(k): tuple(v) for k, v in d['TITLE'].items()}

def png_to_nibbles(png, wpx, h, wb, pal):
    im = Image.open(png).convert('RGB')
    if im.size != (wpx, h):
        raise SystemExit('PNG должен быть %dx%d, а не %s' % (wpx, h, im.size))
    colors = list(pal.items())                     # [(nibble, (r,g,b)), ...]
    px = im.load()
    nib = []
    for y in range(h):
        for x in range(wpx):
            r, g, b = px[x, y]
            n = min(colors, key=lambda c: (c[1][0]-r)**2 + (c[1][1]-g)**2 + (c[1][2]-b)**2)[0]
            nib.append(n)
    out = bytearray()
    for y in range(h):
        row = nib[y*wpx:(y+1)*wpx]
        for xb in range(wb):
            hi = row[xb*2] if xb*2 < wpx else 0
            lo = row[xb*2+1] if xb*2+1 < wpx else 0
            out.append((hi << 4) | lo)
    return bytes(out)

def build_cbm(png):
    es = read_archive_from(pristine_path(MOD + '.DIR'), pristine_path(MOD + '.DAT'))
    ent = [e for e in es if e.name == ENTRY][0]
    hdr = ent.stored[:14]
    wpx, x, y = struct.unpack('<HHH', hdr[:6])
    wb, h, u8, u9 = hdr[6], hdr[7], hdr[8], hdr[9]
    raw = png_to_nibbles(png, wpx, h, wb, get_palette())
    comp = lzss_encode(raw)                        # u32 size + поток
    cbm = hdr[:10] + comp                          # поле size уже внутри comp
    return es, ent, cbm, (wpx, h, wb)

def main():
    check = '--check' in sys.argv
    es, ent, cbm, (wpx, h, wb) = build_cbm(PNG)
    # round-trip: декодируем то, что собрали, и сверяем с квантованными нибблами
    from gamedec import decode_game_lzw_bytes
    raw = decode_game_lzw_bytes(cbm[10:])
    assert len(raw) == wb * h, 'round-trip: размер %d != %d' % (len(raw), wb*h)
    assert raw == png_to_nibbles(PNG, wpx, h, wb, get_palette()), 'round-trip: пиксели разошлись'
    print('round-trip OK: %s %dx%d, CBM %d байт (оригинал %d)' % (ENTRY, wpx, h, len(cbm), len(ent.stored)))
    if check:
        return
    backup(MOD + '.DAT'); backup(MOD + '.DIR')
    ent.stored = cbm
    write_archive(MOD, es)
    print('Записано в игру: %s.DAT/.DIR' % MOD)

if __name__ == '__main__':
    main()
