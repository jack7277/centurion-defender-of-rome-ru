# build_ru.py — кириллица для Centurion: схема "ds-pocket" (2025-11-16, финальная).
# Пещера+таблицы кириллицы живут в ds 0xC410..0xC8C8 — «кармане» между концом BSS (0xC410)
# и буфером декодирования картинок (0xC948, фиксированный; по сейвам не двигается от конфигурации).
# Хвост DGROUP выше 0xC948 — рабочие буферы игры (декод CBM ~14К) и heap: шрифты там затирались
# (проверено сейвами: бой — TACTICS.LZW, карточка провинции — CBM-буфер). Расширять образ ядра
# нельзя: OVL0 грузится сразу за ним (таблица оверлеев, сегмент 0x1B11).
# Ячейка 0xB07C (конец загрузки OVL0) поднята до ds 0xC8C8 (link 0x2AF2), чтобы лоадер
# дочитывал наш блок; heap-топ = эта ячейка минус 0x800 = 0xC0C0 — НИЖЕ кармана.
# 4 места текстового движка ядра патчатся far-call'ами в пещеру; кириллица читается из кармана,
# латиница — по оригинальным таблицам. Y для кириллицы всегда 1 (без таблицы).
# Запуск из analysis/. Идемпотентно: всегда стартует от analysis/orig/.
import json, os, struct

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.normpath(os.path.join(HERE, '..', 'Centurion_Defender_of_Rome'))
ORIG = os.path.join(HERE, 'orig')

# раскладка кармана (ds offsets)
POCKET   = 0xC410
W1, W2   = POCKET, POCKET + 0x40          # 0xC410, 0xC450
B1, B2   = POCKET + 0x80, POCKET + 0x280  # 0xC490, 0xC690
CAVE     = POCKET + 0x400                 # 0xC810
BLOCK_FILE = 0xB400 + POCKET              # 0x17810 = конец оригинального OVL0
DS_LINK  = 0x1E66                         # link-значение сегмента DGROUP (для load 0x1000)
LOAD_END_CELL = 0xB07C                    # ячейка таблицы оверлеев: конец загрузки DGROUP

def cyr_glyphs(font, rows):
    """64 глифа в игровой кодировке (А-Я 0x80-9F, а-п 0xA0-AF, р-я 0xB0-BF), укороченные до rows строк."""
    out = []
    for c in list(range(0x80, 0xB0)) + list(range(0xE0, 0xF0)):
        g = font[c*8:c*8+8]
        out.append(bytes(g[:rows]) if rows < 8 else bytes(g))
    return out

def glyph_w(g):
    w = 0
    for row in g:
        for x in range(8):
            if row & (0x80 >> x):
                w = max(w, x + 1)
    return min(w, 8) if w else 4   # движок сам добавляет +1 межбуквенный

# ---------------- крошечный ассемблер пещеры (все ссылки — абсолютные ds) ----------------
class Asm:
    def __init__(self):
        self.c = bytearray(); self.labels = {}; self.fix8 = []; self.fix16 = []
    def lbl(self, n): self.labels[n] = len(self.c)
    def b(self, *bs): self.c.extend(bs)
    def w16(self, v): self.c.extend(struct.pack('<H', v))
    def jmp8(self, op, lb): self.b(op); self.fix8.append((len(self.c), lb)); self.b(0)
    def call16(self, lb): self.b(0xE8); self.fix16.append((len(self.c), lb)); self.b(0, 0)
    def done(self):
        for pos, lb in self.fix8:
            rel = self.labels[lb] - (pos + 1)
            assert -128 <= rel <= 127, lb
            self.c[pos] = rel & 0xFF
        for pos, lb in self.fix16:
            rel = self.labels[lb] - (pos + 2)
            struct.pack_into('<h', self.c, pos, rel)
        return bytes(self.c)

def build_cave(scratch, dbgbase):
    """Возвращает (code, labels). labels — ds offsets точек входа C1..C4."""
    a = Asm()
    # --- C1: measure W. in: ax = cbw(char); out: al = width. клобберит bx, di
    a.lbl('C1')
    a.b(0x84, 0xE4)                     # test ah,ah
    a.jmp8(0x78, 'C1c')                 # js
    a.b(0x8B, 0xF8)                     # mov di,ax
    a.b(0x8B, 0x1E, 0x56, 0x9B)         # mov bx,[9B56]
    a.b(0x8A, 0x41, 0xE0)               # mov al,[bx+di-0x20]
    a.b(0xCB)                           # retf
    a.lbl('C1c')
    a.b(0x24, 0x7F)                     # and al,7F   (idx = c-0x80)
    a.b(0x30, 0xE4)                     # xor ah,ah
    a.b(0x89, 0xC7)                     # mov di,ax
    a.b(0x80, 0x3E, 0x5C, 0x9B, 0x08)   # cmp byte [9B5C],8
    a.b(0xBB); a.w16(W1)                # mov bx,W1
    a.jmp8(0x74, 'C1f1')                # je
    a.b(0xBB); a.w16(W2)                # mov bx,W2
    a.lbl('C1f1')
    a.b(0x8A, 0x01)                     # mov al,[bx+di]   (ds)
    a.b(0xCB)                           # retf
    # --- C2: draw_char W. in: bl = c-0x20 (bh=0); out: al = width
    a.lbl('C2')
    a.b(0x80, 0xFB, 0x60)               # cmp bl,60
    a.jmp8(0x73, 'C2c')                 # jae
    a.b(0x03, 0x1E, 0x56, 0x9B)         # add bx,[9B56]
    a.b(0x8A, 0x07)                     # mov al,[bx]
    a.b(0xCB)
    a.lbl('C2c')
    a.b(0x80, 0xEB, 0x60)               # sub bl,60
    a.b(0x57)                           # push di
    a.b(0x89, 0xDF)                     # mov di,bx
    a.b(0x80, 0x3E, 0x5C, 0x9B, 0x08)
    a.b(0xBB); a.w16(W1)
    a.jmp8(0x74, 'C2f1')
    a.b(0xBB); a.w16(W2)
    a.lbl('C2f1')
    a.b(0x8A, 0x01)                     # mov al,[bx+di]
    a.b(0x5F)                           # pop di
    a.b(0xCB)
    # --- C3: draw_char Y. in: bl = c-0x20; out: bl = Y (кириллице всегда 1)
    a.lbl('C3')
    a.b(0x80, 0xFB, 0x60)
    a.jmp8(0x73, 'C3c')
    a.b(0x03, 0x1E, 0x58, 0x9B)         # add bx,[9B58]
    a.b(0x8A, 0x1F)                     # mov bl,[bx]
    a.b(0xCB)
    a.lbl('C3c')
    a.b(0xB3, 0x01)                     # mov bl,1
    a.b(0xCB)
    # --- C4: draw_char пролог. in: si=[9B5A], [bp+8]=char; out: si, [bp+8], bl, cl, ch
    a.lbl('C4')
    a.b(0x8A, 0x46, 0x08)               # mov al,[bp+8]
    a.b(0x3C, 0x80)                     # cmp al,80
    a.jmp8(0x73, 'C4c')                 # jae
    a.b(0x2C, 0x20)                     # sub al,20
    a.b(0x88, 0x46, 0x08)               # mov [bp+8],al
    a.b(0x8A, 0xD8)                     # mov bl,al
    a.b(0x8A, 0x0E, 0x5F, 0x9B)         # mov cl,[9B5F]
    a.b(0xD2, 0xE0)                     # shl al,cl
    a.b(0x8A, 0x2E, 0x5C, 0x9B)         # mov ch,[9B5C]
    a.b(0xF6, 0xE5)                     # mul ch
    a.b(0x03, 0xF0)                     # add si,ax
    a.b(0xCB)
    a.lbl('C4c')
    a.b(0x57)                           # push di
    a.b(0x52)                           # push dx
    a.b(0x8A, 0x0E, 0x5F, 0x9B)         # mov cl,[9B5F]
    a.b(0x8A, 0x2E, 0x5C, 0x9B)         # mov ch,[9B5C]
    a.b(0x88, 0xC3)                     # mov bl,al      (char)
    a.b(0x2C, 0x20)                     # sub al,20
    a.b(0x88, 0x46, 0x08)               # mov [bp+8],al   (c-0x20 = 0x60+idx)
    a.b(0x80, 0xEB, 0x80)               # sub bl,80       (idx)
    a.b(0x30, 0xE4)                     # xor ah,ah
    a.b(0x88, 0xD8)                     # mov al,bl
    a.b(0xF6, 0xE5)                     # mul ch          ax = idx*h
    a.b(0x89, 0xC7)                     # mov di,ax
    a.b(0x80, 0xFD, 0x08)               # cmp ch,8
    a.b(0xBB); a.w16(B1)                # mov bx,B1
    a.jmp8(0x74, 'C4f1')
    a.b(0xBB); a.w16(B2)                # mov bx,B2
    a.lbl('C4f1')
    a.b(0x03, 0xDF)                     # add bx,di       (источник глифа, ds)
    a.b(0xBF); a.w16(scratch)           # mov di,scratch
    a.b(0x88, 0xEA)                     # mov dl,ch       (счётчик = h)
    a.lbl('C4copy')
    a.b(0x8A, 0x07)                     # mov al,[bx]     (ds)
    a.b(0x88, 0x05)                     # mov [di],al
    a.b(0x43)                           # inc bx
    a.b(0x47)                           # inc di
    a.b(0xFE, 0xCA)                     # dec dl
    a.jmp8(0x75, 'C4copy')
    a.b(0x5A)                           # pop dx
    a.b(0x5F)                           # pop di
    a.b(0xBE); a.w16(scratch)           # mov si,scratch
    a.b(0x8A, 0x5E, 0x08)               # mov bl,[bp+8]
    a.b(0xCB)                           # retf
    # --- CDBG: разовый лог источника глифа (bx) в CAVETEST.LOG ---
    a.lbl('CDBG')
    a.b(0x80, 0x3E); a.w16(dbgbase); a.b(0x00)      # cmp byte [DBGFLAG],0
    a.jmp8(0x75, 'CDBGx')                            # jne out
    a.b(0xC6, 0x06); a.w16(dbgbase); a.b(0x01)      # mov byte [DBGFLAG],1
    a.b(0x50, 0x53, 0x51, 0x52, 0x56, 0x57)         # push ax bx cx dx si di
    a.b(0x89, 0x1E); a.w16(dbgbase+2)               # mov [DBGSAVE],bx
    a.b(0xB4, 0x3C, 0x33, 0xC9)                     # mov ah,3C; xor cx,cx
    a.b(0xBA); a.w16(dbgbase+4)                     # mov dx,DBGNAME
    a.b(0xCD, 0x21)                                 # int 21
    a.b(0x8B, 0xD8)                                 # mov bx,ax
    a.b(0xB4, 0x40, 0xB9, 0x10, 0x00)               # mov ah,40; mov cx,16
    a.b(0xBA); a.w16(B1)                            # mov dx,B1   (первые 16 байт таблицы)
    a.b(0xCD, 0x21)
    a.b(0xB4, 0x40, 0xB9, 0x10, 0x00)               # ещё 16
    a.b(0x8B, 0x16); a.w16(dbgbase+2)               # mov dx,[DBGSAVE]  (источник глифа)
    a.b(0xCD, 0x21)
    a.b(0xB4, 0x3E, 0xCD, 0x21)                     # close
    a.b(0x5F, 0x5E, 0x5A, 0x59, 0x5B, 0x58)         # pop di si dx cx bx ax
    a.lbl('CDBGx')
    a.b(0xC3)                                       # ret
    code = a.done()
    # служебные ячейки после кода (в пределах кармана)
    code += b'CAVETEST.LOG' + bytes(1)
    return code, {k: CAVE + v for k, v in a.labels.items()}

def build_ov():
    """Пишет карман (таблицы+пещера) в конец OVL0.OVL (file 0x17810 -> ds 0xC410)."""
    ovl = bytearray(open(os.path.join(GAME, 'OVL0.OVL'), 'rb').read())
    assert len(ovl) == 0x17810, hex(len(ovl))
    font = open(os.path.join(HERE, '..', 'decoded', 'FONT_8x8_ru.bin'), 'rb').read()
    assert len(font) == 2048
    cyr8 = cyr_glyphs(font, 8)
    cyr6 = cyr_glyphs(font, 6)
    scratch = CAVE + len(build_cave(0, 0)[0])     # скрэтч сразу за кодом пещеры
    assert scratch + 8 <= 0xC948, hex(scratch)    # буфер декода CBM начинается с 0xC948
    dbgbase = scratch + 8
    cave, labels = build_cave(scratch, dbgbase)
    assert dbgbase + 4 + 13 <= 0xC948, hex(dbgbase)
    blk = (bytes(glyph_w(g) for g in cyr8) +      # W1
           bytes(glyph_w(g) for g in cyr6) +      # W2
           b''.join(cyr8) +                       # B1
           b''.join(cyr6) +                       # B2
           cave)
    assert len(blk) <= 0xC948 - POCKET, hex(len(blk))
    ovl += blk
    # лоадер читает DGROUP целиком (min(end-start, B084)*16 = 64К) — файл обязан быть 0x1B400
    ovl += b'\x00' * (0x1B400 - len(ovl))
    open(os.path.join(GAME, 'OVL0.OVL'), 'wb').write(bytes(ovl))
    print('OVL0.OVL: %x байт (карман %x..%x)' % (len(ovl), POCKET, POCKET + len(blk)))
    return labels, POCKET + len(blk)

def build_exe(labels, pocket_end):
    img = bytearray(open(os.path.join(HERE, 'CENTURIO.unpacked.bin'), 'rb').read())
    # фильтры знакового сравнения: jl -> jb (пропуск байтов >= 0x80)
    for off in (0x8CA4, 0x8A8D):
        assert img[off] == 0x7C, hex(off)
        img[off] = 0x72
    # конец загрузки DGROUP (0xB07C): НЕ трогаем — оригинал 0x2B27 покрывает ds до 0xCC10 > карман.
    # стек лоадера (0xB024): 0x2B27 -> 0x2E66 — как во всех рабочих сборках.
    assert struct.unpack_from('<H', img, 0xB024)[0] == 0x2B27
    struct.pack_into('<H', img, 0xB024, 0x2E66)
    # размер блока DGROUP (0xB084): 0xC41 -> 0x1000 параграфов (64К) — ОБЯЗАТЕЛЬНО,
    # иначе карман за ds 0xC410 вне блока программы и лоадер затирает чужую память.
    assert struct.unpack_from('<H', img, 0xB084)[0] == 0x0C41
    struct.pack_into('<H', img, 0xB084, 0x1000)
    # 4 far-call патча в пещеру: 9A off16 seg16 (seg — релокейтится)
    extra_relocs = []
    def patch(site, span, lbl):
        got = bytes(img[site:site+span])
        img[site] = 0x9A
        struct.pack_into('<H', img, site+1, labels[lbl] - CAVE)           # off в сегменте кармана
        struct.pack_into('<H', img, site+3, DS_LINK + (CAVE >> 4))       # seg link
        extra_relocs.append(site + 3)
        img[site+5:site+span] = b'\x90' * (span - 5)
        return got
    assert patch(0x8CA9, 9, 'C1') == bytes.fromhex('8bf88b1e569b8a41e0')
    assert patch(0x8DB4, 6, 'C2') == bytes.fromhex('031e569b8a07')
    assert patch(0x8DE5, 6, 'C3') == bytes.fromhex('031e589b8a1f')
    assert patch(0x8D95, 24, 'C4') == bytes.fromhex('8a46082c208846088ad88a0e5f9bd2e08a2e5c9bf6e503f0')
    # пятое место: посимвольный сдвиг в строковом цикле (0x8AA0) — то же чтение W, зовём C1
    assert patch(0x8AA0, 7, 'C1') == bytes.fromhex('8b1e569b8a41e0')
    # пересборка EXE из link-образа + таблицы релокаций
    open(os.path.join(HERE, 'CENTURIO.patched.bin'), 'wb').write(bytes(img))  # для runner.py
    R = json.load(open(os.path.join(HERE, 'relocs.json')))
    maxa = max(a for a, _, _ in R)
    need = maxa - 0x10000 + 2
    link = bytearray(img)
    if len(link) < need:
        link.extend(b'\x00' * (need - len(link)))
    relocs = []
    for a, oldv, delta in R:
        off = a - 0x10000
        cur = link[off] | (link[off+1] << 8)
        struct.pack_into('<H', link, off, (cur - 0x1000) & 0xFFFF)
        relocs.append((off & 0xF, off >> 4))
    for off in extra_relocs:
        cur = link[off] | (link[off+1] << 8)
        struct.pack_into('<H', link, off, (cur - 0x1000) & 0xFFFF)
        relocs.append((off & 0xF, off >> 4))
    relocs.sort(key=lambda x: (x[1], x[0]))
    hdr_paras = (28 + 4*len(relocs) + 15) // 16
    hdr_size = hdr_paras * 16
    image_paras = (len(link) + 15) // 16
    minalloc = 0x1e76 - 0x10 - image_paras
    size = hdr_size + len(link)
    hdr = bytearray(hdr_size)
    struct.pack_into('<2sHHHHHH', hdr, 0, b'MZ', size % 512, (size + 511) // 512,
                     len(relocs), hdr_paras, minalloc, 0xFFFF)
    struct.pack_into('<H', hdr, 0x0E, 0x1E66)   # ss link
    struct.pack_into('<H', hdr, 0x10, 0x0800)   # sp
    struct.pack_into('<H', hdr, 0x14, 0x0322)   # ip
    struct.pack_into('<H', hdr, 0x16, 0x0a7b)   # cs link
    struct.pack_into('<H', hdr, 0x18, 28)
    for i, (o, s) in enumerate(relocs):
        struct.pack_into('<HH', hdr, 28 + 4*i, o, s)
    open(os.path.join(GAME, 'CENTURIO.EXE'), 'wb').write(bytes(hdr) + bytes(link))
    print('CENTURIO.EXE: %d байт' % size)

if __name__ == '__main__':
    import shutil
    shutil.copy(os.path.join(ORIG, 'OVL0.OVL'), os.path.join(GAME, 'OVL0.OVL'))
    import textool
    textool.cmd_build()   # тексты из texts.txt -> игровые файлы (от orig)
    labels, pocket_end = build_ov()   # карман кириллицы в OVL0
    build_exe(labels, pocket_end)     # ядро + far-call патчи
