"""Centurion: Defender of Rome — CBM (full-screen image) decoder.

.CBM layout (raw entry in .DAT archives, DIR flag 0xC000):
  [0]  u16  width in pixels          (e.g. 320)
  [2]  u16  x, [4] u16 y             (0,0 for full-screen)
  [6]  u8   width in bytes           (pixels/2, e.g. 160)
  [7]  u8   height                   (e.g. 200)
  [8]  u8   mode flag 1 (E/M variants differ)
  [9]  u8   remap table index -> 16-byte table at CMAP.BIN[48 + u9*16]
  [10] u32  unpacked size            (= w_bytes * h)
  [14] LZSS stream (game variant — see gamedec.py)

Unpacked pixels: 4bpp nibble-packed, 2 px/byte, HIGH nibble = left pixel.

Colors: at draw time the game maps each nibble through a 16-byte remap
table (indexed by header byte u9, tables live in CMAP.BIN past the EGA
palette) into the runtime-built 256-color DAC palette. The DAC palette is
built procedurally at runtime, so exact per-screen colors are learned from
gameplay captures: palettes_learned.json maps image name -> 16 colors.
Images without a learned palette fall back to the EGA palette.

Usage: python cbm_decode.py
Output: decoded/cbm/<MODULE>_<NAME>.png
"""
import os
import json
import struct
import glob
from PIL import Image
from gamedec import decode_game_lzw_bytes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
OUT = os.path.join(ROOT, 'decoded', 'cbm')

CMAP = open(os.path.join(ROOT, 'extracted', 'CENT', 'CMAP.BIN'), 'rb').read()
EGA = [(r * 255 // 63, g * 255 // 63, b * 255 // 63)
       for r, g, b in (tuple(CMAP[i:i + 3]) for i in range(0, 48, 3))]
TABLES = CMAP[48:]

def load_learned():
    p = os.path.join(HERE, 'palettes_learned.json')
    if not os.path.exists(p):
        return {}
    data = json.load(open(p))
    return {k: {int(n): tuple(c) for n, c in v.items()} for k, v in data.items()}

LEARNED = load_learned()

def load_dac():
    p = os.path.join(HERE, 'dac_map.bin')
    if os.path.exists(p):
        raw = open(p, 'rb').read()
        if len(raw) >= 768:
            return [tuple(raw[i*3:i*3+3]) for i in range(256)]
    return None

DAC = load_dac()

def decode_cbm(path):
    """-> (PIL Image, header dict) or None."""
    d = open(path, 'rb').read()
    if len(d) < 14:
        return None
    wpx, x, y = struct.unpack('<HHH', d[:6])
    wb, h = d[6], d[7]
    u8, u9 = d[8], d[9]
    size = struct.unpack('<I', d[10:14])[0]
    if wb == 0 or h == 0 or size > 1 << 20 or size != wb * h:
        return None
    raw = decode_game_lzw_bytes(struct.pack('<I', size) + d[14:])
    if len(raw) != size:
        return None
    remap = TABLES[u9 * 16: u9 * 16 + 16]

    name = os.path.basename(path)[:-4]
    mod = os.path.basename(os.path.dirname(path))
    learned = LEARNED.get(name) or LEARNED.get(mod + '/' + name) or LEARNED.get(mod + '_' + name)

    im = Image.new('RGB', (wpx, h))
    px = im.load()
    for yy in range(h):
        for xb in range(wb):
            b = raw[yy * wb + xb]
            for nib, xx in ((b >> 4, xb * 2), (b & 15, xb * 2 + 1)):
                if xx < wpx:
                    if learned:
                        px[xx, yy] = learned.get(nib, (0, 0, 0))
                    elif DAC:
                        px[xx, yy] = DAC[remap[nib]]
                    else:
                        px[xx, yy] = EGA[remap[nib] & 15]
    return im, dict(w_px=wpx, x=x, y=y, w_bytes=wb, h=h, u8=u8, u9=u9, size=size)

def main():
    os.makedirs(OUT, exist_ok=True)
    ok = bad = 0
    for path in sorted(glob.glob(os.path.join(ROOT, 'extracted', '*', '*.CBM'))):
        rel = os.path.relpath(path, os.path.join(ROOT, 'extracted')).replace('\\', '/')
        name = rel.replace('/', '_')[:-4]
        res = decode_cbm(path)
        if res is None:
            print('%-28s SKIP/FAIL' % rel)
            bad += 1
            continue
        im, hdr = res
        im.save(os.path.join(OUT, name + '.png'))
        ok += 1
        print('%-28s %dx%d  u=%02x,%02x  size=%d' % (rel, hdr['w_px'], hdr['h'], hdr['u8'], hdr['u9'], hdr['size']))
    print('\nOK: %d, failed: %d -> %s' % (ok, bad, OUT))

if __name__ == '__main__':
    main()
