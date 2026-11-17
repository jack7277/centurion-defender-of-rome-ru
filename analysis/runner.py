"""Mini 8086 PC emulator for Centurion RE — capstone-decoded.

Runs CENTURIO.EXE (LZEXE-packed; the stub unpacks itself) headless.
Goal: observe DAC palette writes (ports 3C8/3C9, int10 AH=10) and
framebuffer writes, and dump state per game screen.

DOS/BIOS faked just enough for this game.
"""
import os
import struct
import sys
import time
from capstone import Cs, CS_ARCH_X86, CS_MODE_16
from capstone.x86 import *
from capstone.x86_const import X86_OP_REG, X86_OP_MEM, X86_OP_IMM

HERE = os.path.dirname(os.path.abspath(__file__))
GAMEDIR = os.path.normpath(os.path.join(HERE, '..', 'Centurion_Defender_of_Rome'))
OUTDIR = os.path.join(HERE, 'emu_out')
os.makedirs(OUTDIR, exist_ok=True)

MEM = bytearray(1 << 20)

R16 = {X86_REG_AX: 'ax', X86_REG_CX: 'cx', X86_REG_DX: 'dx', X86_REG_BX: 'bx',
       X86_REG_SP: 'sp', X86_REG_BP: 'bp', X86_REG_SI: 'si', X86_REG_DI: 'di'}
R8 = {X86_REG_AL: ('ax', 0), X86_REG_CL: ('cx', 0), X86_REG_DL: ('dx', 0), X86_REG_BL: ('bx', 0),
      X86_REG_AH: ('ax', 8), X86_REG_CH: ('cx', 8), X86_REG_DH: ('dx', 8), X86_REG_BH: ('bx', 8)}
SREG = {X86_REG_ES: 'es', X86_REG_CS: 'cs', X86_REG_SS: 'ss', X86_REG_DS: 'ds'}

CF, PF, AF, ZF, SF, TF, IF, DF, OF = 1, 4, 16, 64, 128, 256, 512, 1024, 2048

md = Cs(CS_ARCH_X86, CS_MODE_16)
md.detail = True

# ---------------------------------------------------------------- DAC palette
dac = bytearray(768)          # 256 * RGB
dac_events = []               # (step, first_index, bytes written)
dac_cur_index = 0
fb_events = 0

def log_dac(step, count):
    dac_events.append((step, count))

class Machine:
    def __init__(self):
        self.r = {n: 0 for n in
                  ['ax', 'cx', 'dx', 'bx', 'sp', 'bp', 'si', 'di', 'cs', 'ds', 'es', 'ss', 'ip']}
        self.flags = 2
        self.halted = False
        self.steps = 0
        self.files = {}       # handle -> file object
        self.next_handle = 5
        self.dta = 0x8000     # DTA in "PSP" area
        self.video_mode = 3
        self.mem_top = 0xA0000
        self.next_free_seg = 0x2000
        self.trace_file = open(os.path.join(OUTDIR, 'trace.log'), 'w', buffering=8192, encoding='utf-8', errors='replace')
        from collections import deque
        self.trace = deque(maxlen=60)
        self.flow = open(os.path.join(OUTDIR, 'flow.log'), 'w', buffering=65536, encoding='utf-8', errors='replace')

    def dump_trace(self):
        for t in self.trace:
            self.trace_file.write(t + '\n')

    # ---------------- memory
    def phys(self, seg, off):
        if isinstance(off, str):
            off = self.r[off]
        if isinstance(seg, str):
            seg = self.r[seg]
        return ((seg << 4) + (off & 0xFFFF)) & 0xFFFFF

    def rb(self, a): return MEM[a]
    def wb(self, a, v): MEM[a] = v & 0xFF
    def rw(self, a): return MEM[a] | (MEM[(a + 1) & 0xFFFFF] << 8)
    def ww(self, a, v):
        MEM[a] = v & 0xFF
        MEM[(a + 1) & 0xFFFFF] = (v >> 8) & 0xFF

    # ---------------- registers
    def gr(self, reg):
        if reg in R16: return self.r[R16[reg]]
        if reg in R8:
            n, sh = R8[reg]
            return (self.r[n] >> sh) & 0xFF
        if reg in SREG: return self.r[SREG[reg]]
        return 0

    def sr(self, reg, v):
        if reg in R16:
            self.r[R16[reg]] = v & 0xFFFF
        elif reg in R8:
            n, sh = R8[reg]
            if sh:
                self.r[n] = (self.r[n] & 0x00FF) | ((v & 0xFF) << 8)
            else:
                self.r[n] = (self.r[n] & 0xFF00) | (v & 0xFF)
        elif reg in SREG:
            self.r[SREG[reg]] = v & 0xFFFF

    # flags
    def fl(self, m, v): self.flags = (self.flags | m) if v else (self.flags & ~m)
    def tf(self, m): return bool(self.flags & m)

    def set_szp(self, v, bits):
        self.fl(ZF, v == 0)
        self.fl(SF, bool(v & (1 << (bits - 1))))
        self.fl(PF, bin(v & 0xFF).count('1') % 2 == 0)

    def push(self, v):
        self.r['sp'] = (self.r['sp'] - 2) & 0xFFFF
        self.ww(self.phys('ss', self.r['sp']), v)

    def pop(self):
        v = self.rw(self.phys('ss', self.r['sp']))
        self.r['sp'] = (self.r['sp'] + 2) & 0xFFFF
        return v

    # ---------------- effective address
    def ea(self, op, default_seg='ds'):
        m = op.mem
        if m.segment:
            seg = SREG[m.segment]
        elif m.base == X86_REG_BP:
            seg = 'ss'          # 8086: BP-база по умолчанию в SS
        else:
            seg = default_seg
        base = 0
        if m.base: base += self.gr(m.base)
        if m.index: base += self.gr(m.index)
        return self.phys(seg, (base + m.disp) & 0xFFFF)

    def read_op(self, op, default_seg='ds'):
        if op.type == X86_OP_IMM:
            return op.imm & (0xFF if op.size == 1 else 0xFFFF)
        if op.type == X86_OP_REG: return self.gr(op.reg)
        if op.type == X86_OP_MEM:
            a = self.ea(op, default_seg)
            return self.rb(a) if op.size == 1 else self.rw(a)
        return 0

    def write_op(self, op, v, default_seg='ds'):
        if op.type == X86_OP_REG:
            self.sr(op.reg, v)
        elif op.type == X86_OP_MEM:
            a = self.ea(op, default_seg)
            if op.size == 1: self.wb(a, v)
            else: self.ww(a, v)

    # ---------------- stack / IO / DOS
    def io_out(self, port, v, size):
        global dac_cur_index
        if port == 0x3C8:
            dac_cur_index = v & 0xFF
        elif port == 0x3C9:
            dac[dac_cur_index * 3] = v
            # track index advance properly: writes come R,G,B triplets
            dac_writes.append((self.steps, dac_cur_index, v))
            self._dac_sub = getattr(self, '_dac_sub', 0) + 1
            if self._dac_sub == 3:
                self._dac_sub = 0
                dac_cur_index = (dac_cur_index + 1) & 0xFF
        elif port == 0x3DA:
            pass

    def io_in(self, port, size):
        if port == 0x3DA:
            # toggle retrace bits so the game doesn't hang waiting
            self._retr = getattr(self, '_retr', 0) ^ 8
            return self._retr | 1
        if port == 0x60:
            return 0
        return 0

    def dos(self):
        ax = self.r['ax']; ah = ax >> 8; al = ax & 0xFF
        self.log('int21 AH=%02x bx=%04x cx=%04x dx=%04x ds=%04x' % (ah, self.r['bx'], self.r['cx'], self.r['dx'], self.r['ds']))
        if ah == 0x00:  # set video mode
            self.video_mode = al
            self.log('VIDEO MODE %02x' % al)
        elif ah == 0x09:  # print string
            a = self.phys('ds', self.r['dx'])
            s = b''
            while MEM[a] != 0x24 and len(s) < 200:
                s += bytes([MEM[a]]); a += 1
            self.log('PRINT: %s' % s.decode('ascii', 'replace'))
        elif ah == 0x19:  # current drive
            self.sr(X86_REG_AL, 2)  # C:
        elif ah == 0x25:  # set vector
            vec = al
            MEM[vec*4:vec*4+2] = struct.pack('<H', self.r['dx'])
            MEM[vec*4+2:vec*4+4] = struct.pack('<H', self.r['ds'])
        elif ah == 0x35:  # get vector
            vec = al
            self.sr(X86_REG_BX, self.rw(vec*4))
            self.r['es'] = self.rw(vec*4+2)
        elif ah == 0x30:  # DOS version
            self.sr(X86_REG_AX, 5)
            self.sr(X86_REG_BX, 0)
            self.sr(X86_REG_CX, 0)
        elif ah == 0x3D:  # open file
            a = self.phys('ds', self.r['dx'])
            name = b''
            while MEM[a]:
                name += bytes([MEM[a]]); a += 1
            fname = name.decode('ascii', 'replace')
            norm = fname.replace(chr(92), '/')
            if len(norm) > 1 and norm[1] == ':':
                norm = norm[2:]
            norm = norm.lstrip('/')
            path = os.path.join(GAMEDIR, norm)
            if not os.path.exists(path):
                path = os.path.join(GAMEDIR, os.path.basename(norm))
            # try case-insensitive match
            if not os.path.exists(path):
                low = fname.lower()
                for f in os.listdir(GAMEDIR):
                    if f.lower() == low:
                        path = os.path.join(GAMEDIR, f)
                        break
            try:
                f = open(path, 'rb')
                h = self.next_handle; self.next_handle += 1
                self.files[h] = f
                self.sr(X86_REG_AX, h)
                self.fl(CF, False)
                self.log('OPEN %s -> h%d' % (fname, h))
            except OSError:
                # loader builds overlay path from argv[0]; if it fails, feed OVL0.OVL
                alt = os.path.join(GAMEDIR, 'OVL0.OVL')
                try:
                    f = open(alt, 'rb')
                    h = self.next_handle; self.next_handle += 1
                    self.files[h] = f
                    self.sr(X86_REG_AX, h)
                    self.fl(CF, False)
                    self.log('OPEN %s -> h%d (fallback OVL0.OVL)' % (fname, h))
                except OSError:
                    self.sr(X86_REG_AX, 2)
                    self.fl(CF, True)
                    self.log('OPEN FAIL %s' % fname)
        elif ah == 0x3E:  # close
            h = self.r['bx']
            self.files.pop(h, None)
            self.fl(CF, False)
        elif ah == 0x3F:  # read
            h = self.r['bx']; n = self.r['cx']; a = self.phys('ds', self.r['dx'])
            f = self.files.get(h)
            if f is None and h == 0:
                f = getattr(self, '_ovl0', None)
                if f is None:
                    f = open(os.path.join(GAMEDIR, 'OVL0.OVL'), 'rb')
                    self._ovl0 = f
            if f is None:
                self.sr(X86_REG_AX, 0); self.fl(CF, True)
            else:
                data = f.read(n)
                MEM[a:a+len(data)] = data
                self.sr(X86_REG_AX, len(data))
                self.fl(CF, False)
        elif ah == 0x40:  # write (rarely used)
            h = self.r['bx']; n = self.r['cx']
            self.sr(X86_REG_AX, n)
            self.fl(CF, False)
        elif ah == 0x42:  # seek
            h = self.r['bx']; pos = (self.r['cx'] << 16) | self.r['dx']
            f = self.files.get(h)
            if f is None and h == 0:
                f = getattr(self, '_ovl0', None)
                if f is None:
                    f = open(os.path.join(GAMEDIR, 'OVL0.OVL'), 'rb')
                    self._ovl0 = f
            if f:
                f.seek(pos, al)  # al: 0 abs, 1 cur, 2 end
                np_ = f.tell()
                self.sr(X86_REG_AX, np_ & 0xFFFF)
                self.sr(X86_REG_DX, (np_ >> 16) & 0xFFFF)
                self.fl(CF, False)
            else:
                self.fl(CF, True)
        elif ah == 0x44:  # ioctl
            self.sr(X86_REG_DX, 0x80)
            self.fl(CF, False)
        elif ah == 0x48:  # alloc memory
            paras = self.r['bx']
            seg = self.next_free_seg
            self.next_free_seg += paras
            self.sr(X86_REG_AX, seg)
            self.fl(CF, False)
            self.log('ALLOC %d paras -> %04x' % (paras, seg))
        elif ah == 0x49 or ah == 0x4A:
            self.fl(CF, False)
        elif ah == 0x4C:  # exit
            self.log('EXIT code %d' % al)
            self.halted = True
        elif ah == 0x1A:  # set DTA
            self.dta = self.phys('ds', self.r['dx'])
        elif ah == 0x2F:  # get DTA
            self.r['es'] = self.dta >> 4
            self.sr(X86_REG_BX, self.dta & 15)
        elif ah == 0x54:  # verify flag
            self.sr(X86_REG_AL, 0)
        elif ah == 0x2C:  # get time
            self.sr(X86_REG_CX, 0x0800); self.sr(X86_REG_DX, 0)
        elif ah == 0x2A:  # get date
            self.sr(X86_REG_CX, 2026); self.sr(X86_REG_DX, 0x1115)
        else:
            self.log('DOS21 AH=%02x unhandled' % ah)
            self.fl(CF, True)

    def bios(self, num):
        ax = self.r['ax']; ah = ax >> 8; al = ax & 0xFF
        if num == 0x10:
            if ah == 0x00:
                self.video_mode = al
                self.log('BIOS VIDEO MODE %02x' % al)
            elif ah == 0x10:
                if al == 0x12 or al == 0x02:
                    # set DAC block from ES:DX
                    a = self.phys('es', self.r['dx'])
                    count = self.r['cx'] if al == 0x12 else 17
                    first = self.r['bx'] & 0xFFFF if al == 0x12 else 0
                    n = min(count, 256 - first) * 3
                    dac[first*3:first*3+n] = MEM[a:a+n]
                    self.log('PALETTE SET al=%02x first=%d count=%d from %04x:%04x' % (al, first, count, self.r['es'], self.r['dx']))
                    self.dump_palette('int10_%06d' % self.steps)
                elif al == 0x10:
                    a = self.phys('es', self.r['dx'])
                    idx = self.r['bx'] & 0xFF
                    dac[idx*3:idx*3+3] = MEM[a:a+3]
            elif ah == 0x0F:
                self.sr(X86_REG_AX, self.video_mode | 0x50 << 8)
                self.sr(X86_REG_BH, 0)
            elif ah == 0x11:
                pass  # font load etc — ignore
        elif num == 0x11:
            self.sr(X86_REG_AX, 0x0021 | (1 << 6))  # equipment: 80x25 color
        elif num == 0x12:
            self.sr(X86_REG_AX, 640)  # 640 KB
        elif num == 0x15:
            if ah == 0x88:
                self.sr(X86_REG_AX, 0)
            self.fl(CF, True)
        elif num == 0x16:  # keyboard
            if ah == 0x00:
                self.sr(X86_REG_AX, 0)  # no key (blocking read shouldn't happen)
            elif ah == 0x01:
                self.fl(ZF, True)  # no key available
        elif num == 0x1A:
            self.sr(X86_REG_CX, 0); self.sr(X86_REG_DX, self.steps // 1000 & 0xFFFF)
        elif num == 0x33:  # mouse: not present
            self.sr(X86_REG_AX, 0)
        else:
            self.log('BIOS INT %02x AH=%02x unhandled' % (num, ah))

    def log(self, s):
        self.trace_file.write('[%9d] %s\n' % (self.steps, s))

    def in_overlay(self, addr):
        # overlays/load areas legitimately above the kernel image
        return 0x1B108 <= addr < 0x90000

    def dump_palette(self, tag):
        with open(os.path.join(OUTDIR, 'pal_%s.bin' % tag), 'wb') as f:
            f.write(dac)

    def dump_framebuffer(self, tag):
        from PIL import Image
        if self.video_mode == 0x13:
            im = Image.new('RGB', (320, 200))
            px = im.load()
            base = 0xA0000
            for y in range(200):
                for x in range(320):
                    v = MEM[base + y*320 + x]
                    px[x, y] = (dac[v*3]*4, dac[v*3+1]*4, dac[v*3+2]*4)
            im.save(os.path.join(OUTDIR, 'fb_%s.png' % tag))

    # ---------------- main loop
    def run(self, max_steps):
        while not self.halted and self.steps < max_steps:
            self.steps += 1
            addr = self.phys('cs', 'ip')
            code = MEM[addr:addr+16]
            try:
                ins = next(md.disasm(code, self.r['ip']))
            except StopIteration:
                self.log('UNDECODEABLE at %05x' % addr)
                break
            self.trace.append('%05x: %-10s %-20s ax=%04x bx=%04x cx=%04x dx=%04x si=%04x di=%04x bp=%04x sp=%04x ds=%04x es=%04x fl=%04x' % (
                addr, ins.mnemonic, ins.op_str, self.r['ax'], self.r['bx'], self.r['cx'], self.r['dx'],
                self.r['si'], self.r['di'], self.r['bp'], self.r['sp'], self.r['ds'], self.r['es'], self.flags))
            if self.steps < 12000 or 2300 <= self.steps <= 2600:
                self.dump_trace()
                self.trace.clear()
            if addr == 0x1AA9C:
                sp = self.r['sp']; ss = self.r['ss']
                self.log('MANAGER stack: %s' % ' '.join('%04x' % self.rw(((ss<<4)+((sp+i)&0xFFFF))&0xFFFFF) for i in range(0, 28, 2)))
            if self.steps == 700:
                dgp = 0x1E660
                self.log('DG yoffs @C410: %s' % MEM[dgp+0xF600:dgp+0xF600+16].hex())
                self.log('DG latin bmp @C4B0: %s' % MEM[dgp+0xF6A0:dgp+0xF6A0+16].hex())
                self.log('DG cyr bmp @C7B0: %s' % MEM[dgp+0xF9A0:dgp+0xF9A0+16].hex())
                self.log('DG cyr widths @9BFC: %s' % MEM[dgp+0x9BFC:dgp+0x9BFC+16].hex())
            if addr == 0x189C8 and not getattr(self, '_dr_seen', False):
                self._dr_seen = True
                base = (self.r['ds'] << 4)
                self.log('DRAW_STRING hit: ds=%04x desc W=%04x Y=%04x B=%04x h=%02x sp=%02x cs=%02x sh=%02x' % (
                    self.r['ds'],
                    self.rw(base+0x9b56), self.rw(base+0x9b58), self.rw(base+0x9b5a),
                    MEM[base+0x9b5c], MEM[base+0x9b5d], MEM[base+0x9b5e], MEM[base+0x9b5f]))
                dgp = 0x1E660
                self.log('font block @ds C410: %s' % MEM[dgp+0xF600:dgp+0xF600+16].hex())
                self.log('latin bmp  @ds C4B0: %s' % MEM[dgp+0xF6A0:dgp+0xF6A0+16].hex())
                self.log('cyr bmp    @ds C7B0: %s' % MEM[dgp+0xF9A0:dgp+0xF9A0+16].hex())
            self._cur_ip = ins.address
            self.r['ip'] = (ins.address + ins.size) & 0xFFFF
            if ins.mnemonic in ('call', 'lcall', 'int', 'ljmp', 'iret', 'retf'):
                self.flow.write('%9d %05x %s %s -> cs=%04x ip=%04x\n' % (
                    self.steps, addr, ins.mnemonic, ins.op_str, self.r['cs'], self.r['ip']))
            if 0x1A830 <= addr <= 0x1A9A0 or addr in (0x19ED2,):
                self.trace_file.write('WATCH %9d %05x %s %s al=%02x bx=%04x\n' % (
                    self.steps, addr, ins.mnemonic, ins.op_str, self.r['ax'] & 0xFF, self.r['bx']))
            # catch repeated calls to the AH=25/35 wrappers (image 0xA7C0/0xA7C5 = phys 0x1A7C0/0x1A7C5)
            if addr in (0x1A7C0, 0x1A7C5) and self.steps > 400000:
                sp = self.r['sp']; ss = self.r['ss']
                ret = self.rw(((ss << 4) + ((sp + 2) & 0xFFFF)) & 0xFFFFF)  # caller ret addr (near)
                self.trace_file.write('WRAPCALL %9d addr=%05x ax=%04x dx=%04x ds=%04x caller_ip=%04x stack=%s\n' % (
                    self.steps, addr, self.r['ax'], self.r['dx'], self.r['ds'], ret,
                    ' '.join('%04x' % self.rw(((ss << 4) + ((sp + i) & 0xFFFF)) & 0xFFFFF) for i in range(0, 16, 2))))
                self._wrapcalls = getattr(self, '_wrapcalls', 0) + 1
                if self._wrapcalls > 200:
                    self.halted = True
            # wild jump detector
            nxt = self.phys('cs', 'ip')
            if ins.mnemonic in ('jmp', 'ljmp', 'call', 'lcall', 'ret', 'retf', 'retn', 'iret', 'int') or True:
                pass
            if nxt < 0x0FF00 or (0x1B108 < nxt and not self.in_overlay(nxt)):
                self.log('WILD JUMP to %05x' % nxt)
                self.dump_trace()
                self.halted = True
                break
            self.exec_ins(ins)
            if self.steps % 5_000_000 == 0:
                self.log('... %dM steps, cs:ip=%04x:%04x' % (self.steps // 1000000, self.r['cs'], self.r['ip']))
                self.dump_framebuffer('auto_%06dM' % (self.steps // 1000000))
                self.dump_palette('auto_%06dM' % (self.steps // 1000000))
        self.log('STOP steps=%d halted=%s' % (self.steps, self.halted))
        self.dump_framebuffer('final')
        self.dump_palette('final')

    def exec_ins(self, ins):
        m = ins.mnemonic
        ops = ins.operands

        # ---- data movement
        if m == 'mov':
            self.write_op(ops[0], self.read_op(ops[1], SREG.get(ops[0].mem.segment, 'ds') if ops[0].type == X86_OP_MEM else 'ds'))
        elif m == 'movzx':
            self.write_op(ops[0], self.read_op(ops[1]))
        elif m == 'xchg':
            a = self.read_op(ops[0]); b = self.read_op(ops[1])
            self.write_op(ops[0], b); self.write_op(ops[1], a)
        elif m == 'lea':
            self.write_op(ops[0], self.ea(ops[1]) & 0xFFFF if False else ((ops[1].mem.disp + (self.gr(ops[1].mem.base) if ops[1].mem.base else 0) + (self.gr(ops[1].mem.index) if ops[1].mem.index else 0)) & 0xFFFF))
        elif m in ('lds', 'les'):
            a = self.ea(ops[1])
            self.write_op(ops[0], self.rw(a))
            self.r['ds' if m == 'lds' else 'es'] = self.rw(a + 2)
        elif m == 'push':
            self.push(self.read_op(ops[0]))
        elif m == 'pop':
            v = self.pop()
            self.write_op(ops[0], v)
        elif m == 'pushf' or m == 'pushfw':
            self.push(self.flags)
        elif m == 'popf' or m == 'popfw':
            self.flags = self.pop() | 2
        elif m == 'lahf':
            self.sr(X86_REG_AH, self.flags & 0xFF)
        elif m == 'sahf':
            self.flags = (self.flags & ~0xFF) | (self.r['ax'] >> 8 & 0xFF) | 2
        elif m == 'xlat':
            self.sr(X86_REG_AL, self.rb(self.phys('ds', (self.r['bx'] + (self.r['ax'] & 0xFF)) & 0xFFFF)))
        elif m == 'nop':
            pass

        # ---- ALU
        elif m in ('add', 'or', 'adc', 'sbb', 'and', 'sub', 'xor', 'cmp', 'test'):
            bits = 8 if ops[0].size == 1 else 16
            mask = (1 << bits) - 1
            a = self.read_op(ops[0]); b = self.read_op(ops[1], 'ds')
            carry_in = 1 if self.tf(CF) else 0
            if m == 'add' or m == 'adc':
                bb = b + (carry_in if m == 'adc' else 0)
                res = (a + bb) & mask
                self.fl(CF, a + bb > mask)
                self.fl(OF, bool((~(a ^ bb) & (a ^ res)) & (1 << (bits - 1))))
                self.set_szp(res, bits)
                self.write_op(ops[0], res)
            elif m == 'sub' or m == 'sbb' or m == 'cmp':
                bb = b + (carry_in if m == 'sbb' else 0)
                res = (a - bb) & mask
                self.fl(CF, a < bb)
                self.fl(OF, bool(((a ^ bb) & (a ^ res)) & (1 << (bits - 1))))
                self.set_szp(res, bits)
                if m != 'cmp':
                    self.write_op(ops[0], res)
            elif m == 'and' or m == 'test':
                res = a & b
                self.set_szp(res, bits); self.fl(CF, False); self.fl(OF, False)
                if m == 'and': self.write_op(ops[0], res)
            elif m == 'or':
                res = a | b
                self.set_szp(res, bits); self.fl(CF, False); self.fl(OF, False)
                self.write_op(ops[0], res)
            elif m == 'xor':
                res = a ^ b
                self.set_szp(res, bits); self.fl(CF, False); self.fl(OF, False)
                self.write_op(ops[0], res)
        elif m in ('inc', 'dec'):
            bits = 8 if ops[0].size == 1 else 16
            mask = (1 << bits) - 1
            a = self.read_op(ops[0])
            res = (a + 1) & mask if m == 'inc' else (a - 1) & mask
            self.set_szp(res, bits)
            if m == 'inc': self.fl(OF, res == (1 << (bits - 1)))
            else: self.fl(OF, res == (1 << (bits - 1)) - 1)
            self.write_op(ops[0], res)
        elif m == 'neg':
            bits = 8 if ops[0].size == 1 else 16
            mask = (1 << bits) - 1
            a = self.read_op(ops[0])
            res = (-a) & mask
            self.fl(CF, a != 0); self.set_szp(res, bits)
            self.fl(OF, a == (1 << (bits - 1)))
            self.write_op(ops[0], res)
        elif m == 'not':
            self.write_op(ops[0], ~self.read_op(ops[0]) & ((1 << (8 * ops[0].size)) - 1))
        elif m in ('mul', 'imul', 'div', 'idiv'):
            self.exec_muldiv(m, ops)
        elif m in ('cbw', 'cwd', 'cwde', 'cdq'):
            if m in ('cbw', 'cwde'):
                self.r['ax'] = (self.r['ax'] & 0x80) and (self.r['ax'] | 0xFF00) or (self.r['ax'] & 0xFF)
            else:
                self.r['dx'] = 0xFFFF if self.r['ax'] & 0x8000 else 0
        elif m in ('aam', 'aad'):
            al = self.r['ax'] & 0xFF
            if m == 'aam':
                self.r['ax'] = ((al // 10) << 8) | (al % 10)
            else:
                self.r['ax'] = (((self.r['ax'] >> 8) * 10 + al) & 0xFF)

        # ---- shifts/rotates
        elif m in ('rol', 'ror', 'rcl', 'rcr', 'shl', 'sal', 'shr', 'sar'):
            self.exec_shift(m, ops)

        # ---- control flow
        elif m == 'jmp':
            if ops[0].type == X86_OP_IMM:
                self.r['ip'] = ops[0].imm & 0xFFFF
            else:
                v = self.read_op(ops[0])
                if ops[0].size == 4:  # far
                    a = self.ea(ops[0])
                    self.r['ip'] = self.rw(a)
                    self.r['cs'] = self.rw(a + 2)
                else:
                    self.r['ip'] = v & 0xFFFF
        elif m == 'ljmp':
            self.r['ip'] = ops[1].imm & 0xFFFF
            self.r['cs'] = ops[0].imm & 0xFFFF
        elif m == 'call':
            self.push(self.r['ip'])
            self.r['ip'] = ops[0].imm & 0xFFFF if ops[0].type == X86_OP_IMM else self.read_op(ops[0]) & 0xFFFF
        elif m == 'lcall':
            self.push(self.r['cs']); self.push(self.r['ip'])
            if ops[0].type == X86_OP_IMM:
                self.r['ip'] = ops[1].imm & 0xFFFF
                self.r['cs'] = ops[0].imm & 0xFFFF
            else:
                a = self.ea(ops[0])
                self.r['ip'] = self.rw(a); self.r['cs'] = self.rw(a + 2)
        elif m in ('ret', 'retn', 'retf', 'lret'):
            self.r['ip'] = self.pop()
            if m in ('retf', 'lret'):
                self.r['cs'] = self.pop()
            if ops and ops[0].type == X86_OP_IMM:
                self.r['sp'] = (self.r['sp'] + ops[0].imm) & 0xFFFF
        elif m in ('loop', 'loope', 'loopne', 'loopnz', 'loopz', 'jcxz'):
            self.exec_loop(m, ops)
        elif m.startswith('j'):
            self.exec_jcc(m, ops)
        elif m in ('int', 'into'):
            num = ops[0].imm & 0xFF if ops else 4
            self.do_int(num)
        elif m == 'iret':
            self.r['ip'] = self.pop()
            self.r['cs'] = self.pop()
            self.flags = self.pop() | 2

        # ---- string ops
        elif m in ('movsb', 'movsw', 'stosb', 'stosw', 'lodsb', 'lodsw', 'scasb', 'scasw', 'cmpsb', 'cmpsw') or \
             m in ('rep', 'repe', 'repne', 'repz', 'repnz') or \
             any(k in m for k in ('movs', 'stos', 'lods', 'scas', 'cmps')):
            self.exec_string(ins)
        elif m == 'cld': self.fl(DF, False)
        elif m == 'std': self.fl(DF, True)
        elif m == 'clc': self.fl(CF, False)
        elif m == 'stc': self.fl(CF, True)
        elif m == 'cmc': self.fl(CF, not self.tf(CF))
        elif m == 'cli': self.fl(IF, False)
        elif m == 'sti': self.fl(IF, True)
        elif m == 'in':
            v = self.io_in(self.r['dx'] if len(ops) > 0 and ops[0].type == X86_OP_REG else ops[0].imm, ops[-1].size if ops else 1)
            self.sr(X86_REG_AX if ops[-1].size == 2 else X86_REG_AL, v)
        elif m == 'out':
            port = ops[0].imm if ops[0].type == X86_OP_IMM else self.r['dx']
            self.io_out(port, self.read_op(ops[1]), ops[1].size)
        elif m == 'hlt':
            pass
        else:
            self.log('UNIMPL %s %s at %05x' % (m, ins.op_str, ins.address))
            self.dump_trace()
            self._unimpl = getattr(self, '_unimpl', 0) + 1
            if self._unimpl > 3:
                self.halted = True

    def exec_muldiv(self, m, ops):
        if ops:
            bits = 8 if ops[0].size == 1 else 16
            v = self.read_op(ops[0])
        else:
            bits = 16 if 'w' in m else 8
            v = self.read_op(ops[0]) if ops else 0
        if m == 'mul':
            if bits == 8:
                r = (self.r['ax'] & 0xFF) * v
                self.r['ax'] = r & 0xFFFF
                self.fl(CF, r > 0xFF); self.fl(OF, r > 0xFF)
            else:
                r = self.r['ax'] * v
                self.r['ax'] = r & 0xFFFF
                self.r['dx'] = (r >> 16) & 0xFFFF
                self.fl(CF, r > 0xFFFF); self.fl(OF, r > 0xFFFF)
        elif m == 'imul':
            if len(ops) == 1:
                if bits == 8:
                    sv = v - 256 if v > 127 else v
                    sa = self.r['ax'] & 0xFF
                    sa = sa - 256 if sa > 127 else sa
                    r = sa * sv
                    self.r['ax'] = r & 0xFFFF
                    self.fl(CF, r < -128 or r > 127); self.fl(OF, r < -128 or r > 127)
                else:
                    sv = v - 65536 if v > 32767 else v
                    sa = self.r['ax'] - 65536 if self.r['ax'] > 32767 else self.r['ax']
                    r = sa * sv
                    self.r['ax'] = r & 0xFFFF
                    self.r['dx'] = (r >> 16) & 0xFFFF
                    self.fl(CF, r < -32768 or r > 32767); self.fl(OF, r < -32768 or r > 32767)
            elif len(ops) == 2:
                sv = v - 65536 if v > 32767 else v
                sv2 = self.read_op(ops[1])
                sv2 = sv2 - 65536 if sv2 > 32767 else sv2
                r = sv * sv2
                self.write_op(ops[0], r & 0xFFFF)
                self.fl(CF, r < -32768 or r > 32767); self.fl(OF, r < -32768 or r > 32767)
        elif m in ('div', 'idiv'):
            if bits == 8:
                num = self.r['ax']
                if m == 'idiv':
                    num = num - 65536 if num > 32767 else num
                    v = v - 256 if v > 127 else v
                if v == 0:
                    self.do_int(0)
                    return
                q = int(num / v) if m == 'idiv' else num // v
                r_ = num - q * v
                self.r['ax'] = ((r_ & 0xFF) << 8) | (q & 0xFF)
            else:
                num = (self.r['dx'] << 16) | self.r['ax']
                if m == 'idiv':
                    num = num - (1 << 32) if num > (1 << 31) - 1 else num
                    v = v - 65536 if v > 32767 else v
                if v == 0:
                    self.do_int(0)
                    return
                q = int(num / v) if m == 'idiv' else num // v
                r_ = num - q * v
                self.r['ax'] = q & 0xFFFF
                self.r['dx'] = r_ & 0xFFFF

    def exec_shift(self, m, ops):
        bits = 8 if ops[0].size == 1 else 16
        mask = (1 << bits) - 1
        a = self.read_op(ops[0])
        if len(ops) > 1:
            n = self.read_op(ops[1]) & 0x1F
        else:
            n = 1
        if ops[0].type == X86_OP_REG and ops[0].size == 1:
            pass
        for _ in range(n):
            if m in ('shl', 'sal'):
                self.fl(CF, bool(a & (1 << (bits - 1))))
                a = (a << 1) & mask
            elif m == 'shr':
                self.fl(CF, a & 1)
                a >>= 1
            elif m == 'sar':
                self.fl(CF, a & 1)
                a = (a >> 1) | (a & (1 << (bits - 1)))
            elif m == 'rol':
                self.fl(CF, bool(a & (1 << (bits - 1))))
                a = ((a << 1) | (1 if self.tf(CF) else 0)) & mask
            elif m == 'ror':
                self.fl(CF, a & 1)
                a = (a >> 1) | ((1 << (bits - 1)) if self.tf(CF) else 0)
            elif m == 'rcl':
                c = 1 if self.tf(CF) else 0
                self.fl(CF, bool(a & (1 << (bits - 1))))
                a = ((a << 1) | c) & mask
            elif m == 'rcr':
                c = 1 if self.tf(CF) else 0
                self.fl(CF, a & 1)
                a = (a >> 1) | (c << (bits - 1))
        self.set_szp(a, bits)
        self.write_op(ops[0], a)

    def cond(self, m):
        cf, zf, sf, of = self.tf(CF), self.tf(ZF), self.tf(SF), self.tf(OF)
        pf = self.tf(PF)
        return {
            'ja': not cf and not zf, 'jae': not cf, 'jb': cf, 'jc': cf, 'jbe': cf or zf,
            'je': zf, 'jz': zf, 'jne': not zf, 'jnz': not zf,
            'jg': not zf and sf == of, 'jge': sf == of, 'jl': sf != of, 'jle': zf or sf != of,
            'jnc': not cf, 'jnb': not cf, 'jnbe': not cf and not zf, 'jnae': cf,
            'jng': zf or sf != of, 'jnge': sf != of, 'jnl': sf == of, 'jnle': not zf and sf == of,
            'jno': not of, 'jnp': not pf, 'jns': not sf, 'jo': of, 'jp': pf, 'jpe': pf, 'jpo': not pf,
            'js': sf,
        }.get(m, False)

    def exec_jcc(self, m, ops):
        if self.cond(m):
            self.r['ip'] = ops[0].imm & 0xFFFF

    def exec_loop(self, m, ops):
        if m == 'jcxz':
            if self.r['cx'] == 0:
                self.r['ip'] = ops[0].imm & 0xFFFF
            return
        # fast-forward пустых циклов задержки (loop в самого себя)
        if m == 'loop' and ops[0].imm & 0xFFFF == self._cur_ip and self.r['cx'] > 1:
            self.r['cx'] = 1
        self.r['cx'] = (self.r['cx'] - 1) & 0xFFFF
        take = self.r['cx'] != 0
        if m in ('loope', 'loopz'):
            take = take and self.tf(ZF)
        elif m in ('loopne', 'loopnz'):
            take = take and not self.tf(ZF)
        if take:
            self.r['ip'] = ops[0].imm & 0xFFFF

    def do_int(self, num):
        if num == 0x21:
            self.dos()
            return
        if num in (0x10, 0x11, 0x12, 0x15, 0x16, 0x1A, 0x33):
            self.bios(num)
            return
        if num == 0:
            self.log('DIVIDE ERROR int0')
            self.halted = True
            return
        # chained vectors: emulate stack frame + jump through IVT if set
        seg = self.rw(num * 4 + 2)
        off = self.rw(num * 4)
        if seg or off:
            self.push(self.flags)
            self.push(self.r['cs'])
            self.push(self.r['ip'])
            self.r['cs'] = seg
            self.r['ip'] = off
        else:
            self.log('INT %02x unset' % num)

    def exec_string(self, ins):
        # prefixes: rep/repe/repne modify; actual op in ins.mnemonic for capstone
        m = ins.mnemonic
        rep_kind = None
        op_m = m
        if m in ('rep', 'repe', 'repz'):
            rep_kind = 'rep'
            op_m = None
        elif m in ('repne', 'repnz'):
            rep_kind = 'repne'
            op_m = None
        # capstone with detail: rep prefix appears in ins.prefix; mnemonic is the op
        # but mnemonic already includes it for string ops? Handle both:
        if op_m is None:
            # find the real op from bytes after prefixes
            op_m = None
        df = -1 if self.tf(DF) else 1

        def step_movs(sz):
            a = self.phys('ds', self.r['si']); b = self.phys('es', self.r['di'])
            if sz == 1: self.wb(b, self.rb(a))
            else: self.ww(b, self.rw(a))
            self.r['si'] = (self.r['si'] + sz * df) & 0xFFFF
            self.r['di'] = (self.r['di'] + sz * df) & 0xFFFF

        def step_stos(sz):
            b = self.phys('es', self.r['di'])
            if sz == 1: self.wb(b, self.r['ax'] & 0xFF)
            else: self.ww(b, self.r['ax'])
            self.r['di'] = (self.r['di'] + sz * df) & 0xFFFF

        def step_lods(sz):
            a = self.phys('ds', self.r['si'])
            if sz == 1: self.sr(X86_REG_AL, self.rb(a))
            else: self.r['ax'] = self.rw(a)
            self.r['si'] = (self.r['si'] + sz * df) & 0xFFFF

        def step_scas(sz):
            b = self.phys('es', self.r['di'])
            v = self.rb(b) if sz == 1 else self.rw(b)
            a = (self.r['ax'] & 0xFF) if sz == 1 else self.r['ax']
            res = (a - v) & (0xFF if sz == 1 else 0xFFFF)
            self.set_szp(res, 8 if sz == 1 else 16)
            self.fl(CF, a < v)
            self.r['di'] = (self.r['di'] + sz * df) & 0xFFFF

        def step_cmps(sz):
            a_ = self.phys('ds', self.r['si']); b_ = self.phys('es', self.r['di'])
            va = self.rb(a_) if sz == 1 else self.rw(a_)
            vb = self.rb(b_) if sz == 1 else self.rw(b_)
            res = (va - vb) & (0xFF if sz == 1 else 0xFFFF)
            self.set_szp(res, 8 if sz == 1 else 16)
            self.fl(CF, va < vb)
            self.r['si'] = (self.r['si'] + sz * df) & 0xFFFF
            self.r['di'] = (self.r['di'] + sz * df) & 0xFFFF

        table = {'movsb': (step_movs, 1), 'movsw': (step_movs, 2),
                 'stosb': (step_stos, 1), 'stosw': (step_stos, 2),
                 'lodsb': (step_lods, 1), 'lodsw': (step_lods, 2),
                 'scasb': (step_scas, 1), 'scasw': (step_scas, 2),
                 'cmpsb': (step_cmps, 1), 'cmpsw': (step_cmps, 2)}

        # determine real op & whether rep
        has_rep = ins.prefix[0] in (0xF3,) if ins.prefix else False
        has_repne = ins.prefix[0] in (0xF2,) if ins.prefix else False
        fn_sz = table.get(m)
        if fn_sz is None:
            # capstone sometimes gives mnemonic like 'rep movsb'
            for k in table:
                if k in m:
                    fn_sz = table[k]
                    has_rep = m.startswith('rep ') or 'rep ' in m
                    has_rep = 'repne' not in m and 'repnz' not in m and has_rep
                    has_repne = 'repne' in m or 'repnz' in m
                    break
        if fn_sz is None:
            self.log('STRING OP UNIMPL %s' % m)
            return
        fn, sz = fn_sz
        if has_rep or has_repne:
            while self.r['cx']:
                fn(sz)
                self.r['cx'] = (self.r['cx'] - 1) & 0xFFFF
                if has_repne and m.startswith('cmps') or has_repne and m.startswith('scas'):
                    if self.tf(ZF): break
                if has_rep and (m.startswith('cmps') or m.startswith('scas')):
                    if not self.tf(ZF): break
        else:
            fn(sz)


def main():
    # Load the already-unpacked program (produced by emu.py LZEXE unpacking,
    # relocations applied for load segment 0x1000).
    img = open(os.path.join(HERE, 'CENTURIO.patched.bin'), 'rb').read()
    LOAD = 0x1000
    MEM[LOAD * 16: LOAD * 16 + len(img)] = img

    # minimal PSP at 0x0FF0 with command tail " v nosnd k"
    PSP = 0x0FF0
    tail = b' v nosnd k\r'
    MEM[PSP * 16 + 0x80] = len(tail) - 1
    MEM[PSP * 16 + 0x81: PSP * 16 + 0x81 + len(tail)] = tail
    MEM[PSP * 16 + 0x00] = 0xCD  # int 20h
    MEM[PSP * 16 + 0x01] = 0x20
    struct.pack_into('<H', MEM, PSP * 16 + 0x02, 0xA000)  # top of memory
    ENV = 0x0F00
    envblk = b'\x00' + struct.pack('<H', 1) + b'C:' + bytes([92]) + b'CENTURIO.EXE' + b'\x00'
    MEM[ENV * 16: ENV * 16 + len(envblk)] = envblk
    struct.pack_into('<H', MEM, PSP * 16 + 0x2C, ENV)  # environment segment

    m = Machine()
    m.r['cs'] = 0x1a7b        # entry from LZEXE final jump
    m.r['ip'] = 0x0322
    m.r['ds'] = PSP
    m.r['es'] = PSP
    m.r['ss'] = 0x2e66      # EXE hdr ss link 0x1E66 + load 0x1000
    m.r['sp'] = 0x0800
    m.log('entry cs:ip = %04x:%04x (unpacked image at %04x:0)' % (m.r['cs'], m.r['ip'], LOAD))

    max_steps = int(sys.argv[1]) if len(sys.argv) > 1 else 300_000_000
    t0 = time.time()
    m.run(max_steps)
    print('done: %d steps in %.1fs' % (m.steps, time.time() - t0))
    print('video mode', m.video_mode)

if __name__ == '__main__':
    main()
