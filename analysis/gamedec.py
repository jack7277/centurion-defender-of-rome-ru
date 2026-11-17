import struct, os, glob

def decode_game_lzw_bytes(src):
    size = struct.unpack('<I', src[:4])[0]
    data = src[4:]
    ring = bytearray(b' ' * 4096)
    out = bytearray()
    wpos = 4078
    i = 0
    while i < len(data) and len(out) < size:
        flag = data[i]; i += 1
        for b in range(8):
            if len(out) >= size or i >= len(data): break
            if (flag >> b) & 1:
                c = data[i]; i += 1
                ring[wpos] = c; wpos = (wpos + 1) & 4095
                out.append(c)
            else:
                b1, b2 = data[i], data[i+1]; i += 2
                off = b1 | ((b2 & 0xF0) << 4)
                ln = (b2 & 0x0F) + 3
                for k in range(ln):
                    c = ring[(off + k) & 4095]
                    ring[wpos] = c; wpos = (wpos + 1) & 4095
                    out.append(c)
    return bytes(out)

def decode_game_lzw(path):
    return decode_game_lzw_bytes(open(path,'rb').read())

if __name__ == '__main__':
    outroot = '../decoded'
    for f in sorted(glob.glob('../extracted/*/*.LZW')):
        rel = os.path.relpath(f, '../extracted')
        out = decode_game_lzw(f)
        dst = os.path.join(outroot, rel[:-4] + '.bin')
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst,'wb').write(out)
        print('%-30s %6d -> %6d' % (rel, os.path.getsize(f), len(out)))
