# build_docx.py — сборка Centurion_manual_RU.docx из переведённых страниц manual/ru/pNN.txt
# Оформление: размер страницы оригинала, декоративная колонна справа (из скана),
# рубрики small-caps, подрубрики жирные, таблицы, содержание с точками, номера страниц.
# Разметка в pNN.txt:  '## ' рубрика, '### ' подрубрика, '[FIG pNN_figK]' картинка,
# '[TABLE]' + строки 'a|b|c' таблица, '[TOC]текст|страница' строка содержания.
# Остальное — абзацы. Разрыв страницы после каждой pNN (сохраняем пагинацию оригинала).
import os, re
from docx import Document
from docx.shared import Pt, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

HERE = os.path.dirname(os.path.abspath(__file__))
RU = os.path.join(HERE, 'ru')
ASSETS = os.path.join(HERE, 'assets')
OUT = os.path.join(HERE, '..', 'Centurion_manual_RU.docx')
TOC_JSON = os.path.join(HERE, 'toc_pages.json')
TOC_PAGES = {}
if os.path.exists(TOC_JSON):
    import json
    TOC_PAGES = json.load(open(TOC_JSON, encoding='utf-8'))

PAGE_W, PAGE_H = 393, 496          # pt, как оригинал
MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B = 50, 65, 40, 40
BODY_PT = 11

def set_font(run, size=BODY_PT, bold=False, small_caps=False):
    run.font.name = 'Times New Roman'
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.small_caps = small_caps
    rpr = run._element.get_or_add_rPr()
    rf = rpr.find(qn('w:rFonts'))
    if rf is None:
        rf = OxmlElement('w:rFonts'); rpr.append(rf)
    for a in ('w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia'):
        rf.set(qn(a), 'Times New Roman')

def para(doc, text, size=BODY_PT, bold=False, small_caps=False, center=False):
    p = doc.add_paragraph()
    if center: p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(text)
    set_font(r, size, bold, small_caps)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.space_before = Pt(0)
    return p

def add_column_image(section, doc):
    """Декоративная колонна: плавающая картинка в колонтитуле, за текстом, у правого края."""
    img = os.path.join(ASSETS, 'column.png')
    from PIL import Image
    im = Image.open(img)
    h_emu = Emu(int(PAGE_H * 12700))
    w_emu = Emu(int(PAGE_H * 12700 * im.size[0] / im.size[1]))
    x_emu = Emu(int(PAGE_W * 12700)) - w_emu
    hdr_p = section.header.paragraphs[0]
    run = hdr_p.add_run()
    run.add_picture(img, width=w_emu, height=h_emu)
    inline = run._r.xpath('.//wp:inline')[0]
    anchor = OxmlElement('wp:anchor')
    for k, v in (('distT','0'),('distB','0'),('distL','0'),('distR','0'),
                 ('simplePos','0'),('relativeHeight','0'),('behindDoc','1'),
                 ('locked','0'),('layoutInCell','1'),('allowOverlap','1')):
        anchor.set(k, v)
    sp = OxmlElement('wp:simplePos'); sp.set('x','0'); sp.set('y','0'); anchor.append(sp)
    ph = OxmlElement('wp:positionH'); ph.set('relativeFrom','page')
    off = OxmlElement('wp:posOffset'); off.text = str(int(x_emu)); ph.append(off); anchor.append(ph)
    pv = OxmlElement('wp:positionV'); pv.set('relativeFrom','page')
    off = OxmlElement('wp:posOffset'); off.text = '0'; pv.append(off); anchor.append(pv)
    for tag in ('wp:extent','wp:effectExtent'):
        el = inline.find(qn(tag))
        if el is not None: anchor.append(el)
    anchor.append(OxmlElement('wp:wrapNone'))
    for tag in ('wp:docPr','wp:cNvGraphicFramePr'):
        el = inline.find(qn(tag))
        if el is not None: anchor.append(el)
    anchor.append(inline.find(qn('a:graphic')))
    inline.getparent().replace(inline, anchor)

def add_page_number(section):
    p = section.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run()
    set_font(r, 10)
    f1 = OxmlElement('w:fldChar'); f1.set(qn('w:fldCharType'), 'begin')
    it = OxmlElement('w:instrText'); it.set(qn('xml:space'), 'preserve'); it.text = ' PAGE '
    f2 = OxmlElement('w:fldChar'); f2.set(qn('w:fldCharType'), 'end')
    r._r.append(f1); r._r.append(it); r._r.append(f2)

def add_table(doc, rows):
    cells = [r.split('|') for r in rows]
    t = doc.add_table(rows=len(cells), cols=max(len(c) for c in cells))
    t.style = 'Table Grid'
    for i, row in enumerate(cells):
        for j, val in enumerate(row):
            c = t.cell(i, j)
            c.text = ''
            r = c.paragraphs[0].add_run(val)
            set_font(r, 10, bold=(i == 0))
    return t

def main():
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Pt(PAGE_W), Pt(PAGE_H)
    sec.left_margin, sec.right_margin = Pt(MARGIN_L), Pt(MARGIN_R)
    sec.top_margin, sec.bottom_margin = Pt(MARGIN_T), Pt(MARGIN_B)
    add_column_image(sec, doc)
    add_page_number(sec)
    style = doc.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(BODY_PT)
    for n in range(1, 49):
        path = os.path.join(RU, 'p%02d.txt' % n)
        text = open(path, encoding='utf-8').read().strip('\n')
        lns = [l.rstrip() for l in text.split('\n')]
        i = 0
        while i < len(lns):
            ln = lns[i]
            i += 1
            if not ln.strip():
                continue
            if ln.startswith('## '):
                para(doc, ln[3:], size=14, bold=True, small_caps=True)
            elif ln.startswith('### '):
                para(doc, ln[4:], size=12, bold=True)
            elif ln.startswith('[FIG '):
                name = ln[5:].rstrip(']').strip()
                img = os.path.join(ASSETS, name + '.png')
                if os.path.exists(img):
                    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    from PIL import Image
                    im = Image.open(img)
                    w_pt = min(PAGE_W - MARGIN_L - MARGIN_R - 20, im.size[0] / 300 * 72)
                    p.add_run().add_picture(img, width=Pt(w_pt))
            elif ln == '[TABLE]':
                rows = []
                while i < len(lns) and lns[i].strip():
                    rows.append(lns[i]); i += 1
                add_table(doc, rows)
            elif ln.startswith('[TOC]'):
                body, page = ln[5:].rsplit('|', 1)
                page = TOC_PAGES.get(body, page)   # фактическая страница после вёрстки
                p = doc.add_paragraph()
                p.paragraph_format.tab_stops.add_tab_stop(
                    Pt(PAGE_W - MARGIN_L - MARGIN_R - 5), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
                set_font(p.add_run(body + '\t' + page), 11)
            else:
                if n == 1:
                    para(doc, ln, size=20, bold=True, center=True)
                else:
                    para(doc, ln)
        if n < 48:
            doc.add_page_break()
    doc.save(OUT)
    print('OK ->', os.path.abspath(OUT))

if __name__ == '__main__':
    main()
