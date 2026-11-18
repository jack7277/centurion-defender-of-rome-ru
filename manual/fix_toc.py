# fix_toc.py — пересчёт номеров страниц содержания по фактической вёрстке DOCX->PDF.
# Ищет страницу, где заголовок (верхний регистр) реально оказался, пишет toc_pages.json.
import os, subprocess, json, sys
import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
PDF = os.path.join(os.environ['TEMP'], 'manual_pdf', 'Centurion_manual_RU.pdf')

subprocess.run([r'C:\Program Files\LibreOffice\program\soffice.exe', '--headless',
                '--convert-to', 'pdf', '--outdir', os.path.dirname(PDF),
                os.path.join(ROOT, 'Centurion_manual_RU.docx')],
               check=True, capture_output=True, timeout=300)

titles = []
for ln in open(os.path.join(HERE, 'ru', 'p04.txt'), encoding='utf-8'):
    if ln.startswith('[TOC]'):
        titles.append(ln[5:].rsplit('|', 1)[0])

doc = fitz.open(PDF)
pages_text = [' '.join(p.get_text().split()) for p in doc]
pages = {}
for t in titles:
    needle = t.upper()
    for i, txt in enumerate(pages_text):
        if needle in txt:
            pages[t] = str(i + 1)
            break
    else:
        print('НЕ НАЙДЕНО:', t)
json.dump(pages, open(os.path.join(HERE, 'toc_pages.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('страниц в PDF:', len(doc), '; TOC:', len(pages), '/', len(titles))
