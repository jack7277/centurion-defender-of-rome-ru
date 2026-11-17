# unpack_exe.py — распаковка LZEXE-ядра orig/CENTURIO.EXE -> CENTURIO.unpacked.bin + relocs.json
# Вызывается автоматически из build_ru.py, если unpacked-образа нет.
import os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ORIG_EXE = os.path.join(HERE, 'orig', 'CENTURIO.EXE')
OUT_BIN = os.path.join(HERE, 'CENTURIO.unpacked.bin')
OUT_REL = os.path.join(HERE, 'relocs.json')
UNPACKED_SIZE = 45320  # реальный размер распакованного ядра (обрезка хвоста unpacked_emu.bin)

def main():
    if not os.path.exists(ORIG_EXE):
        sys.exit('нет %s — положи туда оригинальный CENTURIO.EXE из своей копии игры' % ORIG_EXE)
    tmp = tempfile.mkdtemp(prefix='cent_unpack_')
    try:
        shutil.copy(ORIG_EXE, os.path.join(tmp, 'CENTURIO.EXE'))
        shutil.copy(os.path.join(HERE, 'emu_reloc.py'), tmp)
        r = subprocess.run([sys.executable, 'emu_reloc.py'], cwd=tmp,
                           capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            sys.exit('emu_reloc упал:\n' + r.stdout[-2000:] + r.stderr[-2000:])
        img = open(os.path.join(tmp, 'unpacked_emu.bin'), 'rb').read()
        open(OUT_BIN, 'wb').write(img[:UNPACKED_SIZE])
        shutil.move(os.path.join(tmp, 'relocs.json'), OUT_REL)
        print('OK: CENTURIO.unpacked.bin (%d байт) + relocs.json' % UNPACKED_SIZE)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

if __name__ == '__main__':
    main()
