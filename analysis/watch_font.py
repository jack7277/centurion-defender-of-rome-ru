# watch_font.py — быстрый прогон: целостность блока кириллицы по хешу + фейковая мышь.
# Скрипт мыши/клавиш правится ниже под навигацию до карты.
import os, sys, struct, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import runner
from runner import Machine, MEM
from capstone.x86 import *

BLK_LO, BLK_HI = 0x1E660 + 0xF600, 0x1E660 + 0x10000
SNAPSHOT_AT = 2000          # шаг, к которому шрифты уже загружены

# (шаг, x_pix, y_pix, btn)  btn: 1=нажать, 0=отпустить
MOUSE_SCRIPT = []
KEY_SCRIPT = []             # (шаг, ax)

class W(Machine):
    def __init__(self):
        super().__init__()
        self.mx, self.my, self.mbtn = 160, 100, 0
        self.ref = None
        self._wlog = open(os.path.join(runner.OUTDIR, 'fontwatch.log'), 'w', encoding='utf-8')

    def bios(self, num):
        ax = self.r['ax']; ah = ax >> 8
        if num == 0x33:
            if ah == 0x00:
                self.sr(X86_REG_AX, 0xFFFF); self.sr(X86_REG_BX, 2)
            elif ah == 0x03:
                self.sr(X86_REG_BX, self.mbtn)
                self.sr(X86_REG_CX, self.mx * 2)
                self.sr(X86_REG_DX, self.my)
            elif ah == 0x04:
                self.mx = (self.r['cx'] // 2) & 0xFFFF; self.my = self.r['dx'] & 0xFFFF
            else:
                self.sr(X86_REG_AX, 0)
            return
        super().bios(num)

if __name__ == '__main__':
    img = open(os.path.join(HERE, 'CENTURIO.patched.bin'), 'rb').read()
    LOAD = 0x1000
    MEM[LOAD * 16: LOAD * 16 + len(img)] = img
    PSP = 0x0FF0
    tail = b' v nosnd k\r'
    MEM[PSP * 16 + 0x80] = len(tail) - 1
    MEM[PSP * 16 + 0x81: PSP * 16 + 0x81 + len(tail)] = tail
    MEM[PSP * 16 + 0x00] = 0xCD; MEM[PSP * 16 + 0x01] = 0x20
    struct.pack_into('<H', MEM, PSP * 16 + 0x02, 0xA000)
    ENV = 0x0F00
    envblk = b'\x00' + struct.pack('<H', 1) + b'C:' + bytes([92]) + b'CENTURIO.EXE' + b'\x00'
    MEM[ENV * 16: ENV * 16 + len(envblk)] = envblk
    struct.pack_into('<H', MEM, PSP * 16 + 0x2C, ENV)
    m = W()
    m.r['cs'] = 0x1a7b; m.r['ip'] = 0x0322
    m.r['ds'] = PSP; m.r['es'] = PSP
    m.r['ss'] = 0x2e66; m.r['sp'] = 0x0800
    max_steps = int(sys.argv[1]) if len(sys.argv) > 1 else 30_000_000
    t0 = time.time()
    # свой цикл поверх m.exec_ins не нужен — используем run, но с проверкой через io? проще: свой loop
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    md = runner.md
    script_i = 0
    while not m.halted and m.steps < max_steps:
        m.steps += 1
        if m.steps == SNAPSHOT_AT:
            m.ref = bytes(MEM[BLK_LO:BLK_HI])
        if m.ref is not None and m.steps % 100000 == 0:
            cur = bytes(MEM[BLK_LO:BLK_HI])
            if cur != m.ref:
                diffs = [i for i in range(len(m.ref)) if cur[i] != m.ref[i]]
                m._wlog.write('CORRUPT step=%d ndiff=%d first=+%04x..+%04x\n' % (
                    m.steps, len(diffs), diffs[0], diffs[-1]))
                m._wlog.flush()
                m.ref = cur
        for s in MOUSE_SCRIPT:
            if s[0] == m.steps:
                m.mx, m.my, m.mbtn = s[1], s[2], s[3]
                m.log('MOUSE -> %d,%d btn%d' % (s[1], s[2], s[3]))
        addr = (m.r['cs'] << 4) + m.r['ip']
        code = MEM[addr:addr+16]
        try:
            ins = next(md.disasm(code, m.r['ip']))
        except StopIteration:
            break
        m._cur_ip = ins.address
        m.r['ip'] = (ins.address + ins.size) & 0xFFFF
        m.exec_ins(ins)
        if m.steps % 2_000_000 == 0:
            m.dump_framebuffer('wf_%03dM' % (m.steps // 1000000))
            m.log('wf %dM cs:ip=%04x:%04x' % (m.steps // 1000000, m.r['cs'], m.r['ip']))
    m._wlog.close()
    print('done: %d steps in %.0fs video=%02x' % (m.steps, time.time() - t0, m.video_mode))
