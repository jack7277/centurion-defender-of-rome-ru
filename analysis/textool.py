# textool.py — дамп и обратная сборка текстов Centurion: Defender of Rome
#
#   python analysis/textool.py dump    -> texts.txt (UTF-8, редактируемый)
#   python analysis/textool.py build   -> патчит файлы игры по texts.txt
#   python analysis/textool.py restore -> вернуть оригиналы из analysis/orig/
#   python analysis/textool.py test    -> round-trip тест LZSS на всех ресурсах
#
# Оригиналы игровых файлов при первой сборке копируются в analysis/orig/
# и дальше сборка всегда идёт от них (идемпотентно).

import os, re, struct, sys, shutil
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = os.path.join(ROOT, 'Centurion_Defender_of_Rome')
ORIG = os.path.join(ROOT, 'analysis', 'orig')
TXT  = os.path.join(ROOT, 'texts.txt')

# ---------------- LZSS (формат игры) ----------------

def lzss_decode(src):
    size = struct.unpack('<I', src[:4])[0]
    data = src[4:]
    ring = bytearray(b' ' * 4096)
    out = bytearray()
    wpos = 4078
    i = 0
    while i < len(data) and len(out) < size:
        flag = data[i]; i += 1
        for b in range(8):
            if len(out) >= size or i >= len(data): break
            if (flag >> b) & 1:
                c = data[i]; i += 1
                ring[wpos] = c; wpos = (wpos + 1) & 4095
                out.append(c)
            else:
                b1, b2 = data[i], data[i+1]; i += 2
                off = b1 | ((b2 & 0xF0) << 4)
                ln = (b2 & 0x0F) + 3
                for k in range(ln):
                    c = ring[(off + k) & 4095]
                    ring[wpos] = c; wpos = (wpos + 1) & 4095
                    out.append(c)
    return bytes(out)

def lzss_encode(data):
    N = 4096
    n = len(data)
    pos = defaultdict(list)          # byte -> список индексов (по возрастанию)
    tokens = []                      # int (литерал) или (ringpos, len)
    t = 0
    while t < n:
        best_l = 0; best_i = -1
        for i in reversed(pos[data[t]]):
            if i < t - N: break
            l = 0
            while l < 18 and t + l < n and i + l < t and data[i+l] == data[t+l]:
                l += 1
            if l > best_l:
                best_l = l; best_i = i
                if l == 18: break
        if best_l >= 3:
            tokens.append(((4078 + best_i) % N, best_l))
            step = best_l
        else:
            tokens.append(data[t])
            step = 1
        for k in range(t, min(t + step, n)):
            pos[data[k]].append(k)
        t += step
    out = bytearray(struct.pack('<I', n))
    i = 0
    while i < len(tokens):
        group = tokens[i:i+8]; i += 8
        flag = 0
        body = bytearray()
        for b, tok in enumerate(group):
            if isinstance(tok, int):
                flag |= (1 << b)
                body.append(tok)
            else:
                j, l = tok
                body.append(j & 0xFF)
                body.append(((j >> 4) & 0xF0) | (l - 3))
        out.append(flag)
        out += body
    return bytes(out)

# ---------------- архивы DIR/DAT ----------------

class Entry:
    __slots__ = ('name', 'flags', 'offset', 'stored')
    def __init__(self, name, flags, offset, stored):
        self.name, self.flags, self.offset, self.stored = name, flags, offset, stored

def read_archive(mod):
    """Читает пару MOD.DIR/MOD.DAT из папки GAME (или ORIG)."""
    dr = open(gamepath(mod + '.DIR'), 'rb').read()
    dat = open(gamepath(mod + '.DAT'), 'rb').read()
    entries = []
    for i in range(0, len(dr), 20):
        rec = dr[i:i+20]
        off = struct.unpack('<I', rec[0:4])[0]
        size = struct.unpack('<H', rec[4:6])[0]
        name = rec[6:18].split(b'\x00')[0].decode('ascii')
        flags = struct.unpack('<H', rec[18:20])[0]
        entries.append(Entry(name, flags, off, dat[off:off+size]))
    return entries

def write_archive(mod, entries):
    """Пересобирает MOD.DAT/MOD.DIR: данные подряд с offset 4 (в порядке исходных
    смещений), порядок записей в DIR и сигнатура сохраняются."""
    sig = read_pristine(mod + '.DAT')[:4]
    out = bytearray(sig)
    newoff = {}
    for e in sorted(entries, key=lambda e: e.offset):
        newoff[id(e)] = len(out)
        out += e.stored
    dr = bytearray()
    for e in entries:                      # исходный порядок записей DIR
        nm = e.name.encode('ascii')
        dr += struct.pack('<IH', newoff[id(e)], len(e.stored)) + nm + b'\x00' * (12 - len(nm)) + struct.pack('<H', e.flags)
    open(gamepath(mod + '.DAT'), 'wb').write(bytes(out))
    open(gamepath(mod + '.DIR'), 'wb').write(bytes(dr))

def gamepath(name):
    """Путь к файлу игры; для чтения исходников используем ORIG если есть."""
    return os.path.join(GAME, name)

def pristine_path(name):
    p = os.path.join(ORIG, name)
    return p if os.path.exists(p) else gamepath(name)

def backup(name):
    os.makedirs(ORIG, exist_ok=True)
    p = os.path.join(ORIG, name)
    if not os.path.exists(p):
        shutil.copy2(gamepath(name), p)

def read_pristine(name):
    return open(pristine_path(name), 'rb').read()

# ---------------- источники текста ----------------

def scan_fixed(data, base=0, minlen=4):
    """Null-terminated ASCII-строки, отфильтрованные от мусора кода."""
    res = []
    for m in re.finditer(rb'[\x20-\x7e\n]{%d,}\x00' % minlen, data):
        s = m.group()[:-1]
        off = base + m.start()
        alnum = sum(1 for c in s if (0x41 <= c <= 0x5A) or (0x61 <= c <= 0x7A) or (0x30 <= c <= 0x39) or c == 0x20)
        alpha = sum(1 for c in s if (0x41 <= c <= 0x5A) or (0x61 <= c <= 0x7A))
        if alpha < 2 or alnum / len(s) < 0.75:
            continue
        res.append((off, s))
    return res

def parse_table(data):
    """TEXTA-Z / SCOUT: u16-таблица смещений + null-terminated записи.
    Последний элемент таблицы — сентинел (= длина данных), не строка."""
    cnt = struct.unpack('<H', data[:2])[0] // 2
    offs = struct.unpack('<%dH' % cnt, data[:cnt*2])
    assert offs[-1] == len(data), 'сентинел таблицы != конец данных'
    out = []
    for o in offs[:-1]:
        end = data.index(b'\x00', o)
        out.append(data[o:end])
    return out

def build_table(entries):
    cnt = len(entries) + 1          # + сентинел
    offs = []
    blob = bytearray()
    base = cnt * 2
    for s in entries:
        offs.append(base + len(blob))
        blob += s + b'\x00'
    offs.append(base + len(blob))
    return struct.pack('<%dH' % cnt, *offs) + bytes(blob)

PLACES_REC = 20
PLACES_NAME_OFF = 2
PLACES_NAME_LEN = 18   # максимум 17 символов + \x00

def esc(s):
    return s.replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '\\r')

def unesc(s):
    return s.replace('\\n', '\n').replace('\\r', '\r').replace('\\\\', '\\')

TECH_RE = re.compile(r'^[a-z0-9_]+\.(cbm|dat|dir|lzw|bin|ovl|exe|rol)$', re.I)
MODULES = {'batlvga','navl','batl','cent','eglad','einit','emap','enaval','enego',
           'erace','mglad','minit','mmap','mnaval','mnego','mrace','ovl0','centurio',
           'adlib','roland','speaker','tandy','nosnd','lapc','init','init2','xmenu',
           'love1','love2','?love1','race','race2','laps','show','arena','oars1','oars2',
           'bombs','smok','flag','xsink','shark','zrman','rwimp','lman','lwimp',
           'lcat0','lcat1','lcat2','cn1','cn2','cn3a','cn3b','cn4a','cn4b','cn4c','cn4d',
           'cn6','cn7a','cn7b','cn8a','cn8b','cn9a','cn9b','cn9c','cn9d'}

def is_tech(txt):
    t = txt.strip().lower()
    return bool(TECH_RE.match(t)) or t in MODULES

# ---------------- dump ----------------

def cmd_dump():
    entries = []   # (src, key, max, text)
    # 1. OVL0.OVL — основной массив текста (интро, меню, события, кредиты)
    ovl = read_pristine('OVL0.OVL')
    fixed = {}
    for off, s in scan_fixed(ovl, base=0):
        if off < 0xB000:                      # ниже — код, строки там артефакты
            continue
        if 0x1505C <= off < 0x1585C:          # шрифт 8x8 — не текст
            continue
        fixed[off] = s
    # блок интро: берём все строки, включая короткие ('glory...')
    for m in re.finditer(rb'[\x20-\x7e\n]{2,}\x00', ovl[0x11852:0x11AAD]):
        fixed[0x11852 + m.start()] = m.group()[:-1]
    for off in sorted(fixed):
        txt = fixed[off].decode('ascii')
        entries.append(('OVL0.OVL', '0x%X' % off, str(len(fixed[off])), txt))
    # 2. ENEGO TEXTA-Z + SCOUT (MNEGO идентичен, патчится вместе)
    arch = read_archive_from(pristine_path('ENEGO.DIR'), pristine_path('ENEGO.DAT'))
    for e in arch:
        if not (e.name.startswith('TEXT') or e.name == 'SCOUT.LZW'):
            continue
        data = lzss_decode(e.stored)
        for idx, s in enumerate(parse_table(data)):
            txt = s.decode('ascii', errors='replace')
            entries.append(('ENEGO/' + e.name, str(idx), '*', txt))
    # 3. CENT: PLACES (названия городов), NEWGAME
    arch = read_archive_from(pristine_path('CENT.DIR'), pristine_path('CENT.DAT'))
    for e in arch:
        if e.name == 'PLACES.LZW':
            data = lzss_decode(e.stored)
            for r in range(len(data) // PLACES_REC):
                rec = data[r*PLACES_REC:(r+1)*PLACES_REC]
                name = rec[PLACES_NAME_OFF:PLACES_NAME_OFF+PLACES_NAME_LEN].split(b'\x00')[0]
                if name:
                    entries.append(('CENT/PLACES.LZW', str(r), str(PLACES_NAME_LEN - 1), name.decode('ascii')))
        elif e.name == 'NEWGAME.LZW':
            data = lzss_decode(e.stored)
            for off, s in scan_fixed(data):
                entries.append(('CENT/NEWGAME.LZW', '0x%X' % off, str(len(s)), s.decode('ascii')))

    with open(TXT, 'w', encoding='utf-8-sig', newline='\n') as f:
        f.write(HEADER)
        for i, (src, key, mx, txt) in enumerate(entries):
            tech = ' tech=1' if is_tech(txt) else ''
            f.write('[%04d] src=%s key=%s max=%s%s\n' % (i, src, key, mx, tech))
            for line in txt.split('\n'):
                f.write('; ' + esc(line) + '\n')
            f.write(esc(txt) + '\n')
    print('OK: %d строк -> %s' % (len(entries), TXT))

def read_archive_from(dirpath, datpath):
    dr = open(dirpath, 'rb').read()
    dat = open(datpath, 'rb').read()
    entries = []
    for i in range(0, len(dr), 20):
        rec = dr[i:i+20]
        off = struct.unpack('<I', rec[0:4])[0]
        size = struct.unpack('<H', rec[4:6])[0]
        name = rec[6:18].split(b'\x00')[0].decode('ascii')
        flags = struct.unpack('<H', rec[18:20])[0]
        entries.append(Entry(name, flags, off, dat[off:off+size]))
    return entries

HEADER = """# Centurion: Defender of Rome — ТЕКСТЫ ИГРЫ
#
# КАК РЕДАКТИРОВАТЬ:
#   Под каждым заголовком [NNNN] сначала идут строки с ';' — это оригинал
#   (не трогайте их, они только для справки), а ПОСЛЕДНЯЯ строка без ';' —
#   редактируемый текст. Именно она попадёт в игру.
#   \\n внутри строки = перевод строки в игре. Реальный перенос строки тоже работает.
#   max=NN  — текст НЕ ДЛИННЕЕ NN символов (место в файле фиксировано!).
#   max=*   — длина свободная (ресурс пересобирается целиком).
#   В строках ENEGO/TEXTx символ ~ разделяет варианты одной фразы —
#   сохраняйте количество '~', иначе сместятся варианты ответов.
#   Русский текст пишите обычными буквами — при сборке кодируется в cp866.
#   tech=1 в заголовке — служебная строка (имя файла/модуля), сборка её
#   ПРОПУСКАЕТ, даже если вы её изменили. Не переводите такие строки.
#
"""

# ---------------- build ----------------

HDR_RE = re.compile(r'^\[(\d+)\] src=(\S+) key=(\S+) max=(\S+?)( tech=1)?\s*$')

def parse_txt():
    entries = {}
    cur = None
    for line in open(TXT, encoding='utf-8-sig'):
        line = line.rstrip('\n')
        m = HDR_RE.match(line)
        if m:
            cur = {'id': m.group(1), 'src': m.group(2), 'key': m.group(3),
                   'max': m.group(4), 'tech': bool(m.group(5)), 'body': []}
            entries[cur['id']] = cur
            continue
        if line.startswith('#') or cur is None:
            continue
        if line.startswith(';'):
            continue
        cur['body'].append(line)
    for cur in entries.values():
        cur['text'] = unesc('\n'.join(cur['body']).rstrip('\n'))
    return list(entries.values())

def game_encode(s):
    """Русский текст -> байты игры: cp866 для А-Я/а-п/р-я, Ёё -> Ее (слотов 0xF0+ нет)."""
    s = s.replace('Ё', 'Е').replace('ё', 'е')
    out = bytearray()
    for ch in s:
        if 'А' <= ch <= 'Я':
            out.append(0x80 + ord(ch) - ord('А'))
        elif 'а' <= ch <= 'п':
            out.append(0xA0 + ord(ch) - ord('а'))
        elif 'р' <= ch <= 'я':
            out.append(0xB0 + ord(ch) - ord('р'))  # р-я на 0xB0-0xBF (непрерывный диапазон 0x80-0xBF)
        else:
            out.extend(ch.encode('cp866'))
    return bytes(out)

def encode_text(s, entry_desc, errors):
    s = s.replace('—', '-').replace('–', '-').replace('«', '"').replace('»', '"')
    try:
        return game_encode(s)
    except UnicodeEncodeError as ex:
        errors.append('%s: нет в cp866: %s' % (entry_desc, ex))
        return s.encode('cp866', errors='replace')

def cmd_build():
    for f in ('OVL0.OVL', 'CENT.DAT', 'CENT.DIR', 'ENEGO.DAT', 'ENEGO.DIR',
              'MNEGO.DAT', 'MNEGO.DIR'):
        backup(f)
    entries = parse_txt()
    errors, warnings, done = [], [], 0

    # --- OVL0.OVL: фиксированные смещения ---
    ovl = bytearray(read_pristine('OVL0.OVL'))
    touched = False
    for e in entries:
        if e['src'] != 'OVL0.OVL':
            continue
        off = int(e['key'], 16)
        mx = int(e['max'])
        raw = encode_text(e['text'], e['id'], errors)
        old = bytes(ovl[off:off+mx])
        if raw == old:
            continue
        if e['tech']:
            warnings.append('%s: tech=1 (служебная строка), пропущено: %r' % (e['id'], e['text'][:50]))
            continue
        if len(raw) > mx:
            errors.append('%s (%s @%s): длиннее max=%d (%d)' % (e['id'], e['src'], e['key'], mx, len(raw)))
            continue
        ovl[off:off+mx+1] = raw + b'\x00' * (mx + 1 - len(raw))
        touched = True; done += 1
    # --- шрифт/кириллицу вшивает build_ru.py (descriptor + append-блок) ---
    if touched:
        open(gamepath('OVL0.OVL'), 'wb').write(bytes(ovl))

    # --- ресурсы архивов ---
    # собираем изменения: {mod: {name: new_stored_bytes}}
    changes = defaultdict(dict)
    for mod in ('ENEGO', 'MNEGO', 'CENT'):
        arch = read_archive_from(pristine_path(mod + '.DIR'), pristine_path(mod + '.DAT'))
        decoded = {}
        for ent in arch:
            if ent.flags == 0x8000:
                decoded[ent.name] = lzss_decode(ent.stored)

        for e in entries:
            src = e['src']
            if src.startswith('ENEGO/') and mod in ('ENEGO', 'MNEGO'):
                name = src.split('/', 1)[1]
                idx = int(e['key'])
                if name not in decoded:
                    continue
                data = decoded[name]
                table = parse_table(data)
                raw = encode_text(e['text'], e['id'], errors)
                if table[idx] == raw:
                    continue
                if e['tech']:
                    warnings.append('%s: tech=1, пропущено: %r' % (e['id'], e['text'][:50]))
                    continue
                table[idx] = raw
                decoded[name] = build_table(table)
                changes[mod][name] = decoded[name]
                done += 1
            elif src == 'CENT/PLACES.LZW' and mod == 'CENT':
                data = bytearray(decoded['PLACES.LZW'])
                r = int(e['key'])
                raw = encode_text(e['text'], e['id'], errors)
                mx = PLACES_NAME_LEN - 1
                if len(raw) > mx:
                    errors.append('%s (PLACES rec %s): длиннее %d' % (e['id'], e['key'], mx))
                    continue
                o = r * PLACES_REC + PLACES_NAME_OFF
                old = data[o:o+PLACES_NAME_LEN]
                new = raw + b'\x00' * (PLACES_NAME_LEN - len(raw))
                if bytes(old) != new:
                    data[o:o+PLACES_NAME_LEN] = new
                    decoded['PLACES.LZW'] = bytes(data)
                    changes[mod]['PLACES.LZW'] = decoded['PLACES.LZW']
                    done += 1
            elif src == 'CENT/NEWGAME.LZW' and mod == 'CENT':
                data = bytearray(decoded['NEWGAME.LZW'])
                off = int(e['key'], 16)
                mx = int(e['max'])
                raw = encode_text(e['text'], e['id'], errors)
                if len(raw) > mx:
                    errors.append('%s (NEWGAME @%s): длиннее %d' % (e['id'], e['key'], mx))
                    continue
                if bytes(data[off:off+mx]) != raw:
                    data[off:off+mx+1] = raw + b'\x00' * (mx + 1 - len(raw))
                    decoded['NEWGAME.LZW'] = bytes(data)
                    changes[mod]['NEWGAME.LZW'] = decoded['NEWGAME.LZW']
                    done += 1

        # перепаковка архива при изменениях
        if changes.get(mod):
            arch2 = read_archive_from(pristine_path(mod + '.DIR'), pristine_path(mod + '.DAT'))
            for ent in arch2:
                if ent.name in changes[mod]:
                    ent.stored = lzss_encode(changes[mod][ent.name])
            write_archive(mod, arch2)
            print('пересобран %s.DAT/.DIR (%d ресурсов изменено)' % (mod, len(changes[mod])))

    for w in warnings:
        print('WARN:', w)
    for er in errors:
        print('ERROR:', er)
    print('OK: применено %d замен' % done)
    if errors:
        sys.exit(1)

# ---------------- test ----------------

def cmd_test():
    import glob
    fails = 0
    for f in sorted(glob.glob(os.path.join(ROOT, 'extracted', '*', '*.LZW'))):
        src = open(f, 'rb').read()
        dec = lzss_decode(src)
        enc = lzss_encode(dec)
        dec2 = lzss_decode(enc)
        ok = dec2 == dec
        if not ok:
            fails += 1
            print('FAIL', f)
    print('round-trip LZSS: %s' % ('все ок' if not fails else '%d ошибок' % fails))
    # round-trip таблиц
    arch = read_archive_from(pristine_path('ENEGO.DIR'), pristine_path('ENEGO.DAT'))
    for e in arch:
        if e.name.startswith('TEXT') or e.name == 'SCOUT':
            data = lzss_decode(e.stored)
            if build_table(parse_table(data)) != data:
                print('FAIL table', e.name); fails += 1
    print('round-trip таблиц: %s' % ('все ок' if not fails else 'есть ошибки'))

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'dump'
    if cmd == 'restore':
        for f in os.listdir(ORIG):
            shutil.copy2(os.path.join(ORIG, f), gamepath(f))
            print('восстановлен', f)
        sys.exit(0)
    {'dump': cmd_dump, 'build': cmd_build, 'test': cmd_test}[cmd]()
