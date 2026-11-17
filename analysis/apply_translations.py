# apply_translations.py — подставляет переводы из translations.py в texts.txt
# Проверяет лимиты max= в байтах cp866 и покрытие перевода.
import os, re, sys, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TXT = os.path.join(ROOT, 'texts.txt')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from translations import TR, TR2
import json

# id в texts.txt могут меняться при переделке дампа — переводим через (src,key)
_idmap = json.load(open(os.path.join(ROOT, 'analysis', 'texts_map.json')))
TR_BY_KEY = {tuple(_idmap[k]): v for k, v in TR.items() if k in _idmap}
TR_BY_KEY.update(TR2)

HDR_RE = re.compile(r'^\[(\d+)\] src=(\S+) key=(\S+) max=(\S+?)( tech=1)?\s*$')

lines = open(TXT, encoding='utf-8-sig').read().split('\n')
out = []
cur = None
body_start = None
stats = {'translated': 0, 'over': [], 'missing': []}
entries = {}

# сначала соберём структуру: id -> (header_idx, body_indices, max, tech, src, key)
for i, line in enumerate(lines):
    m = HDR_RE.match(line)
    if m:
        cur = m.group(1)
        entries[cur] = {'hdr': i, 'max': m.group(4), 'tech': bool(m.group(5)),
                        'src': m.group(2), 'key': m.group(3), 'body': []}
    elif cur and not line.startswith(';') and not line.startswith('#'):
        entries[cur]['body'].append(i)

for eid, e in entries.items():
    txt = TR_BY_KEY.get((e['src'], e['key']))
    if txt is None:
        # есть ли реальный текст, который стоило бы перевести?
        orig = ';'.join(lines[j] for j in e['body']).strip()
        if orig and not e['tech']:
            stats['missing'].append(eid)
        continue
    if e['tech']:
        print('пропуск tech', eid)
        continue
    enc = txt.replace('—', '-').replace('–', '-').replace('«', '"').replace('»', '"').encode('cp866')
    if e['max'] != '*' and len(enc) > int(e['max']):
        stats['over'].append((eid, len(enc), int(e['max']), txt))
    # записать: тело заменяется одной строкой (экранированной)
    esc = txt.replace('\\', '\\\\').replace('\n', '\\n')
    first = e['body'][0]
    lines[first] = esc
    for j in e['body'][1:]:
        lines[j] = None
    stats['translated'] += 1

open(TXT, 'w', encoding='utf-8-sig', newline='\n').write('\n'.join(l for l in lines if l is not None))
print('переведено:', stats['translated'])
if stats['over']:
    print('ПРЕВЫШЕНИЕ ЛИМИТА:')
    for eid, got, mx, txt in stats['over']:
        print(' ', eid, got, '>', mx, txt)
if stats['missing']:
    print('без перевода (%d):' % len(stats['missing']), ' '.join(stats['missing']))
