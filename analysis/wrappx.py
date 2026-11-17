# wrappx.py — замер ширины строки в пикселях (font#1) и перенос строк по бюджету
# usage: python wrappx.py [budget]  — читает строки из stdin
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ovl = open(os.path.join(HERE, 'orig', 'OVL0.OVL'), 'rb').read()
WL = ovl[0x1509C:0x1509C+0x60]
font = open(os.path.join(HERE, '..', 'decoded', 'FONT_8x8_ru.bin'), 'rb').read()

def glyph_w(g):
    w = 0
    for row in g:
        for x in range(8):
            if row & (0x80 >> x): w = max(w, x + 1)
    return min(w, 8) if w else 4

CYR = {}
for c in list(range(0x80, 0xB0)) + list(range(0xE0, 0xF0)):
    CYR[c] = glyph_w(font[c*8:c*8+8])

def enc(ch):
    if 'А' <= ch <= 'Я': return 0x80 + ord(ch) - ord('А')
    if 'а' <= ch <= 'п': return 0xA0 + ord(ch) - ord('а')
    if 'р' <= ch <= 'я': return 0xB0 + ord(ch) - ord('р')
    b = ch.encode('cp866', errors='replace');  return b[0]

def wpx(s):
    t = 0
    for ch in s:
        b = enc(ch)
        t += (CYR.get(b, 4) if b >= 0x80 else (WL[b-0x20] if 0x20 <= b < 0x80 else 4)) + 1
    return t

def wrap(s, budget):
    out, cur = [], ''
    for word in s.split(' '):
        cand = (cur + ' ' + word).strip()
        if cur and wpx(cand) > budget:
            out.append(cur); cur = word
        else:
            cur = cand
    if cur: out.append(cur)
    return out

if __name__ == '__main__':
    budget = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    data = open(0, 'r', encoding='utf-8', errors='replace') if not sys.stdin.isatty() else sys.stdin
    for line in data:
        line = line.rstrip('\n')
        print('%3d  %s' % (wpx(line), line))
