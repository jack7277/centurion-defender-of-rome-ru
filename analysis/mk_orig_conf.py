import os, re
HERE = os.path.dirname(os.path.abspath(__file__))
tp = os.path.join(os.environ['TEMP'], 'cent_orig')
s = open(os.path.join(HERE, 'dosbox.conf'), encoding='utf-8').read()
s = re.sub(r'mount c ".*"', lambda m: 'mount c "' + tp + '"', s)
open(os.path.join(HERE, 'dosbox_orig.conf'), 'w', encoding='utf-8').write(s)
print([l for l in s.splitlines() if 'mount' in l])
