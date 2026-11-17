"""Centurion: Defender of Rome — sprite decoder.

Sprite sets live in the .DAT archives as <name>DAT.LZW + <name>HDR.LZW pairs
(LZSS-compressed; see gamedec.py). After decompression:
  HDR = array of 14-byte records:
        [id:2][x:2][y:2][w:1][h:1][u8:1][u9:1][dat_offset:4]
  DAT = raw 8bpp pixel data, sprites laid out back to back, each w*h bytes.

This tool decodes every *DAT/*HDR pair from the decoded/ tree into
decoded/sprites/<MODULE>_<NAME>/sprite_XXX.png plus a contact sheet
_sheet.png per set for quick visual checks.

Usage: python sprite_decode.py
"""
import os
import struct
import glob
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DECODED = os.path.join(HERE, '..', 'decoded')
OUT = os.path.join(DECODED, 'sprites')

# EGA palette from CENT/CMAP.BIN (values 0/21/42/63 -> scale to 0..255)
def load_palette():
    raw = open(os.path.join(HERE, '..', 'extracted', 'CENT', 'CMAP.BIN'), 'rb').read()[:48]
    pal = []
    for i in range(0, 48, 3):
        r, g, b = raw[i], raw[i + 1], raw[i + 2]
        pal.append((min(255, r * 4 + r // 16), min(255, g * 4 + g // 16), min(255, b * 4 + b // 16)))
    return pal

PAL = load_palette()

def parse_hdr(hdr):
    """Return list of (id, x, y, w, h, u8, u9, offset)."""
    sprites = []
    for i in range(len(hdr) // 14):
        rec = hdr[i * 14:(i + 1) * 14]
        sid, x, y = struct.unpack('<HHH', rec[:6])
        w, h, u8, u9 = rec[6], rec[7], rec[8], rec[9]
        off = struct.unpack('<I', rec[10:14])[0]
        sprites.append((sid, x, y, w, h, u8, u9, off))
    return sprites

def sprite_image(dat, w, h, off, end=None):
    """Extract one sprite as an RGB image (palette-mapped, index 0 kept as black).

    Pixel data is raw 8bpp row-major; the record's w*h can overshoot the
    real data by a byte or two for the last sprite, so clamp to `end`
    (next sprite's offset / DAT size) and pad the missing tail with 0.
    """
    if end is None:
        end = len(dat)
    avail = max(0, end - off)
    buf = dat[off:off + min(w * h, avail)]
    if len(buf) < w * h:
        buf = buf + b'\x00' * (w * h - len(buf))
    im = Image.new('RGB', (w, h))
    px = im.load()
    for yy in range(h):
        for xx in range(w):
            v = buf[yy * w + xx]
            px[xx, yy] = PAL[v & 15] if v < 16 else (v, v, v)
    return im

def decode_set(hdr_path, dat_path, out_dir):
    hdr = open(hdr_path, 'rb').read()
    dat = open(dat_path, 'rb').read()
    sprites = parse_hdr(hdr)
    os.makedirs(out_dir, exist_ok=True)
    meta = []
    offs = [s[7] for s in sprites] + [len(dat)]
    for i, (sid, x, y, w, h, u8, u9, off) in enumerate(sprites):
        end = min([o for o in offs[i + 1:] if o > off], default=len(dat))
        if w == 0 or h == 0 or off >= len(dat):
            meta.append((i, sid, x, y, w, h, u8, u9, off, 'BAD'))
            continue
        im = sprite_image(dat, w, h, off, end)
        im.save(os.path.join(out_dir, 'sprite_%03d.png' % i))
        meta.append((i, sid, x, y, w, h, u8, u9, off, 'ok'))
    # contact sheet
    thumbs = []
    for i, (sid, x, y, w, h, u8, u9, off) in enumerate(sprites):
        if w == 0 or h == 0 or off >= len(dat):
            continue
        end = min([o for o in offs[i + 1:] if o > off], default=len(dat))
        thumbs.append(sprite_image(dat, w, h, off, end))
    if thumbs:
        cellw = max(t.width for t in thumbs) + 4
        cellh = max(t.height for t in thumbs) + 4
        cols = max(1, int(16))
        rows = (len(thumbs) + cols - 1) // cols
        sheet = Image.new('RGB', (cols * cellw, rows * cellh), (24, 24, 32))
        for i, t in enumerate(thumbs):
            sheet.paste(t, ((i % cols) * cellw + 2, (i // cols) * cellh + 2))
        scale = 2 if cellw < 60 else 1
        if scale > 1:
            sheet = sheet.resize((sheet.width * scale, sheet.height * scale), Image.NEAREST)
        sheet.save(os.path.join(out_dir, '_sheet.png'))
    return meta

def main():
    rows = []
    for hdr_path in sorted(glob.glob(os.path.join(DECODED, '*', '*HDR.bin'))):
        dat_path = hdr_path[:-7] + 'DAT.bin'
        if not os.path.exists(dat_path):
            continue
        rel = os.path.relpath(hdr_path, DECODED).replace('\\', '/')
        rel = rel[:-len('HDR.bin')]  # e.g. 'BATL/BG'
        out_dir = os.path.join(OUT, rel.replace('/', '_'))
        meta = decode_set(hdr_path, dat_path, out_dir)
        bad = sum(1 for m in meta if m[-1] != 'ok')
        rows.append((rel, len(meta), bad))
        print('%-24s sprites=%3d bad=%d -> %s' % (rel, len(meta), bad, os.path.basename(out_dir)))
    print('\nTotal sets: %d' % len(rows))

if __name__ == '__main__':
    main()
