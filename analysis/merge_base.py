# merge_base.py — приведение перевода texts.txt к базе centurion_translate_thread.
# База: форумные посты (cp1251) + TEXT-файлы (UTF-16LE): блоки "EN строка + RU варианты".
# Совпадение — по нормализованному английскому оригиналу записи.
# RU подставляется только если влезает в max= записи (иначе оставляем наш, в отчёт).
#   python merge_base.py          — dry-run, только отчёт
#   python merge_base.py apply    — применить к texts.txt
import os, re, sys, glob

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
BASE = os.path.join(ROOT, 'centurion_translate_thread')
TXT = os.path.join(ROOT, 'texts.txt')
REPORT = os.path.join(HERE, 'merge_base_report.txt')

MARKUP = re.compile(r'\[/?(?:B|I|U|QUOTE[^\]]*|CUT[^\]]*|OFFTOP)\]', re.I)

def norm_en(s):
    return re.sub(r'\s+', ' ', s).replace('~', '').replace('﻿', '').strip().lower()

def clean(s):
    return MARKUP.sub('', s).strip()

def is_en(s):
    if not s or re.search('[А-Яа-яЁё]', s):
        return False
    return bool(re.search('[A-Za-z]', s))

def is_ru(s):
    return bool(re.search('[А-Яа-яЁё]', s))

def parse_blocks(text):
    """Извлекает пары (EN, RU) из блоков, разделённых пустыми строками."""
    pairs = []
    for block in re.split(r'\r?\n\s*\r?\n', text):
        lines = [clean(l) for l in block.splitlines()]
        lines = [l for l in lines if l]
        en = [l for l in lines if is_en(l)]
        ru = [l for l in lines if is_ru(l)]
        if not en or not ru:
            continue
        en_s = ' '.join(en)
        # убираем русские вставки из EN (бывает "GGA Мятеж")
        if not is_en(en_s):
            en_s = ' '.join(w for w in en_s.split(' ') if not re.search('[А-Яа-яЁё]', w))
        ru_s = ru[0].split(';')[0].strip()   # первый вариант из перечисленных через ;
        if re.search(r'(?i)gamerun|katarn|kokka|zabrus|передовик', ru_s):
            continue                       # это обсуждение на форуме, а не перевод
        if en_s and ru_s:
            pairs.append((en_s, ru_s))
    return pairs

def load_base():
    pairs = []
    files = []
    files += sorted(glob.glob(os.path.join(BASE, '_Gamerun', 'from_thread_*.txt')))
    files += sorted(glob.glob(os.path.join(BASE, '_katarn', 'from_thread_*.txt')))
    for f in files:
        pairs += parse_blocks(open(f, encoding='cp1251', errors='replace').read())
    for f in sorted(glob.glob(os.path.join(BASE, '_Gamerun', '00', 'TEXT*.*'))):
        if f.lower().endswith('.rar'):
            continue
        raw = open(f, 'rb').read()
        try:
            text = raw.decode('utf-16-le') if raw[:2] == b'\xff\xfe' else raw.decode('cp1251')
        except UnicodeDecodeError:
            continue
        pairs += parse_blocks(text)
    m = {}
    for en, ru in pairs:
        m.setdefault(norm_en(en), ru)   # первый источник в приоритете
    return m, len(pairs)

def split_phrases(s):
    """-> (phrases, seps): разбиваем по двойным пробелам и '~'. seps[i] — разделитель ПОСЛЕ phrases[i]."""
    parts = re.split(r'(  +|~)', s)
    phrases = parts[0::2]
    seps = parts[1::2] + ['']
    return phrases, seps

def sanitize(s):
    for a, b in [('‘', "'"), ('’', "'"), ('“', '"'), ('”', '"'),
                 ('«', '"'), ('»', '"'), ('…', '...'), ('﻿', ''), (' ', ' ')]:
        s = s.replace(a, b)
    return s

HDR = re.compile(r'^\[(\d+)\] src=(\S+) key=(\S+) max=(\d+|\*)')

def main():
    base, npairs = load_base()
    print('база: %d пар EN->RU, уникальных EN: %d' % (npairs, len(base)))
    lines = open(TXT, encoding='utf-8').read().split('\n')
    out = open(REPORT, 'w', encoding='utf-8')
    recs = [i for i, l in enumerate(lines) if HDR.match(l)]
    stats = {'match': 0, 'same': 0, 'replace': 0, 'toolong': 0, 'noen': 0}
    changes = []
    for k, hi in enumerate(recs):
        end = recs[k+1] if k+1 < len(recs) else len(lines)
        hdr = HDR.match(lines[hi])
        rid = hdr.group(1)
        maxb = int(hdr.group(4)) if hdr.group(4) != '*' else 0   # 0 = без лимита
        en_parts = [l[1:].strip() for l in lines[hi+1:end] if l.startswith(';')]
        ti = [j for j in range(hi+1, end) if lines[j] and not lines[j].startswith(';')]
        if not ti:
            continue
        ti = ti[0]
        en = norm_en(' '.join(en_parts))
        if not en:
            stats['noen'] += 1
            continue
        ru = base.get(en)
        cur = lines[ti]
        if ru:
            stats['match'] += 1
            if ru == cur:
                stats['same'] += 1
                continue
            if maxb > 0 and len(ru.encode('cp866', errors='replace')) > maxb:
                stats['toolong'] += 1
                out.write('[%s] TOOLONG max=%d (%d б)\n  EN: %s\n  база: %s\n  наш:  %s\n' % (
                    rid, maxb, len(ru.encode('cp866', errors='replace')), en, ru, cur))
                continue
            stats['replace'] += 1
            changes.append((ti, sanitize(ru)))
            out.write('[%s] max=%d\n  EN: %s\n  база: %s\n  наш:  %s\n' % (rid, maxb, en, ru, cur))
            continue
        # пофразовая замена (диалоги ENEGO/MNEGO: несколько фраз через '~' и двойные пробелы)
        en_p, en_s = split_phrases(' '.join(en_parts))
        ru_p, ru_s = split_phrases(cur)
        if len(en_p) > 1 and len(en_p) == len(ru_p):
            hit = 0
            new_p = []
            for ep, rp in zip(en_p, ru_p):
                b = base.get(norm_en(ep))
                if b:
                    b = sanitize(b)
                    new_p.append(b)
                    if b != rp:
                        hit += 1
                else:
                    new_p.append(rp)
            if hit:
                stats['replace'] += 1
                new_text = ''.join(p + s for p, s in zip(new_p, ru_s))
                changes.append((ti, new_text))
                out.write('[%s] пофразово (%d фраз)\n  было: %s\n  стало: %s\n' % (rid, hit, cur, new_text))
    print(stats)
    if 'apply' in sys.argv:
        for ti, ru in changes:
            lines[ti] = ru
        open(TXT, 'w', encoding='utf-8', newline='').write('\n'.join(lines))
        print('применено: %d замен' % len(changes))
    out.close()
    print('отчёт:', REPORT)

if __name__ == '__main__':
    main()
