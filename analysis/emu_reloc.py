# Minimal 8086 emulator for the LZEXE stub+decompressor of CENTURIO.EXE
import struct, sys

img = open('CENTURIO.EXE','rb').read()[32:]
MEM = bytearray(1 << 20)
LOAD = 0x1000
MEM[LOAD*16 : LOAD*16 + len(img)] = img

RELOCS = []
r = {n: 0 for n in ['ax','bx','cx','dx','si','di','bp','sp','cs','ds','es','ss','ip']}
r['cs'] = LOAD + 0x7c6; r['ip'] = 0x12
r['ds'] = LOAD - 0x10; r['es'] = LOAD - 0x10
r['ss'] = 0x3000; r['sp'] = 0xFFFE
DF = 0
CF = 0
ZF = 0
SF = 0
OF = 0

def phys(seg, off):
    if isinstance(off, str): off = r[off]
    return ((r[seg] << 4) + (off & 0xFFFF)) & 0xFFFFF
def rb(addr): return MEM[addr]
def wb(addr, v): MEM[addr] = v & 0xFF
def rw(addr): return MEM[addr] | (MEM[(addr+1) & 0xFFFFF] << 8)
def ww(addr, v):
    MEM[addr] = v & 0xFF
    MEM[(addr+1) & 0xFFFFF] = (v >> 8) & 0xFF

def get16(seg, off): return rw(phys(seg, off))

def push(v):
    r['sp'] = (r['sp'] - 2) & 0xFFFF
    ww(phys('ss', r['sp']), v & 0xFFFF)
def pop():
    v = get16('ss', r['sp']); r['sp'] = (r['sp'] + 2) & 0xFFFF
    return v

REG8 = ['al','cl','dl','bl','ah','ch','dh','bh']
def get8(i):
    base = REG8[i]
    rx = base[0] + 'x'
    if base[1] == 'l': return r[rx] & 0xFF
    else: return (r[rx] >> 8) & 0xFF
def set8(i, v):
    base = REG8[i]; rx = base[0] + 'x'
    if base[1] == 'l': r[rx] = (r[rx] & 0xFF00) | (v & 0xFF)
    else: r[rx] = (r[rx] & 0x00FF) | ((v & 0xFF) << 8)

steps = 0
from collections import deque
trace = deque(maxlen=40)
while True:
    steps += 1
    if steps > 5_000_000:
        print('step limit'); break
    addr = phys('cs', 'ip')
    op = rb(addr)
    b1 = rb(addr+1)
    trace.append('cs=%04x ip=%04x  %02x %02x %02x %02x   ax=%04x bx=%04x cx=%04x dx=%04x si=%04x di=%04x bp=%04x es=%04x ds=%04x CF=%d ZF=%d' % (
        r['cs'], r['ip'], op, b1, rb(addr+2), rb(addr+3),
        r['ax'], r['bx'], r['cx'], r['dx'], r['si'], r['di'], r['bp'], r['es'], r['ds'], CF, ZF))
    def adv(n=1): r['ip'] = (r['ip'] + n) & 0xFFFF
    if   op == 0x50: push(r['ax']); adv()
    elif op == 0x51: push(r['cx']); adv()
    elif op == 0x52: push(r['dx']); adv()
    elif op == 0x53: push(r['bx']); adv()
    elif op == 0x55: push(r['bp']); adv()
    elif op == 0x56: push(r['si']); adv()
    elif op == 0x57: push(r['di']); adv()
    elif op == 0x58: r['ax'] = pop(); adv()
    elif op == 0x59: r['cx'] = pop(); adv()
    elif op == 0x5A: r['dx'] = pop(); adv()
    elif op == 0x5B: r['bx'] = pop(); adv()
    elif op == 0x5D: r['bp'] = pop(); adv()
    elif op == 0x5E: r['si'] = pop(); adv()
    elif op == 0x5F: r['di'] = pop(); adv()
    elif op == 0x06: push(r['es']); adv()
    elif op == 0x0E: push(r['cs']); adv()
    elif op == 0x1E: push(r['ds']); adv()
    elif op == 0x07: r['es'] = pop(); adv()
    elif op == 0x17: r['ss'] = pop(); adv()
    elif op == 0x1F: r['ds'] = pop(); adv()
    elif op == 0xFA: adv()
    elif op == 0xFB: adv()
    elif op == 0xFC: DF = 0; adv()
    elif op == 0xFD: DF = 1; adv()
    elif op == 0xF8: CF = 0; adv()
    elif op == 0xF9: CF = 1; adv()
    elif 0xB0 <= op <= 0xB7: set8(op - 0xB0, b1); adv(2)
    elif 0xB8 <= op <= 0xBF:
        r[['ax','cx','dx','bx','sp','bp','si','di'][op-0xB8]] = rw(addr+1); adv(3)
    elif op == 0x8B:
        m = b1
        if m >= 0xC0:  # mov r16, r16
            reg16 = ['ax','cx','dx','bx','sp','bp','si','di']
            r[reg16[(m>>3)&7]] = r[reg16[m&7]]; adv(2)
        elif m == 0xC3: r['ax'] = r['bx']; adv(2)
        elif m == 0xD0: r['dx'] = r['ax']; adv(2)
        elif m == 0xE8: r['bp'] = r['ax']; adv(2)
        elif m == 0xC1: r['ax'] = r['cx']; adv(2)
        elif m == 0xF1: r['si'] = r['cx']; adv(2)
        elif m == 0x2E: mm = rw(addr+2); r['bp'] = get16('ds', mm); adv(4)
        elif m == 0x0E: mm = rw(addr+2); r['cx'] = get16('ds', mm); adv(4)
        elif m == 0x1E: mm = rw(addr+2); r['bx'] = get16('ds', mm); adv(4)
        elif m == 0x16: mm = rw(addr+2); r['dx'] = get16('ds', mm); adv(4)
        elif m == 0x36: mm = rw(addr+2); r['si'] = get16('ds', mm); adv(4)
        elif m == 0x3E: mm = rw(addr+2); r['di'] = get16('ds', mm); adv(4)
        else: print('unhandled 8B %02x @%05x' % (m, addr)); break
    elif op == 0x88:
        if b1 >= 0xC0:
            set8(b1&7, get8((b1>>3)&7)); adv(2)
        else: print('unhandled 88 %02x @%05x' % (b1, addr)); break
    elif op == 0x89:
        if b1 >= 0xC0:
            reg16 = ['ax','cx','dx','bx','sp','bp','si','di']
            r[reg16[b1&7]] = r[reg16[(b1>>3)&7]]; adv(2)
        else: print('unhandled 89 %02x @%05x' % (b1, addr)); break
    elif op == 0x8C:
        if b1 >= 0xC0:
            reg16 = ['ax','cx','dx','bx','sp','bp','si','di']
            sregs = ['es','cs','ss','ds']
            r[reg16[b1&7]] = r[sregs[(b1>>3)&3]]; adv(2)
        else: print('unhandled 8C %02x @%05x' % (b1, addr)); break
    elif op == 0x8E:
        if b1 >= 0xC0:
            reg16 = ['ax','cx','dx','bx','sp','bp','si','di']
            sregs = ['es','cs','ss','ds']
            r[sregs[(b1>>3)&3]] = r[reg16[b1&7]]; adv(2)
        else: print('unhandled 8E %02x @%05x' % (b1, addr)); break
    elif op == 0x31:
        if b1 >= 0xC0:
            reg16 = ['ax','cx','dx','bx','sp','bp','si','di']
            rm = b1&7; rg = (b1>>3)&7
            r[reg16[rm]] ^= r[reg16[rg]]; ZF = int(r[reg16[rm]]==0); CF=0; OF=0; SF=(r[reg16[rm]]>>15)&1
            adv(2)
        else: print('unhandled 31 %02x @%05x' % (b1, addr)); break
    elif op == 0x4E: r['si'] = (r['si']-1)&0xFFFF; adv()
    elif op == 0x4A: r['dx'] = (r['dx']-1)&0xFFFF; ZF = int(r['dx']==0); adv()
    elif op == 0x48: r['ax'] = (r['ax']-1)&0xFFFF; ZF = int(r['ax']==0); adv()
    elif op == 0x4F: r['di'] = (r['di']-1)&0xFFFF; adv()
    elif op == 0x4C: r['sp'] = (r['sp']-1)&0xFFFF; adv()
    elif op == 0x41: r['cx'] = (r['cx']+1)&0xFFFF; adv()
    elif op == 0x40: r['ax'] = (r['ax']+1)&0xFFFF; adv()
    elif op == 0x43: r['bx'] = (r['bx']+1)&0xFFFF; adv()
    elif op == 0x47: r['di'] = (r['di']+1)&0xFFFF; adv()
    elif op == 0x46: r['si'] = (r['si']+1)&0xFFFF; adv()
    elif op == 0x42: r['dx'] = (r['dx']+1)&0xFFFF; adv()
    elif op == 0xAC:
        set8(0, rb(phys('ds', r['si'])))
        r['si'] = (r['si'] + (-1 if DF else 1)) & 0xFFFF; adv()
    elif op == 0xAD:
        r['ax'] = get16('ds', r['si'])
        r['si'] = (r['si'] + (-2 if DF else 2)) & 0xFFFF; adv()
    elif op == 0xAA:
        wb(phys('es', r['di']), r['ax'] & 0xFF)
        r['di'] = (r['di'] + (-1 if DF else 1)) & 0xFFFF; adv()
    elif op == 0xA4:
        wb(phys('es', r['di']), rb(phys('ds', r['si'])))
        r['si'] = (r['si'] + (-1 if DF else 1)) & 0xFFFF
        r['di'] = (r['di'] + (-1 if DF else 1)) & 0xFFFF; adv()
    elif op == 0xA5:
        ww(phys('es', r['di']), get16('ds', r['si']))
        r['si'] = (r['si'] + (-2 if DF else 2)) & 0xFFFF
        r['di'] = (r['di'] + (-2 if DF else 2)) & 0xFFFF; adv()
    elif op == 0xF3 and b1 == 0xA5:
        while r['cx']:
            ww(phys('es', r['di']), get16('ds', r['si']))
            r['si'] = (r['si'] + (-2 if DF else 2)) & 0xFFFF
            r['di'] = (r['di'] + (-2 if DF else 2)) & 0xFFFF
            r['cx'] -= 1
        adv(2)
    elif op == 0xF3 and b1 == 0xA4:
        while r['cx']:
            wb(phys('es', r['di']), rb(phys('ds', r['si'])))
            r['si'] = (r['si'] + (-1 if DF else 1)) & 0xFFFF
            r['di'] = (r['di'] + (-1 if DF else 1)) & 0xFFFF
            r['cx'] -= 1
        adv(2)
    elif op == 0xE3:
        d = b1; d = d - 256 if d > 127 else d
        if r['cx'] == 0: r['ip'] = (r['ip'] + 2 + d) & 0xFFFF
        else: adv(2)
    elif op == 0xE2:
        d = b1; d = d - 256 if d > 127 else d
        r['cx'] = (r['cx'] - 1) & 0xFFFF
        if r['cx']: r['ip'] = (r['ip'] + 2 + d) & 0xFFFF
        else: adv(2)
    elif op == 0xE0:  # loopne? no, 0xE0 = loopne
        d = b1; d = d - 256 if d > 127 else d
        r['cx'] = (r['cx'] - 1) & 0xFFFF
        if r['cx'] and not ZF: r['ip'] = (r['ip'] + 2 + d) & 0xFFFF
        else: adv(2)
    elif op == 0x03:
        if b1 == 0x1E: mm = rw(addr+2); r['bx'] = (r['bx'] + get16('ds', mm)) & 0xFFFF; adv(4)
        elif b1 == 0xC3: r['ax'] = (r['ax'] + r['bx']) & 0xFFFF; adv(2)
        else: print('unhandled 03 %02x @%05x' % (b1, addr)); break
    elif op == 0x01:
        if b1 >= 0xC0:
            reg16 = ['ax','cx','dx','bx','sp','bp','si','di']
            rm = b1&7; rg = (b1>>3)&7
            old = r[reg16[rm]]; v = (old + r[reg16[rg]]) & 0xFFFF
            r[reg16[rm]] = v; CF=int(v<old); SF=(v>>15)&1; ZF=int(v==0); OF=int((~(old^r[reg16[rg]])&(old^v))>>15)&1
            adv(2)
        elif b1 == 0x06:  # add [disp16], r16
            reg16 = ['ax','cx','dx','bx','sp','bp','si','di']
            mm = rw(addr+2); rg = (b1>>3)&7
            a = phys('ds', mm); v = (rw(a) + r[reg16[rg]]) & 0xFFFF; ww(a, v)
            ZF = int(v==0); CF = int(v < r[reg16[rg]]); adv(4)
        else: print('unhandled 01 %02x @%05x' % (b1, addr)); break
    elif op == 0x29:
        if b1 >= 0xC0:
            reg16 = ['ax','cx','dx','bx','sp','bp','si','di']
            rm = b1&7; rg = (b1>>3)&7
            old = r[reg16[rm]]; v = (old - r[reg16[rg]]) & 0xFFFF
            r[reg16[rm]] = v; ZF = int(v==0); CF = int(old < r[reg16[rg]]); SF = (v>>15)&1; OF = int(((old^r[reg16[rg]])&(old^v))>>15)&1
            adv(2)
        else: print('unhandled 29 %02x @%05x' % (b1, addr)); break
    elif op == 0x2B:
        if   b1 == 0xD8: r['bx'] = (r['bx']-r['ax'])&0xFFFF; ZF=int(r['bx']==0); adv(2)
        elif b1 == 0xD0: r['dx'] = (r['dx']-r['ax'])&0xFFFF; ZF=int(r['dx']==0); adv(2)
        elif b1 == 0xE8: r['bp'] = (r['bp']-r['ax'])&0xFFFF; ZF=int(r['bp']==0); adv(2)
        elif b1 == 0xDA: r['bx'] = (r['bx']-r['dx'])&0xFFFF; ZF=int(r['bx']==0); adv(2)
        elif b1 == 0xC5: r['ax'] = (r['ax']-r['bp'])&0xFFFF; ZF=int(r['ax']==0); adv(2)
        else: print('unhandled 2B %02x @%05x' % (b1, addr)); break
    elif op == 0x39:
        if b1 == 0xD5: ZF = int(r['bp']==r['dx']); CF = int(r['bp']<r['dx']); adv(2)
        elif b1 == 0xC8: ZF = int(r['ax']==r['bx']); CF = int(r['ax']<r['bx']); adv(2)
        else: print('unhandled 39 %02x @%05x' % (b1, addr)); break
    elif op == 0x3B:
        if b1 == 0xC8: ZF = int(r['cx']==r['ax']); CF = int(r['cx']<r['ax']); adv(2)
        else: print('unhandled 3B %02x @%05x' % (b1, addr)); break
    elif op == 0x83:
        if b1 >= 0xC0:
            reg16 = ['ax','cx','dx','bx','sp','bp','si','di']
            sub = (b1>>3)&7; rm = b1&7
            imm = rb(addr+2); imm = imm-256 if imm>127 else imm; imm &= 0xFFFF
            old = r[reg16[rm]]
            if   sub == 0: v = (old + imm) & 0xFFFF; r[reg16[rm]] = v; CF=int(v<old); SF=(v>>15)&1; ZF=int(v==0); OF=int((~(old^imm)&(old^v))>>15)&1
            elif sub == 1: v = old | imm; r[reg16[rm]] = v; SF=(v>>15)&1; ZF=int(v==0); CF=0; OF=0
            elif sub == 4: v = old & imm; r[reg16[rm]] = v; SF=(v>>15)&1; ZF=int(v==0); CF=0; OF=0
            elif sub == 5: v = (old - imm) & 0xFFFF; r[reg16[rm]] = v; CF=int(old<imm); SF=(v>>15)&1; ZF=int(v==0); OF=int(((old^imm)&(old^v))>>15)&1
            elif sub == 7: v = (old - imm) & 0xFFFF; CF=int(old<imm); SF=(v>>15)&1; ZF=int(v==0); OF=int(((old^imm)&(old^v))>>15)&1
            adv(3)
        elif b1 == 0xF8:  # cmp ax, imm8
            imm = rb(addr+2); imm = imm-256 if imm>127 else imm
            v = r['ax']; ZF = int(v == (imm & 0xFFFF)); CF = int(v < (imm & 0xFFFF)); adv(3)
        else: print('unhandled 83 %02x @%05x' % (b1, addr)); break
    elif op == 0x80:
        if b1 >= 0xC0:
            sub = (b1>>3)&7; rm = b1&7; imm = rb(addr+2); v = get8(rm)
            if   sub == 0: set8(rm, (v + imm) & 0xFF)
            elif sub == 1: set8(rm, v | imm)
            elif sub == 4: set8(rm, v & imm); ZF = int((v & imm)==0)
            elif sub == 5: set8(rm, (v - imm) & 0xFF); CF = int(v < imm); ZF = int(((v-imm)&0xFF)==0)
            elif sub == 7: ZF = int(v==imm); CF = int(v<imm)
            adv(3)
        elif b1 == 0xFC:            imm = rb(addr+2); v=(r['ax']>>8)&0xFF; ZF = int(v==imm); CF = int(v<imm); adv(3)
        elif b1 == 0xE4:
            imm = rb(addr+2); v = ((r['ax']>>8) & imm) & 0xFF
            r['ax'] = (r['ax'] & 0xFF) | (v << 8); ZF = int(v==0); adv(3)
        elif b1 == 0xC4:
            imm = rb(addr+2); r['ax'] = (r['ax'] & 0xFF) | ((((r['ax']>>8) + imm) & 0xFF) << 8); adv(3)
        elif b1 == 0xCC:
            imm = rb(addr+2); v = ((r['ax']>>8) | imm) & 0xFF
            r['ax'] = (r['ax'] & 0xFF) | (v << 8); adv(3)
        else: print('unhandled 80 %02x @%05x' % (b1, addr)); break
    elif op == 0x0A:
        if b1 == 0xC0: ZF = int((r['ax']&0xFF)==0); adv(2)
        else: print('unhandled 0A %02x @%05x' % (b1, addr)); break
    elif op == 0x0B:
        if b1 == 0xED: ZF = int(r['bp']==0); adv(2)
        elif b1 == 0xC0: ZF = int(r['ax']==0); adv(2)
        else: print('unhandled 0B %02x @%05x' % (b1, addr)); break
    elif op == 0x08:
        if b1 >= 0xC0:
            v = get8(b1&7) | get8((b1>>3)&7)
            set8(b1&7, v); ZF = int(v==0); SF = (v>>7)&1; CF = 0; OF = 0
            adv(2)
        else: print('unhandled 08 %02x @%05x' % (b1, addr)); break
    elif op == 0x09:
        if b1 >= 0xC0:
            reg16 = ['ax','cx','dx','bx','sp','bp','si','di']
            rm = b1&7; rg = (b1>>3)&7
            r[reg16[rm]] |= r[reg16[rg]]; ZF = int(r[reg16[rm]]==0); SF=(r[reg16[rm]]>>15)&1; CF=0; OF=0
            adv(2)
        else: print('unhandled 09 %02x @%05x' % (b1, addr)); break
    elif op == 0x0C:
        r['ax'] = (r['ax'] & 0xFF00) | ((r['ax'] & 0xFF) | b1); adv(2)
    elif op == 0x25:
        r['ax'] &= rw(addr+1); ZF = int(r['ax']==0); adv(3)
    elif op == 0x3D:
        v = rw(addr+1); ZF = int(r['ax']==v); CF = int(r['ax']<v); adv(3)
    elif op == 0x3C:
        v = r['ax'] & 0xFF; ZF = int(v==b1); CF = int(v<b1); adv(2)
    elif op == 0x2D:
        r['ax'] = (r['ax'] - rw(addr+1)) & 0xFFFF; ZF = int(r['ax']==0); adv(3)
    elif op == 0x05:
        r['ax'] = (r['ax'] + rw(addr+1)) & 0xFFFF; adv(3)
    elif op == 0xD1:
        if   b1 == 0xED: CF = r['bp'] & 1; r['bp'] >>= 1; adv(2)
        elif b1 == 0xE8: CF = r['ax'] & 1; r['ax'] >>= 1; adv(2)
        elif b1 == 0xE9: CF = r['cx'] & 1; r['cx'] >>= 1; adv(2)
        elif b1 == 0xFB: CF = r['bx'] & 1; r['bx'] >>= 1; adv(2)
        elif b1 == 0xE0: CF = (r['ax']>>15)&1; r['ax'] = (r['ax']<<1)&0xFFFF; adv(2)
        elif b1 == 0xE3: CF = (r['bx']>>15)&1; r['bx'] = (r['bx']<<1)&0xFFFF; adv(2)
        elif b1 == 0xE7: CF = (r['di']>>15)&1; r['di'] = (r['di']<<1)&0xFFFF; adv(2)
        elif b1 == 0xD1:
            c = CF; CF = (r['cx']>>15)&1; r['cx'] = ((r['cx']<<1)|c)&0xFFFF; adv(2)
        elif b1 == 0xD0:
            c = CF; CF = (r['ax']>>15)&1; r['ax'] = ((r['ax']<<1)|c)&0xFFFF; adv(2)
        else: print('unhandled D1 %02x @%05x' % (b1, addr)); break
    elif op == 0xD2 and b1 >= 0xC0:
        n = r['cx'] & 0x1F
        sub = (b1>>3)&7; rm = b1&7
        for _ in range(n):
            v = get8(rm)
            if sub == 4:   # shl
                CF = (v>>7)&1; v = (v<<1)&0xFF
            elif sub == 5: # shr
                CF = v&1; v >>= 1
            elif sub == 7: # sar
                CF = v&1; v = (v>>1)|(v&0x80)
            elif sub == 0: # rol
                CF = (v>>7)&1; v = ((v<<1)|CF)&0xFF
            elif sub == 1: # ror
                CF = v&1; v = (v>>1)|(CF<<7)
            elif sub == 2: # rcl
                c = CF; CF = (v>>7)&1; v = ((v<<1)|c)&0xFF
            elif sub == 3: # rcr
                c = CF; CF = v&1; v = (v>>1)|(c<<7)
            set8(rm, v)
        adv(2)
    elif op == 0xD3:
        n = r['cx'] & 0x1F
        if   b1 == 0xE8:
            for _ in range(n): CF = r['ax'] & 1; r['ax'] >>= 1
            adv(2)
        elif b1 == 0xEB:
            for _ in range(n): CF = r['bx'] & 1; r['bx'] >>= 1
            adv(2)
        elif b1 == 0xEF:
            for _ in range(n): CF = r['di'] & 1; r['di'] >>= 1
            adv(2)
        elif b1 == 0xEE:
            for _ in range(n): CF = r['si'] & 1; r['si'] >>= 1
            adv(2)
        elif b1 == 0xE0:
            for _ in range(n): CF = (r['ax']>>15)&1; r['ax'] = (r['ax']<<1)&0xFFFF
            adv(2)
        elif b1 == 0xE3:
            for _ in range(n): CF = (r['bx']>>15)&1; r['bx'] = (r['bx']<<1)&0xFFFF
            adv(2)
        elif b1 == 0xE5:
            for _ in range(n): CF = (r['bp']>>15)&1; r['bp'] = (r['bp']<<1)&0xFFFF
            adv(2)
        else: print('unhandled D3 %02x @%05x' % (b1, addr)); break
    elif op == 0x2E:  # cs: prefix
        if b1 == 0x8B and rb(addr+2) == 0x2E:
            mm = rw(addr+3); r['bp'] = get16('cs', mm); adv(5)
        elif b1 == 0x8B and rb(addr+2) == 0x1E:
            mm = rw(addr+3); r['bx'] = get16('cs', mm); adv(5)
        elif b1 == 0xFF and rb(addr+2) == 0x2F:
            # jmp far cs:[bx]  -> final jump into unpacked program; STOP here
            mm = phys('cs', r['bx'])
            nip = rw(mm); ncs = rw(mm+2)
            print('FINAL JUMP to %04x:%04x' % (ncs, nip))
            r['ip'] = nip; r['cs'] = ncs
            break
        else: print('unhandled 2E %02x %02x @%05x' % (b1, rb(addr+2), addr)); break
    elif op == 0x8A:
        if b1 >= 0xC0:
            set8((b1>>3)&7, get8(b1&7)); adv(2)
        elif b1 == 0xC2: set8(0, r['dx'] & 0xFF); adv(2)
        elif b1 == 0xC6: set8(0, (r['dx']>>8) & 0xFF); adv(2)
        else: print('unhandled 8A %02x @%05x' % (b1, addr)); break
    elif op == 0x26:  # es: prefix
        if b1 == 0x8A:
            m = rb(addr+2)
            if m < 0x40:  # mov r8, es:[rm16]
                ea_map = {0: r['bx']+r['si'], 1: r['bx']+r['di'], 2: r['bp']+r['si'], 3: r['bp']+r['di'],
                          4: r['si'], 5: r['di'], 6: rw(addr+3), 7: r['bx']}
                nn = 4 if m == 6 else 3
                set8((m>>3)&7, rb(phys('es', ea_map[m&7]))); adv(nn)
            else: print('unhandled 26 8A %02x @%05x' % (m, addr)); break
        elif b1 == 0x01 and rb(addr+2) == 0x1D:
            a = phys('es', r['di'])
            v = rw(a); v = (v + r['bx']) & 0xFFFF; ww(a, v); adv(3)
            RELOCS.append((a, rw(a) - r['bx'] & 0xFFFF, r['bx']))
        else: print('unhandled 26 %02x %02x @%05x' % (b1, rb(addr+2), addr)); break
    elif op == 0x36:  # ss: prefix
        print('ss prefix @%05x' % addr); break
    elif op == 0x81 and b1 >= 0xC0:
        reg16 = ['ax','cx','dx','bx','sp','bp','si','di']
        sub = (b1>>3)&7; rm = b1&7; imm = rw(addr+2); old = r[reg16[rm]]
        if   sub == 0: v = (old + imm) & 0xFFFF; r[reg16[rm]] = v; CF=int(v<old); SF=(v>>15)&1; ZF=int(v==0); OF=int((~(old^imm)&(old^v))>>15)&1
        elif sub == 1: v = old | imm; r[reg16[rm]] = v; SF=(v>>15)&1; ZF=int(v==0); CF=0; OF=0
        elif sub == 4: v = old & imm; r[reg16[rm]] = v; SF=(v>>15)&1; ZF=int(v==0); CF=0; OF=0
        elif sub == 5: v = (old - imm) & 0xFFFF; r[reg16[rm]] = v; CF=int(old<imm); SF=(v>>15)&1; ZF=int(v==0); OF=int(((old^imm)&(old^v))>>15)&1
        elif sub == 7: v = (old - imm) & 0xFFFF; CF=int(old<imm); SF=(v>>15)&1; ZF=int(v==0); OF=int(((old^imm)&(old^v))>>15)&1
        adv(4)
    elif op == 0xEB:
        d = b1; d = d - 256 if d > 127 else d
        r['ip'] = (r['ip'] + 2 + d) & 0xFFFF
    elif op == 0xE9:
        d = rw(addr+1); d = d - 65536 if d > 32767 else d
        r['ip'] = (r['ip'] + 3 + d) & 0xFFFF
    elif op == 0x74:
        d = b1; d = d - 256 if d > 127 else d
        if ZF: r['ip'] = (r['ip'] + 2 + d) & 0xFFFF
        else: adv(2)
    elif op == 0x75:
        d = b1; d = d - 256 if d > 127 else d
        if not ZF: r['ip'] = (r['ip'] + 2 + d) & 0xFFFF
        else: adv(2)
    elif op == 0x72:
        d = b1; d = d - 256 if d > 127 else d
        if CF: r['ip'] = (r['ip'] + 2 + d) & 0xFFFF
        else: adv(2)
    elif 0x70 <= op <= 0x7F:
        d = b1; d = d - 256 if d > 127 else d
        cond = {
            0x70: OF, 0x71: not OF, 0x72: CF, 0x73: not CF,
            0x74: ZF, 0x75: not ZF, 0x76: CF or ZF, 0x77: not (CF or ZF),
            0x78: SF, 0x79: not SF, 0x7A: 0, 0x7B: 1,
            0x7C: SF != OF, 0x7D: SF == OF, 0x7E: (SF != OF) or ZF, 0x7F: (SF == OF) and not ZF,
        }[op]
        if cond: r['ip'] = (r['ip'] + 2 + d) & 0xFFFF
        else: adv(2)
    elif op == 0xCB:
        r['ip'] = pop(); r['cs'] = pop()
    elif op == 0xC3:
        r['ip'] = pop()
    elif op == 0xCD:
        if b1 == 0x21 and ((r['ax']>>8) == 0x4C): print('exit'); break
        elif b1 == 0x21 and ((r['ax']>>8) == 9): print('CHECKSUM FAIL'); break
        else: print('int %02x' % b1); break
    elif op == 0xC6 and b1 == 0x06:
        mm = rw(addr+2); wb(phys('ds', mm), rb(addr+4)); adv(5)
    elif op == 0xC7 and b1 == 0x06:
        mm = rw(addr+2); ww(phys('ds', mm), rw(addr+4)); adv(6)
    elif op == 0xFF and b1 == 0x06:
        mm = rw(addr+2); push(get16('ds', mm)); adv(4)
    elif op == 0x8F and b1 == 0x06:
        mm = rw(addr+2); ww(phys('ds', mm), pop()); adv(4)
    elif op == 0x90: adv()
    else:
        print('unknown op %02x %02x at %05x (cs=%04x ip=%04x)' % (op, b1, addr, r['cs'], r['ip']))
        break

print('steps', steps)
for t in trace: print(t)
print('cs=%04x ip=%04x ds=%04x es=%04x si=%04x di=%04x bx=%04x' % (r['cs'], r['ip'], r['ds'], r['es'], r['si'], r['di'], r['bx']))
import json; json.dump(RELOCS, open('relocs.json','w'))
open('unpacked_emu.bin','wb').write(MEM[LOAD*16:LOAD*16+0x18000])
