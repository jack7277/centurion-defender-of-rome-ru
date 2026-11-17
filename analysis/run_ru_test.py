# run_ru_test.py — прогон русской сборки в DOSBox заэкранно, скриншоты в screens_ru/
import ctypes, subprocess, time, os, sys
from ctypes import wintypes
import win32gui, win32ui, win32con
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DOSBOX = os.path.join(HERE, 'dosbox', 'dosbox-staging-v0.83.1', 'dosbox.exe')
CONF = os.path.join(HERE, 'dosbox.conf')
OUT = os.path.join(os.environ.get('TEMP', HERE), 'centurion_screens')
os.makedirs(OUT, exist_ok=True)

user32 = ctypes.windll.user32

def find(pid=None):
    out = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, lp):
        if user32.IsWindowVisible(hwnd):
            if pid is not None:
                wp = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wp))
                if wp.value != pid:
                    return True
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if 'CENTURIO' in buf.value or 'DOSBox' in buf.value:
                out.append(hwnd)
        return True
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out[0] if out else None

def capture(hwnd, path):
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    w, h = right-left, bottom-top
    hdc = win32gui.GetWindowDC(hwnd)
    mfc = win32ui.CreateDCFromHandle(hdc)
    save = mfc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mfc, w, h)
    save.SelectObject(bmp)
    user32.PrintWindow(hwnd, save.GetSafeHdc(), 2)
    bmpinfo = bmp.GetInfo()
    bmpstr = bmp.GetBitmapBits(True)
    im = Image.frombuffer('RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRX', 0, 1)
    im.save(path)
    win32gui.DeleteObject(bmp.GetHandle())
    save.DeleteDC(); mfc.DeleteDC(); win32gui.ReleaseDC(hwnd, hdc)

def key(hwnd, vk):
    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, vk, 0)
    time.sleep(0.08)
    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, vk, 0)

proc = subprocess.Popen([DOSBOX, '-conf', CONF], cwd=HERE)
hwnd = None
for _ in range(60):
    time.sleep(0.5)
    hwnd = find(proc.pid)
    if hwnd:
        break
if not hwnd:
    print('окно DOSBox не найдено'); proc.kill(); sys.exit(1)
print('hwnd', hwnd, 'за экраном')

try:
    shots = int(sys.argv[1]) if len(sys.argv) > 1 else 18
    for i in range(shots):
        time.sleep(5)
        hwnd = find(proc.pid)
        if not hwnd:
            print('окно закрылось'); break
        capture(hwnd, os.path.join(OUT, 'ru_%02d.png' % i))
        print('shot', i, 't=%ds' % (i*5+5), flush=True)
        if i in (7, 10, 13):     # Enter: титры/интро -> дальше
            key(hwnd, 0x0D)
finally:
    proc.kill()
print('готово:', OUT)
