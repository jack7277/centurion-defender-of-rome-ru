# font_editor.py — GUI-редактор шрифта игры (decoded/FONT_8x8_ru.bin) + кнопка пересборки
# Запуск: python analysis/font_editor.py
import os, subprocess, sys, threading
import tkinter as tk
from tkinter import ttk, messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
FONT_PATH = os.path.join(ROOT, 'decoded', 'FONT_8x8_ru.bin')
CELL = 26

def enc(ch):
    if 'А' <= ch <= 'Я': return 0x80 + ord(ch) - ord('А')
    if 'а' <= ch <= 'п': return 0xA0 + ord(ch) - ord('а')
    if 'р' <= ch <= 'я': return 0xB0 + ord(ch) - ord('р')
    b = ch.encode('cp866', errors='replace')
    return b[0]

def bin_idx(c):
    # индекс в файле шрифта (cp866-раскладка) по игровому коду
    return 0xE0 + (c - 0xB0) if 0xB0 <= c <= 0xBF else c

def dec(c):
    if 0x80 <= c <= 0x9F: return chr(ord('А') + c - 0x80)
    if 0xA0 <= c <= 0xAF: return chr(ord('а') + c - 0xA0)
    if 0xB0 <= c <= 0xBF: return chr(ord('р') + c - 0xB0)
    try: return bytes([c]).decode('cp866')
    except Exception: return '?'

PRESETS = [
    'АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ',
    'абвгдежзийклмнопрстуфхцчшщъыьэюя',
    '0123456789.,:;!?-()"\'/%',
    'ЛЕГЕНДЫ ГЛАСЯТ: Рим был задуман богами',
    'Сенат и народ Рима доверяют тебе судьбу',
]

def glyph_w(g):
    w = 0
    for row in g:
        for x in range(8):
            if row & (0x80 >> x): w = max(w, x + 1)
    return w

# игровая ширина: латиница — из таблицы OVL0, кириллица — по битмапу (как пишет build_ru)
_WL = open(os.path.join(HERE, 'orig', 'OVL0.OVL'), 'rb').read()[0x1509C:0x1509C+0x60]
def game_w(c, g):
    if c < 0x80:
        return _WL[c-0x20] if 0x20 <= c < 0x80 else 4
    return min(glyph_w(g), 8) if glyph_w(g) else 4

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Шрифт Centurion RU')
        self.font = bytearray(open(FONT_PATH, 'rb').read())
        assert len(self.font) == 2048
        self.cur = 0x80
        self.dirty = False
        self._build()
        self._load_glyph()
        self._refresh_list()
        self._preview()

    def _build(self):
        left = ttk.Frame(self); left.pack(side='left', fill='y', padx=4, pady=4)
        self.listbox = tk.Listbox(left, width=14, height=28, font=('Consolas', 11), exportselection=False)
        self.listbox.pack(side='left', fill='y')
        sb = ttk.Scrollbar(left, command=self.listbox.yview); sb.pack(side='right', fill='y')
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.bind('<<ListboxSelect>>', self._on_select)

        mid = ttk.Frame(self); mid.pack(side='left', padx=8, pady=4)
        self.canvas = tk.Canvas(mid, width=8*CELL, height=8*CELL+2, bg='black',
                                highlightthickness=1, highlightbackground='#666')
        self.canvas.pack()
        self.canvas.bind('<Button-1>', self._toggle)
        self.canvas.bind('<B1-Motion>', self._toggle)
        self.info = ttk.Label(mid, text='', font=('Consolas', 10))
        self.info.pack(pady=2)

        right = ttk.Frame(self); right.pack(side='left', fill='both', expand=True, padx=8, pady=4)
        ttk.Label(right, text='Предпросмотр (как в игре, с межбукв. +1):').pack(anchor='w')
        self.ptext = ttk.Combobox(right, font=('Consolas', 11), width=42, values=PRESETS)
        self.ptext.pack(anchor='w', pady=2)
        self.ptext.insert(0, PRESETS[0])
        self.ptext.bind('<KeyRelease>', lambda e: self._preview())
        self.ptext.bind('<<ComboboxSelected>>', lambda e: self._preview())
        self.pcanvas = tk.Canvas(right, width=560, height=300, bg='#200804',
                                 highlightthickness=1, highlightbackground='#666')
        self.pcanvas.pack(anchor='w', pady=4)
        btns = ttk.Frame(right); btns.pack(anchor='w', pady=6)
        ttk.Button(btns, text='Сохранить шрифт', command=self._save).pack(side='left', padx=3)
        ttk.Button(btns, text='Выровнять всё влево', command=self._align_all).pack(side='left', padx=3)
        ttk.Button(btns, text='Пересборка', command=lambda: self._rebuild(False)).pack(side='left', padx=3)
        ttk.Button(btns, text='Пересборка + тест в DOSBox', command=lambda: self._rebuild(True)).pack(side='left', padx=3)
        self.status = ttk.Label(right, text='', font=('Consolas', 9), wraplength=380, justify='left')
        self.status.pack(anchor='w', pady=4)

    def _refresh_list(self):
        self.listbox.delete(0, 'end')
        chars = list(range(0x80, 0xC0)) + list(range(0x20, 0x80))
        for c in chars:
            g = self.font[bin_idx(c)*8:bin_idx(c)*8+8]
            self.listbox.insert('end', '%02X  %s  w%d' % (c, dec(c), game_w(c, g)))
        self.listbox.see(self.cur - 0x80 if self.cur >= 0x80 else self.cur + 0x40)

    def _on_select(self, _e=None):
        sel = self.listbox.curselection()
        if not sel: return
        i = sel[0]
        self.cur = i + 0x80 if i < 0x40 else i - 0x40 + 0x20
        self._load_glyph()

    def _load_glyph(self):
        self.canvas.delete('all')
        g = self.font[bin_idx(self.cur)*8:bin_idx(self.cur)*8+8]
        for y in range(8):
            for x in range(8):
                on = g[y] & (0x80 >> x)
                self.canvas.create_rectangle(x*CELL+1, y*CELL+1, (x+1)*CELL, (y+1)*CELL,
                                             fill='#ff9030' if on else '#181818', outline='#333')
        self.info.config(text='%02X %s   ширина %d px (+1)' % (self.cur, dec(self.cur), game_w(self.cur, g)))

    def _toggle(self, ev):
        x, y = ev.x // CELL, ev.y // CELL
        if not (0 <= x < 8 and 0 <= y < 8): return
        g = bin_idx(self.cur)*8
        self.font[g+y] ^= (0x80 >> x)
        self.dirty = True
        self._load_glyph()
        self._preview()

    def _render_line(self, text):
        # строка -> 1-битная картинка (по пикселям, как в игре)
        w = 0
        for ch in text:
            c = enc(ch)
            if c >= 0x20:
                g = self.font[bin_idx(c)*8:bin_idx(c)*8+8]
                w += game_w(c, g) + 1
        w = max(w, 1)
        img = Image.new('RGB', (w, 8), (0x20, 0x08, 0x04))
        x = 0
        for ch in text:
            c = enc(ch)
            if c < 0x20: continue
            g = self.font[bin_idx(c)*8:bin_idx(c)*8+8]
            for gy in range(8):
                row = g[gy]
                for gx in range(8):
                    if row & (0x80 >> gx):
                        img.putpixel((x + gx, gy), (0xFF, 0xB0, 0x60))
            x += game_w(c, g) + 1
        return img, w

    def _preview(self):
        global Image, ImageTk
        from PIL import Image, ImageTk
        lines = [self.ptext.get()] + [p for p in PRESETS if p != self.ptext.get()]
        cw = max(self.pcanvas.winfo_width(), 560) - 12
        self.pcanvas.delete('all')
        self._pimgs = []
        y = 8
        for text in lines:
            img, w = self._render_line(text)
            z = 4.0 if w * 4 <= cw else min(4.0, cw / w)
            img = img.resize((max(1, round(w * z)), max(1, round(8 * z))), Image.NEAREST)
            pim = ImageTk.PhotoImage(img)
            self._pimgs.append(pim)
            self.pcanvas.create_image(6, y, anchor='nw', image=pim)
            y += img.size[1] + 10
        self.pcanvas.config(height=y + 4)

    def _align_all(self):
        n = 0
        for c in list(range(0x80, 0xC0)) + list(range(0x20, 0x80)):
            o = c*8
            g = self.font[o:o+8]
            shift = 8
            for row in g:
                for x in range(8):
                    if row & (0x80 >> x):
                        shift = min(shift, x)
                        break
            if shift in (0, 8): continue
            for y in range(8):
                self.font[o+y] = (g[y] << shift) & 0xFF
            n += 1
        if n:
            self.dirty = True
            self._load_glyph(); self._refresh_list(); self._preview()
        self.status.config(text='Выравнивание влево: сдвинуто %d глифов (не забудь сохранить)' % n)

    def _save(self):
        open(FONT_PATH, 'wb').write(bytes(self.font))
        self.dirty = False
        self.status.config(text='Сохранено: %s' % FONT_PATH)

    def _rebuild(self, with_test):
        if self.dirty: self._save()
        def work():
            self.status.config(text='Сборка...')
            r = subprocess.run([sys.executable, os.path.join(HERE, 'build_ru.py')],
                               capture_output=True, text=True, encoding='cp866', errors='replace')
            tail = '\n'.join((r.stdout + r.stderr).splitlines()[-3:])
            self.status.config(text=tail)
            if with_test and r.returncode == 0:
                subprocess.Popen([sys.executable, os.path.join(HERE, 'run_ru_test.py'), '6'],
                                 creationflags=subprocess.CREATE_NEW_CONSOLE)
        threading.Thread(target=work, daemon=True).start()

    def destroy(self):
        if self.dirty and not messagebox.askyesno('Шрифт', 'Есть несохранённые правки. Выйти без сохранения?'):
            return
        super().destroy()

if __name__ == '__main__':
    App().mainloop()
