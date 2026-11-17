# audit_wrap.py — аудит ручных переносов в texts.txt под текущий шрифт.
#   python audit_wrap.py          — отчёт: разброс px по строкам каждой записи
#   python audit_wrap.py fix      — перебалансировать прозаические записи и переписать texts.txt
# Балансировка: то же число строк, суммарные байты <= max, DP по словам,
# минимизация разброса ширин. Списки/меню/титры (мало слов в строке) не трогаем.
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wrappx import wpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TXT = os.path.join(ROOT, 'texts.txt')

HDR = re.compile(r'^\[(\d+)\] src=(\S+) key=(\S+) max=(\d+)(?: tech=1)?\s*$')

def parse():
    lines = open(TXT, encoding='utf-8').read().split('\n')
    recs = []
    for i, ln in enumerate(lines):
        m = HDR.match(ln)
        if m:
            recs.append({'id': m.group(1), 'max': int(m.group(4)),
                         'tech': 'tech=1' in ln, 'hdr_i': i,
                         'text_i': None, 'text': None})
    for k, r in enumerate(recs):
        end = recs[k+1]['hdr_i'] if k+1 < len(recs) else len(lines)
        for j in range(r['hdr_i']+1, end):
            if lines[j] and not lines[j].startswith(';'):
                r['text_i'] = j
                r['text'] = lines[j]   # одна строка файла, \n — литеральные escapes
        # если текстовых строк несколько — собираем все (редкость)
        texts = [lines[j] for j in range(r['hdr_i']+1, end)
                 if lines[j] and not lines[j].startswith(';')]
        if len(texts) > 1:
            r['text'] = '\n'.join(texts)  # не трогаем такие в fix
    return lines, recs

def entry_lines(text):
    # литеральный \n в файле = перевод строки в игре
    parts = text.split('\\n')
    if parts and parts[-1] == '':
        parts.pop()
    return parts

def blen(text):
    # байты cp866; \n в игре = 1 байт
    return len(text.replace('\\n', '\n').encode('cp866'))

def is_prose(lines):
    # проза = в среднем >=4 слов на строку и >=2 строк
    if len(lines) < 2:
        return False
    words = [len(l.split()) for l in lines if l.strip()]
    return bool(words) and sum(words) / len(words) >= 4

def report(recs):
    rows = []
    for r in recs:
        if r['tech'] or r['text'] is None or '\n' in r['text'] and '\\n' not in r['text']:
            continue
        ls = entry_lines(r['text'])
        if not is_prose(ls):
            continue
        ws = [wpx(l) for l in ls]
        spread = max(ws) - min(ws)
        rows.append((spread, r, ws))
    rows.sort(key=lambda x: -x[0])
    for spread, r, ws in rows:
        flag = ' OVER!' if blen(r['text']) > r['max'] else ''
        print('%s max=%d lines=%d spread=%3d px %s  %s' % (
            r['id'], r['max'], len(ws), spread, ws, flag))
    print('всего прозаических многострочных записей:', len(rows))
    return rows

SKIP = {'0052', '0542'}          # титульный блок и титры — структурные, не трогаем

def balance_seg(words, n, maxpx):
    """Разбить слова на n строк, минимизируя разброс ширин. Возвращает список строк или None."""
    N = len(words)
    if n == 0 or N == 0:
        return None
    if n == 1:
        return [' '.join(words)]
    target = wpx(' '.join(words)) // n
    memo = {}
    def go(i, k):
        if k == n:
            return (0, []) if i == N else None
        if (i, k) in memo: return memo[(i, k)]
        res = None
        cur = ''
        for j in range(i, N):
            cur = words[j] if not cur else cur + ' ' + words[j]
            w = wpx(cur)
            if w > maxpx + 10: break
            r = go(j+1, k+1)
            if r is None: continue
            c = r[0] + (w - target) ** 2
            if res is None or c < res[0]: res = (c, [cur] + r[1])
        memo[(i, k)] = res
        return res
    r = go(0, 0)
    return r[1] if r else None

def balance(text, maxb):
    ls = entry_lines(text)
    # сегменты по пустым строкам; пустые строки сохраняем как разделители
    segs = []           # ('lines', [...]) или ('blank', '')
    cur = []
    for l in ls:
        if l.strip() == '':
            if cur: segs.append(cur); cur = []
            segs.append('')
        else:
            cur.append(l)
    if cur: segs.append(cur)
    maxpx = max(wpx(l) for l in ls)
    lead = re.match(r'^\s*', ls[0]).group(0)   # отступ/пробел продолжения фразы
    out = []
    for seg in segs:
        if seg == '':
            out.append('')
            continue
        words = [w for w in ' '.join(seg).split(' ') if w]
        r = balance_seg(words, len(seg), maxpx)
        if r is None:
            return None
        out.extend(r)
    if out and lead:
        out[0] = lead + out[0]
    new = '\\n'.join(out)
    if text.endswith('\\n'):
        new += '\\n'
    if blen(new) > maxb:
        return None
    return new

def fix(rows, lines):
    changed = 0
    for spread, r, ws in rows:
        if spread < 30 or r['id'] in SKIP or '\n' in r['text'] and '\\n' not in r['text']:
            continue
        new = balance(r['text'], r['max'])
        if not new or new == r['text']:
            continue
        nls = entry_lines(new)
        old_nb = [w for w, l in zip(ws, entry_lines(r['text'])) if l.strip()]
        new_nb = [wpx(l) for l in nls if l.strip()]
        if len(nls) != len(ws) or len(new_nb) != len(old_nb):
            continue
        if max(new_nb) - min(new_nb) >= max(old_nb) - min(old_nb) - 15:
            continue
        if max(new_nb) > max(old_nb) + 10:
            continue
        print('FIX %s: %s -> %s  (%d b, max %d)' % (r['id'], old_nb, new_nb, blen(new), r['max']))
        lines[r['text_i']] = new
        changed += 1
    if changed:
        open(TXT, 'w', encoding='utf-8', newline='').write('\n'.join(lines))
    print('изменено записей:', changed)

if __name__ == '__main__':
    lines, recs = parse()
    rows = report(recs)
    if 'fix' in sys.argv:
        fix(rows, lines)
