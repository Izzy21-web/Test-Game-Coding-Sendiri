"""
AGENT DUTY - game FPS agen rahasia di dalam mansion (raycasting) dengan Python
Instal : pip install pygame numpy
Jalan  : python agent_duty.py
Menu: START GAME > pilih difficulty. Kontrol bisa diatur di SETTINGS | Klik kiri tembak | R reload
         1/2/3 ganti senjata | Shift lari | ENTER ulang | ESC keluar
Semua grafik & suara dibuat lewat kode (tanpa file gambar/audio).
Gambar menu (agen kiri, kartu) bisa diganti gambar sendiri: buat folder 'gambar' di samping file ini (lihat bagian MENU UTAMA).
Pause (ESC): LANJUTKAN / PENGATURAN / MENU UTAMA | Multiplayer: Free For All, 5 VS 5, 10 VS 10 (tanpa friendly fire), sampai 20 bot
"""
import math, random, os, json, socket, time, threading, ipaddress
from collections import deque
from types import SimpleNamespace as NS
import numpy as np
import pygame as pg

import sys
SAVE = os.path.join(os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__)), "agent_duty_settings.json")      # versi .exe: simpan di samping file .exe (bukan folder sementara)
CFG = dict(name="AGENT", sens=5, vol=8, ip="127.0.0.1", input="auto", psens=5, res=0, keys=dict(maju=pg.K_w, mundur=pg.K_s, kiri=pg.K_a, kanan=pg.K_d, lari=pg.K_LSHIFT, reload=pg.K_r, lompat=pg.K_SPACE, granat=pg.K_g, flash=pg.K_f))
try:
    with open(SAVE) as f: _sv = json.load(f)
    CFG["res"] = int(_sv.get("res", 0)); CFG["sens"], CFG["vol"], CFG["ip"] = int(_sv["sens"]), int(_sv["vol"]), str(_sv.get("ip", "127.0.0.1")); CFG["keys"].update({k: int(v) for k, v in _sv["keys"].items()})
    CFG["input"] = _sv.get("input", "auto") if _sv.get("input") in ("auto", "kbm", "pad") else "auto"; CFG["psens"] = max(1, min(10, int(_sv.get("psens", 5))))
except Exception: pass
def clean_name(s, fb):                           # username: maks 12 karakter ASCII (huruf, angka, spasi, _ dan -); kosong / diawali "BOT" -> fb
    s = "".join(c for c in str(s) if c.isascii() and (c.isalnum() or c in "_- "))[:12].strip()
    return fb if not s or s.upper().startswith("BOT") else s

def uniq_name(s, taken):                         # jika sudah dipakai pemain lain di lobi, tambahkan angka
    base, k, low = s, 2, {x.lower() for x in taken}
    while s.lower() in low: s = f"{base[:10]}{k}"; k += 1
    return s

try: CFG["name"] = clean_name(_sv.get("name", "AGENT"), "AGENT")
except Exception: pass

def save_cfg():
    try:
        with open(SAVE, "w") as f: json.dump(CFG, f)
    except Exception: pass
if os.name == "nt":                          # Windows dengan skala 125% / 150%: tanpa ini jendela diperbesar paksa oleh Windows -> gambar buram / pecah
    try: import ctypes; ctypes.windll.user32.SetProcessDPIAware()
    except Exception: pass
os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
SR = 22050
pg.mixer.pre_init(SR, -16, 2, 512)
pg.init()
MIX = pg.mixer.get_init()          # None jika tidak ada perangkat audio
if MIX: pg.mixer.set_num_channels(24)       # banyak bot menembak bersamaan: butuh lebih banyak kanal suara
EYE = .28                                   # tinggi mata pemain dinaikkan agar setara dengan musuh
W, H, SC = 320, 200, 3                      # resolusi render, skala jendela
VWD, VHT = W * SC, H * SC                   # LAYAR VIRTUAL 960 x 600: menu, HUD, dan 3D digambar di sini, lalu diskalakan HALUS ke jendela (tanpa melar, tanpa kotak-kotak)
try: DESK = tuple(pg.display.get_desktop_sizes()[0])
except Exception: _i = pg.display.Info(); DESK = (_i.current_w, _i.current_h)
RESF = (("960 x 600", 960, 600, "16:10 (awal)"), ("1280 x 720", 1280, 720, "HD 16:9"), ("1366 x 768", 1366, 768, "16:9"), ("1440 x 900", 1440, 900, "16:10"),
        ("1600 x 900", 1600, 900, "HD+ 16:9"), ("1680 x 1050", 1680, 1050, "16:10"), ("1920 x 1080", 1920, 1080, "FULL HD 16:9"), ("LAYAR PENUH", 0, 0, "ikut monitor"))
WIN, SCB, OX, OY, VK = None, None, 0, 0, 1.0
def res_mode(i):                                # -> (flags, ukuran) atau None bila tidak muat di monitor ini
    if not 0 <= i < len(RESF): return None
    _, w, h, _ = RESF[i]
    if w == 0 or (w, h) == DESK: return pg.FULLSCREEN, DESK
    if (w, h) == (VWD, VHT) or (w <= DESK[0] and h <= DESK[1] - 90): return 0, (w, h)       # sisakan ruang untuk judul jendela + taskbar
    return None
def res_name(i=None): i = CFG["res"] if i is None else i; return RESF[i][0] if 0 <= i < len(RESF) else RESF[0][0]
def apply_display(first=False):
    global WIN, SCB, OX, OY, VK
    m = res_mode(CFG["res"])
    if m is None: CFG["res"] = 0; m = res_mode(0)
    flags, size = m
    if not first: vis, grab = pg.mouse.get_visible(), pg.event.get_grab()
    WIN = pg.display.set_mode(size, flags); WIN.fill((0, 0, 0))
    VK = min(size[0] / VWD, size[1] / VHT); vw, vh = int(VWD * VK), int(VHT * VK)
    if abs(VK - 1) < 1e-6: vw, vh, VK = VWD, VHT, 1.0
    OX, OY = (size[0] - vw) // 2, (size[1] - vh) // 2                         # pita hitam di tepi bila rasio jendela berbeda (gambar tidak dilebarkan)
    SCB = None if (vw, vh) == (VWD, VHT) else pg.Surface((vw, vh)).convert()
    if not first: pg.mouse.set_visible(vis); pg.event.set_grab(grab); pg.mouse.get_rel()
def res_step(d):                                # ganti ukuran layar ke pilihan berikut / sebelumnya yang muat di monitor
    n = len(RESF); i = CFG["res"]
    for _ in range(n):
        i = (i + d) % n
        if res_mode(i) is not None: break
    CFG["res"] = i; apply_display(); save_cfg()
def present():                                  # tampilkan layar virtual ke jendela (skala halus bila ukuran jendela berbeda)
    if SCB is None: WIN.blit(DISP, (OX, OY))
    else: pg.transform.smoothscale(DISP, SCB.get_size(), SCB); WIN.blit(SCB, (OX, OY))
    pg.display.flip()
def ev_fix(e):                                  # posisi mouse di jendela -> posisi di layar virtual (menu tetap bisa diklik pada ukuran apa pun)
    if e.type in (pg.MOUSEMOTION, pg.MOUSEBUTTONDOWN, pg.MOUSEBUTTONUP) and (OX or OY or VK != 1.0):
        return pg.event.Event(e.type, dict(e.dict, pos=(int((e.pos[0] - OX) / VK), int((e.pos[1] - OY) / VK))))
    return e
apply_display(True)
screen = pg.Surface((VWD, VHT)).convert()
pg.display.set_caption("AGENT DUTY")
canvas = pg.Surface((W, H))
clock = pg.time.Clock()
font, small, big, mid = pg.font.Font(None, 30), pg.font.Font(None, 22), pg.font.Font(None, 96), pg.font.Font(None, 66); tiny = pg.font.Font(None, 16)
rng = np.random.default_rng(7)
D = pg.draw

# ================= CONTROLLER (gamepad) =================
try:
    from pygame._sdl2 import controller as _ctl                 # API SDL GameController: tata letak tombol seragam di semua merek
    _ctl.init()
except Exception: _ctl = None
try: pg.joystick.init()
except Exception: pass
# nomor tombol / sumbu SDL GameController (tetap, tidak bergantung konstanta modul pygame yang bisa berbeda antar versi)
_CAX = dict(lx=0, ly=1, rx=2, ry=3, lt=4, rt=5)
_CBT = dict(a=0, b=1, x=2, y=3, back=4, start=6, ls=7, rs=8, lb=9, rb=10, du=11, dd=12, dl=13, dr=14)
_JBT = dict(a=0, b=1, x=2, y=3, lb=4, rb=5, back=6, start=7, ls=8, rs=9)                  # cadangan: joystick biasa (tata letak Xbox)

def stick(x, y, dz=.22):                       # deadzone melingkar + kurva halus (aim pelan presisi, penuh tetap cepat)
    m = math.hypot(x, y)
    if m < dz: return 0.0, 0.0
    k = (min(1.0, m) - dz) / (1 - dz); k = k ** 1.5 / m; return x * k, y * k

class Pad:
    def __init__(s, idx, dev, kind):
        s.idx, s.dev, s.kind = idx, dev, kind; s.ax = dict(lx=0.0, ly=0.0, rx=0.0, ry=0.0, lt=0.0, rt=0.0); s.bt = {n: False for n in _CBT}; s.prev, s.pax = dict(s.bt), dict(s.ax)
        s.sprint = False; s.hold = {}; s.ok = True; s.err = ""
        try: s.name = dev.name if hasattr(dev, "name") and isinstance(dev.name, str) else dev.get_name()
        except Exception: s.name = "Controller"
    def alive(s):
        try: return s.ok and (s.dev.attached() if s.kind == "ctl" else True)
        except Exception: return False
    def poll(s):
        s.prev, s.pax = s.bt, s.ax
        try:
            d = s.dev
            if s.kind == "ctl":
                A = lambda n: max(-1.0, min(1.0, d.get_axis(_CAX[n]) / 32767.0))
                s.ax = dict(lx=A("lx"), ly=A("ly"), rx=A("rx"), ry=A("ry"), lt=max(0.0, A("lt")), rt=max(0.0, A("rt")))
                s.bt = {n: bool(d.get_button(i)) for n, i in _CBT.items()}
            else:
                na = d.get_numaxes(); G = lambda i: d.get_axis(i) if i < na else 0.0
                s.ax = dict(lx=G(0), ly=G(1), rx=G(2), ry=G(3), lt=(G(4) + 1) / 2 if na > 5 else 0.0, rt=(G(5) + 1) / 2 if na > 5 else 0.0)
                s.bt = {n: bool(d.get_button(i)) for n, i in _JBT.items()}; hx, hy = d.get_hat(0) if d.get_numhats() else (0, 0)
                s.bt.update(du=hy > 0, dd=hy < 0, dl=hx < 0, dr=hx > 0)
        except Exception as ex:
            s.err = f"{type(ex).__name__}: {ex}"
            if s.kind == "ctl":                                                    # API GameController bermasalah: pindah ke joystick biasa
                try: j = pg.joystick.Joystick(s.idx); j.init(); s.dev, s.kind, s.err = j, "joy", s.err + " -> joystick biasa"
                except Exception: s.ok = False
            else: s.ok = False
        if s.bt["ls"] and not s.prev["ls"]: s.sprint = not s.sprint            # klik stik kiri = lari (toggle)
        if math.hypot(s.ax["lx"], s.ax["ly"]) < .2: s.sprint = False
    def live(s):                               # ringkasan input saat ini (untuk layar Settings)
        on = [n.upper() for n, v in s.bt.items() if v] + [f"{n.upper()} {v:+.1f}" for n, v in s.ax.items() if abs(v) > .3]
        return " ".join(on) if on else "(belum ada input)"
    def pressed(s, n): return s.bt.get(n, False) and not s.prev.get(n, False)
    def trig_down(s, n, th=.5): return s.ax[n] > th and s.pax[n] <= th                  # lt / rt baru ditekan
    def dirs(s, dt):                           # arah navigasi menu (d-pad / stik kiri) dengan auto-repeat
        want = dict(u=s.bt["du"] or s.ax["ly"] < -.6, d=s.bt["dd"] or s.ax["ly"] > .6, l=s.bt["dl"] or s.ax["lx"] < -.6, r=s.bt["dr"] or s.ax["lx"] > .6); out = []
        for k, on in want.items():
            if not on: s.hold.pop(k, None)
            elif k not in s.hold: s.hold[k] = .45; out.append(k)
            else:
                s.hold[k] -= dt
                if s.hold[k] <= 0: s.hold[k] = .14; out.append(k)
        return out

PADS = []; _pad_t = [0.0]
def pads_scan():                               # buka controller baru / buang yang sudah dicabut
    have = {p.idx: p for p in PADS}; new = []
    try: n = _ctl.get_count() if _ctl else pg.joystick.get_count()
    except Exception: n = 0
    for i in range(n):
        if i in have and have[i].alive(): new.append(have[i]); continue
        try:
            if _ctl and _ctl.is_controller(i): new.append(Pad(i, _ctl.Controller(i), "ctl"))
            else: j = pg.joystick.Joystick(i); j.init(); new.append(Pad(i, j, "joy"))
        except Exception: pass
    PADS[:] = new

def pads_poll(dt):
    _pad_t[0] -= dt
    if _pad_t[0] <= 0: pads_scan(); _pad_t[0] = 1.0
    for p in PADS: p.poll()

def kb_on(): return CFG["input"] != "pad" or not PADS                  # mode CONTROLLER tanpa controller terpasang: keyboard + mouse tetap bisa dipakai
def uses_pad(): return pad_of(pidx()) is not None and (CFG["input"] == "pad" or (CO() and pidx() == 1))      # HUD menampilkan nama tombol controller
def input_label(): return {"auto": "OTOMATIS", "kbm": "KEYBOARD + MOUSE", "pad": "CONTROLLER"}[CFG["input"]]

# ================= SUARA (disintesis dengan numpy) =================
def T(d): return np.arange(int(SR * d)) / SR
def nz(d): return rng.uniform(-1, 1, int(SR * d))
def lp(x, k): return np.convolve(x, np.ones(k) / k, "same")
class Mute:                                  # pengganti kalau audio tidak tersedia
    def play(self, *a): pass
    def stop(self): pass
    def set_volume(self, v): pass
def snd(x, vol=0.9):
    x = x / (np.abs(x).max() + 1e-9) * vol
    a = (x * 32000).astype(np.int16)
    try:
        ch = MIX[2]
        return pg.sndarray.make_sound(np.ascontiguousarray(a if ch == 1 else np.column_stack([a] * ch)))
    except Exception:
        return Mute()
def place(buf, x, at, g=1.0):
    i = int(SR * at); seg = x[:len(buf) - i]; buf[i:i + len(seg)] += seg * g
def click(f=2200, d=.05):
    t = T(d); n = nz(d)
    return ((n - lp(n, 6)) * .7 + np.sin(2 * np.pi * f * t) * .5) * np.exp(-t / .007)
def thud(d=.14, f=95):
    t = T(d); return (lp(nz(d), 18) * 1.5 + np.sin(2 * np.pi * f * t)) * np.exp(-t / .035)
def boom(d, f0, decay, k, nd):          # dentuman senjata: dentum + retakan + gema
    t = T(d)
    thump = np.sin(2 * np.pi * np.cumsum(f0 * np.exp(-t * 14) + 45) / SR) * np.exp(-t / decay)
    crack = nz(d) * np.exp(-t / .012)
    body = lp(nz(d), k) * np.exp(-t / nd) * 3
    return thump * .9 + crack * .8 + body
def growl(d, f0, wob, dec=None):
    t = T(d); f = f0 + 25 * np.sin(2 * np.pi * wob * t)
    saw = (np.cumsum(f) / SR % 1) * 2 - 1
    env = np.sin(np.pi * t / d) if dec is None else np.exp(-t / dec)
    return (lp(saw, 6) + lp(nz(d), 12) * .5) * env

def voice(d, f0, f1, dec=None):             # suara manusia: teriak / erangan / jeritan
    t = T(d); f = np.linspace(f0, f1, len(t)) * (1 + .03 * np.sin(2 * np.pi * 6 * t))
    saw = (np.cumsum(f) / SR % 1) * 2 - 1
    env = np.sqrt(np.sin(np.pi * t / d)) if dec is None else np.exp(-t / dec)
    return (lp(saw, 3) + lp(nz(d), 5) * .25) * env

def uhh(f0a, f0b, f1):                        # erangan pria "uhh": pita suara + formant vokal /uh/
    d = .4; t = T(d); ph = np.cumsum(np.linspace(f0a, f0b, len(t))) / SR
    src = (ph % 1) * 2 - 1 + nz(d) * .12                          # sumber suara + sedikit napas
    fr = np.fft.rfftfreq(len(src), 1 / SR)
    h = .04 + sum(a / (1 + ((fr - f) / bw) ** 2) for f, bw, a in ((f1, 90, 1.0), (f1 * 1.86, 110, .6), (2450, 170, .25), (f0a * 1.5, 80, .35)))
    return np.fft.irfft(np.fft.rfft(src) * h, len(src)) * (1 - np.exp(-t / .012)) * np.exp(-t / .16)

def splat_snd():                              # benturan peluru ke tubuh (basah, pendek) - tanpa suara manusia
    t = T(.14); return lp(nz(.14), 5) * np.exp(-t / .03) + np.sin(2 * np.pi * 160 * t) * np.exp(-t / .025) * .6

def flash_snd():                              # ledakan flashbang + denging di telinga
    b = np.zeros(int(SR * 1.8)); place(b, boom(.5, 150, .05, 4, .12), 0); place(b, np.sin(2 * np.pi * 3800 * T(1.7)) * np.exp(-T(1.7) / 1.0) * .12, .05); return b

def supp_snd():                               # tembakan bersuppressor: dentuman tumpul + desis pendek
    t = T(.22); th = np.sin(2 * np.pi * np.cumsum(90 * np.exp(-t * 25) + 55) / SR) * np.exp(-t / .05)
    return th * .8 + lp(nz(.22), 12) * np.exp(-t / .025) * 1.6 + nz(.22) * np.exp(-t / .004) * .12

def reload_mag():
    b = np.zeros(int(SR * 1.5))
    place(b, click(1800), 0); place(b, thud(), .30, 1.1)
    place(b, click(1400), .75); place(b, click(1100, .06), .80)
    place(b, click(900, .06), 1.10); place(b, click(2600), 1.17)
    return b
def reload_sg():
    b = np.zeros(int(SR * 1.9))
    for at in (.1, .45, .8): place(b, click(1200, .06), at); place(b, thud(.08, 150), at + .03, .5)
    place(b, lp(nz(.15), 4) * np.exp(-T(.15) / .08), 1.2); place(b, click(700, .07), 1.2); place(b, click(2400), 1.42)
    return b

SND = {
    "pistol": snd(boom(.45, 140, .09, 6, .10)), "rifle": snd(boom(.30, 110, .06, 5, .07), .8),
    "shotgun": snd(boom(.9, 90, .22, 14, .35)), "rmag": snd(reload_mag(), .8), "rsg": snd(reload_sg(), .8),
    "empty": snd(click(1000), .6), "step": snd(thud(.1, 70), .35), "hurt": snd(uhh(125, 92, 640)), "hurt2": snd(uhh(115, 84, 600)), "splat": snd(splat_snd(), .8),
    "thud": snd(thud(.28, 60) * 1.4, .8),
    "boom": snd(boom(1.1, 60, .35, 22, .6), 1.0), "flashbang": snd(flash_snd(), 1.0), "clink": snd(click(1700, .06), .5), "m416": snd(supp_snd(), .6),
    "throw": snd((lambda n: lp(n, 6) * np.sin(np.pi * np.arange(len(n)) / len(n)))(nz(.25)), .5),
    "slash": snd((lambda n: (n - lp(n, 4)) * np.sin(np.pi * np.arange(len(n)) / len(n)))(nz(.22)), .7),
    "pickup": snd(np.concatenate([np.sin(2 * np.pi * 660 * T(.08)), np.sin(2 * np.pi * 990 * T(.1))]) * .6, .5),
}
t6 = T(6)   # dengung latar yang mencekam (loop mulus)
ambient = snd((np.sin(2 * np.pi * 55 * t6) + np.sin(2 * np.pi * 55.5 * t6) + .6 * np.sin(2 * np.pi * 82.5 * t6))
              * (.7 + .3 * np.sin(2 * np.pi * .5 * t6)), .2)
def play(name, d=0):
    s = SND[name]; s.set_volume(max(.05, 1 - d / 22) * CFG["vol"] / 10); s.play()

# ================= TEKSTUR (dibuat prosedural) =================
YY, XX = np.mgrid[0:64, 0:64]
def noisy(base, amp=14):
    t = np.empty((64, 64, 3), np.float32); t[:] = base
    return t + rng.integers(-amp, amp, (64, 64, 1))
def blobs(k):
    a = rng.random((64, 64))
    b = sum(np.roll(np.roll(a, i, 0), j, 1) for i in range(k) for j in range(k))
    return (b - b.mean()) / b.std()
def tex_wallpaper():                          # wallpaper damask merah marun + lis kayu
    t = noisy((92, 28, 36), 8)
    t[(((XX % 16 - 8) ** 2 + (YY % 16 - 8) ** 2) < 12) | (((XX % 16) + (YY % 16)) % 16 < 1)] = (140, 100, 52)
    t[YY >= 52] = (54, 32, 24); t[YY == 51] = (170, 125, 60)
    return t * (1 + .12 * blobs(9))[..., None]
def tex_wood():                               # panel kayu gelap / lemari
    t = noisy((78, 46, 30), 8) * (1 + .22 * np.sin(XX * .9 + blobs(5)))[..., None]
    t[(XX % 32 < 2) | (YY % 32 < 2)] = (28, 17, 12); t[(XX % 32 == 2) | (YY % 32 == 2)] = (120, 78, 48)
    return t
def tex_plaster():                            # dinding krem + lukisan berbingkai emas
    t = noisy((178, 166, 142), 6) * (1 + .1 * blobs(9))[..., None]
    t[YY >= 50] = (88, 58, 38); t[YY == 49] = (150, 110, 60)
    t[8:36, 14:50] = (160, 120, 45); t[11:33, 17:47] = (34, 46, 56); t[16:30, 22:42] = (70, 92, 70); t[22:30, 30:40] = (96, 78, 52)
    return t
def tex_floor():                              # lantai parket kayu
    t = noisy((98, 62, 40), 8); a = np.where((XX // 16 + YY // 16) % 2 == 0, XX % 8, YY % 8)
    t[a < 1] = (46, 27, 17); return t * (1 + .2 * blobs(7))[..., None]
def tex_ceil():                               # langit-langit kayu berpetak
    t = noisy((74, 66, 60), 5); t[(XX % 32 < 3) | (YY % 32 < 3)] = (40, 28, 20); return t

def tex_brick():
    t = noisy((140, 66, 52), 14); t[(YY % 16 < 2) | ((XX + (YY // 16 % 2) * 16) % 32 < 2)] = (60, 54, 50); return t * (1 + .14 * blobs(9))[..., None]
def tex_concrete():
    t = noisy((128, 128, 124), 10) * (1 + .15 * blobs(11))[..., None]; t[(XX % 32 < 1) | (YY % 32 < 1)] = (88, 88, 86); t[blobs(9) > 1.5] = (92, 88, 80); return t
def tex_glass():
    t = noisy((70, 110, 140), 6); t[(XX % 32 < 3) | (YY % 32 < 3)] = (40, 46, 52); t[((XX + YY) % 28 < 3) & (XX % 32 > 3) & (YY % 32 > 3)] = (150, 190, 215); return t
def tex_metal2():
    t = noisy((150, 154, 160), 8); t[(XX % 32 < 2) | (YY % 32 < 2)] = (70, 72, 78); t[((XX % 32 - 5) ** 2 + (YY % 32 - 5) ** 2) < 4] = (210, 210, 216); return t * (1 + .1 * blobs(9))[..., None]
def tex_bark():
    t = noisy((92, 64, 40), 12) * (1 + .3 * np.sin(XX * 1.3 + blobs(5)))[..., None]; t[blobs(9) > 1.3] = (60, 90, 40); return t
def tex_leaves():
    t = noisy((34, 82, 36), 18); t[blobs(5) > .9] = (66, 128, 52); t[blobs(5) < -1.0] = (18, 52, 24); return t
def tex_cabin():
    t = noisy((150, 108, 66), 8); t[YY % 12 < 2] = (70, 46, 28); return t * (1 + .15 * np.sin(XX * .7 + blobs(5)))[..., None]
def tex_stone():
    t = noisy((120, 118, 114), 12); t[(YY % 21 < 1) | ((XX + YY // 21 * 11) % 27 < 1)] = (60, 58, 56); return t * (1 + .15 * blobs(9))[..., None]
def tex_locker():
    t = noisy((50, 90, 150), 6); t[XX % 16 < 2] = (24, 40, 70)
    for a, b in ((14, 18), (32, 36)): t[(YY > a) & (YY < b) & (XX % 16 > 3) & (XX % 16 < 13)] = (20, 30, 50)
    t[(XX % 16 > 11) & (XX % 16 < 14) & (YY > 40) & (YY < 50)] = (200, 200, 205); return t
def tex_school():
    t = noisy((220, 210, 180), 6); t[(YY > 40) & (YY < 46)] = (90, 140, 100); t[YY >= 46] = (200, 190, 160)
    t[8:36, 12:52] = (40, 70, 56); t[8:10, 12:52] = (130, 100, 70); t[34:36, 12:52] = (130, 100, 70); return t * (1 + .06 * blobs(9))[..., None]
def tex_white():
    t = noisy((226, 222, 212), 5) * (1 + .06 * blobs(9))[..., None]; t[YY >= 52] = (150, 120, 90); return t
def tex_tile():
    t = noisy((190, 190, 186), 6); k = ((XX // 16) + (YY // 16)) % 2 == 0; t[k] = t[k] * .86; t[(XX % 16 < 1) | (YY % 16 < 1)] = (120, 120, 118); return t
def tex_grass(): return noisy((52, 110, 46), 16) * (1 + .25 * blobs(5))[..., None]
def tex_asphalt():
    t = noisy((52, 52, 56), 8) * (1 + .15 * blobs(7))[..., None]; t[(XX % 32 < 3) & (YY < 16)] = (210, 200, 90); return t
def tex_conc_floor():
    t = noisy((120, 120, 116), 8) * (1 + .12 * blobs(9))[..., None]; t[(XX % 32 < 1) | (YY % 32 < 1)] = (80, 80, 78); return t
def tex_ceil_white():
    t = noisy((205, 205, 200), 4); t[(XX % 16 < 1) | (YY % 16 < 1)] = (150, 150, 146); return t
def make_sky(top, bot, cloud):                 # langit melingkar 360 derajat (gradasi + awan)
    y = (np.arange(64) / 63.0)[:, None, None]; sky = np.repeat(np.array(top, np.float32) * (1 - y) + np.array(bot, np.float32) * y, 512, axis=1)
    cl = np.kron(np.random.default_rng(3).random((8, 64)), np.ones((8, 8))); cl = (cl + np.roll(cl, 4, 1) + np.roll(cl, -4, 1)) / 3
    m = (np.clip((cl - .55) * 3, 0, 1) * .6)[..., None]; return sky * (1 - m) + np.array(cloud, np.float32) * m

WALLS = np.stack([tex_wallpaper(), tex_wood(), tex_plaster(), tex_brick(), tex_concrete(), tex_glass(), tex_metal2(), tex_bark(), tex_leaves(), tex_cabin(), tex_stone(), tex_locker(), tex_school(), tex_white()]).clip(0, 255).astype(np.float32)
FLOORS = {"parket": tex_floor().clip(0, 255), "tile": tex_tile().clip(0, 255), "grass": tex_grass().clip(0, 255), "asphalt": tex_asphalt().clip(0, 255), "beton": tex_conc_floor().clip(0, 255)}
CEILS = {"kayu": tex_ceil().clip(0, 255), "putih": tex_ceil_white().clip(0, 255)}
SKIES = {"day": make_sky((70, 130, 210), (185, 218, 246), (255, 255, 255)), "dusk": make_sky((58, 60, 120), (250, 160, 92), (255, 190, 140)), "gray": make_sky((118, 128, 142), (204, 208, 212), (236, 236, 240))}
FLOOR, CEIL, SKY, FOGD, WH = FLOORS["parket"], CEILS["kayu"], None, 13, 1.6      # WH = tinggi dinding / atap (1 = tinggi musuh)

def to_tex(s):
    rgb = pg.surfarray.array3d(s).transpose(1, 0, 2).astype(np.float32) * (.85 + .3 * rng.random((64, 64, 1)))
    return np.dstack([rgb, pg.surfarray.array_alpha(s).T.astype(np.float32)])
def surf(): return pg.Surface((64, 64), pg.SRCALPHA)
def make_enemy(kind, jacket, pants, skin, ph=0):      # ph = fase langkah kaki (animasi jalan)
    s = surf(); wd = {"bodyguard": 4, "boss": 6}.get(kind, 0); OL = (14, 10, 12)
    dk = lambda c, k=.6: tuple(int(v * k) for v in c); lt = lambda c: tuple(min(255, int(v * 1.25) + 12) for v in c)
    def poly(pts, col): D.polygon(s, col, pts); D.polygon(s, OL, pts, 1)
    sw_ = 3 if ph else -3
    for lx, o in ((21 - wd // 2, sw_), (34 + wd // 2, -sw_)):                                       # kaki bercelana + sepatu
        poly([(lx, 41), (lx + 9, 41), (lx + 9 + o // 2, 58), (lx + o // 2, 58)], pants)
        poly([(lx - 1 + o // 2, 57), (lx + 10 + o // 2, 57), (lx + 12 + o // 2, 63), (lx - 2 + o // 2, 63)], (20, 18, 20))
    poly([(19 - wd, 19), (45 + wd, 19), (47 + wd, 44), (17 - wd, 44)], jacket)                      # badan
    poly([(19 - wd, 19), (27, 19), (33, 44), (17 - wd, 44)], dk(jacket, .72)); D.line(s, lt(jacket), (43 + wd, 22), (44 + wd, 40), 2)
    D.rect(s, (28, 22, 18), (18 - wd, 40, 30 + 2 * wd, 3)); D.rect(s, (205, 175, 60), (30, 40, 4, 3))   # ikat pinggang + gesper
    if kind in ("agen", "bodyguard", "boss"):                                                        # kemeja putih + dasi
        poly([(27, 19), (37, 19), (32, 33)], (236, 236, 240)); poly([(31, 22), (33, 22), (34, 36), (32, 39), (30, 36)], (170, 20, 30) if kind == "boss" else (14, 14, 16))
    elif kind == "preman": D.rect(s, dk(jacket, .6), (25, 31, 14, 8)); D.polygon(s, dk(jacket, .5), [(27, 19), (37, 19), (32, 25)])   # kantong + kerah hoodie
    else: poly([(26, 19), (32, 30), (38, 19)], dk(jacket, .55))                                      # kerah jaket kulit
    D.rect(s, dk(skin, .8), (28, 15, 8, 6))                                                          # leher
    for ax, ay, hx, hy in ((21 - wd, 22, 13 - wd, 38), (43 + wd, 22, 51 + wd, 33)):                   # lengan + tangan
        D.line(s, OL, (ax, ay), (hx, hy), 7); D.line(s, jacket, (ax, ay), (hx, hy), 5); D.circle(s, skin, (hx, hy), 3); D.circle(s, OL, (hx, hy), 3, 1)
    if kind == "penjahat": poly([(50 + wd, 28), (61, 28), (61, 32), (54 + wd, 32), (54 + wd, 37), (51 + wd, 37)], (36, 36, 42))   # pistol
    elif kind in ("agen", "boss"): poly([(36, 29), (62, 29), (62, 33), (44, 34), (44, 41), (40, 41), (40, 34), (36, 34)], (28, 28, 34))  # SMG / rifle
    elif kind == "preman": D.line(s, OL, (52, 36), (58, 7), 5); D.line(s, (165, 165, 175), (52, 36), (58, 7), 3)                   # pipa besi
    D.ellipse(s, OL, (23, 2, 18 + wd // 2, 19)); D.ellipse(s, skin, (24, 3, 16 + wd // 2, 17))       # kepala
    D.circle(s, skin, (23, 12), 2); D.circle(s, skin, (41 + wd // 2, 12), 2)                          # telinga
    if kind in ("agen", "bodyguard", "boss"): D.rect(s, (8, 8, 10), (25, 9, 14 + wd // 2, 4)); D.line(s, (8, 8, 10), (24, 10), (22, 16), 1)   # kacamata hitam
    else: D.circle(s, (20, 20, 24), (28, 11), 1); D.circle(s, (20, 20, 24), (36, 11), 1)              # mata
    D.line(s, dk(skin, .5), (29, 17), (35, 17), 1)                                                    # mulut
    if kind == "preman": D.ellipse(s, (28, 28, 34), (23, 0, 18, 9)); D.rect(s, (70, 70, 80), (23, 6, 18, 3))                       # kupluk
    elif kind == "penjahat": D.ellipse(s, (34, 24, 18), (24, 1, 16, 8)); poly([(24, 13), (40, 13), (38, 21), (26, 21)], (170, 28, 30))   # rambut + bandana
    elif kind == "agen": D.ellipse(s, (30, 24, 20), (24, 1, 16, 7)); D.line(s, (210, 210, 40), (22, 16), (24, 24), 1)              # rambut + kabel earpiece
    elif kind == "boss": D.ellipse(s, (200, 200, 205), (24, 1, 16, 6)); poly([(29, 18), (35, 18), (34, 23), (30, 23)], (60, 50, 44)); D.circle(s, (240, 200, 60), (32, 27), 2)
    return to_tex(s)
def make_dead(body, skin):
    s = surf(); D.ellipse(s, (95, 8, 8), (4, 50, 56, 12)); D.rect(s, body, (12, 48, 36, 10))
    D.circle(s, skin, (50, 53), 6); D.line(s, (40, 40, 60), (12, 52), (2, 58), 4); return to_tex(s)
def make_fire():
    s = surf()
    for r, c in ((30, (255, 170, 40)), (18, (255, 230, 120)), (8, (255, 255, 235))): D.circle(s, c, (32, 32), r)
    return to_tex(s)
def make_item(kind):
    s = surf()
    if kind == "health":
        D.rect(s, (230, 230, 230), (14, 24, 36, 26)); D.rect(s, (200, 20, 20), (28, 27, 8, 20)); D.rect(s, (200, 20, 20), (22, 33, 20, 8))
    elif kind == "armor":
        D.polygon(s, (40, 90, 210), [(16, 24), (48, 24), (52, 50), (12, 50)]); D.line(s, (120, 170, 255), (20, 28), (44, 28), 3)
    elif kind == "granat": D.ellipse(s, (70, 110, 60), (20, 24, 24, 30)); D.rect(s, (150, 150, 150), (29, 16, 6, 10)); D.circle(s, (200, 200, 200), (40, 20), 5, 2)
    elif kind == "flash":  D.rect(s, (190, 190, 200), (24, 20, 16, 34)); D.rect(s, (240, 200, 60), (24, 20, 16, 7)); D.rect(s, (60, 60, 70), (24, 38, 16, 4))
    else:
        D.rect(s, (80, 86, 50), (12, 30, 40, 22))
        for i in range(5): D.rect(s, (215, 175, 45), (16 + i * 7, 22, 5, 11))
    return to_tex(s)

def make_blast(circles):
    s = surf()
    for r, c in circles: D.circle(s, c, (32, 32), r)
    return to_tex(s)

def make_cp(on):                              # lampu checkpoint: oranye = belum, hijau = aktif
    s = surf(); c = (70, 235, 130) if on else (235, 150, 40)
    D.rect(s, (60, 56, 56), (29, 26, 6, 36)); D.rect(s, (60, 56, 56), (22, 58, 20, 5))
    D.circle(s, tuple(v // 3 for v in c), (32, 18), 14); D.circle(s, c, (32, 18), 10); D.circle(s, (255, 255, 235), (32, 18), 4)
    return to_tex(s)

# ================= KARAKTER 3D BERGAYA BLOK (voxel ala Minecraft) =================
SHOE, BELT = (22, 20, 22), (30, 24, 20)
def vox_model(kind, jc, pc, sk, dead=False, arm=False):             # daftar balok: (x0, x1, y0, y1, z0, z1, warna, bagian, bias). depan = -z, tinggi total 32
    dk = lambda c, k: tuple(int(v * k) for v in c); B = []; s = 1.25 if kind == "bodyguard" else 1.0; suit = kind in ("agen", "bodyguard", "boss")
    bx = lambda x0, x1, y0, y1, z0, z1, col, part="", bias=0.0: B.append((x0, x1, y0, y1, z0, z1, col, part, bias))
    bx(-4, -.1, 0, 12, -2, 2, pc, "legL"); bx(.1, 4, 0, 12, -2, 2, pc, "legR")                                      # kaki + sepatu
    bx(-4.2, -.1, 0, 2.4, -3.4, 2.2, SHOE, "legL"); bx(.1, 4.2, 0, 2.4, -3.4, 2.2, SHOE, "legR")
    bx(-4 * s, 4 * s, 12, 24, -2, 2, jc); bx(-4 * s - .2, 4 * s + .2, 12, 13.4, -2.2, 2.2, BELT); bx(-.9, .9, 12, 13.4, -2.6, -2.2, (205, 175, 60), "", .5)   # badan + ikat pinggang
    for sd, part in ((-1, "armL"), (1, "armR")):                                                                      # lengan + tangan
        xa, xb = sorted((sd * 4 * s, sd * (4 * s + 4))); bx(xa, xb, 15, 24, -2, 2, jc, part); bx(xa - .1, xb + .1, 12, 15, -2.1, 2.1, sk, part)
    bx(-4, 4, 24, 32, -4, 4, sk)                                                                                       # kepala
    if suit: bx(-4.3, 4.3, 27.3, 29.6, -4.5, -4, (8, 8, 10), "", .5); bx(-4.4, -4, 27.3, 29, -4, 1, (8, 8, 10), "", .5); bx(4, 4.4, 27.3, 29, -4, 1, (8, 8, 10), "", .5)   # kacamata hitam
    else:
        for ex in (-3.2, 1.2): bx(ex, ex + 2, 27.2, 28.8, -4.4, -4, (238, 238, 242), "", .5); bx(ex + (.9 if ex < 0 else 0), ex + (2 if ex < 0 else 1.1), 27.2, 28.4, -4.6, -4.4, (30, 40, 70), "", .8)   # mata
    bx(-1.6, 1.6, 25.2, 26.1, -4.3, -4, dk(sk, .55), "", .5)                                                           # mulut
    hair = (200, 200, 205) if kind == "boss" else (34, 24, 18) if kind == "penjahat" else (30, 24, 20)
    if kind in ("agen", "bodyguard", "boss", "penjahat", "pl"): bx(-4.3, 4.3, 31, 32.8, -4.3, 4.3, hair); bx(-4.3, 4.3, 26.5, 32, 1.5, 4.3, hair)   # rambut
    if kind == "preman": bx(-4.6, 4.6, 30, 34.2, -4.6, 4.6, (28, 28, 34)); bx(-4.7, 4.7, 30, 31.8, -4.7, 4.7, (72, 72, 84)); bx(-3.4, 3.4, 14, 17.4, -2.5, -2, dk(jc, .6), "", .6)   # kupluk + kantong hoodie
    if kind == "penjahat": bx(-4.4, 4.4, 25.2, 27.8, -4.4, 4.4, (170, 28, 30), "", .3); bx(-3, 3, 22, 24, -2.4, -2, dk(jc, .55), "", .6)                          # bandana + kerah
    if suit: bx(-1.9, 1.9, 17, 24, -2.4, -2, (236, 236, 240), "", .6); bx(-.7, .7, 14, 23, -2.8, -2.4, (170, 20, 30) if kind == "boss" else (14, 14, 16), "", .9)   # kemeja + dasi
    wp = {"preman": (-10, 15, (165, 165, 175), 1.0), "penjahat": (3, 14, (36, 36, 42), 1.2), "agen": (-10, 15, (28, 28, 34), 1.5), "boss": (-10, 15, (28, 28, 34), 1.5)}.get(kind)
    if wp and not dead: bx(4 * s + 2 - wp[3] / 2 - .1, 4 * s + 2 + wp[3] / 2 + .1, wp[0], wp[1], -wp[3] / 2, wp[3] / 2, wp[2], "armR")                                               # senjata di tangan kanan
    if arm:                                                                                                            # armor baja bos: helm, dada, bahu, lengan bawah, tulang kering
        ST, GD = (84, 90, 104), (205, 168, 62)
        bx(-4.7, 4.7, 29.6, 33.6, -4.7, 4.7, ST, "", .2); bx(-.7, .7, 33.6, 35.3, -3.2, 3.2, GD, "", .3); bx(-4.7, -4, 24.6, 30, -4.7, 4.7, ST, "", .2); bx(4, 4.7, 24.6, 30, -4.7, 4.7, ST, "", .2)
        bx(-4.7, 4.7, 14, 24.4, -3, -2, ST, "", 1.4); bx(-4.7, 4.7, 18.6, 19.8, -3.2, -3, GD, "", 1.7); bx(-4.7, 4.7, 14, 24.4, 2, 3, ST, "", 1.0); bx(-1, 1, 21, 23.6, -3.2, -3, GD, "", 1.7)
        for sd, part in ((-1, "armL"), (1, "armR")):
            xa, xb = sorted((sd * 4 * s, sd * (4 * s + 4))); bx(xa - .7, xb + .7, 21.6, 25.4, -2.8, 2.8, ST, part, .5); bx(xa - .7, xb + .7, 24.4, 25.4, -2.8, 2.8, GD, part, .7); bx(xa - .3, xb + .3, 15.2, 19.2, -2.5, 2.5, ST, part, .4)
        bx(-4.2, -.2, 3, 10, -2.6, -2, ST, "legL", .5); bx(.2, 4.2, 3, 10, -2.6, -2, ST, "legR", .5)
    return B

FACES = (((-1, 0, 0), ((0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1))), ((1, 0, 0), ((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1))),
         ((0, -1, 0), ((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1))), ((0, 1, 0), ((0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1))),
         ((0, 0, -1), ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))), ((0, 0, 1), ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))))
VL = (-.35, .75, -.55); VLn = math.sqrt(sum(v * v for v in VL)); VL = tuple(v / VLn for v in VL)

def vox_cmds(kind, jc, pc, sk, rel, sw, dead, arm=False):   # model -> daftar (warna, poligon 2D), urut dari belakang ke depan
    S = 1.75; cr, sr = math.cos(rel), math.sin(rel); tl = .5 if dead else .22; ct, st = math.cos(tl), math.sin(tl); out = []; lift = 13 if dead else 0
    gun = kind in ("agen", "boss", "penjahat"); s = 1.25 if kind == "bodyguard" else 1.0
    th = {"legL": sw, "legR": -sw, "armL": -sw, "armR": sw}
    if gun: th["armR"] = math.radians(85 if kind == "penjahat" else 80); th["armL"] = math.radians(50) if kind != "penjahat" else -sw
    if kind == "preman": th["armR"] = math.radians(115)
    if dead: th = {"legL": .25, "legR": -.15, "armL": -.5, "armR": .6}
    piv = {"legL": (-2, 12, 0), "legR": (2, 12, 0), "armL": (-4 * s - 2, 24, 0), "armR": (4 * s + 2, 24, 0)}
    def tf(v, part, pt):                                                       # rotasi bagian tubuh -> jatuh -> putar -> miring kamera
        x, y, z = v
        if part:
            a = th[part]; c, s_ = math.cos(a), math.sin(a); py, pz = piv[part][1:] if pt else (0, 0); dy, dz = y - py, z - pz
            y, z = py + dy * c - dz * s_, pz + dy * s_ + dz * c
        if dead: y, z = -z + (2.5 if pt else 0), y + (-16 if pt else 0)           # tubuh rebah telentang
        x, z = x * cr + z * sr, -x * sr + z * cr
        return x, y * ct + z * st, -y * st + z * ct
    for x0, x1, y0, y1, z0, z1, col, part, bias in vox_model(kind, jc, pc, sk, dead, arm):
        vs = {}
        for iz in (0, 1):
            for iy in (0, 1):
                for ix in (0, 1): vs[ix, iy, iz] = tf((x1 if ix else x0, y1 if iy else y0, z1 if iz else z0), part, True)
        for nrm, idx in FACES:
            nc = tf(nrm, part, False)
            if nc[2] >= -.01: continue
            pts = [vs[i] for i in idx]; k = max(.4, min(1.25, .45 + .62 * max(0.0, nc[0] * VL[0] + nc[1] * VL[1] + nc[2] * VL[2])))
            out.append((sum(p[2] for p in pts) / 4 - bias, tuple(min(255, int(c * k)) for c in col), [(int(32 + p[0] * S), int(62 - p[1] * S - lift)) for p in pts]))
    out.sort(key=lambda o: -o[0]); return [(c, p) for _, c, p in out]

def vox_tex(kind, jc, pc, sk, rel, sw, dead, arm=False):
    s = surf()
    if dead: D.ellipse(s, (95, 8, 8), (4, 40, 56, 20))
    for col, pts in vox_cmds(kind, jc, pc, sk, rel, sw, dead, arm): D.polygon(s, col, pts); D.polygon(s, tuple(int(v * .5) for v in col), pts, 1)
    return to_tex(s)

CHAR_CACHE = {}
def char_tex(key, kind, cols, fa, ex, ey, ph, moving, dead, arm=False):       # tekstur karakter 3D sesuai sudut pandang (di-cache)
    rel = (fa - math.atan2(P.y - ey, P.x - ex)) % (2 * math.pi); b = int(rel / (2 * math.pi) * 16 + .5) % 16
    sw = -1 if (dead or not moving) else int((math.sin(ph * 4.4) + 1) * 1.99); ck = (key, b, sw, dead, arm); t = CHAR_CACHE.get(ck)
    if t is None: t = CHAR_CACHE[ck] = vox_tex(kind, *cols, b * 2 * math.pi / 16, 0.0 if sw < 0 else (sw - 1.5) / 1.5 * .6, dead, arm)
    return t

TYPES = {"preman": dict(hp=45, spd=2.1, dmg=10, rng=0, cd=1.0, snd="", c=((72, 74, 82), (46, 58, 96), (205, 160, 125))),
         "penjahat": dict(hp=60, spd=1.5, dmg=9, rng=11, cd=1.7, snd="pistol", c=((104, 64, 40), (40, 40, 48), (190, 140, 105))),
         "agen": dict(hp=90, spd=1.8, dmg=7, rng=12, cd=.85, snd="rifle", c=((24, 24, 30), (20, 20, 26), (215, 170, 135))),
         "bodyguard": dict(hp=160, spd=2.6, dmg=16, rng=0, cd=1.0, snd="", c=((18, 18, 22), (18, 18, 22), (170, 120, 90))),
         "boss": dict(hp=900, spd=2.0, dmg=9, rng=14, cd=.45, snd="rifle", c=((226, 226, 232), (30, 30, 36), (190, 140, 105)))}
TEX = {"fire": make_fire(), **{k: make_item(k) for k in ("health", "armor", "ammo", "granat", "flash")}}
TEX["cp0"], TEX["cp1"] = make_cp(False), make_cp(True)
TEX["boom"] = make_blast(((30, (200, 50, 10)), (22, (255, 140, 20)), (14, (255, 220, 90)), (7, (255, 255, 220))))
TEX["flashfx"] = make_blast(((30, (255, 255, 255)), (20, (255, 255, 255))))
PJ = ((24, 24, 30), (40, 70, 140), (150, 44, 44), (50, 120, 64))         # warna jas pemain multiplayer

# ================= PETA & UTILITAS =================
N = 40
THEMES = {
    "RUMAH": dict(gen="rooms", walls=(14, 14, 3, 4), furn=2, minsz=10, nf=60, floor="parket", ceil="putih", sky=None, fogd=13, grade=(1.06, .97, .92)),
    "MANSION": dict(gen="rooms", walls=(1, 1, 2, 3), furn=2, minsz=12, nf=70, floor="parket", ceil="kayu", sky=None, fogd=13, grade=(1.08, .94, .9)),
    "PEDESAAN": dict(gen="village", walls=(10, 11, 9), floor="grass", ceil="kayu", sky="day", fogd=24, grade=(1.04, 1.0, .94)),
    "HUTAN": dict(gen="forest", walls=(8, 9, 11), floor="grass", ceil="kayu", sky="day", fogd=17, grade=(.9, 1.02, .9)),
    "KOTA": dict(gen="city", walls=(4, 5, 6), floor="asphalt", ceil="kayu", sky="dusk", fogd=24, grade=(1.06, .97, .94)),
    "BANDARA": dict(gen="airport", walls=(5, 6, 7), floor="beton", ceil="putih", sky="gray", fogd=26, grade=(.98, 1.0, 1.04)),
    "SEKOLAH": dict(gen="school", walls=(13, 12, 4), floor="tile", ceil="putih", sky=None, fogd=15, grade=(1.02, 1.0, .96))}

for _k, _v in dict(RUMAH=1.7, MANSION=2.0, SEKOLAH=1.8, PEDESAAN=1.6, HUTAN=2.3, KOTA=2.5, BANDARA=1.9).items(): THEMES[_k]["wh"] = _v   # dalam ruangan: atap tinggi; luar ruangan: dinding tinggi tanpa atap

def set_theme(name):                           # ganti lantai / langit / kabut / warna sesuai lokasi
    global FLOOR, CEIL, SKY, FOGD, GRADE, WH
    T = THEMES[name]; FLOOR, CEIL, FOGD, WH = FLOORS[T["floor"]], CEILS[T["ceil"]], T["fogd"], T["wh"]
    SKY = SKIES[T["sky"]] if T["sky"] else None; GRADE = np.array(T["grade"], np.float32)

def blank(b):
    m = np.zeros((N, N), np.int8); m[0, :] = m[-1, :] = m[:, 0] = m[:, -1] = b; return m

def hollow(m, x, y, w, h, wid, door="s"):      # bangunan berongga + pintu selebar 2 sel
    m[y:y + h, x:x + w] = wid; m[y + 1:y + h - 1, x + 1:x + w - 1] = 0; cx, cy = x + w // 2, y + h // 2
    if door == "s": m[y + h - 1, cx:cx + 2] = 0
    elif door == "n": m[y, cx:cx + 2] = 0
    elif door == "e": m[cy:cy + 2, x + w - 1] = 0
    else: m[cy:cy + 2, x] = 0

def gen_rooms(T):                              # rumah / mansion: ruangan acak + pintu + perabot
    ids, furn, minsz, nf = T["walls"], T["furn"], T["minsz"], T["nf"]; m = blank(ids[0]); doors = set()
    def split(x0, y0, x1, y1):
        w, h = x1 - x0, y1 - y0
        if w < minsz and h < minsz: return
        vert = (w >= h) if (w >= minsz and h >= minsz) else (w >= minsz)
        a0, a1 = (x0, x1) if vert else (y0, y1)
        ends = lambda c: ((c, y0 - 1), (c, y1)) if vert else ((x0 - 1, c), (x1, c))
        cand = [c for c in range(a0 + 5, a1 - 5) if not any(e in doors for e in ends(c))]
        if not cand: return
        c = random.choice(cand); wt = random.choice(ids); lo, hi = (y0, y1) if vert else (x0, x1)
        for p in range(lo, hi):
            if vert: m[p, c] = wt
            else: m[c, p] = wt
        for _ in range(2):
            p = random.randint(lo + 1, hi - 3)
            for q in (p, p + 1):
                if vert: m[q, c] = 0; doors.add((c, q))
                else: m[c, q] = 0; doors.add((q, c))
        if vert: split(x0, y0, c, y1); split(c + 1, y0, x1, y1)
        else: split(x0, y0, x1, c); split(x0, c + 1, x1, y1)
    split(1, 1, N - 1, N - 1)
    for _ in range(nf):
        x, y = random.randint(2, N - 4), random.randint(2, N - 4); w, h = random.choice(((1, 1), (2, 1), (1, 2)))
        near = any((x + i, y + j) in doors for i in range(-2, w + 2) for j in range(-2, h + 2))
        if not m[y - 1:y + h + 1, x - 1:x + w + 1].any() and not near and not (x < 8 and y < 8): m[y:y + h, x:x + w] = furn
    return m

def gen_school(T):                             # koridor panjang + 8 ruang kelas bermeja
    cw, lk, br = T["walls"]; m = blank(br); m[1:N - 1, 1:N - 1] = 0
    for wx in (9, 19, 29): m[1:17, wx] = cw; m[23:N - 1, wx] = cw
    m[16, 1:N - 1] = lk; m[23, 1:N - 1] = lk
    for c in (4, 14, 24, 34): m[16, c:c + 2] = 0; m[23, c:c + 2] = 0
    for x0, x1 in ((1, 8), (10, 18), (20, 28), (30, 38)):
        for y0, y1 in ((2, 15), (24, 37)):
            for yy in range(y0 + 3, y1 - 2, 3):
                for xx in range(x0 + 1, x1 - 1, 3): m[yy, xx:xx + 2] = 2
    return m

def gen_forest(T):                             # hutan: gerombolan pohon alami
    b, l, st = T["walls"]; m = blank(b); r = np.random.random((N, N)) < .38
    for _ in range(3): r = sum(np.roll(np.roll(r, i, 0), j, 1) for i in (-1, 0, 1) for j in (-1, 0, 1)) >= 5
    ids = np.where(np.random.random((N, N)) < .6, b, l); ids[np.random.random((N, N)) < .08] = st
    r[0, :] = r[-1, :] = r[:, 0] = r[:, -1] = True; m[r] = ids[r]; return m

def gen_village(T):                            # pedesaan: rumah kayu, pagar tanaman, jerami
    cab, stn, hed = T["walls"]; m = blank(hed); placed = []
    for _ in range(80):
        w, h = random.randint(7, 9), random.randint(6, 8); x, y = random.randint(2, N - w - 2), random.randint(2, N - h - 2)
        if all(x + w + 3 < a or a + c + 3 < x or y + h + 3 < b or b + d + 3 < y for a, b, c, d in placed) and not (x < 8 and y < 8):
            placed.append((x, y, w, h)); hollow(m, x, y, w, h, random.choice((cab, cab, stn)), random.choice("nsew"))
            if m[y + h // 2, x + 2] == 0: m[y + h // 2, x + 2:x + 4] = 2
            if len(placed) >= 7: break
    for _ in range(16):
        x, y = random.randint(2, N - 10), random.randint(2, N - 10); L = random.randint(4, 8)
        if random.random() < .5 and not m[y - 1:y + 2, x:x + L].any(): m[y, x:x + L] = hed
        elif not m[y:y + L, x - 1:x + 2].any(): m[y:y + L, x] = hed
    for _ in range(50):
        x, y = random.randint(2, N - 3), random.randint(2, N - 3)
        if not m[y - 1:y + 2, x - 1:x + 2].any() and not (x < 8 and y < 8): m[y, x] = random.choice((hed, stn))
    return m

def gen_city(T):                               # kota: blok gedung, jalan, toko yang bisa dimasuki, mobil
    br, co, gl = T["walls"]; m = blank(co)
    for bx in (4, 16, 28):
        for by in (4, 16, 28):
            wid = random.choice((br, br, co, gl))
            if random.random() < .5: hollow(m, bx, by, 8, 8, wid, random.choice("nsew")); m[by + 3, bx + 2:bx + 4] = 2
            else: m[by:by + 8, bx:bx + 8] = wid
    for _ in range(30):
        x, y = random.randint(2, N - 4), random.randint(2, N - 4); w, h = random.choice(((2, 1), (1, 2), (1, 1)))
        if not m[y - 1:y + h + 1, x - 1:x + w + 1].any() and not (x < 8 and y < 8): m[y:y + h, x:x + w] = 7
    return m

def gen_airport(T):                            # bandara: terminal (konter, pilar) + apron dengan pesawat
    co, gl, me = T["walls"]; m = blank(co); m[20, 1:N - 1] = gl
    for dx in (6, 18, 30): m[20, dx:dx + 3] = 0
    for px in (8, 16, 24, 32): m[6:8, px:px + 2] = co
    for cx in (6, 14, 22, 30): m[12, cx:cx + 5] = 2
    m[27:30, 5:19] = me; m[25:27, 16:18] = me; m[24:28, 9:11] = me; m[30:34, 9:11] = me
    m[34:37, 21:35] = me; m[32:34, 33:35] = me; m[31:34, 26:28] = me; m[37:39, 26:28] = me
    for _ in range(12):
        x, y = random.randint(2, N - 5), random.randint(22, N - 3)
        if not m[y - 1:y + 2, x - 1:x + 3].any(): m[y, x:x + 2] = me
    return m

GENS = {"rooms": gen_rooms, "school": gen_school, "forest": gen_forest, "village": gen_village, "city": gen_city, "airport": gen_airport}
def build_stage(name):
    T = THEMES[name]
    for _ in range(80):
        m = GENS[T["gen"]](T); m[2:5, 2:5] = 0
        seen = np.zeros((N, N), bool); seen[3, 3] = True; q = deque([(3, 3)])
        while q:
            x, y = q.popleft()
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if m[ny, nx] == 0 and not seen[ny, nx]: seen[ny, nx] = True; q.append((nx, ny))
        if seen.sum() > 450: break
    m[(m == 0) & ~seen] = T["walls"][0]; return m

def build_arena():                            # ruang bos: aula besar tersendiri, pilar jadi tempat berlindung
    m = np.ones((N, N), np.int8); m[8:32, 2:38] = 0
    m[7, 1:39] = m[32, 1:39] = 3; m[7:33, 1] = m[7:33, 38] = 3
    for px, py in ((9, 12), (9, 26), (19, 12), (19, 26), (29, 12), (29, 26), (14, 19), (24, 19)): m[py:py + 2, px:px + 2] = 2
    return m
def bfs(src):
    d = np.full((N, N), 9999, np.int32); d[src[1], src[0]] = 0; q = deque([src])
    while q:
        x, y = q.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if MAP[ny, nx] == 0 and d[ny, nx] > d[y, x] + 1: d[ny, nx] = d[y, x] + 1; q.append((nx, ny))
    return d
def free(x, y, r=.25):
    return not any(MAP[int(y + dy), int(x + dx)] for dx in (-r, r) for dy in (-r, r))
def los(x0, y0, x1, y1):
    n = int(math.hypot(x1 - x0, y1 - y0) / .2) + 1
    return not any(MAP[int(y0 + (y1 - y0) * i / n), int(x0 + (x1 - x0) * i / n)] for i in range(1, n))

P = NS(); MAP = DIST = MM = None; enemies, items, projs, cps = [], [], [], []; DIFF = {}; parts, decals, nades, blasts = [], [], [], []
LIGHT, FLICK = 1.0, 0.0

# ================= PEMAIN LOKAL (1 pemain, atau 2 pemain split screen) =================
# Semua fungsi game membaca pemain aktif lewat variabel global P. Pada split screen, P diganti-ganti (as_pl) sesuai pemain yang sedang diproses.
PL = [P]
SHARED = {"mode", "diff", "floor", "stage", "conts", "used", "wave", "time", "cp", "cut", "paused", "loadout0"}      # data misi yang dipakai bersama kedua pemain
class Co2(NS):                                 # pemain ke-2: atribut bersama diteruskan ke pemain 1 (tidak ada salinan yang bisa selisih)
    def __getattr__(s, n):
        if n in SHARED: return getattr(PL[0], n)
        raise AttributeError(n)
    def __setattr__(s, n, v):
        if n in SHARED: setattr(PL[0], n, v)
        else: NS.__setattr__(s, n, v)
def CO(): return len(PL) > 1
class as_pl:                                   # with as_pl(i): ...  -> sementara jadikan pemain ke-i sebagai P
    def __init__(s, i): s.i = i
    def __enter__(s): global P; s.old = P; P = PL[s.i]
    def __exit__(s, *a): global P; P = s.old
def pidx():                                    # nomor pemain aktif (pakai "is": SimpleNamespace dibandingkan isinya bila memakai ==)
    return next((i for i, q in enumerate(PL) if q is P), 0)
def say(text, secs=2.5):
    for q in PL: q.msg = (text, secs)

DIFFS = {
    "EASY": dict(stages=["RUMAH", "KOTA", "MANSION"], floors=3, n=28, add=5, hp=.8, dmg=.7, spd=.9, cd=1.3, spr=.10, sight=14, conts=99, guards=4, gr=4, fb=3, items=34, mix=[45, 30, 20, 5],
                 desc="Musuh sedikit & lemah, 3 lokasi + ruang bos, continue tak terbatas"),
    "MEDIUM": dict(stages=["RUMAH", "PEDESAAN", "KOTA", "BANDARA", "MANSION"], floors=5, n=34, add=5, hp=1.0, dmg=1.0, spd=1.0, cd=1.0, spr=.06, sight=18, conts=5, guards=8, gr=3, fb=2, items=28, mix=[35, 30, 25, 10],
                   desc="Seimbang: 5 lokasi + ruang bos, 5 continue"),
    "HARD": dict(stages=["RUMAH", "PEDESAAN", "HUTAN", "KOTA", "SEKOLAH", "BANDARA", "MANSION"], floors=7, n=36, add=5, hp=1.5, dmg=1.4, spd=1.15, cd=.7, spr=.03, sight=22, conts=3, guards=12, gr=2, fb=2, items=22, mix=[20, 30, 35, 15],
                 desc="Musuh banyak & kuat, 7 lokasi (semua map) + ruang bos, hanya 3 continue")}

def snap_pl(q): return dict(a=q.a, hp=q.hp, armor=q.armor, weap=[dict(w) for w in q.weap], cur=q.cur)
def save_cp(x, y):
    P.cp = dict(x=x, y=y, a=P.a, hp=P.hp, armor=P.armor, weap=[dict(w) for w in P.weap], cur=P.cur, snaps=[snap_pl(q) for q in PL])

def start_game(key, cfg=None, co=False):
    global DIFF
    TEAM.clear(); TSC[:] = [0, 0]                                         # mode tim hanya berlaku di multiplayer (diisi ulang oleh start_mp)
    DIFF = cfg or DIFFS[key]; P.mode = "campaign"; P.diff = key; P.floor = (cfg or {}).get("floor", 0); P.hp, P.armor, P.kills, P.time = 100, 50, 0, 0.0
    P.conts, P.used, P.cur = DIFF["conts"], 0, 0; P.gr, P.fb = DIFF["gr"], DIFF["fb"]
    mk = lambda **k: k
    P.weap = [mk(name="PISTOL", mag=12, ammo=12, mags=4, dmg=24, delay=.32, pel=1, spr=.012, auto=False, snd="pistol", rl=1.5, rsnd="rmag", ln=230, zoom=.5),
              mk(name="ASSAULT RIFLE", mag=60, ammo=60, mags=3, dmg=16, delay=.075, pel=1, spr=.022, auto=True, snd="m416", rl=2.0, rsnd="rmag", ln=300, zoom=.42, alert=4, fl=.4),
              mk(name="SHOTGUN", mag=6, ammo=6, mags=3, dmg=13, delay=.85, pel=9, spr=.07, auto=False, snd="shotgun", rl=2.0, rsnd="rsg", ln=320, zoom=.52)]
    P.loadout0 = [dict(w) for w in P.weap]; P.itemq, P.last_by, P.feed = [], -1, []
    P.paused = False; P.ph = P.mt = P.rv = P.dtimer = 0.0; PL[:] = [P]; DISTS.clear()
    if co:                                                                    # split screen: pemain ke-2 dengan perlengkapan sendiri
        q = Co2(); q.weap = [dict(w) for w in P.weap]; q.hp, q.armor, q.kills, q.cur, q.gr, q.fb, q.last_by = 100, 50, 0, 0, DIFF["gr"], DIFF["fb"], -1
        q.state, q.msg, q.splats, q.sp_t, q.ph, q.mt, q.rv = "wait", ("", 0), [], -1.0, 0.0, 0.0, 0.0; PL.append(q)
    new_floor()

def next_floor():
    P.floor += 1
    for q in PL:                                                              # bonus pindah lokasi untuk semua pemain
        q.hp = min(100, q.hp + 30); q.armor = min(100, q.armor + 25)
        for w in q.weap: w["mags"] = min(9, w["mags"] + 1)
    new_floor()

def sync_partner(sx, sy):                      # split screen: pemain ke-2 muncul di samping pemain 1 dengan kondisi awal yang sama
    p1, p2 = PL[0], PL[1]
    for f in ("a", "cd", "rl", "flash", "kick", "hurt", "ahit", "bob", "dtimer", "z", "vz", "scope", "swap", "pitch", "off", "shake", "blind", "tcd", "roll", "zk", "run", "step", "inv"): setattr(p2, f, getattr(p1, f))
    p2.x, p2.y = (sx + .7, sy) if free(sx + .7, sy) else (sx, sy); p2.state, p2.splats, p2.sp_t, p2.msg, p2.rv, p2.ph, p2.mt = "wait", [], -1.0, p1.msg, 0.0, 0.0, 0.0

def new_floor():
    global MAP, DIST, MM, enemies, items, projs, cps, parts, decals, nades, blasts
    arena = P.floor == DIFF["floors"]                             # stage terakhir = ruang bos
    stage = "MANSION" if arena else DIFF["stages"][P.floor]; set_theme(stage); P.stage = "RUANG BOS" if arena else stage
    MAP = build_arena() if arena else build_stage(stage); sx, sy = (4.5, 19.5) if arena else (3.5, 3.5)
    DIST = bfs((int(sx), int(sy))); P.x, P.y = sx, sy; P.a = 0.0 if arena else .6
    P.cd = P.rl = P.flash = P.kick = P.hurt = P.ahit = P.bob = P.dtimer = 0.0; P.z = P.vz = P.scope = P.swap = P.pitch = P.off = P.shake = P.blind = P.tcd = P.roll = 0.0; P.zk = 1.0; P.run = False; P.step = 0.0; P.inv = 2.0
    P.state = "play"; P.wave = False; projs = []; parts, decals, nades, blasts = [], [], [], []; P.splats = []; P.sp_t = -1.0
    cells = [(x, y) for y in range(N) for x in range(N) if DIST[y, x] < 9999]; random.shuffle(cells)
    if arena:
        boss = Enemy("boss", 34.5, 19.5); boss.awake = True; enemies = [boss]
        for x, y in [c for c in cells if c[0] > 24 and abs(c[0] - 34) + abs(c[1] - 19) > 3][:DIFF["guards"]]:
            e = Enemy(random.choice(("preman", "penjahat", "agen")), x + .5, y + .5); e.awake = True; enemies.append(e)
        items = [[x + .5, y + .5, random.choice(["health", "armor", "ammo", "ammo", "granat", "flash"])] for x, y in [c for c in cells if 3 < c[0] < 22][:12]]
        cps = [[16.5, 19.5, False]]; P.msg = ("RUANG BOS  -  DON VARGO", 3)
    else:
        far = [c for c in cells if DIST[c[1], c[0]] > 11]; kinds = [k for k in TYPES if k != "boss"]
        enemies = [Enemy(random.choices(kinds, DIFF["mix"])[0], x + .5, y + .5) for x, y in far[:DIFF["n"] + DIFF["add"] * P.floor]]
        items = [[x + .5, y + .5, random.choice(["health", "armor", "ammo", "ammo", "granat", "flash"])] for x, y in cells[:DIFF["items"]]]
        cps = []; far_d = DIST[DIST < 9999].max()
        for fr in (.3, .55, .8):                                  # 3 checkpoint di sepanjang lantai
            cand = [c for c in cells if abs(DIST[c[1], c[0]] - far_d * fr) < 3]
            if cand: x, y = random.choice(cand); cps.append([x + .5, y + .5, False])
        P.msg = (f"{stage}   ({P.floor + 1}/{DIFF['floors']})", 3)
    if CO(): sync_partner(sx, sy)
    save_cp(sx, sy)
    MM = pg.Surface((N * 3, N * 3)); MM.fill((10, 8, 8))
    for y in range(N):
        for x in range(N):
            if MAP[y, x]: D.rect(MM, (110, 90, 80), (x * 3, y * 3, 3, 3))

def respawn():                                                    # lanjut dari checkpoint terakhir (semua pemain)
    c = P.cp
    for i, q in enumerate(PL):
        sn = c["snaps"][i] if i < len(c.get("snaps", ())) else snap_pl(q); px, py = c["x"], c["y"]
        if i and free(px + .7, py): px += .7
        q.x, q.y, q.a = px, py, c["a"]; q.hp = max(sn["hp"], 60); q.armor = sn["armor"]; q.weap = [dict(w) for w in sn["weap"]]; q.cur = sn["cur"]
        q.cd = q.rl = q.hurt = q.ahit = 0.0; q.z = q.vz = q.scope = q.swap = q.pitch = q.blind = q.shake = 0.0; q.inv = 3.0; q.state = "play"; q.rv = 0.0
    P.conts -= 1; P.used += 1; projs.clear()
    for e in enemies: e.awake = P.floor == DIFF["floors"]

def add_decal(x, y, r):                       # bercak darah di lantai (maks. 160 terakhir)
    if not MAP[int(y), int(x)]: decals.append([x, y, r])
    if len(decals) > 160: del decals[0]

def bleed(x, y, h, nd, nf=0, big=False):      # percikan darah dari titik yang kena tembak
    a0 = math.atan2(y - P.y, x - P.x)
    for _ in range(nd):
        a = a0 + random.gauss(0, .7); v = random.uniform(.6, 3.4 if big else 2.4)
        parts.append([x, y, h + random.uniform(-.1, .1), math.cos(a) * v, math.sin(a) * v, random.uniform(-.3, 2.4), random.uniform(.03, .08 if big else .06)])
    for _ in range(nf): add_decal(x + random.gauss(0, .25), y + random.gauss(0, .25), random.uniform(.06, .34 if big else .2))
    if len(parts) > 220: del parts[:60]

def player_splats(d):                         # darah muncrat di layar saat pemain terkena tembakan
    for _ in range(min(10, 3 + int(d / 5))):
        vw = 480 if CO() else W * SC; x = random.choice((random.uniform(0, .25), random.uniform(.75, 1))) * vw if random.random() < .7 else random.uniform(.2, .8) * vw
        life = random.uniform(1.0, 1.8); P.splats.append([x, random.uniform(.05, .9) * H * SC, random.uniform(14, 38), life, life, random.uniform(30, 90)])
    del P.splats[:-30]

def hurt(d, by=None):
    if P.inv > 0: return
    P.last_by = by if by is not None else -1
    a = min(P.armor, d); P.armor -= a; d -= a                                  # armor menyerap damage lebih dulu; sisanya baru mengurangi health
    if d <= 0: P.ahit = .35; play("clink")                                      # tertahan armor: layar sedikit biru keabu-abuan, health aman
    else: P.hp -= d; P.hurt = .35; play(random.choice(("hurt", "hurt2"))); player_splats(d)
    if P.hp <= 0:
        P.hp = 0
        if P.mode == "mp": mp_die()
        elif CO(): P.state = "down"; P.rv = 0.0; P.msg = ("KAMU TERJATUH!  Teman mendekat untuk membantumu berdiri", 4)
        else: P.state = "dead" if P.conts > 0 else "over"

class Enemy:
    def __init__(s, k, x, y):
        s.k, s.x, s.y = k, x, y; fl = 0 if k == "boss" else P.floor; s.hp = s.maxhp = TYPES[k]["hp"] * DIFF["hp"] * (1 + .07 * fl); s.armor = s.maxarmor = 450 * DIFF["hp"] if k == "boss" else 0.0
        s.dm = DIFF["dmg"] * (1 + .05 * fl); s.awake, s.cd, s.flash = False, random.uniform(.4, 1.4), 0
        s.wp, s.wt, s.n, s.sd, s.sdt = "rifle", 0.0, 0, 1, 0.0; s.stun = s.ph = s.mt = 0.0; s.fa = random.uniform(0, 6.28)
    def hit(s, d, h=.6):
        s.flash = .12; s.awake = True; dd = math.hypot(s.x - P.x, s.y - P.y)
        if s.armor > 0:                                                    # armor bos menyerap 70% damage sampai hancur
            a = min(s.armor, d * .7); s.armor -= a; d -= a; play("clink", dd)
            if s.armor <= 0: say("ARMOR BOS HANCUR!", 2.5)
        s.hp -= d
        bleed(s.x, s.y, h, min(18, 6 + int(d / 3)), 2)                       # semprotan darah + bercak di lantai
        if P.time - P.sp_t > .05: play("splat", dd); P.sp_t = P.time
        if s.hp <= 0: P.kills += 1; bleed(s.x, s.y, .5, 26, 8, True); play("thud", dd); hitmark(True)
    def fire(s, spread, dmg, snd_, n=1, cone=0.0):               # tembakan musuh (n > 1 = shotgun menyebar)
        a0 = s.fa = math.atan2(P.y - s.y, P.x - s.x)
        for _ in range(n):
            a = a0 + random.gauss(0, spread) + (random.uniform(-cone, cone) if n > 1 else 0)
            projs.append([s.x, s.y, math.cos(a) * 14, math.sin(a) * 14, dmg * s.dm])
        play(snd_, math.hypot(P.x - s.x, P.y - s.y))
    def walk(s, dx, dy, sp, dt):                                 # gerak + geser di dinding
        n = math.hypot(dx, dy) or 1; mx, my = dx / n * sp * dt, dy / n * sp * dt; s.fa = math.atan2(dy, dx); s.mt = .2
        if free(s.x + mx, s.y, .3): s.x += mx
        if free(s.x, s.y + my, .3): s.y += my
        s.ph += math.hypot(mx, my)
    def boss_ai(s, dt, d, seen):          # bos: jauh = rifle / shotgun, dekat = pistol / pisau
        s.wt -= dt; s.sdt -= dt
        if s.sdt <= 0: s.sd = random.choice((-1, 1)); s.sdt = random.uniform(1.2, 2.5)
        if s.wt <= 0 or (s.wp in ("rifle", "shotgun") and d < 2.5) or (s.wp in ("pisau", "pistol") and d > 9):
            s.wt = random.uniform(3, 5); s.wp = random.choice(("pisau", "pistol")) if d < 6 else random.choice(("rifle", "shotgun"))
        ax, ay = P.x - s.x, P.y - s.y; sp = TYPES["boss"]["spd"] * DIFF["spd"]; qx, qy = -ay, ax
        if not seen:
            cx, cy = int(s.x), int(s.y)
            nx, ny = min(((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)), key=lambda q: DIST[q[1], q[0]])
            return s.walk(nx + .5 - s.x, ny + .5 - s.y, sp, dt)
        if s.wp == "pisau":                                      # serbu & tebas dengan pisau
            s.walk(ax, ay, sp * 1.5, dt)
            if d < 1.2 and s.cd <= 0 and P.z < .25: hurt(22 * s.dm); play("slash"); s.cd = .8 * DIFF["cd"]
        elif s.wp == "pistol":                                   # pistol cepat sambil bergeser
            k = 1 if d > 3.5 else -.4; s.walk(ax * k + qx * s.sd * .8, ay * k + qy * s.sd * .8, sp, dt)
            if s.cd <= 0: s.fire(DIFF["spr"], 9, "pistol"); s.cd = .45 * DIFF["cd"]
        elif s.wp == "rifle":                                    # rifle jarak jauh, tembakan beruntun
            k = 1 if d > 12 else -1 if d < 7 else 0; s.walk(ax * k + qx * s.sd, ay * k + qy * s.sd, sp, dt)
            if s.cd <= 0: s.n += 1; s.fire(DIFF["spr"] * .8, 7, "rifle"); s.cd = (1.1 if s.n % 4 == 0 else .16) * DIFF["cd"]
        else:                                                    # shotgun menyebar
            k = 1 if d > 9 else -1 if d < 5 else 0; s.walk(ax * k + qx * s.sd, ay * k + qy * s.sd, sp, dt)
            if s.cd <= 0: s.fire(.03, 5, "shotgun", 7, .2); s.cd = 1.6 * DIFF["cd"]
    def update(s, dt):
        if s.hp <= 0: return
        s.mt = max(0.0, s.mt - dt)
        if s.stun > 0: s.stun -= dt; return                    # terkena flashbang: diam tak berdaya
        c = TYPES[s.k]; d = math.hypot(P.x - s.x, P.y - s.y)
        seen = d < DIFF["sight"] and los(s.x, s.y, P.x, P.y)
        if seen and not s.awake: s.awake = True
        if not s.awake: return
        s.cd -= dt; s.flash -= dt
        if s.k == "boss": return s.boss_ai(dt, d, seen)
        if c["rng"] and seen and d < c["rng"]:                  # penjahat & agen menembak
            s.fa = math.atan2(P.y - s.y, P.x - s.x)
            if s.cd <= 0:
                a = math.atan2(P.y - s.y, P.x - s.x) + random.gauss(0, DIFF["spr"]); projs.append([s.x, s.y, math.cos(a) * 14, math.sin(a) * 14, c["dmg"] * s.dm])
                s.cd = c["cd"] * DIFF["cd"]; play(c["snd"], d)
            if d < 4.5: return
        elif d < .85:                                           # cakar jarak dekat
            s.fa = math.atan2(P.y - s.y, P.x - s.x)
            if s.cd <= 0: hurt(c["dmg"] * s.dm); s.cd = DIFF["cd"]
            return
        if seen: tx, ty = P.x, P.y
        else:                                                   # ikuti peta jarak (pathfinding)
            cx, cy = int(s.x), int(s.y)
            nx, ny = min(((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)), key=lambda q: DIST[q[1], q[0]])
            tx, ty = nx + .5, ny + .5
        a = s.fa = math.atan2(ty - s.y, tx - s.x); s.mt = .2; mx, my = math.cos(a) * c["spd"] * DIFF["spd"] * dt, math.sin(a) * c["spd"] * DIFF["spd"] * dt
        for o in enemies:                                       # jangan menumpuk
            ox, oy = s.x - o.x, s.y - o.y
            if o is not s and o.hp > 0 and abs(ox) < .6 and abs(oy) < .6: mx += ox * dt * 1.2; my += oy * dt * 1.2
        if free(s.x + mx, s.y, .22): s.x += mx
        if free(s.x, s.y + my, .22): s.y += my
        s.ph += math.hypot(mx, my)

def shoot_ray(ang, dmg, vs=0.0):
    dx, dy = math.cos(ang), math.sin(ang); d = 0.0
    while d < 30:
        d += .05
        if MAP[int(P.y + dy * d), int(P.x + dx * d)]: break
    best, bd = None, d; slope = P.off / (H * P.zk) + vs                   # kemiringan bidikan vertikal
    for e in targets():
        rx, ry = e.x - P.x, e.y - P.y; f = rx * dx + ry * dy
        if e.hp > 0 and 0 < f < bd and -.05 <= .5 + EYE + P.z + slope * f <= 1.05 and abs(rx * dy - ry * dx) < (.5 if e.k == "boss" else .35): best, bd = e, f
    if best: hitmark(); best.hit(dmg, max(.15, min(.9, .5 + EYE + P.z + slope * bd)))

def start_reload():
    w = P.weap[P.cur]
    if P.rl <= 0 and w["mags"] > 0 and w["ammo"] < w["mag"]: P.rl = w["rl"]; play(w["rsnd"])

def throw(kind):                              # G = granat, F = flashbang
    if P.tcd > 0 or (P.gr if kind == "granat" else P.fb) <= 0: return
    if kind == "granat": P.gr -= 1
    else: P.fb -= 1
    P.tcd = .7; P.swap = .3; play("throw"); c_, s_ = math.cos(P.a), math.sin(P.a); sx, sy = P.x + c_ * .4, P.y + s_ * .4
    if MAP[int(sy), int(sx)]: sx, sy = P.x, P.y
    nd = [sx, sy, .45 + EYE + P.z, c_ * 7.5, s_ * 7.5, 2.2 + P.pitch * 5, 2.0 if kind == "granat" else 1.6, kind]
    nades.append(nd + [NET.id if P.mode == "mp" else -1] + ([pidx()] if CO() else []))
    if P.mode == "mp": NET.send({"t": "nade", "n": [v if isinstance(v, str) else round(float(v), 3) for v in nd]})

def explode(n):
    x, y, kind = n[0], n[1], n[7]; own = n[9] if len(n) > 9 and n[9] < len(PL) else 0; d = math.hypot(P.x - x, P.y - y)
    if kind == "granat":                                                   # granat: ledakan, damage area
        play("boom", d); blasts.append([x, y, 0.0, .6, "boom"])
        with as_pl(own):                                                   # kill dicatat untuk pelempar
            for e in enemies:
                ed = math.hypot(e.x - x, e.y - y)
                if e.hp > 0 and ed < 4.5 and los(x, y, e.x, e.y): e.hit(170 * (1 - ed / 4.5) + 20, .5)
        if P.mode == "mp" and NET.host:
            for b in list(BOTS.values()):
                r_ = RPS[b.id]; bd = math.hypot(r_.x - x, r_.y - y)
                if b.al and bd < 4.5 and los(x, y, r_.x, r_.y) and not friendly(n[8], b.id): bot_hit(b.id, 170 * (1 - bd / 4.5) + 20, n[8])
        for i, q in enumerate(PL):                                         # semua pemain di sekitar ledakan ikut terkena
            if q.state not in ("play", "pause"): continue
            with as_pl(i):
                dd = math.hypot(P.x - x, P.y - y); P.shake = max(P.shake, 1.4 / (1 + dd * .4))
                if dd < 4.5 and los(x, y, P.x, P.y) and not friendly(n[8], NET.id): hurt(70 * (1 - dd / 4.5) + 8, n[8])
    else:                                                                  # flashbang: membutakan musuh & pemain
        play("flashbang", d); blasts.append([x, y, 0.0, .35, "flashfx"])
        for e in enemies:
            ed = math.hypot(e.x - x, e.y - y)
            if e.hp > 0 and ed < 10 and los(x, y, e.x, e.y): e.stun = max(e.stun, 1.5 if e.k == "boss" else 4.5 * (1 - ed / 14)); e.awake = True
        if P.mode == "mp" and NET.host:
            for b in BOTS.values():
                r_ = RPS[b.id]
                if b.al and math.hypot(r_.x - x, r_.y - y) < 10 and los(x, y, r_.x, r_.y) and not friendly(n[8], b.id): b.stun = max(b.stun, 3.0)
        for i, q in enumerate(PL):
            if q.state not in ("play", "pause"): continue
            with as_pl(i):
                dd = math.hypot(P.x - x, P.y - y)
                if dd < 13 and los(x, y, P.x, P.y) and not friendly(n[8], NET.id):
                    face = (math.cos(P.a) * (x - P.x) + math.sin(P.a) * (y - P.y)) / max(dd, .1) > .1
                    P.blind = max(P.blind, (3.2 if face else 1.2) * (1 - dd / 13) + .4)

def pad_of(slot):                              # controller milik pemain (slot 0 = P1, slot 1 = P2); None = tidak ada
    n = len(PADS)
    if CO():
        if CFG["input"] == "pad": return PADS[slot] if slot < n else None             # keduanya controller
        if n >= 2 and CFG["input"] == "auto": return PADS[slot]                       # P1 boleh keyboard + controller 1, P2 controller 2
        return PADS[0] if (slot == 1 and n) else None                                 # P1 keyboard+mouse, P2 controller
    return PADS[0] if (slot == 0 and n and CFG["input"] != "kbm") else None

def gather_input(slot, rel=(0, 0), click_ev=False):      # satukan keyboard / mouse / controller menjadi satu bentuk input per frame
    I = NS(fw=0.0, st=0.0, mx=0, my=0, rx=0.0, ry=0.0, kturn=0.0, kpitch=0.0, run=False, fire=False, fire_ev=False, aim=False, jump=False)
    if slot == 0 and kb_on():
        k = pg.key.get_pressed(); K = CFG["keys"]; b = pg.mouse.get_pressed()
        I.fw, I.st = k[K["maju"]] - k[K["mundur"]], k[K["kanan"]] - k[K["kiri"]]; I.mx, I.my = rel
        I.kturn = (k[pg.K_RIGHT] or k[pg.K_e]) - (k[pg.K_LEFT] or k[pg.K_q]); I.kpitch = k[pg.K_UP] - k[pg.K_DOWN]
        I.run = bool(k[K["lari"]] or (K["lari"] == pg.K_LSHIFT and k[pg.K_RSHIFT])); I.fire, I.fire_ev, I.aim, I.jump = bool(b[0]), bool(click_ev), bool(b[2]), bool(k[K["lompat"]])
    pad = pad_of(slot)
    if pad:
        lx, ly = stick(pad.ax["lx"], pad.ax["ly"]); rx, ry = stick(pad.ax["rx"], pad.ax["ry"], .15)
        I.st = max(-1.0, min(1.0, I.st + lx)); I.fw = max(-1.0, min(1.0, I.fw - ly)); I.rx, I.ry = rx, ry
        I.run = I.run or pad.sprint; I.fire = I.fire or pad.ax["rt"] > .45; I.fire_ev = I.fire_ev or pad.trig_down("rt", .45); I.aim = I.aim or pad.ax["lt"] > .4; I.jump = I.jump or pad.bt["a"]
    return I

def pad_actions(slot):                         # tombol aksi sekali-tekan milik controller (untuk pemain P yang sedang aktif)
    pad = pad_of(slot)
    if not pad: return
    if pad.pressed("x"): start_reload()
    if pad.pressed("rb"): throw("granat")
    if pad.pressed("lb"): throw("flash")
    if pad.pressed("y") or pad.pressed("dr"): switch_weapon((P.cur + 1) % 3)
    if pad.pressed("dl"): switch_weapon((P.cur - 1) % 3)

def update_player(dt, I):                      # bagian yang khusus satu pemain: bidik, jalan, tembak, ambil item
    sc = 1 - .6 * P.scope
    P.a += I.mx * .0028 * CFG["sens"] / 5 * sc + I.kturn * 2.2 * dt + I.rx * 3.3 * CFG["psens"] / 5 * sc * dt
    P.pitch = max(-.85, min(.85, P.pitch - I.my * .0028 * CFG["sens"] / 5 * sc + I.kpitch * 1.4 * dt - I.ry * 2.0 * CFG["psens"] / 5 * sc * dt))
    dx, dy = math.cos(P.a), math.sin(P.a); vx, vy = dx * I.fw - dy * I.st, dy * I.fw + dx * I.st; n = math.hypot(vx, vy)
    if n:
        run = I.run; P.run = run                                                   # SHIFT / klik stik kiri = lari
        sp = (6.5 if run else 3.6) * (1 - .45 * P.scope) * dt * min(1.0, n) / n; P.bob += dt * (14 if run else 9)
        P.step -= dt; P.mt = .25; P.ph += math.hypot(vx * sp, vy * sp)
        if P.step <= 0 and P.z <= 0: play("step", 14); P.step = .27 if run else .45
        if free(P.x + vx * sp, P.y, .28): P.x += vx * sp
        if free(P.x, P.y + vy * sp, .28): P.y += vy * sp
    else: P.run = False
    P.mt = max(0.0, P.mt - dt)
    P.cd -= dt; P.flash -= dt; P.hitm = max(0.0, getattr(P, "hitm", 0.0) - dt); P.hurt = max(0, P.hurt - dt); P.ahit = max(0.0, P.ahit - dt); P.kick = max(0, P.kick - dt * 160); P.inv -= dt; P.swap = max(0.0, P.swap - dt)
    P.roll *= max(0.0, 1 - 9 * dt); P.shake = max(0.0, P.shake - dt * 2); P.blind = max(0.0, P.blind - dt); P.tcd -= dt
    for q in P.splats: q[3] -= dt
    P.splats = [q for q in P.splats if q[3] > 0]
    tgt = 1.0 if (I.aim and P.rl <= 0) else 0.0                                   # tahan klik kanan / LT = scope
    P.scope += (tgt - P.scope) * min(1.0, dt * 14); P.scope = 0.0 if P.scope < .01 else 1.0 if P.scope > .99 else P.scope
    if I.jump and P.z <= 0: P.vz = 2.4; play("step", 6)                           # SPACE / tombol A = lompat
    if P.z > 0 or P.vz > 0:
        P.vz -= 9 * dt; P.z = max(0.0, P.z + P.vz * dt)
        if P.z == 0: P.vz = 0.0; play("step", 8)
    P.msg = (P.msg[0], P.msg[1] - dt)
    if P.rl > 0:
        P.rl -= dt
        if P.rl <= 0: w = P.weap[P.cur]; w["mags"] -= 1; w["ammo"] = w["mag"]
    w = P.weap[P.cur]
    if (I.fire if w["auto"] else I.fire_ev) and P.cd <= 0 and P.rl <= 0 and P.swap <= 0:
        if w["ammo"] > 0:
            w["ammo"] -= 1; P.cd = w["delay"]; P.flash = .07; P.kick = 28 if w["pel"] == 1 else 60; play(w["snd"])
            if P.mode == "mp": NET.send({"t": "shot", "w": P.cur})
            for _ in range(w["pel"]): shoot_ray(P.a + random.gauss(0, w["spr"] * (1 - .7 * P.scope)), w["dmg"], random.gauss(0, w["spr"] * (1 - .7 * P.scope)))
            for e in enemies:                                    # suara tembakan memancing musuh
                if e.hp > 0 and math.hypot(e.x - P.x, e.y - P.y) < w.get("alert", 10): e.awake = True
        else: P.cd = .3; play("empty"); start_reload()
    for it in items[:]:
        if math.hypot(it[0] - P.x, it[1] - P.y) < .7:
            if it[2] == "health" and P.hp < 100: P.hp = min(100, P.hp + 30); m = "+30 HEALTH"
            elif it[2] == "armor" and P.armor < 100: P.armor = min(100, P.armor + 30); m = "+30 ARMOR"
            elif it[2] == "granat" and P.gr < 6: P.gr += 1; m = "+1 GRANAT"
            elif it[2] == "flash" and P.fb < 6: P.fb += 1; m = "+1 FLASHBANG"
            elif it[2] == "ammo":
                for q in P.weap: q["mags"] = min(9, q["mags"] + 1)
                m = "+1 MAGAZINE (SEMUA SENJATA)"
            else: continue
            items.remove(it); play("pickup"); P.msg = (m, 2)
            if P.mode == "mp": P.itemq.append([it, 20.0])
    for c in cps:
        if not c[2] and math.hypot(c[0] - P.x, c[1] - P.y) < .9:
            c[2] = True; P.hp = min(100, P.hp + 20); play("pickup"); P.msg = ("CHECKPOINT TERSIMPAN  (+20 HEALTH)", 2.5)
            for j, q in enumerate(PL):                               # split screen: teman ikut dipulihkan / dibangunkan
                if q is P: continue
                if q.state == "down": revive(q)
                elif q.state == "play": q.hp = min(100, q.hp + 20); q.msg = ("CHECKPOINT TERSIMPAN  (+20 HEALTH)", 2.5)
            save_cp(c[0], c[1])

def revive(q, hp=50):                          # pemain yang terjatuh dibangunkan teman / checkpoint
    q.hp, q.state, q.inv, q.rv, q.hurt = hp, "play", 2.5, 0.0, 0.0; q.msg = ("KAMU BERDIRI LAGI!", 2.5); q.splats = []

def idle_player(dt):                           # pemain terjatuh: hanya efek layar yang berjalan
    P.hitm = max(0.0, getattr(P, "hitm", 0.0) - dt); P.hurt = max(0, P.hurt - dt); P.ahit = max(0.0, P.ahit - dt); P.flash -= dt; P.blind = max(0.0, P.blind - dt); P.shake = max(0.0, P.shake - dt * 2); P.mt = 0.0; P.scope = 0.0
    for q in P.splats: q[3] -= dt
    P.splats = [q for q in P.splats if q[3] > 0]; P.msg = (P.msg[0], P.msg[1] - dt)

DISTS, DTM = {}, [0.0]
def enemy_step(dt):                            # musuh mengejar pemain terdekat yang masih hidup
    global DIST
    if not CO():
        for e in enemies: e.update(dt)
        return
    alive = [i for i, q in enumerate(PL) if q.state == "play"]
    if not alive: return
    DTM[0] -= dt
    if DTM[0] <= 0 or any(i not in DISTS for i in alive): DTM[0] = .4; DISTS.clear(); DISTS.update({i: bfs((int(PL[i].x), int(PL[i].y))) for i in alive})
    for e in enemies:
        i = min(alive, key=lambda j: (PL[j].x - e.x) ** 2 + (PL[j].y - e.y) ** 2); DIST = DISTS[i]
        with as_pl(i): e.update(dt)

def update_world(dt):                          # bagian dunia (sekali per frame): granat, partikel, musuh, peluru musuh, bos
    global DIST
    P.time += dt
    for n in nades[:]:                                                          # fisika granat / flashbang: melengkung, memantul
        n[6] -= dt; n[5] -= 9 * dt; nx, ny = n[0] + n[3] * dt, n[1] + n[4] * dt; n[2] += n[5] * dt
        if MAP[int(n[1]), int(nx)]: n[3] *= -.4; nx = n[0]; play("clink", math.hypot(nx - P.x, n[1] - P.y))
        if MAP[int(ny), int(nx)]: n[4] *= -.4; ny = n[1]
        n[0], n[1] = nx, ny
        if n[2] > .98: n[2] = .98; n[5] = -abs(n[5]) * .3
        if n[2] <= .04: n[2] = .04; n[5] = -n[5] * .4 if n[5] < -1.2 else 0.0; n[3] *= .75; n[4] *= .75
        if n[2] <= .05: n[3] *= 1 - 3 * dt; n[4] *= 1 - 3 * dt
        if n[6] <= 0: nades.remove(n); explode(n)
    for f in blasts[:]:
        f[2] += dt
        if f[2] > f[3]: blasts.remove(f)
    for p in parts[:]:                                                          # partikel darah jatuh dengan gravitasi
        p[0] += p[3] * dt; p[1] += p[4] * dt; p[2] += p[5] * dt; p[5] -= 9 * dt
        if MAP[int(p[1]), int(p[0])]: parts.remove(p)
        elif p[2] <= 0:
            parts.remove(p)
            if random.random() < .5: add_decal(p[0], p[1], random.uniform(.03, .09))
    if not CO():
        P.dtimer = getattr(P, "dtimer", 0) - dt
        if P.dtimer <= 0: DIST = bfs((int(P.x), int(P.y))); P.dtimer = .4
    enemy_step(dt)
    for p in projs[:]:
        p[0] += p[2] * dt; p[1] += p[3] * dt
        if MAP[int(p[1]), int(p[0])]: projs.remove(p); continue
        for i, q in enumerate(PL):
            if q.state in ("play", "pause") and math.hypot(p[0] - q.x, p[1] - q.y) < .45 and q.z < .12:
                with as_pl(i): hurt(p[4])
                projs.remove(p); break
    boss = next((e for e in enemies if e.k == "boss"), None)
    if boss and boss.hp <= 0: begin_cutscene("outro")                  # boss tumbang = game tamat
    elif not boss and P.mode == "campaign" and not any(e.hp > 0 for e in enemies):
        for q in PL: q.state = "clear"
    if boss and boss.hp > 0 and not P.wave and boss.hp < boss.maxhp * .5:      # fase 2: pasukan bantuan
        P.wave = True; say("PASUKAN BANTUAN DATANG!", 3)
        spots = [(x + .5, y + .5) for y in range(9, 31) for x in range(26, 37) if MAP[y, x] == 0]; random.shuffle(spots)
        for x, y in spots[:DIFF["guards"] // 2 + 2]:
            e = Enemy(random.choice(("penjahat", "agen", "agen")), x, y); e.awake = True; enemies.append(e)

def update(dt, I):                             # satu pemain (solo / multiplayer): bagian pemain + dunia
    update_player(dt, I); update_world(dt)

def co_step(dt, rel, click_ev):                # satu frame split screen: tiap pemain diproses sendiri, dunia sekali
    p1, p2 = PL
    if p2.state == "wait" and p1.state == "play": p2.state = "play"; p2.inv = 2.0
    if P.paused or p1.state in ("cut", "ending"): return
    for i in range(2):
        with as_pl(i):
            if i == 1 and pad_of(1) is None: P.msg = ("Controller P2 tidak terhubung", .6)
            if P.state == "play":
                I = gather_input(i, rel if i == 0 else (0, 0), click_ev if i == 0 else False)
                pad_actions(i)
                update_player(dt, I)
            elif P.state == "down": idle_player(dt)
    for i, q in enumerate(PL):                                                  # teman berdiri didekat = membantu bangun
        if q.state == "down":
            o = PL[1 - i]
            if o.state == "play" and math.hypot(o.x - q.x, o.y - q.y) < 1.6:
                q.rv += dt
                if q.rv >= 2.5: revive(q)
            else: q.rv = max(0.0, q.rv - dt * 2)
    if any(q.state == "play" for q in PL): update_world(dt)
    if all(q.state == "down" for q in PL):                                      # keduanya jatuh = misi gagal
        st = "dead" if P.conts > 0 else "over"
        for q in PL: q.state = st

# ================= RENDER =================
def make_view(w):                              # larik kamera + vinyet + kanvas untuk lebar render w
    gy, gx = np.mgrid[0:H, 0:w]
    return (2 * np.arange(w) / w - 1, np.clip(1.15 - .55 * (((gx - w / 2) / (w / 2)) ** 2 + ((gy - H / 2) / (H / 2)) ** 2), .3, 1).T[..., None].astype(np.float32), None)
CAMX, VIG, _ = make_view(W); VIEWS = {W: (CAMX, VIG, canvas)}; DISP = screen
def set_view(i=None):                          # i=None: layar penuh; i=0 / 1: separuh kiri / kanan (split screen)
    global screen, W, CAMX, VIG, canvas
    w = 320 if i is None else 160
    if w not in VIEWS: c_, v_, _ = make_view(w); VIEWS[w] = (c_, v_, pg.Surface((w, H)))
    W = w; CAMX, VIG, canvas = VIEWS[w]
    screen = DISP if i is None else DISP.subsurface(pg.Rect(i * 480, 0, 480, 600))
GRADE = np.array([1.08, .94, .9], np.float32)

def draw_dot(frame, zb, x, y, h, r, col, flat=False):      # bercak/titik kecil di dunia 3D (r = jari-jari, satuan dunia)
    rx, ry = x - P.x, y - P.y; inv = 1 / (P.plx * P.dy - P.dx * P.ply); ty = inv * (-P.ply * rx + P.plx * ry)
    if ty < .25 or ty > 18: return
    sx = int(W / 2 * (1 + inv * (P.dy * rx - P.dx * ry) / ty)); sy = P.hor + int((.5 + EYE + P.z - h) * H / ty * P.zk)
    pw = max(1, int(r * H / ty * P.zk)); ph = max(1, pw // 3) if flat else pw
    x0, x1, y0, y1 = max(sx - pw, 0), min(sx + pw + 1, W), max(sy - ph, 0), min(sy + ph + 1, H)
    if x0 >= x1 or y0 >= y1: return
    m = (((np.arange(x0, x1) - sx) / pw) ** 2)[:, None] + (((np.arange(y0, y1) - sy) / ph) ** 2)[None, :] <= 1
    m &= (zb[x0:x1] > ty)[:, None]
    frame[x0:x1, y0:y1] = np.where(m[..., None], np.array(col, np.float32) * max(.3, min(1, 1.2 - ty / (FOGD * 1.1))) * LIGHT, frame[x0:x1, y0:y1])

def draw_sprite(frame, zb, x, y, tex, scale=1.0, low=1.0, glow=False, hit=False):
    rx, ry = x - P.x, y - P.y; inv = 1 / (P.plx * P.dy - P.dx * P.ply)
    ty = inv * (-P.ply * rx + P.plx * ry)
    if ty < .2 or ty > 30: return
    sx = int(W / 2 * (1 + inv * (P.dy * rx - P.dx * ry) / ty)); size = int(H / ty * P.zk); sw = int(size * scale)
    if sw < 2: return
    cy = P.hor + int(size * ((1 - scale) / 2 * low + EYE + P.z)); x0, y0 = sx - sw // 2, cy - sw // 2
    c0, c1, r0, r1 = max(x0, 0), min(x0 + sw, W), max(y0, 0), min(y0 + sw, H)
    if c0 >= c1 or r0 >= r1: return
    cols, rows = np.arange(c0, c1), np.arange(r0, r1)
    u, v = ((cols - x0) * 64 // sw).clip(0, 63), ((rows - y0) * 64 // sw).clip(0, 63)
    px = tex[v[None, :], u[:, None]]
    m = (px[..., 3] > 128) & (zb[cols] > ty)[:, None]
    b = 1.0 if glow else max(.12, min(1, 1.25 - ty / FOGD)) * LIGHT
    rgb = px[..., :3] * .5 + np.array((150, 8, 8), np.float32) if hit else px[..., :3]
    frame[c0:c1, r0:r1][m] = (rgb * b)[m]

def render():
    P.dx, P.dy = math.cos(P.a), math.sin(P.a); fov = .66 + (P.weap[P.cur]["zoom"] - .66) * P.scope; zk = P.zk = .66 / fov; fov *= W / 320; P.plx, P.ply = -P.dy * fov, P.dx * fov      # view sempit (split screen) = sudut pandang horizontal lebih kecil, skala piksel tetap
    rdx, rdy = P.dx + P.plx * CAMX, P.dy + P.ply * CAMX
    eh = 1 + 2 * (EYE + P.z)                                              # tinggi mata (naik saat lompat)
    off = int(max(-190, min(190, math.tan(P.pitch) * H * zk))) + int(random.uniform(-1, 1) * P.shake * 14); hor = P.hor = H // 2 + off; P.off = off   # cakrawala bergeser saat menengok atas/bawah
    nc = max(0, min(H, hor)); ic = hor - 1 - np.arange(nc); ifl = np.arange(nc, H) - hor
    fr = .5 * H / (ifl + .5) * eh / zk; cr = .5 * H / (ic + .5) * (2 * (WH - EYE - P.z)) / zk
    fx, fy = P.x + fr[None, :] * rdx[:, None], P.y + fr[None, :] * rdy[:, None]
    cx_, cy_ = (P.x + cr[None, :] * rdx[:, None]) * 64, (P.y + cr[None, :] * rdy[:, None]) * 64
    tx, ty = (fx * 64).astype(int) & 63, (fy * 64).astype(int) & 63
    fb = (np.clip(1.15 - fr / (FOGD * .85), .05, 1) * LIGHT)[None, :, None]; cb = (np.clip(1.15 - cr / (FOGD * .85), .05, 1) * LIGHT)[None, :, None]
    frame = np.empty((W, H, 3), np.float32)
    frame[:, nc:] = FLOOR[ty, tx] * fb
    if SKY is None: frame[:, :nc] = CEIL[cy_.astype(int) & 63, cx_.astype(int) & 63] * cb
    else: frame[:, :nc] = SKY[np.clip(np.arange(nc) * 63 // max(hor, 1), 0, 63)[None, :], ((np.arctan2(rdy, rdx) / (2 * math.pi)) % 1 * 512).astype(int)[:, None]] * (.85 + .15 * LIGHT)   # langit luar ruangan
    # --- DDA untuk semua kolom sekaligus ---
    mx, my = np.full(W, int(P.x)), np.full(W, int(P.y))
    ddx, ddy = np.abs(1 / np.where(rdx == 0, 1e-9, rdx)), np.abs(1 / np.where(rdy == 0, 1e-9, rdy))
    stx, sty = np.where(rdx < 0, -1, 1), np.where(rdy < 0, -1, 1)
    sdx = np.where(rdx < 0, (P.x - mx) * ddx, (mx + 1 - P.x) * ddx)
    sdy = np.where(rdy < 0, (P.y - my) * ddy, (my + 1 - P.y) * ddy)
    hit, side = np.zeros(W, bool), np.zeros(W, int)
    for _ in range(48):
        act = ~hit; xs = (sdx < sdy) & act; ys_ = ~(sdx < sdy) & act
        sdx = sdx + np.where(xs, ddx, 0); mx = mx + np.where(xs, stx, 0)
        sdy = sdy + np.where(ys_, ddy, 0); my = my + np.where(ys_, sty, 0)
        side = np.where(act, np.where(xs, 0, 1), side); hit = hit | (MAP[my, mx] > 0)
        if hit.all(): break
    perp = np.where(side == 0, sdx - ddx, sdy - ddy).clip(.05)
    wx = np.where(side == 0, P.y + perp * rdy, P.x + perp * rdx); wx -= np.floor(wx)
    texx = (wx * 64).astype(int).clip(0, 63); lineh = H / perp * zk; top = hor - lineh * (WH - .5 - EYE - P.z)
    tt = (np.arange(H)[None, :] - top[:, None]) / lineh[:, None]; inw = (tt >= 0) & (tt < WH)               # tt = jarak dari puncak dinding (satuan dunia)
    texy = (63 - np.floor(((WH - tt) % 1) * 64)).astype(int)                                             # tekstur diulang tiap 1 satuan, rata dari lantai
    wall = WALLS[(MAP[my, mx] - 1)[:, None], texy.clip(0, 63), texx[:, None]]
    wall *= (np.clip(1.25 - perp / FOGD, .06, 1) * np.where(side == 1, .72, 1) * LIGHT)[:, None, None]
    frame[inw] = wall[inw]
    # --- sprite (musuh, bola api, item) ---
    for dc in decals: draw_dot(frame, perp, dc[0], dc[1], .01, dc[2], (92, 6, 6), True)     # bercak darah di lantai
    sp = [(e.x, e.y, char_tex(e.k, e.k, TYPES[e.k]["c"], e.fa, e.x, e.y, e.ph, e.mt > 0, e.hp <= 0, e.armor > 0), 1.3 if e.k == "boss" else 1.0, 1.0, False, e.flash > 0) for e in enemies if (e.x - P.x) ** 2 + (e.y - P.y) ** 2 < 900]
    sp += [(p[0], p[1], TEX["fire"], .12, .5, True, False) for p in projs]
    sp += [(i[0], i[1], TEX[i[2]], .38, 1.0, False, False) for i in items]
    if P.mode == "mp": sp += [(r.x, r.y, rp_tex(r), 1.0, 1.0, False, r.flash > 0) for r in RPS.values() if (r.x - P.x) ** 2 + (r.y - P.y) ** 2 < 900]
    if CO(): sp += [(o.x, o.y, char_tex("co%d" % j, "agen", (PJ[j % 4], (20, 20, 26), (215, 170, 135)), o.a, o.x, o.y, o.ph, o.mt > 0, o.hp <= 0 or o.state == "down"), 1.0, 1.0, False, False) for j, o in enumerate(PL) if o is not P and o.state != "wait"]
    sp += [(c[0], c[1], TEX["cp1" if c[2] else "cp0"], .55, 1.0, True, False) for c in cps]
    sp += [(f[0], f[1], TEX[f[4]], max(.05, 2.2 * math.sin(math.pi * min(1, f[2] / f[3])) ** .6), .6, True, False) for f in blasts]
    sp.sort(key=lambda o: -((o[0] - P.x) ** 2 + (o[1] - P.y) ** 2))
    P.zb = perp
    for o in sp: draw_sprite(frame, perp, *o)
    for n in nades:
        draw_dot(frame, perp, n[0], n[1], n[2], .07, (70, 100, 55) if n[7] == "granat" else (205, 205, 210)); draw_dot(frame, perp, n[0], n[1], n[2] + .03, .03, (170, 190, 150))
    for p in parts: draw_dot(frame, perp, p[0], p[1], p[2], p[6], (175, 8, 8))              # percikan darah di udara
    # --- efek: cahaya moncong, darah, vignette, grain ---
    if P.flash > 0: frame *= (1 + P.flash * 8, 1 + P.flash * 6, 1 + P.flash * 2)
    frame *= GRADE * VIG; frame += (np.random.random((W, H, 1)) - .5) * 9
    if P.hurt > 0: frame[..., 0] += P.hurt * 220; frame[..., 1:] *= 1 - P.hurt
    if P.ahit > 0: k_ = P.ahit / .35 * .16; frame *= 1 - k_; frame += np.array((100, 122, 150), np.float32) * k_      # armor menahan peluru: semburat biru keabu-abuan tipis
    pg.surfarray.blit_array(canvas, np.clip(frame, 0, 255).astype(np.uint8))
    screen.blit(pg.transform.smoothscale(canvas, (W * SC, H * SC)), (0, 0))

SKIN, SLV, MET, DRK, WOOD = (212, 160, 126), (22, 22, 27), (62, 62, 70), (34, 34, 40), (118, 72, 40)
GUNS = {   # (jarak dasar, panjang ujung laras, [kotak: x0, x1, y0, y1, z0, z1, warna])  z = ke depan, y = ke bawah
    "PISTOL": (.85, .86, [(-.03, .03, -.045, .015, 0, .78, MET), (-.015, .015, -.03, -.005, .78, .86, DRK), (-.028, .028, .015, .045, 0, .5, DRK),
                          (-.027, .027, .045, .17, 0, .17, DRK), (-.045, .045, .05, .19, -.04, .2, SKIN), (-.04, .05, .1, .4, -.7, 0, SLV)]),
    "ASSAULT RIFLE": (1.0, 1.95, [(-.012, .012, -.03, -.005, .9, 1.2, DRK), (-.021, .021, -.046, .002, 1.15, 1.95, DRK), (-.03, .03, -.04, .03, .5, 1.0, MET),
                         (-.034, .034, -.05, .035, 0, .55, MET), (-.02, .02, .035, .22, .2, .36, DRK), (-.02, .02, .035, .13, 0, .1, DRK),
                         (-.012, .012, .03, .13, .72, .8, DRK), (-.025, .025, -.04, .045, -.5, 0, DRK),
                         (-.018, .018, -.056, -.045, .22, .5, MET), (-.026, .026, -.09, -.056, .3, .5, DRK), (-.026, .026, -.098, -.09, .3, .5, MET),
                         (-.04, .04, .04, .14, -.06, .1, SKIN), (-.03, .03, .13, .2, .7, .84, SKIN),
                         (-.04, .05, .08, .4, -.7, -.05, SLV), (-.095, -.04, .05, .4, -.3, .55, SLV)]),
    "SHOTGUN": (1.0, 1.4, [(-.014, .014, -.035, -.005, .3, 1.35, MET), (-.014, .014, -.003, .02, .3, 1.15, DRK), (-.032, .032, -.005, .045, .55, .9, WOOD),
                           (-.034, .034, -.05, .04, -.15, .3, MET), (-.028, .028, -.025, .08, -.65, -.15, WOOD),
                           (-.04, .04, .03, .12, -.12, .05, SKIN), (-.05, .03, .03, .1, .55, .85, SKIN),
                           (-.04, .05, .08, .4, -.8, -.1, SLV), (-.095, -.04, .05, .4, -.3, .55, SLV)])}

def gun_box(ox, oy, zb, b, f=640):            # gambar 1 balok dengan proyeksi perspektif (sisi atas, samping, belakang)
    x0, x1, y0, y1, z0, z1, col = b; cx, cy = screen.get_width() // 2, screen.get_height() // 2
    pr = lambda x, y, z: (cx + (ox + x) / max(z, .12) * f, cy + (oy + y) / max(z, .12) * f)
    za, zz = zb + z0, zb + z1; mx, my = ox + (x0 + x1) / 2, oy + (y0 + y1) / 2
    xs, yt = (x0 if mx > 0 else x1), (y0 if my > 0 else y1)
    sh = lambda k: tuple(min(255, int(c * k)) for c in col)
    for pts, k in (([pr(xs, y0, za), pr(xs, y1, za), pr(xs, y1, zz), pr(xs, y0, zz)], .8),
                   ([pr(x0, yt, za), pr(x1, yt, za), pr(x1, yt, zz), pr(x0, yt, zz)], 1.3),
                   ([pr(x0, y0, za), pr(x1, y0, za), pr(x1, y1, za), pr(x0, y1, za)], .62)):
        D.polygon(screen, sh(k), pts); D.polygon(screen, sh(.35), pts, 1)

def draw_weapon(t):
    w = P.weap[P.cur]; nm = w["name"]
    zb, tip, boxes = GUNS[nm]; sc = P.scope
    low = math.sin(math.pi * (1 - P.rl / w["rl"])) * .45 if P.rl > 0 else 0.0
    ox = (.25 + math.sin(P.bob) * .012) * (1 - .93 * sc)
    oy = .21 + abs(math.cos(P.bob)) * .01 + low + P.z * .7 + {"PISTOL": -.105, "ASSAULT RIFLE": -.135, "SHOTGUN": -.12}[nm] * sc + P.swap / .25 * .5 - P.kick * .0015
    zb -= P.kick * .004
    for b in sorted(boxes, key=lambda q: -q[4]): gun_box(ox, oy, zb, b)
    if P.flash > 0:                                          # kilatan moncong di ujung laras
        cx, cy = screen.get_width() // 2, screen.get_height() // 2; z = zb + tip; r = 640 / z * .12 * w.get("fl", 1)
        fx, fy = cx + ox / z * 640, cy + (oy - .02) / z * 640
        D.polygon(screen, (255, 200, 80), [(fx + math.cos(i * math.pi / 6) * r * (1.9 if i % 2 == 0 else .7), fy + math.sin(i * math.pi / 6) * r * (1.9 if i % 2 == 0 else .7)) for i in range(12)])
        D.circle(screen, (255, 245, 200), (int(fx), int(fy)), int(r * .7))

def txt(s, pos, f=font, col=(235, 225, 205)):
    sd = f.render(s, True, (0, 0, 0))                                          # kontur hitam agar terbaca tanpa latar
    for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1), (2, 2)): screen.blit(sd, (pos[0] + ox, pos[1] + oy))
    screen.blit(f.render(s, True, col), pos)
def bar(x, y, w, h, frac, col, label):
    D.rect(screen, (14, 8, 8), (x - 2, y - 2, w + 4, h + 4)); D.rect(screen, col, (x, y, int(w * max(0, min(1, frac))), h))
    D.rect(screen, (130, 115, 105), (x - 2, y - 2, w + 4, h + 4), 1); txt(label, (x + 6, y + 1), small)

def make_scope():                              # lensa scope: layar gelap dengan lingkaran bening di tengah
    sw, sh = screen.get_size(); m = pg.Surface((sw, sh), pg.SRCALPHA); m.fill((0, 0, 0, 255)); R = int(sh * .43)
    for i in range(10): D.circle(m, (0, 0, 0, 230 - i * 25), (sw // 2, sh // 2), R + 27 - i * 3)
    D.circle(m, (0, 0, 0, 0), (sw // 2, sh // 2), R - 3); return m
SCOPE = make_scope()

def draw_scope():
    if P.scope <= 0: return
    sw, sh = screen.get_size(); cx, cy = sw // 2, sh // 2; R = int(sh * .43); nm = P.weap[P.cur]["name"]
    if nm == "ASSAULT RIFLE":                                  # red dot sight: bingkai kaca + titik merah
        a = min(1.0, P.scope * 1.5); fw, fh = 150, 104; o = pg.Surface((fw + 40, fh + 40), pg.SRCALPHA)
        D.rect(o, (10, 10, 12, int(235 * a)), (0, 0, fw + 40, fh + 40), 20); D.rect(o, (40, 70, 80, int(40 * a)), (20, 20, fw, fh))
        screen.blit(o, (cx - (fw + 40) // 2, cy - (fh + 40) // 2))
        D.circle(screen, (255, 40, 40), (cx, cy), 4); D.circle(screen, (255, 80, 80), (cx, cy), 24, 1)
    elif nm == "PISTOL": D.circle(screen, (255, 50, 50), (cx, cy), 4); D.circle(screen, (255, 120, 120), (cx, cy), 9, 1)   # red dot
    else: D.circle(screen, (235, 235, 235), (cx, cy), 22, 2); D.line(screen, (235, 235, 235), (cx - 30, cy), (cx - 22, cy), 2); D.line(screen, (235, 235, 235), (cx + 22, cy), (cx + 30, cy), 2)   # iron sight

def draw_blood():                              # percikan darah di layar + tetesan mengalir ke bawah
    if not P.splats: return
    sw, sh = screen.get_size(); o = pg.Surface((sw, sh), pg.SRCALPHA)
    for x, y, r, life, mx, dr in P.splats:
        age = 1 - life / mx; col = (125, 4, 4, int(215 * min(1.0, life / (mx * .6)))); x, y, r = int(x), int(y), int(r)
        D.circle(o, col, (x, y), r)
        for k in range(5): D.circle(o, col, (int(x + math.cos(k * 1.3 + r) * r * 1.2), int(y + math.sin(k * 1.3 + r) * r * 1.2)), max(2, int(r * .28)))
        D.line(o, col, (x, y), (x, int(y + dr * age)), max(2, int(r * .22))); D.circle(o, col, (x, int(y + dr * age)), max(2, int(r * .16)))
    screen.blit(o, (0, 0))

def draw_flash():                              # layar putih saat terkena flashbang
    if P.blind <= 0: return
    sw, sh = screen.get_size(); o = pg.Surface((sw, sh)); o.fill((255, 255, 255)); o.set_alpha(int(255 * min(1.0, P.blind / 1.6))); screen.blit(o, (0, 0))

def draw_throwables(sh):                       # jumlah granat (G) dan flashbang (F) di samping HUD pemain
    for i, (kind, n, key) in enumerate((("granat", P.gr, "granat"), ("flash", P.fb, "flash"))):
        x, y, on = 572, sh - 72 + i * 34, n > 0
        D.rect(screen, (28, 20, 20), (x - 2, y - 2, 72, 30)); D.rect(screen, (95, 80, 70), (x - 2, y - 2, 72, 30), 1)
        if kind == "granat":
            D.ellipse(screen, (70, 110, 60) if on else (50, 60, 50), (x + 3, y + 7, 15, 17)); D.rect(screen, (150, 150, 150), (x + 8, y + 2, 5, 7)); D.circle(screen, (190, 190, 190), (x + 15, y + 5), 3, 1)
        else:
            D.rect(screen, (190, 190, 200) if on else (100, 100, 108), (x + 4, y + 4, 12, 20)); D.rect(screen, (240, 200, 60) if on else (110, 100, 60), (x + 4, y + 4, 12, 5)); D.rect(screen, (60, 60, 70), (x + 4, y + 14, 12, 3))
        txt(f"{pg.key.name(CFG['keys'][key]).upper()} x{n}", (x + 22, y + 6), small, (235, 225, 205) if on else (130, 115, 105))

def gun_icon(x, y, kind, on):                 # ikon senjata (tampak samping) untuk HUD
    m, g, wd = ((205, 205, 215), (120, 120, 130), (170, 108, 60)) if on else ((112, 112, 122), (70, 70, 78), (96, 64, 40))
    if kind == 0:                             # 1 = pistol
        x += 8; D.rect(screen, m, (x + 14, y + 7, 34, 8)); D.rect(screen, g, (x + 44, y + 9, 6, 4))
        D.polygon(screen, g, [(x + 17, y + 15), (x + 29, y + 15), (x + 26, y + 29), (x + 15, y + 29)])
        D.line(screen, m, (x + 30, y + 16), (x + 38, y + 16), 2); D.line(screen, m, (x + 38, y + 16), (x + 36, y + 22), 2)
    elif kind == 1:                           # 2 = assault rifle (suppressor, red dot, magasin panjang, grip)
        D.polygon(screen, g, [(x, y + 10), (x + 14, y + 9), (x + 14, y + 18), (x + 5, y + 21)])
        D.rect(screen, m, (x + 14, y + 8, 30, 8)); D.rect(screen, m, (x + 34, y + 9, 14, 6))
        D.rect(screen, g, (x + 48, y + 9, 16, 6)); D.rect(screen, (24, 24, 28), (x + 56, y + 9, 8, 6))
        D.rect(screen, g, (x + 26, y + 3, 9, 5)); D.rect(screen, (230, 50, 50) if on else (110, 40, 40), (x + 30, y + 4, 2, 2))
        D.polygon(screen, g, [(x + 24, y + 16), (x + 30, y + 16), (x + 33, y + 30), (x + 26, y + 30)])
        D.rect(screen, g, (x + 17, y + 16, 5, 9)); D.rect(screen, g, (x + 40, y + 15, 3, 8))
    else:                                     # 3 = shotgun
        D.rect(screen, m, (x + 24, y + 8, 40, 4)); D.rect(screen, g, (x + 24, y + 12, 34, 3)); D.rect(screen, wd, (x + 34, y + 11, 14, 6))
        D.rect(screen, g, (x + 16, y + 8, 10, 9)); D.polygon(screen, wd, [(x, y + 11), (x + 16, y + 9), (x + 16, y + 17), (x + 3, y + 25)])

def draw_slots(sh):                           # slot senjata 1 / 2 / 3 dengan gambar + sisa peluru
    for i, w in enumerate(P.weap):
        x0, y0, on = 258 + i * 78, sh - 72, i == P.cur
        D.rect(screen, (70, 28, 24) if on else (28, 20, 20), (x0, y0, 74, 46)); D.rect(screen, (225, 180, 80) if on else (95, 80, 70), (x0, y0, 74, 46), 2)
        gun_icon(x0 + 5, y0 + 8, i, on)
        txt(str(i + 1), (x0 + 6, y0 + 3), small, (255, 220, 120) if on else (150, 135, 120))
        a = str(w["ammo"]); txt(a, (x0 + 68 - small.size(a)[0], y0 + 29), small, (255, 90, 80) if w["ammo"] == 0 else (235, 225, 205) if on else (150, 135, 120))
    txt(P.weap[P.cur]["name"], (258, sh - 22), small, (240, 220, 170))

def draw_face(x, y, t):                       # wajah agen di HUD, berubah sesuai kondisi
    skin = (222, 172, 136); ko = P.state in ("dead", "over", "down"); ouch = P.hurt > 0
    D.rect(screen, (24, 18, 18), (x, y, 64, 72)); D.rect(screen, (150, 130, 105), (x, y, 64, 72), 2)
    D.polygon(screen, (16, 16, 20), [(x + 2, y + 70), (x + 8, y + 54), (x + 56, y + 54), (x + 62, y + 70)])
    D.polygon(screen, (235, 235, 235), [(x + 26, y + 54), (x + 38, y + 54), (x + 32, y + 66)])
    D.line(screen, (170, 25, 30), (x + 32, y + 57), (x + 32, y + 70), 3)
    D.rect(screen, skin, (x + 26, y + 46, 12, 10)); D.ellipse(screen, skin, (x + 16, y + 8, 32, 42))
    D.ellipse(screen, (28, 22, 18), (x + 15, y + 5, 34, 15))
    if ko:
        for ex in (x + 22, x + 36):
            D.line(screen, (30, 20, 20), (ex, y + 22), (ex + 7, y + 29), 2); D.line(screen, (30, 20, 20), (ex + 7, y + 22), (ex, y + 29), 2)
    else:
        for ex in (x + 18, x + 34): D.rect(screen, (8, 8, 10), (ex, y + 23, 12, 8))
        D.line(screen, (8, 8, 10), (x + 30, y + 25), (x + 34, y + 25), 2)
    if P.hp < 66: D.ellipse(screen, (150, 95, 125), (x + 36, y + 33, 9, 6))
    if P.hp < 35:
        D.line(screen, (170, 15, 15), (x + 25, y + 10), (x + 28, y + 30), 2); D.line(screen, (170, 15, 15), (x + 28, y + 36), (x + 30, y + 46), 2)
    my = y + 40
    if ko or ouch or P.hp < 25: D.ellipse(screen, (80, 20, 20), (x + 26, my - 3, 12, 9))
    elif P.state in ("clear", "ending"): D.arc(screen, (120, 40, 40), (x + 24, my - 6, 16, 10), math.pi, 2 * math.pi, 2)
    else: D.line(screen, (120, 60, 50), (x + 26, my), (x + 38, my), 2)
    if ouch: D.rect(screen, (255, 0, 0), (x, y, 64, 72), 3)

def make_danger(sw, sh):                       # vinyet merah tebal di tepi layar
    yy, xx = np.mgrid[0:sh, 0:sw]; d = np.sqrt(((xx - sw / 2) / (sw / 2)) ** 2 + ((yy - sh / 2) / (sh / 2)) ** 2)
    arr = np.zeros((sh, sw, 4), np.uint8); arr[..., 0], arr[..., 1], arr[..., 2] = 170, 6, 8; arr[..., 3] = (np.clip((d - .35) / .85, 0, 1) ** 1.6 * 235).astype(np.uint8)
    return pg.image.frombuffer(arr.tobytes(), (sw, sh), "RGBA").convert_alpha()
_DG = {}
def danger_for(sw, sh):
    if (sw, sh) not in _DG: _DG[(sw, sh)] = make_danger(sw, sh)
    return _DG[(sw, sh)]

def draw_danger(t):                            # layar memerah berdenyut saat sekarat (menggantikan bar health)
    k = max(0.0, min(1.0, (50 - P.hp) / 50))
    if k <= 0: return
    sw, sh = screen.get_size(); pulse = .8 + .2 * math.sin(t * (4 + 6 * k))
    dg = danger_for(sw, sh); dg.set_alpha(int(255 * min(1.0, k * 1.15) * pulse)); screen.blit(dg, (0, 0))
    tint = pg.Surface((sw, sh)); tint.fill((120, 0, 0)); tint.set_alpha(int(70 * k)); screen.blit(tint, (0, 0))

def draw_armor(sh, co=False):                  # panel armor abu-abu: ikon rompi berisi angka + 3 segmen biru + bar putih (semua mode)
    x, y = (10, sh - 54) if co else (16, sh - 66); pw, ph = (150, 44) if co else (236, 54); a = max(0.0, min(100.0, P.armor))
    iw, ih = 32, ph - 12; ix, iy = x + 8, y + 6
    pts = [(ix + 5, iy), (ix + iw - 5, iy), (ix + iw, iy + 6), (ix + iw, iy + ih - 4), (ix + iw - 6, iy + ih), (ix + 6, iy + ih), (ix, iy + ih - 4), (ix, iy + 6)]
    D.polygon(screen, (86, 90, 98), pts); D.polygon(screen, (28, 30, 34), pts, 2); D.line(screen, (130, 134, 142), (ix + 5, iy + 2), (ix + iw - 5, iy + 2), 1)
    s_ = str(int(a)); r_ = small.render(s_, True, (245, 245, 248)); screen.blit(r_, (ix + iw // 2 - r_.get_width() // 2, iy + ih // 2 - r_.get_height() // 2))
    bx = ix + iw + 12; bw = pw - (bx - x) - 10; sg = (bw - 8) // 3; sy, sh_ = y + int(ph * .2), max(6, int(ph * .22))
    for k in range(3):
        f = max(0.0, min(1.0, a / (100 / 3) - k)); sx = bx + k * (sg + 4); D.rect(screen, (20, 24, 30), (sx - 1, sy - 1, sg + 2, sh_ + 2)); D.rect(screen, (46, 54, 66), (sx, sy, sg, sh_)); D.rect(screen, (30, 140, 205), (sx, sy, int(sg * f), sh_))
    by = y + int(ph * .58); bh = max(5, int(ph * .17)); D.rect(screen, (20, 24, 30), (bx - 1, by - 1, bw + 2, bh + 2)); D.rect(screen, (46, 54, 66), (bx, by, bw, bh)); D.rect(screen, (250, 250, 252), (bx, by, int(bw * a / 100), bh))

def draw_nade_box(x, y, kind, n, key):
    on = n > 0
    if kind == "granat": D.ellipse(screen, (70, 130, 60) if on else (60, 70, 60), (x + 2, y + 7, 15, 17)); D.rect(screen, (170, 170, 170), (x + 7, y + 2, 5, 7)); D.circle(screen, (200, 200, 200), (x + 14, y + 5), 3, 1)
    else: D.rect(screen, (200, 200, 210) if on else (110, 110, 118), (x + 3, y + 4, 12, 20)); D.rect(screen, (240, 200, 60) if on else (110, 100, 60), (x + 3, y + 4, 12, 5)); D.rect(screen, (60, 60, 70), (x + 3, y + 14, 12, 3))
    txt(f"{pg.key.name(CFG['keys'][key]).upper()} x{n}", (x + 24, y + 6), small, (235, 225, 205) if on else (130, 115, 105))

WHT, SHD, OLN = (240, 240, 242), (168, 170, 176), (28, 28, 32)
def _poly(pts, ox, oy, col=WHT):
    q = [(ox + x, oy + y) for x, y in pts]; D.polygon(screen, col, q); D.polygon(screen, OLN, q, 1)

def hud_gun(ox, oy, kind, on):                 # siluet senjata putih besar ala HUD shooter modern
    c, d = (WHT, SHD) if on else ((120, 120, 126), (84, 84, 90))
    if kind == 0:                              # pistol
        _poly([(48, 12), (124, 12), (124, 28), (48, 28)], ox, oy, c); _poly([(116, 14), (140, 16), (140, 24), (116, 26)], ox, oy, d)
        _poly([(48, 28), (74, 28), (66, 52), (48, 52)], ox, oy, c); _poly([(74, 28), (96, 28), (96, 34), (80, 34), (76, 28)], ox, oy, d)
        D.rect(screen, d, (ox + 62, oy + 15, 40, 4)); D.rect(screen, d, (ox + 122, oy + 8, 4, 5)); D.rect(screen, d, (ox + 52, oy + 8, 4, 5))
    elif kind == 1:                            # assault rifle: popor, receiver, red dot, handguard, suppressor, magasin, grip
        _poly([(0, 16), (32, 12), (36, 32), (10, 36), (0, 28)], ox, oy, c)
        _poly([(32, 10), (96, 10), (96, 30), (32, 32)], ox, oy, c)
        _poly([(60, 0), (86, 0), (86, 9), (60, 9)], ox, oy, d); D.rect(screen, (235, 60, 60) if on else (120, 50, 50), (ox + 64, oy + 3, 4, 3))
        _poly([(96, 12), (138, 12), (138, 28), (96, 28)], ox, oy, c); D.line(screen, OLN, (ox + 110, oy + 14), (ox + 110, oy + 26), 1); D.line(screen, OLN, (ox + 124, oy + 14), (ox + 124, oy + 26), 1)
        _poly([(138, 15), (168, 15), (168, 25), (138, 25)], ox, oy, d)
        _poly([(64, 30), (82, 30), (90, 54), (72, 54)], ox, oy, d); _poly([(40, 31), (54, 31), (52, 50), (42, 50)], ox, oy, c)
        _poly([(112, 28), (120, 28), (120, 40), (112, 40)], ox, oy, d)
    else:                                      # shotgun: laras panjang, tabung magasin, pompa, popor kayu
        _poly([(0, 18), (36, 12), (36, 32), (10, 42), (0, 34)], ox, oy, c)
        _poly([(36, 10), (66, 10), (66, 30), (36, 32)], ox, oy, c); _poly([(66, 11), (168, 11), (168, 18), (66, 18)], ox, oy, d)
        _poly([(66, 19), (150, 19), (150, 25), (66, 25)], ox, oy, c); _poly([(100, 24), (130, 24), (130, 34), (100, 34)], ox, oy, c)
        _poly([(40, 32), (52, 32), (50, 48), (42, 48)], ox, oy, d)

def kbox(x, y, label):                         # kotak tombol putih berhuruf hitam
    w_ = max(22, small.size(label)[0] + 10); D.rect(screen, WHT, (x, y, w_, 20)); D.rect(screen, OLN, (x, y, w_, 20), 1)
    r = small.render(label, True, (20, 20, 22)); screen.blit(r, (x + w_ // 2 - r.get_width() // 2, y + 10 - r.get_height() // 2)); return w_

def hud_grenade(cx, y, on):
    c, d = (WHT, SHD) if on else ((110, 110, 116), (80, 80, 86))
    D.circle(screen, c, (cx + 14, y + 34), 14); D.circle(screen, OLN, (cx + 14, y + 34), 14, 1); D.rect(screen, d, (cx + 9, y + 14, 10, 9)); D.rect(screen, OLN, (cx + 9, y + 14, 10, 9), 1)
    D.line(screen, c, (cx + 18, y + 16), (cx + 30, y + 24), 3); D.circle(screen, c, (cx + 30, y + 28), 5, 2); D.line(screen, d, (cx + 6, y + 30), (cx + 22, y + 30), 2)

def hud_flash(cx, y, on):
    c, d = (WHT, SHD) if on else ((110, 110, 116), (80, 80, 86))
    D.rect(screen, c, (cx + 6, y + 10, 18, 46)); D.rect(screen, OLN, (cx + 6, y + 10, 18, 46), 1); D.rect(screen, d, (cx + 6, y + 10, 18, 9)); D.rect(screen, d, (cx + 6, y + 36, 18, 5))
    D.rect(screen, c, (cx + 21, y + 4, 4, 12)); D.rect(screen, OLN, (cx + 21, y + 4, 4, 12), 1)

def draw_weapon_panel(sw, sh, w, t, K=.82):    # panel senjata digambar ke kanvas sementara lalu diperkecil (K = skala)
    global screen
    tmp = pg.Surface((440, 120), pg.SRCALPHA); old = screen; screen = tmp
    try: _weapon_panel(w, 6, 6)
    finally: screen = old
    if sw < 700: K = .58                                                          # view split screen: panel lebih kecil
    ww, hh = int(440 * K), int(120 * K); gx_, gy_ = (10, 10) if sw < 700 else (22, 24); old.blit(pg.transform.smoothscale(tmp, (ww, hh)), (sw - ww - gx_, sh - hh - gy_))

def _weapon_panel(w, x0, base):
    screen.set_clip(pg.Rect(x0 - 6, base - 6, 190, 68))
    for i in range(len(P.weap)):                                              # gambar senjata bergulir naik-turun saat ganti
        pos = (i - P.cur + 1) % 3 - 1; hud_gun(x0, int(base + (pos + P.roll) * 76), i, i == P.cur and abs(P.roll) < .5)
    screen.set_clip(None)
    n, mx_ = w["ammo"], w["mag"]; shown = int(mx_ * (1 - P.rl / w["rl"])) if P.rl > 0 else n                # reload: angka naik pelan-pelan
    low = P.rl <= 0 and n <= max(1, int(mx_ * .3)); col = (255, 45, 35) if low else WHT; bx = x0 + 190; s1 = str(shown); txt(s1, (bx, base + 2), mid, col)
    sx = bx + mid.size(s1)[0] + 12; txt(str(w["mags"] * mx_), (sx, base + 14), font, (255, 45, 35) if w["mags"] == 0 else WHT)
    for k in range(3): D.rect(screen, SHD, (sx + 2, base + 38 + k * 4, 16, 2))                                  # ikon magasin mini
    txt(w["name"], (bx, base + 58), tiny, (200, 190, 165))
    y2 = base + 80; kn = (lambda k: {"reload": "X", "granat": "RB", "flash": "LB"}[k]) if uses_pad() else (lambda k: pg.key.name(CFG["keys"][k]).upper())
    kb = kbox(x0 + 6, y2, kn("reload"))
    for k in range(3): D.rect(screen, WHT if P.rl <= 0 else (255, 200, 90), (x0 + 14 + kb + k * 4, y2 + 3, 2, 14))
    D.line(screen, SHD, (x0 + 300, base + 2), (x0 + 300, base + 100), 1)                                          # pemisah
    for cx, kind, cnt, key in ((x0 + 316, "flash", P.fb, "flash"), (x0 + 372, "granat", P.gr, "granat")):
        on = cnt > 0; (hud_flash if kind == "flash" else hud_grenade)(cx, base, on)
        txt(str(cnt), (cx + 28, base + 2), small, WHT if on else (130, 130, 136)); kbox(cx, y2, kn(key))

def ring_seg(cx, cy, r0, r1, a0, a1, n=8):    # potongan cincin (busur tebal) sebagai poligon
    o = [(cx + math.cos(a0 + (a1 - a0) * i / n) * r1, cy + math.sin(a0 + (a1 - a0) * i / n) * r1) for i in range(n + 1)]
    return o + [(cx + math.cos(a0 + (a1 - a0) * i / n) * r0, cy + math.sin(a0 + (a1 - a0) * i / n) * r0) for i in range(n, -1, -1)]
def draw_crosshair(sw, sh, nm):                # crosshair PUTIH per senjata (kontur hitam tipis agar tetap terbaca di dinding terang)
    cx, cy = sw // 2, sh // 2; WH, SD = (255, 255, 255), (0, 0, 0)
    if nm == "SHOTGUN":                        # 4 busur diagonal + titik tengah
        R, th, half = 24, 2, math.radians(12)
        for sh_ in (True, False):
            for k in range(4):
                c = math.radians(45 + 90 * k); e = 1 if sh_ else 0
                D.polygon(screen, SD if sh_ else WH, ring_seg(cx, cy, R - th / 2 - e, R + th / 2 + e, c - half - .04 * e, c + half + .04 * e))
    else:                                      # ASSAULT RIFLE = plus berjarak | PISTOL = bentuk T (tanpa batang atas)
        t_, g_, L_ = 2, 3, 10
        bars = [(cx + 1 + g_, cy - 1, L_, t_), (cx - 1 - g_ - L_, cy - 1, L_, t_), (cx - 1, cy + 1 + g_, t_, L_)]
        if nm != "PISTOL": bars.append((cx - 1, cy - 1 - g_ - L_, t_, L_))
        for x_, y_, w_, h_ in bars: D.rect(screen, SD, (x_ - 1, y_ - 1, w_ + 2, h_ + 2))
        for x_, y_, w_, h_ in bars: D.rect(screen, WH, (x_, y_, w_, h_))
    D.rect(screen, SD, (cx - 2, cy - 2, 4, 4)); D.rect(screen, WH, (cx - 1, cy - 1, 2, 2))           # titik tengah

def hitmark(kill=False):                       # dipanggil saat peluru / granat kita mengenai musuh (kill=True: merah, lebih lama)
    if not hasattr(P, "hitm"): P.hitm, P.hitk = 0.0, False
    if kill: P.hitm, P.hitk = .55, True
    else:
        if P.hitm <= 0: P.hitk = False
        P.hitm = max(P.hitm, .3)
def hit_polys(cx, cy, r0, ln=13, hw=1.8, ol=1.5):    # 4 batang diagonal berujung runcing ke tengah: (kontur hitam, isi)
    out, fil = [], []
    for a in (45, 135, 225, 315):
        u = (math.cos(math.radians(a)), math.sin(math.radians(a))); v = (-u[1], u[0]); r1 = r0 + ln
        pt = lambda d, s_: (cx + u[0] * d + v[0] * s_, cy + u[1] * d + v[1] * s_)
        fil.append([pt(r0, 0), pt(r0 + 4, hw), pt(r1, hw), pt(r1, -hw), pt(r0 + 4, -hw)])
        out.append([pt(r0 - ol, 0), pt(r0 + 4, hw + ol), pt(r1 + ol, hw + ol), pt(r1 + ol, -hw - ol), pt(r0 + 4, -hw - ol)])
    return out, fil
def draw_hitmarker(sw, sh):                    # penanda kena tembak: putih (merah saat membunuh), kontur hitam, memudar cepat; berlaku di semua mode
    t_ = getattr(P, "hitm", 0.0)
    if t_ <= 0: return
    kill = getattr(P, "hitk", False); k = min(1.0, t_ / (.55 if kill else .3)); cx, cy = sw // 2, sh // 2
    sf = pg.Surface((64, 64), pg.SRCALPHA); out, fil = hit_polys(32, 32, 5 + (1 - k) * 5)
    for p_ in out: D.polygon(sf, (0, 0, 0), p_)
    for p_ in fil: D.polygon(sf, (255, 60, 50) if kill else (255, 255, 255), p_)
    sf.set_alpha(int(255 * min(1.0, k * 1.8))); screen.blit(sf, (cx - 32, cy - 32))

def draw_hud(t):
    sw, sh = screen.get_size(); w = P.weap[P.cur]; co = CO()
    mp = P.mode == "mp"
    draw_armor(sh, co)
    if not mp: draw_face(sw - 80, 10, t)
    draw_weapon_panel(sw, sh, w, t)                    # armor kiri bawah, senjata kanan bawah, wajah kanan atas
    alive = sum(e.hp > 0 for e in enemies)
    rt = lambda s_, y, f=small, c=(235, 225, 205): txt(s_, (sw - 92 - f.size(s_)[0], y), f, c)      # teks rata kanan di kiri wajah
    if mp: pass
    else:
        rt(("RUANG BOS" if P.floor == DIFF["floors"] else f"{P.stage}  {P.floor + 1}/{DIFF['floors']}") + f"   {P.diff}", 12)
        rt(f"KILLS  {P.kills}", 32, font, (255, 220, 120))
        rt(f"SISA {alive}     CP {sum(c[2] for c in cps)}/{len(cps)}     CONT {P.conts if P.conts < 50 else 'INF'}", 60)
    D.rect(screen, (120, 100, 70), (11, 9, 122, 122), 1); screen.blit(MM, (12, 10))               # map kiri atas
    for e in enemies:
        if e.hp > 0: D.rect(screen, (230, 40, 40), (12 + e.x * 3 - 1, 10 + e.y * 3 - 1, 3, 3))
    for c in cps: D.rect(screen, (90, 255, 140) if c[2] else (255, 170, 50), (12 + c[0] * 3 - 2, 10 + c[1] * 3 - 2, 4, 4))
    D.circle(screen, (70, 255, 90), (int(12 + P.x * 3), int(10 + P.y * 3)), 3)
    if co:
        for q in PL:
            if q is not P and q.state != "wait": D.circle(screen, (255, 210, 70), (int(12 + q.x * 3), int(10 + q.y * 3)), 3)
        draw_co_status()
    bs = next((e for e in enemies if e.k == "boss" and e.hp > 0 and e.awake), None)
    if bs:
        bwid = 340 if co else 440; bx = sw // 2 - bwid // 2; bar(bx, 104, bwid, 22, bs.hp / bs.maxhp, (200, 40, 40), f"DON VARGO  [{bs.wp.upper()}]    {int(bs.hp)} / {int(bs.maxhp)}")
        if bs.maxarmor: D.rect(screen, (14, 8, 8), (bx - 2, 130, bwid + 4, 12)); D.rect(screen, (96, 150, 235), (bx, 132, int(bwid * max(0, bs.armor) / bs.maxarmor), 8)); D.rect(screen, (130, 115, 105), (bx - 2, 130, bwid + 4, 12), 1)
        for q in (1, 2, 3): D.line(screen, (20, 8, 8), (bx + bwid // 4 * q, 102), (bx + bwid // 4 * q, 128), 2)      # penanda 25 / 50 / 75 persen
        txt(f"{int(bs.hp / bs.maxhp * 100)}%", (bx + bwid + 10, 106), small)
    if P.scope < .3: draw_crosshair(sw, sh, w["name"])
    draw_hitmarker(sw, sh)
    if P.rl > 0 and int(t * 6) % 2: txt("RELOADING...", (sw // 2 - 70, sh // 2 + 40))
    if P.run and not mp: txt("RUN", (16, sh - 96), small, (255, 200, 90))
    if P.msg[1] > 0: txt(P.msg[0], (sw // 2 - 110, sh // 2 + 80), font, (255, 220, 120))
    if t < 6 and co: center("SPLIT SCREEN   P1: keyboard + mouse   P2: controller", 184, small)
    elif t < 6:
        txt("AGENT DUTY", (sw // 2 - big.size("AGENT DUTY")[0] // 2, 40), big, (240, 200, 90))
        txt("Bersihkan jaringan komplotan penjahat", (sw // 2 - 190, 112))
        center("WASD jalan | SHIFT lari | SPACE lompat | Klik kiri tembak | Klik kanan bidik | R reload", 150, small); center("1/2/3 atau roll mouse = senjata | G = granat | F = flashbang", 174, small)
    if P.mode == "mp": draw_mp_overlay(sw, sh)
    if P.state != "play": draw_state()

# ================= LOOP UTAMA =================
def center(s, y, f=font, col=(235, 225, 205)):
    w = screen.get_width()
    if f.size(s)[0] > w - 16:                                                  # teks terlalu lebar untuk view sempit: bungkus ke beberapa baris
        for i, ln in enumerate(wrap(s, f, w - 28)): txt(ln, (w // 2 - f.size(ln)[0] // 2, y + i * (f.get_height() + 2)), f, col)
    else: txt(s, (w // 2 - f.size(s)[0] // 2, y), f, col)

def draw_co_status():                          # split screen: bar nyawa kedua pemain di bawah peta
    for i, q in enumerate(PL):
        y = 140 + i * 18; hp = max(0, q.hp) / 100; txt(f"P{i + 1}", (12, y), small, (255, 225, 130) if q is P else (190, 180, 160))
        D.rect(screen, (14, 8, 8), (38, y + 2, 84, 11)); D.rect(screen, (60, 200, 90) if hp > .35 else (230, 70, 60), (40, y + 4, int(80 * hp), 7)); D.rect(screen, (130, 115, 105), (38, y + 2, 84, 11), 1)
        if q.state == "down": txt("JATUH", (128, y), small, (240, 100, 90))

def draw_ending():
    sw, sh = screen.get_size(); mm, ss = divmod(int(P.time), 60)
    pts = 100 - P.used * 12 - max(0, P.time / 60 - (DIFF["floors"] + 1) * 5) * 3 + {"EASY": 0, "MEDIUM": 5, "HARD": 12}[P.diff]
    rank = "S" if pts >= 90 else "A" if pts >= 75 else "B" if pts >= 55 else "C"
    center("TAMAT", 36, big, (240, 200, 90)); center("MISSION COMPLETE", 112, font, (170, 230, 180))
    for i, l in enumerate(("Don Vargo, pemimpin komplotan, akhirnya tumbang.", "Seluruh mansion kini aman dan bukti kejahatannya ada di tanganmu.",
                           "Markas pusat memanggil: tugas selesai, Agen.", "Sampai jumpa di misi berikutnya.")): center(l, 165 + i * 30, font)
    for i, l in enumerate((f"Tingkat kesulitan : {P.diff}", f"Waktu            : {mm:02d}:{ss:02d}", f"Musuh dikalahkan : {P.kills}", f"Continue dipakai : {P.used}")):
        txt(l, (sw // 2 - 150, 310 + i * 28))
    center("RANK  " + rank, 440, big, (255, 210, 90)); center("ENTER = menu utama", sh - 50)

def draw_state():
    sw, sh = screen.get_size(); st = P.state; my = sh // 2; B = big if sw >= 700 else mid; F = font if sw >= 700 else small
    o = pg.Surface((sw, sh), pg.SRCALPHA)
    o.fill((110, 0, 0, 150) if st in ("dead", "over", "mpdead") else (110, 0, 0, 105) if st == "down" else (0, 0, 0, 185) if st in ("pause", "ending", "mpend") else (0, 50, 25, 150)); screen.blit(o, (0, 0))
    if st == "dead":
        center("MISSION FAILED", my - 80, B, (235, 70, 60)); center(f"ENTER = lanjut dari checkpoint terakhir  (sisa continue: {P.conts})", my + 20, F); center("ESC = menu utama", my + 70, small)
    elif st == "over": center("GAME OVER", my - 80, B, (235, 70, 60)); center("Continue habis.  ENTER = menu utama", my + 20, F)
    elif st == "down":
        center("TERJATUH", my - 70, B, (235, 70, 60)); center("Teman mendekat untuk membantumu berdiri, atau capai checkpoint", my + 10, small)
        D.rect(screen, (14, 8, 8), (sw // 2 - 80, my + 54, 160, 12)); D.rect(screen, (90, 220, 120), (sw // 2 - 78, my + 56, int(156 * min(1.0, P.rv / 2.5)), 8)); D.rect(screen, (130, 115, 105), (sw // 2 - 80, my + 54, 160, 12), 1)
    elif st == "clear":
        center("LOKASI BERSIH", my - 80, B, (120, 235, 150)); center(f"Lokasi {P.floor + 1} dari {DIFF['floors']} bersih.  ENTER = " + ("masuk ke RUANG BOS" if P.floor + 1 == DIFF["floors"] else "pindah ke lokasi berikutnya"), my + 20, F)
        center("Bonus: +30 health, +25 armor, +1 magazine", my + 80, small)
    elif st == "pause": draw_pause_menu()
    elif st == "mpdead":
        by = P.last_by; center("KAMU TERBUNUH", my - 80, B, (235, 70, 60))
        center("oleh " + (LOB.get(by, f"AGENT-{by + 1}") if by >= 0 and by != NET.id else "dirimu sendiri"), my + 20, F); center(f"Bangkit lagi dalam {int(P.rt) + 1} detik...", my + 56, small)
    elif st == "mpend":
        center("MATCH SELESAI", 24, big, (240, 200, 90)); center(("PEMENANG:  " + LOB.get(P.winner, "?")) if P.winner is not None else P.notice, 112, font, (255, 225, 130))
        scoreboard(sw // 2, 170); center("ENTER = kembali ke menu", sh - 50)
    elif st == "wait": pass
    else: draw_ending()

def make_bg():
    sw, sh = screen.get_size(); b = pg.Surface((sw, sh))
    for y in range(0, sh, 4): c = int(10 + 30 * y / sh); D.rect(b, (c + 8, c // 2 + 4, c // 2 + 6), (0, y, sw, 4))
    D.polygon(b, (14, 10, 12), [(180, 520), (180, 330), (330, 330), (480, 250), (630, 330), (780, 330), (780, 520)])
    D.polygon(b, (10, 7, 9), [(300, 330), (480, 200), (660, 330)])
    for wx in range(210, 760, 70):
        for wy in (370, 440): D.rect(b, (230, 170, 70) if random.random() < .45 else (30, 22, 20), (wx, wy, 26, 40))
    D.rect(b, (8, 6, 8), (0, 520, sw, sh - 520)); return b
BG = make_bg()
I_SENS, I_VOL, I_INP, I_PSENS, I_RES, I_BACK = 9, 10, 11, 12, 13, 14                  # indeks baris pengaturan setelah 9 baris tombol
KEYNAMES = [("Maju", "maju"), ("Mundur", "mundur"), ("Kiri (geser)", "kiri"), ("Kanan (geser)", "kanan"), ("Lari", "lari"), ("Reload", "reload"), ("Lompat", "lompat"), ("Granat", "granat"), ("Flashbang", "flash")]

def menu_rows(S):
    if S["mode"] == "main": return [("START GAME", ""), ("SETTINGS", ""), ("QUIT", "")]
    if S["mode"] == "diff": return [(k, f"{v['floors']} lokasi + bos") for k, v in DIFFS.items()] + [("BACK", "")]
    bar_ = lambda v: "<  " + "|" * v + "." * (10 - v) + "  >"
    rows = [(n, pg.key.name(CFG["keys"][k]).upper()) for n, k in KEYNAMES]
    rows += [("Sensitivitas mouse", bar_(CFG["sens"])), ("Volume", bar_(CFG["vol"])), ("Kontrol", "<  " + input_label() + "  >"), ("Sensitivitas stik", bar_(CFG["psens"])), ("Layar", "<  " + res_name() + "  >"), ("KEMBALI", "")]
    if S["wait"] is not None: rows[S["wait"]] = (rows[S["wait"]][0], "tekan tombol...")
    return rows

def block(s_, y, f=small, col=(200, 185, 160)):    # paragraf rata tengah yang otomatis dibungkus; mengembalikan y berikutnya
    for ln in wrap(s_, f, screen.get_width() - 60): txt(ln, (screen.get_width() // 2 - f.size(ln)[0] // 2, y), f, col); y += f.get_height() + 1
    return y

def draw_settings(S):
    sw, sh = screen.get_size(); screen.blit(BG, (0, 0)); st = S["mode"] == "settings"
    center("AGENT DUTY", 4, mid, (240, 200, 90))
    y0, sp = (100, 24) if st else (210, 46); rows = menu_rows(S); rects = []
    center({"main": "Bersihkan mansion. Hentikan komplotannya.", "diff": "PILIH TINGKAT KESULITAN", "settings": "SETTINGS & KONTROL"}[S["mode"]], y0 - 32, font, (200, 180, 150))
    for i, (a, b) in enumerate(rows):
        r = pg.Rect(sw // 2 - 290, y0 + i * sp, 580, sp - 3); rects.append(r); on = i == S["sel"]
        if on: D.rect(screen, (95, 30, 30), r); D.rect(screen, (200, 150, 70), r, 2)
        ty = r.y + (2 if st else 6); txt(a, (r.x + 14, ty), font, (255, 235, 180) if on else (190, 175, 150)); txt(b, (r.right - 14 - font.size(b)[0], ty), font, (230, 200, 120))
    if S["mode"] == "diff" and S["sel"] < 3: center(DIFFS[list(DIFFS)[S["sel"]]]["desc"], y0 + 4 * sp + 16, small, (210, 190, 160))
    if st:
        y = y0 + len(rows) * sp + 6
        y = block("Keyboard + mouse: tembak klik kiri | bidik klik kanan | senjata 1/2/3 atau roll mouse | pause ESC | ubah tombol: pilih baris + ENTER, lalu tekan tombol baru", y)
        y = block("Controller: stik kiri jalan | stik kanan lihat | RT tembak | LT bidik | A lompat | X reload | RB granat | LB flashbang | Y atau D-pad ganti senjata | klik stik kiri lari | Start pause", y)
        if PADS:
            p0 = PADS[0]; y = block(f"Controller: {p0.name[:30]}  [{'SDL' if p0.kind == 'ctl' else 'joystick'}]   input: {p0.live()}", y, small, (150, 220, 150))
            if p0.err: block("Catatan: " + p0.err[:110], y, small, (230, 190, 110))
        else: block("Controller: tidak terdeteksi (colokkan, tunggu sekitar 1 detik). Di Windows pastikan terbaca di Pengaturan Bluetooth / Game Controllers.", y, small, (230, 150, 120))
    return rects

# ================= MENU PAUSE: LANJUTKAN / PENGATURAN / MENU UTAMA =================
DEF_KEYS = dict(maju=pg.K_w, mundur=pg.K_s, kiri=pg.K_a, kanan=pg.K_d, lari=pg.K_LSHIFT, reload=pg.K_r, lompat=pg.K_SPACE, granat=pg.K_g, flash=pg.K_f)
PG_GOLD, PG_GOLD2, PG_MUTE = (235, 185, 85), (255, 235, 180), (150, 135, 110)
PM = dict(page=0, sel=0, tab=0, row=0, wait=None, anim=0.0, r_main=[], r_tabs=[], r_rows=[], r_sl={}, r_arr=[], r_cards=[], r_back=None)
PM_ITEMS = (("LANJUTKAN", "Kembali ke permainan", "play"), ("PENGATURAN", "Tombol, suara, bidik, dan input", "gear"), ("MENU UTAMA", "Keluar dari permainan ini", "exit"))
PS_TABS = ("TOMBOL", "AUDIO & BIDIK", "INPUT", "LAYAR")
PS_SLIDERS = (("sens", "Sensitivitas mouse", "Kecepatan putar kamera dengan mouse", 1), ("vol", "Volume", "Suara efek dan dengung latar", 0), ("psens", "Sensitivitas stik", "Kecepatan putar kamera dengan stik controller", 1))
PS_INPUTS = (("auto", "OTOMATIS", "Keyboard + mouse dan controller aktif bersamaan"), ("kbm", "KEYBOARD + MOUSE", "Controller diabaikan"), ("pad", "CONTROLLER", "Main dengan controller (tanpa controller, keyboard tetap bisa)"))
PS_CW = 36                                                                  # lebar satu sel slider (termasuk celah)

def rrect(col, rect, w=0, rad=8):
    try: D.rect(screen, col, rect, w, border_radius=rad)
    except TypeError: D.rect(screen, col, rect, w)

def glass(rect, col, rad=12):                    # panel setengah transparan
    r = pg.Rect(rect); s_ = pg.Surface(r.size, pg.SRCALPHA)
    try: D.rect(s_, col, s_.get_rect(), 0, border_radius=rad)
    except TypeError: D.rect(s_, col, s_.get_rect())
    screen.blit(s_, r.topleft)

def keycap(x, y, lab):                           # kotak tombol kecil (petunjuk Q / E)
    r = pg.Rect(x, y, 26, 26); rrect((235, 225, 205), r, 0, 5); s_ = small.render(lab, True, (20, 16, 16)); screen.blit(s_, (r.centerx - s_.get_width() // 2, r.y + 5))

def pause_open(): PM.update(page=0, sel=0, tab=0, row=0, wait=None, anim=0.0, menu=False)

def pause_close():                               # keluar dari pause (solo / multiplayer: state; co-op: flag paused)
    if CO(): P.paused = False
    else: P.state = "play"
    set_mouse(True)

def pause_rows(): return (10, 3, 1, len(RESF))[PM["tab"]]

def ps_adjust(row, d):                           # ubah slider (tab 2) atau pilihan input (tab 3)
    if PM["tab"] == 1:
        k, _, _, lo = PS_SLIDERS[row]; CFG[k] = max(lo, min(10, CFG[k] + d))
        if k == "vol": ambient.set_volume(CFG["vol"] / 10)
    elif PM["tab"] == 2:
        ks = [m_[0] for m_ in PS_INPUTS]; CFG["input"] = ks[(ks.index(CFG["input"]) + d) % len(ks)]
    elif PM["tab"] == 3: res_step(d)
    save_cfg()

def ps_set_slider(row, x):                       # klik / seret langsung pada bar slider
    r = PM["r_sl"].get(row)
    if r is None: return
    k, _, _, lo = PS_SLIDERS[row]; CFG[k] = max(lo, min(10, int((x - r.x) // PS_CW) + 1))
    if k == "vol": ambient.set_volume(CFG["vol"] / 10)
    save_cfg()

def pause_pick(i):                               # item menu utama pause dipilih
    if i == 0: return "resume"
    if i == 1: PM.update(page=1, tab=0, row=0, wait=None); return None
    return "menu"

def pause_back(): PM.update(page=0, sel=1, wait=None); save_cfg()

def pause_event(e):                              # -> "resume" / "menu" / None
    pgi, tab = PM["page"], PM["tab"]
    if e.type == pg.KEYDOWN:
        k = e.key
        if PM["wait"] is not None:                                          # menunggu tombol baru
            if k != pg.K_ESCAPE: CFG["keys"][KEYNAMES[PM["wait"]][1]] = k; save_cfg()
            PM["wait"] = None; return None
        if k == pg.K_ESCAPE:
            if pgi == 1: pause_back(); return None
            return "resume"
        if pgi == 0:
            if k == pg.K_m: return "menu"
            if k in (pg.K_UP, pg.K_DOWN): PM["sel"] = (PM["sel"] + (1 if k == pg.K_DOWN else -1)) % len(PM_ITEMS)
            elif k in (pg.K_RETURN, pg.K_KP_ENTER, pg.K_SPACE): return pause_pick(PM["sel"])
            return None
        row = PM["row"]
        if k in (pg.K_q, pg.K_PAGEUP): PM.update(tab=(tab - 1) % 4, row=0)
        elif k in (pg.K_e, pg.K_PAGEDOWN): PM.update(tab=(tab + 1) % 4, row=0)
        elif k == pg.K_BACKSPACE: pause_back()
        elif k in (pg.K_UP, pg.K_DOWN):
            d = 1 if k == pg.K_DOWN else -1
            if tab == 0: PM["row"] = row // 5 * 5 + (row % 5 + d) % 5
            elif tab == 1: PM["row"] = (row + d) % 3
            elif tab == 3: res_step(d)
        elif k in (pg.K_LEFT, pg.K_RIGHT):
            d = 1 if k == pg.K_RIGHT else -1
            if tab == 0: PM["row"] = (row + 5) % 10
            else: ps_adjust(row, d)
        elif k in (pg.K_RETURN, pg.K_KP_ENTER, pg.K_SPACE):
            if tab == 0:
                if row < 9: PM["wait"] = row
                else: CFG["keys"].update(DEF_KEYS); save_cfg()
            elif tab == 2: ps_adjust(0, 1)
    elif e.type == pg.MOUSEMOTION:
        if pgi == 0:
            for i, r in enumerate(PM["r_main"]):
                if r.collidepoint(e.pos): PM["sel"] = i
        else:
            for i, r in PM["r_rows"]:
                if r.collidepoint(e.pos) and PM["wait"] is None: PM["row"] = i
            if tab == 1 and e.buttons[0]:
                for i, r in PM["r_sl"].items():
                    if r.inflate(0, 30).collidepoint(e.pos): ps_set_slider(i, e.pos[0])
    elif e.type == pg.MOUSEBUTTONDOWN and e.button == 1:
        if pgi == 0:
            for i, r in enumerate(PM["r_main"]):
                if r.collidepoint(e.pos): PM["sel"] = i; return pause_pick(i)
            return None
        if PM["wait"] is not None: PM["wait"] = None; return None
        if PM["r_back"] is not None and PM["r_back"].collidepoint(e.pos): pause_back(); return None
        for i, r in enumerate(PM["r_tabs"]):
            if r.collidepoint(e.pos): PM.update(tab=i, row=0); return None
        if tab == 1:
            for i, r in PM["r_sl"].items():
                if r.inflate(0, 30).collidepoint(e.pos): PM["row"] = i; ps_set_slider(i, e.pos[0]); return None
            for i, r, d in PM["r_arr"]:
                if r.collidepoint(e.pos): PM["row"] = i; ps_adjust(i, d); return None
        elif tab == 2:
            for i, r in PM["r_cards"]:
                if r.collidepoint(e.pos): CFG["input"] = PS_INPUTS[i][0]; save_cfg(); return None
        elif tab == 3:
            for i, r in PM["r_cards"]:
                if r.collidepoint(e.pos): CFG["res"] = i; apply_display(); save_cfg(); return None
        else:
            for i, r in PM["r_rows"]:
                if r.collidepoint(e.pos):
                    PM["row"] = i
                    if i < 9: PM["wait"] = i
                    else: CFG["keys"].update(DEF_KEYS); save_cfg()
                    return None
    return None

def pause_icon(kind, cx, cy, on):
    g = PG_GOLD if on else PG_MUTE
    if kind == "play": D.polygon(screen, g, [(cx - 8, cy - 13), (cx - 8, cy + 13), (cx + 14, cy)])
    elif kind == "gear":
        D.circle(screen, g, (cx, cy), 11)
        for k in range(8): D.circle(screen, g, (int(cx + math.cos(k * math.pi / 4) * 14), int(cy + math.sin(k * math.pi / 4) * 14)), 4)
        D.circle(screen, (46, 24, 26) if on else (22, 16, 18), (cx, cy), 5)
    else:
        D.rect(screen, g, (cx - 15, cy - 15, 16, 30), 3)
        D.polygon(screen, (220, 70, 60), [(cx - 3, cy - 5), (cx + 5, cy - 5), (cx + 5, cy - 11), (cx + 17, cy), (cx + 5, cy + 11), (cx + 5, cy + 5), (cx - 3, cy + 5)])

def pause_info():
    if P.mode == "mp":
        n_ = sum(1 for v in TEAM.values() if v == 0); n2_ = len(TEAM) - n_
        return f"MULTIPLAYER  -  {f'{n_} VS {n2_}' if TEAM else 'FREE FOR ALL'}  -  {P.stage}"
    loc = "RUANG BOS" if P.floor == DIFF["floors"] else f"{P.stage}  {P.floor + 1}/{DIFF['floors']}"
    return f"CAMPAIGN  -  {P.diff}  -  {loc}" + ("  -  CO-OP" if CO() else "")

def mini_bar(x, y, w, label, frac, col):
    txt(label, (x, y), small, (200, 185, 160)); bx = x + 78
    D.rect(screen, (14, 8, 8), (bx, y + 2, w - 78, 14)); D.rect(screen, col, (bx + 2, y + 4, int((w - 82) * max(0, min(1, frac))), 10)); D.rect(screen, (130, 115, 105), (bx, y + 2, w - 78, 14), 1)

def pause_status(x, y, w, h):                    # kartu status di sisi kanan menu pause
    glass((x, y, w, h), (18, 12, 15, 226), 14); rrect((120, 96, 60), (x, y, w, h), 2, 14)
    txt("STATUS", (x + 22, y + 14), font, PG_GOLD); D.rect(screen, (150, 120, 70), (x + 22, y + 44, w - 44, 2)); yy = y + 58
    for i, q in enumerate(PL if CO() else [P]):
        tag = f"P{i + 1} " if CO() else ""
        mini_bar(x + 22, yy, w - 44, tag + "HEALTH", q.hp / 100, (70, 200, 100) if q.hp > 35 else (230, 70, 60)); yy += 24
        if not CO(): mini_bar(x + 22, yy, w - 44, "ARMOR", q.armor / 100, (96, 150, 235)); yy += 24
    yy += 8; w_ = P.weap[P.cur]; rows = []
    if P.mode == "mp":
        me = MPS.get(NET.id, [0, 0]); rows += [("KILL", str(me[0])), ("MATI", str(me[1]))]
        if TEAM: rows.append(("SKOR TIM", "T"))
        rows.append(("PESERTA", str(len(RPS) + 1)))
    else:
        mm, ss = divmod(int(P.time), 60)
        rows += [("KILL", str(P.kills)), ("WAKTU", f"{mm:02d}:{ss:02d}"), ("SISA MUSUH", str(sum(e.hp > 0 for e in enemies))), ("CHECKPOINT", f"{sum(c[2] for c in cps)} / {len(cps)}"), ("CONTINUE", str(P.conts) if P.conts < 50 else "INF")]
    rows += [("AMUNISI", f"{w_['ammo']} / {w_['mag']}  (+{w_['mags']})"), ("GRANAT / FLASH", f"{P.gr} / {P.fb}")]
    for lab, val in rows:
        txt(lab, (x + 22, yy + 3), small, (170, 155, 130))
        if val == "T":                                                    # skor tim berwarna
            parts = [(str(TSC[0]), TCOL[0]), ("  -  ", PG_MUTE), (str(TSC[1]), TCOL[1])]; xx = x + w - 22 - sum(font.size(p_)[0] for p_, _ in parts)
            for p_, c_ in parts: txt(p_, (xx, yy), font, c_); xx += font.size(p_)[0]
        else: txt(val, (x + w - 22 - font.size(val)[0], yy), font, PG_GOLD2)
        yy += 29

def pause_main(sw, sh, e_, tk):
    s_ = pg.Surface((sw, sh), pg.SRCALPHA); D.polygon(s_, (14, 8, 10, 236), [(0, 0), (int(440 * e_), 0), (int(380 * e_), sh), (0, sh)]); screen.blit(s_, (0, 0))
    D.line(screen, PG_GOLD, (int(440 * e_), 0), (int(380 * e_), sh), 3); D.line(screen, (150, 40, 40), (int(452 * e_), 0), (int(392 * e_), sh), 2)
    ox = int((1 - e_) * -60); txt("PAUSE", (50 + ox, 34), big, PG_GOLD)
    D.rect(screen, PG_GOLD, (50 + ox, 118, 90, 4)); D.rect(screen, (200, 60, 55), (146 + ox, 118, 30, 4))
    for j, ln in enumerate(wrap(pause_info(), small, 330)[:3]): txt(ln, (50 + ox, 132 + j * 18), small, (200, 185, 160))
    PM["r_main"] = []
    for i, (lab, hint, ic) in enumerate(PM_ITEMS):
        on = i == PM["sel"]; base = pg.Rect(50, 206 + i * 86, 340, 72); PM["r_main"].append(base); r = base.move((14 if on else 0) + ox, 0)
        rrect((88, 28, 30) if on else (30, 20, 24), r, 0, 12); rrect(PG_GOLD if on else (90, 76, 68), r, 3 if on else 2, 12)
        if on: D.rect(screen, PG_GOLD, (r.x + 2, r.y + 14, 5, r.h - 28))
        D.circle(screen, (46, 24, 26) if on else (22, 16, 18), (r.x + 46, r.centery), 25); D.circle(screen, PG_GOLD if on else (90, 76, 68), (r.x + 46, r.centery), 25, 2)
        pause_icon(ic, r.x + 46, r.centery, on)
        txt(lab, (r.x + 88, r.y + 12), font, PG_GOLD2 if on else (190, 175, 150)); txt(hint, (r.x + 88, r.y + 42), small, (230, 200, 120) if on else (130, 118, 100))
    pause_status(500, 100, 420, 366)
    center("ATAS / BAWAH = pilih     ENTER = konfirmasi     ESC = lanjut     M = menu utama", sh - 40, small, PG_MUTE)

def pause_settings(sw, sh, e_, tk):
    tab = PM["tab"]; PM["r_tabs"], PM["r_rows"], PM["r_arr"], PM["r_cards"], PM["r_sl"] = [], [], [], [], {}
    txt("PENGATURAN", (60, 22), mid, PG_GOLD); D.rect(screen, PG_GOLD, (62, 76, 110, 4)); D.rect(screen, (200, 60, 55), (178, 76, 30, 4))
    px, py, pw, ph = 60, 92, 840, 448; glass((px, py, pw, ph), (18, 12, 15, 240), 14); rrect((150, 120, 70), (px, py, pw, ph), 2, 14)
    tw, tg = 180, 10; tx0 = px + (pw - (4 * tw + 3 * tg)) // 2; ty = py + 16
    keycap(tx0 - 36, ty + 7, "Q"); keycap(tx0 + 4 * tw + 3 * tg + 10, ty + 7, "E")
    for i, nm in enumerate(PS_TABS):
        r = pg.Rect(tx0 + i * (tw + tg), ty, tw, 40); PM["r_tabs"].append(r); on = i == tab
        rrect((88, 28, 30) if on else (30, 22, 24), r, 0, 8); rrect(PG_GOLD if on else (80, 68, 60), r, 2 if on else 1, 8)
        txt(nm, (r.centerx - font.size(nm)[0] // 2, r.y + 10), font, PG_GOLD2 if on else (170, 155, 130))
        if on: D.rect(screen, PG_GOLD, (r.x + 14, r.bottom - 4, r.w - 28, 3))
    D.line(screen, (90, 74, 60), (px + 24, ty + 54), (px + pw - 24, ty + 54), 1)
    top = ty + 74
    if tab == 0:                                                           # ---- tombol: 2 kolom x 5 baris
        cw, rh = 370, 46
        for i in range(10):
            col_, rw = divmod(i, 5); r = pg.Rect(px + 30 + col_ * (cw + 40), top + rw * (rh + 8), cw, rh); PM["r_rows"].append((i, r)); on = PM["row"] == i
            rrect((70, 26, 28) if on else (28, 20, 22), r, 0, 8); rrect(PG_GOLD if on else (70, 58, 52), r, 2 if on else 1, 8)
            if i < 9:
                nm, key = KEYNAMES[i]; code = CFG["keys"][key]; waiting = PM["wait"] == i
                txt(nm, (r.x + 16, r.y + 12), font, PG_GOLD2 if on else (190, 175, 150))
                if waiting: lab, c_, cwid = "TEKAN TOMBOL...", ((255, 110, 100) if int(tk * 3) % 2 else (200, 80, 70)), 190
                else: lab = pg.key.name(code).upper(); c_ = (240, 210, 120); cwid = max(64, small.size(lab)[0] + 28)
                chip = pg.Rect(r.right - 12 - cwid, r.y + 8, cwid, 30); dup = list(CFG["keys"].values()).count(code) > 1 and not waiting
                rrect((46, 36, 28), chip, 0, 6); rrect((230, 80, 70) if dup else PG_GOLD if on else (110, 92, 70), chip, 2, 6)
                txt(lab, (chip.centerx - small.size(lab)[0] // 2, chip.y + 7), small, c_)
            else:
                lab = "RESET KE BAWAAN"; txt(lab, (r.centerx - font.size(lab)[0] // 2, r.y + 12), font, PG_GOLD2 if on else (190, 175, 150))
        vals = list(CFG["keys"].values())
        if len(set(vals)) < len(vals): txt("Peringatan: dua aksi memakai tombol yang sama (ditandai merah)", (px + 30, top + 5 * (rh + 8) + 2), small, (240, 120, 100))
        hint = "ATAS / BAWAH / KIRI / KANAN = pilih     ENTER atau klik = ubah tombol     ESC = batal"
    elif tab == 1:                                                         # ---- slider
        for i, (k, nm, ds, lo) in enumerate(PS_SLIDERS):
            r = pg.Rect(px + 30, top + i * 100, pw - 60, 88); PM["r_rows"].append((i, r)); on = PM["row"] == i; v = CFG[k]
            rrect((70, 26, 28) if on else (28, 20, 22), r, 0, 10); rrect(PG_GOLD if on else (70, 58, 52), r, 2 if on else 1, 10)
            txt(nm, (r.x + 20, r.y + 14), font, PG_GOLD2 if on else (190, 175, 150)); txt(ds, (r.x + 20, r.y + 48), small, PG_MUTE)
            sx, sy = r.x + 330, r.y + 30; PM["r_sl"][i] = pg.Rect(sx, sy, 10 * PS_CW, 28)
            for j in range(10):
                c = pg.Rect(sx + j * PS_CW, sy, PS_CW - 6, 28)
                if j < v: rrect((int(205 + 5 * j), int(175 - 9 * j), 60), c, 0, 5)
                else: rrect((40, 32, 30), c, 0, 5); rrect((80, 68, 60), c, 1, 5)
            for d, ax in ((-1, sx - 26), (1, sx + 10 * PS_CW + 8)):
                ar = pg.Rect(ax - 6, sy - 2, 32, 32); PM["r_arr"].append((i, ar, d)); m_ = ar.centerx
                D.polygon(screen, PG_GOLD if on else (130, 112, 86), [(m_ + 6 * -d, sy + 5), (m_ + 6 * -d, sy + 23), (m_ + 6 * d, sy + 14)] if d > 0 else [(m_ + 6 * -d, sy + 5), (m_ + 6 * -d, sy + 23), (m_ + 6 * d, sy + 14)])
            s_ = str(v); txt(s_, (r.right - 20 - font.size(s_)[0], r.y + 28), font, PG_GOLD)
        hint = "ATAS / BAWAH = pilih     KIRI / KANAN = ubah nilai     klik atau seret bar juga bisa"
    elif tab == 2:                                                         # ---- input
        cw_, chh, gap_ = 250, 150, 20; cx0 = px + (pw - (3 * cw_ + 2 * gap_)) // 2
        for i, (k, nm, ds) in enumerate(PS_INPUTS):
            r = pg.Rect(cx0 + i * (cw_ + gap_), top, cw_, chh); PM["r_cards"].append((i, r)); on = CFG["input"] == k
            rrect((70, 26, 28) if on else (28, 20, 22), r, 0, 10); rrect(PG_GOLD if on else (70, 58, 52), r, 3 if on else 1, 10)
            D.circle(screen, PG_GOLD if on else (90, 78, 66), (r.right - 20, r.y + 22), 7, 0 if on else 2)
            txt(nm, (r.x + 16, r.y + 16), font, PG_GOLD2 if on else (190, 175, 150))
            for j, ln in enumerate(wrap(ds, small, cw_ - 32)[:4]): txt(ln, (r.x + 16, r.y + 58 + j * 18), small, PG_MUTE)
        sr = pg.Rect(cx0, top + chh + 24, 3 * cw_ + 2 * gap_, 100); rrect((22, 16, 18), sr, 0, 10); rrect((90, 76, 66), sr, 1, 10)
        if PADS:
            p0 = PADS[0]; txt("Controller terdeteksi", (sr.x + 18, sr.y + 12), font, (130, 225, 150)); txt(p0.name[:48], (sr.x + 18, sr.y + 42), small, (200, 190, 165)); txt("Input: " + p0.live()[:70], (sr.x + 18, sr.y + 66), small, (150, 220, 150))
        else:
            txt("Controller tidak terdeteksi", (sr.x + 18, sr.y + 12), font, (240, 140, 110)); txt("Colokkan controller lalu tunggu sekitar 1 detik.", (sr.x + 18, sr.y + 46), small, PG_MUTE)
        hint = "KIRI / KANAN = ganti pilihan     ENTER atau klik = pilih"
    else:                                                                  # ---- layar: ukuran jendela / layar penuh (langsung diterapkan)
        cw_, chh, gx_, gy_ = 190, 112, 14, 14; cx0 = px + (pw - (4 * cw_ + 3 * gx_)) // 2
        for i, (nm, w_, h_, nt) in enumerate(RESF):
            r = pg.Rect(cx0 + (i % 4) * (cw_ + gx_), top + (i // 4) * (chh + gy_), cw_, chh); ok = res_mode(i) is not None; on = CFG["res"] == i
            if ok: PM["r_cards"].append((i, r))
            rrect((70, 26, 28) if on else (28, 20, 22), r, 0, 10); rrect(PG_GOLD if on else (70, 58, 52) if ok else (50, 44, 40), r, 3 if on else 1, 10)
            c1 = PG_GOLD2 if on else (190, 175, 150) if ok else (95, 85, 76)
            txt(nm, (r.x + 14, r.y + 14), font, c1)
            if on: D.circle(screen, PG_GOLD, (r.right - 18, r.y + 22), 7)
            rw_, rh_ = DESK if w_ == 0 else (w_, h_); bw = 54; bh = max(8, int(bw * rh_ / rw_)); b = pg.Rect(r.x + 14, r.y + 52, bw, bh)
            rrect((60, 52, 46) if ok else (40, 36, 34), b, 0, 3); rrect(c1, b, 1, 3)
            txt(nt if ok else "tidak muat di monitor", (r.x + 14, r.bottom - 26), small, PG_MUTE if ok else (120, 90, 80))
        txt(f"Monitor: {DESK[0]} x {DESK[1]}. Gambar tidak melar; beda rasio = ada pita hitam di tepi.", (px + 30, top + 2 * (chh + gy_) + 2), small, PG_MUTE)
        hint = "KIRI / KANAN = ganti ukuran     atau klik kartu     (langsung diterapkan)"
    br = pg.Rect(px + 30, py + ph - 56, 170, 38); PM["r_back"] = br
    rrect((30, 20, 24), br, 0, 8); rrect(PG_GOLD, br, 2, 8); D.polygon(screen, PG_GOLD, [(br.x + 24, br.centery), (br.x + 36, br.centery - 8), (br.x + 36, br.centery + 8)])
    txt("KEMBALI", (br.x + 50, br.y + 9), font, PG_GOLD2)
    txt(hint, (px + 230 + (pw - 260 - small.size(hint)[0]) // 2, py + ph - 45), small, PG_MUTE)
    center("ESC = kembali ke " + ("menu utama" if PM.get("menu") else "menu pause") + "     Q / E = ganti tab", sh - 40, small, PG_MUTE)

def draw_pause_menu():
    sw, sh = screen.get_size(); PM["anim"] = min(1.0, PM["anim"] + .1); a = PM["anim"]; e_ = a * a * (3 - 2 * a); tk = pg.time.get_ticks() / 1000
    if PM["page"] == 0: pause_main(sw, sh, e_, tk)
    else: pause_settings(sw, sh, e_, tk)

# ================= CUTSCENE: gambar bergaya foto lama + teks mengetik =================
def wrap(text, f, maxw):
    lines, cur = [], ""
    for w_ in text.split():
        if cur and f.size(cur + " " + w_)[0] > maxw: lines.append(cur); cur = w_
        else: cur = (cur + " " + w_).strip()
    return lines + [cur]

def grad(p, top, bot, y0=0, y1=360):
    for y in range(y0, y1, 4): k = (y - y0) / max(1, y1 - y0); D.rect(p, tuple(int(a + (b - a) * k) for a, b in zip(top, bot)), (0, y, 640, 4))

def stars(p, t, n=45):
    r = random.Random(3)
    for _ in range(n): x, y = r.randint(0, 640), r.randint(0, 180); b = 150 + int(80 * math.sin(t * 2 + x)); D.circle(p, (b, b, b), (x, y), 1)

def house(p, cx, base, sc, lit, col, t):                       # siluet mansion + jendela menyala berkedip
    r = random.Random(5); w = int(320 * sc); i_ = lambda v: int(v * sc)
    D.polygon(p, col, [(cx - w // 2, base), (cx - w // 2, base - i_(120)), (cx + w // 2, base - i_(120)), (cx + w // 2, base)])
    D.polygon(p, col, [(cx - w // 3, base - i_(100)), (cx - w // 3, base - i_(170)), (cx, base - i_(235)), (cx + w // 3, base - i_(170)), (cx + w // 3, base - i_(100))])
    D.rect(p, col, (cx + i_(60), base - i_(215), i_(24), i_(60)))
    for i in range(7):
        for hy in (36, 88):
            on = lit and r.random() < .65 and math.sin(t * 3 + i * 2 + hy) > -.85
            D.rect(p, (240, 190, 90) if on else (26, 22, 28), (cx - w // 2 + i_(18) + int(i * (w - i_(50)) / 6), base - i_(hy) - i_(8), i_(16), i_(22)))
    D.rect(p, (18, 14, 18), (cx - i_(12), base - i_(46), i_(24), i_(46)))

def fence(p, y, h, col):
    for x in range(0, 640, 14): D.line(p, col, (x, y), (x, y - h), 2)
    D.line(p, col, (0, y - h // 3), (640, y - h // 3), 2); D.line(p, col, (0, y - h * 2 // 3), (640, y - h * 2 // 3), 2)

def agent_back(p, x, y, sc, col=(8, 8, 10)):                   # siluet agen dari belakang (y = telapak kaki)
    i_ = lambda v: int(v * sc)
    D.rect(p, col, (x - i_(14), y - i_(48), i_(11), i_(48))); D.rect(p, col, (x + i_(3), y - i_(48), i_(11), i_(48)))
    D.polygon(p, col, [(x - i_(26), y - i_(50)), (x - i_(22), y - i_(100)), (x + i_(22), y - i_(100)), (x + i_(26), y - i_(50))])
    D.rect(p, col, (x - i_(6), y - i_(110), i_(12), i_(12))); D.circle(p, col, (x, y - i_(120)), max(2, i_(13)))

def portrait(p, x, y, sc=1.0):                                 # Don Vargo: jas putih, dasi merah, kacamata hitam
    i_ = lambda v: int(v * sc); sk = (205, 155, 120)
    D.polygon(p, (232, 232, 238), [(x - i_(70), y + i_(170)), (x - i_(55), y + i_(105)), (x + i_(55), y + i_(105)), (x + i_(70), y + i_(170))])
    D.polygon(p, (250, 250, 252), [(x - i_(20), y + i_(105)), (x + i_(20), y + i_(105)), (x, y + i_(150))])
    D.polygon(p, (170, 20, 30), [(x - i_(6), y + i_(112)), (x + i_(6), y + i_(112)), (x + i_(9), y + i_(160)), (x, y + i_(170)), (x - i_(9), y + i_(160))])
    D.rect(p, sk, (x - i_(12), y + i_(88), i_(24), i_(22))); D.ellipse(p, sk, (x - i_(36), y + i_(20), i_(72), i_(78)))
    D.ellipse(p, (205, 205, 212), (x - i_(38), y + i_(10), i_(76), i_(38))); D.rect(p, (10, 10, 12), (x - i_(32), y + i_(52), i_(64), i_(14)))
    D.polygon(p, (70, 58, 52), [(x - i_(14), y + i_(82)), (x + i_(14), y + i_(82)), (x + i_(8), y + i_(98)), (x - i_(8), y + i_(98))])

def stamp(p, label, col, pos, ang=-12):
    ss = pg.Surface((250, 64), pg.SRCALPHA); D.rect(ss, col + (230,), (0, 0, 250, 64), 4); r = font.render(label, True, col)
    ss.blit(r, (125 - r.get_width() // 2, 16)); p.blit(pg.transform.rotate(ss, ang), pos)

def art_night(p, t):
    grad(p, (8, 10, 28), (46, 34, 56)); stars(p, t); D.circle(p, (60, 58, 80), (520, 70), 40); D.circle(p, (235, 235, 210), (520, 70), 28)
    house(p, 320, 300, 1.0, True, (10, 8, 12), t); D.rect(p, (6, 6, 8), (0, 300, 640, 60)); fence(p, 320, 34, (4, 4, 6))
    fog = pg.Surface((640, 70), pg.SRCALPHA); fog.fill((130, 140, 160, 38)); p.blit(fog, (int(10 * math.sin(t * .5)), 270))

def art_dosir(p, t):
    p.fill((40, 28, 22)); D.rect(p, (200, 168, 108), (60, 40, 520, 290)); D.rect(p, (200, 168, 108), (60, 22, 120, 24)); D.rect(p, (236, 229, 210), (80, 60, 480, 250))
    D.rect(p, (24, 20, 20), (100, 80, 170, 200)); D.rect(p, (96, 92, 104), (108, 88, 154, 184)); portrait(p, 185, 98, .8)
    for i, l in enumerate(("DOSIR  #A-0412", "NAMA   : DON VARGO", "PROFIL : BOS SENJATA GELAP", "LOKASI : MANSION VARGO", "STATUS : BURONAN NO. 1")): p.blit(small.render(l, True, (40, 36, 34)), (290, 92 + i * 34))
    if t > 1.2: stamp(p, "BURONAN", (190, 30, 30), (330, 220))

def art_brief(p, t):
    grad(p, (10, 18, 28), (18, 28, 40)); D.rect(p, (6, 14, 20), (70, 30, 500, 200)); D.rect(p, (30, 90, 100), (70, 30, 500, 200), 3)
    for gx in range(70, 570, 40): D.line(p, (20, 60, 70), (gx, 30), (gx, 230), 1)
    for gy in range(30, 230, 40): D.line(p, (20, 60, 70), (70, gy), (570, gy), 1)
    n = DIFF.get("floors", 3) + 1; on = int(t * 2) % 2
    for i in range(n): D.rect(p, (60, 150, 160), (210, 190 - i * 34, 220, 28), 2)
    D.circle(p, (230, 40, 40) if on else (110, 20, 20), (320, 190 - (n - 1) * 34 + 14), 6)
    D.polygon(p, (8, 8, 10), [(180, 360), (200, 300), (260, 280), (380, 280), (440, 300), (460, 360)]); D.circle(p, (12, 12, 14), (320, 262), 38)
    D.circle(p, (60, 200, 255) if on else (30, 100, 140), (368, 268), 4)
    for k in range(3): D.circle(p, (60, 150, 190), (368, 268), 12 + k * 10 + int(t * 8) % 10, 1)

def art_gate(p, t):
    grad(p, (10, 12, 30), (40, 30, 52)); stars(p, t, 35); D.circle(p, (235, 235, 210), (110, 60), 22)
    house(p, 320, 190, .42, True, (10, 8, 12), t); D.rect(p, (8, 8, 10), (0, 190, 640, 170)); D.polygon(p, (34, 30, 32), [(300, 190), (340, 190), (560, 360), (80, 360)])
    k = min(1.0, t / 8); ay = 340 - int(120 * k); sc = 1.05 - .55 * k
    beam = pg.Surface((640, 360), pg.SRCALPHA); D.polygon(beam, (255, 240, 170, 55), [(320 + int(24 * sc), ay - int(70 * sc)), (260, 190), (400, 190)]); p.blit(beam, (0, 0))
    agent_back(p, 320, ay, sc)
    if t > 2.2: tt = big.render("AGENT DUTY", True, (240, 200, 90)); tt.set_alpha(min(255, int((t - 2.2) * 200))); p.blit(tt, (320 - tt.get_width() // 2, 40))

def art_down(p, t):
    grad(p, (30, 20, 16), (70, 44, 30))
    for i in range(-8, 9): D.line(p, (40, 26, 18), (320, 120), (320 + i * 90, 360), 2)
    for j in range(1, 9): D.line(p, (40, 26, 18), (0, 120 + j * j * 4), (640, 120 + j * j * 4), 2)
    D.ellipse(p, (110, 8, 8), (170, 235, 320, 85)); D.polygon(p, (230, 230, 236), [(200, 252), (380, 232), (420, 264), (220, 294)])
    D.polygon(p, (40, 40, 46), [(380, 232), (530, 244), (530, 266), (420, 264)]); D.circle(p, (205, 155, 120), (185, 262), 26); D.ellipse(p, (205, 205, 212), (160, 238, 40, 22))
    D.line(p, (170, 20, 30), (230, 262), (300, 258), 5); D.polygon(p, (20, 20, 24), [(90, 304), (140, 296), (146, 310), (96, 318)])
    D.rect(p, (14, 14, 18), (250, 318, 76, 42)); D.rect(p, (14, 14, 18), (352, 328, 76, 32)); D.rect(p, (6, 6, 8), (246, 350, 84, 10)); D.rect(p, (6, 6, 8), (348, 352, 84, 8))

def art_docs(p, t):
    grad(p, (28, 20, 16), (52, 36, 26)); D.rect(p, (22, 22, 26), (110, 150, 420, 190)); D.rect(p, (70, 70, 78), (110, 150, 420, 190), 4)
    for i in range(5):
        D.rect(p, (238 - i * 6, 232 - i * 6, 216 - i * 6), (150 + i * 16, 60 + i * 9, 210, 150)); D.rect(p, (110, 100, 90), (150 + i * 16, 60 + i * 9, 210, 150), 1)
    for k in range(6): D.line(p, (90, 90, 100), (230, 112 + k * 16), (330 + (k % 3) * 20, 112 + k * 16), 2)
    D.rect(p, (110, 24, 28), (390, 200, 120, 84)); D.line(p, (210, 170, 70), (400, 214), (500, 214), 2); D.rect(p, (90, 150, 190), (150, 280, 38, 16))
    if t > 1.0: stamp(p, "BUKTI DISITA", (40, 140, 70), (300, 250), 10)

def art_dawn(p, t):
    grad(p, (30, 40, 90), (255, 160, 80), 0, 260); D.rect(p, (255, 160, 80), (0, 256, 640, 50)); D.circle(p, (255, 230, 150), (470, 238), 54); D.circle(p, (255, 245, 210), (470, 238), 38)
    house(p, 230, 300, .9, False, (14, 10, 14), t); D.rect(p, (10, 8, 10), (0, 300, 640, 60)); fence(p, 318, 30, (6, 6, 8))
    for cx, body in ((400, (236, 236, 240)), (540, (46, 46, 54))):
        blink = (int(t * 4) + (cx > 450)) % 2; D.rect(p, body, (cx - 60, 322, 120, 28)); D.rect(p, body, (cx - 36, 304, 72, 22)); D.rect(p, (30, 40, 60), (cx - 30, 308, 60, 14))
        D.rect(p, (255, 40, 40) if blink else (60, 10, 10), (cx - 24, 298, 22, 8)); D.rect(p, (60, 100, 255) if not blink else (10, 20, 60), (cx + 2, 298, 22, 8))
        gl = pg.Surface((200, 120), pg.SRCALPHA); D.circle(gl, (255, 40, 40, 70) if blink else (40, 80, 255, 70), (100, 60), 55); p.blit(gl, (cx - 100, 250))

def art_walk(p, t):
    grad(p, (70, 60, 110), (255, 170, 90), 0, 240); D.circle(p, (255, 235, 160), (320, 232), 84); D.circle(p, (255, 248, 215), (320, 232), 58)
    D.rect(p, (14, 10, 14), (0, 232, 640, 128)); D.polygon(p, (36, 30, 32), [(304, 232), (336, 232), (620, 360), (20, 360)])
    k = min(1.0, t / 9); ay = 345 - int(90 * k); sc = 1.15 - .6 * k; D.polygon(p, (22, 16, 20), [(320, ay), (330, ay), (340, 360), (300, 360)])
    agent_back(p, 320, ay, sc)
    if t > 2: tt = big.render("MISSION COMPLETE", True, (240, 200, 90)); tt.set_alpha(min(255, int((t - 2) * 200))); p.blit(tt, (320 - tt.get_width() // 2, 40))

def art_loc_rumah(p, t):                       # rumah persembunyian: malam, lampu teras, mobil
    grad(p, (10, 14, 34), (44, 34, 54)); stars(p, t, 30); D.circle(p, (225, 225, 205), (540, 60), 24); D.rect(p, (10, 8, 12), (0, 290, 640, 70)); fence(p, 316, 30, (6, 6, 8))
    D.rect(p, (46, 40, 52), (190, 170, 260, 125)); D.polygon(p, (30, 22, 30), [(170, 175), (320, 90), (470, 175)])
    for wx in (215, 360): D.rect(p, (240, 190, 90) if (int(t * 2) + wx) % 5 else (120, 90, 50), (wx, 205, 56, 46)); D.line(p, (40, 30, 30), (wx + 28, 205), (wx + 28, 251), 2)
    D.rect(p, (60, 36, 26), (296, 230, 44, 65)); gl = pg.Surface((160, 160), pg.SRCALPHA); D.circle(gl, (255, 220, 120, 60), (80, 80), 70); p.blit(gl, (238, 160)); D.circle(p, (255, 230, 150), (318, 222), 5)
    D.rect(p, (14, 14, 18), (500, 270, 110, 26)); D.rect(p, (14, 14, 18), (520, 252, 70, 22)); D.circle(p, (6, 6, 8), (522, 298), 9); D.circle(p, (6, 6, 8), (588, 298), 9)

def art_loc_desa(p, t):                        # pedesaan: pegunungan, sawah, rumah kayu, asap cerobong
    grad(p, (70, 50, 110), (250, 150, 90), 0, 220); D.polygon(p, (60, 44, 90), [(0, 220), (120, 120), (230, 220)]); D.polygon(p, (50, 38, 78), [(180, 220), (340, 100), (520, 220)]); D.polygon(p, (66, 50, 96), [(420, 220), (560, 130), (640, 200), (640, 220)])
    D.rect(p, (60, 110, 50), (0, 220, 640, 140))
    for k in range(5): D.rect(p, (70 + k * 6, 130 + k * 8, 56), (0, 235 + k * 26, 640, 16))
    for hx, hy in ((90, 262), (300, 250), (480, 280)):
        D.rect(p, (110, 76, 46), (hx, hy, 70, 40)); D.polygon(p, (150, 110, 60), [(hx - 8, hy), (hx + 35, hy - 32), (hx + 78, hy)]); D.rect(p, (240, 190, 90), (hx + 28, hy + 12, 14, 14))
        for k in range(4): D.circle(p, (200, 200, 205), (hx + 55 + int(math.sin(t + k) * 4), hy - 20 - k * 14 - int(t * 6) % 14), 3 + k)
    D.ellipse(p, (200, 160, 60), (540, 320, 60, 28))

def art_loc_hutan(p, t):                       # hutan: pohon rapat, sinar bulan, kabut, kunang-kunang
    grad(p, (6, 18, 20), (16, 44, 36)); beam = pg.Surface((640, 360), pg.SRCALPHA)
    for bx in (150, 330, 500): D.polygon(beam, (200, 230, 200, 28), [(bx, 0), (bx + 40, 0), (bx + 140, 360), (bx - 60, 360)])
    p.blit(beam, (0, 0)); r = random.Random(9)
    for i in range(14):
        x, w, c = r.randint(0, 640), r.randint(16, 40), r.randint(0, 20)
        D.rect(p, (28 + c, 20 + c, 14), (x, 80, w, 280)); D.polygon(p, (10 + c // 2, 40 + c, 22), [(x - 60, 150), (x + w // 2, 10), (x + w + 60, 150)])
    D.rect(p, (14, 30, 20), (0, 330, 640, 30))
    for k in range(18): D.circle(p, (200, 255, 140), ((k * 97 + int(t * 20)) % 640, 200 + (k * 53) % 140 + int(math.sin(t + k) * 8)), 2)
    fog = pg.Surface((640, 90), pg.SRCALPHA); fog.fill((120, 150, 140, 46)); p.blit(fog, (int(8 * math.sin(t * .4)), 250))

def art_loc_kota(p, t):                        # kota: gedung berjendela, jalan, lampu jalan, papan neon
    grad(p, (50, 40, 100), (250, 140, 90), 0, 230); r = random.Random(4)
    for x in range(0, 640, 48):
        h, c = r.randint(90, 220), r.randint(0, 14); D.rect(p, (18 + c, 16 + c, 30 + c), (x, 230 - h, 44, h + 130))
        for wy in range(230 - h + 10, 220, 16):
            for wx in range(x + 6, x + 38, 12): D.rect(p, (250, 200, 100) if r.random() < .45 else (36, 34, 50), (wx, wy, 6, 9))
    D.rect(p, (20, 20, 26), (0, 300, 640, 60)); D.polygon(p, (34, 34, 40), [(250, 230), (390, 230), (640, 360), (0, 360)])
    for lx in (160, 480): D.rect(p, (10, 10, 12), (lx, 170, 5, 120)); D.circle(p, (255, 220, 140), (lx + 2, 170), 8)
    if int(t * 2) % 2: D.rect(p, (255, 40, 80), (520, 120, 70, 22), 3)

def art_loc_sekolah(p, t):                     # sekolah: gedung bata, menara jam, bendera merah putih
    grad(p, (60, 62, 90), (230, 150, 110), 0, 240); D.rect(p, (30, 70, 40), (0, 270, 640, 90)); D.rect(p, (150, 70, 56), (80, 150, 480, 125)); D.rect(p, (150, 70, 56), (270, 100, 100, 50))
    for wx in range(100, 540, 52):
        for wy in (170, 220): D.rect(p, (250, 210, 120) if (wx // 52 + wy) % 3 else (50, 50, 70), (wx, wy, 30, 34))
    D.polygon(p, (90, 40, 34), [(262, 100), (320, 52), (378, 100)]); D.circle(p, (240, 240, 230), (320, 124), 18); D.line(p, (20, 20, 20), (320, 124), (320, 112), 2); D.line(p, (20, 20, 20), (320, 124), (330, 128), 2)
    D.rect(p, (60, 40, 30), (296, 235, 48, 40)); D.line(p, (200, 200, 200), (590, 150), (590, 300), 3); D.rect(p, (200, 40, 40), (592, 152, 30, 10)); D.rect(p, (250, 250, 250), (592, 162, 30, 10))

def art_loc_bandara(p, t):                     # bandara: landasan, menara kontrol, pesawat, lampu landasan berkedip
    grad(p, (110, 130, 170), (210, 200, 190), 0, 220); D.rect(p, (70, 74, 80), (0, 220, 640, 140)); D.polygon(p, (50, 52, 58), [(300, 220), (340, 220), (640, 360), (0, 360)])
    for k in range(7): D.rect(p, (230, 230, 230), (318, 230 + k * k * 3, 4 + k, 4 + k))
    D.rect(p, (180, 184, 190), (500, 110, 28, 120)); D.rect(p, (60, 100, 130), (486, 90, 56, 30)); D.rect(p, (200, 60, 60), (510, 70, 8, 22))
    D.ellipse(p, (230, 232, 238), (60, 190, 260, 56)); D.polygon(p, (200, 204, 212), [(160, 220), (260, 220), (200, 280)]); D.polygon(p, (200, 204, 212), [(60, 205), (92, 160), (110, 205)])
    for k in range(6): D.rect(p, (60, 100, 130), (92 + k * 22, 202, 12, 8))
    for k in range(8): D.circle(p, (255, 200, 80) if (int(t * 3) + k) % 2 else (120, 90, 40), (40 + k * 80, 300 + (k % 2) * 8), 3)

def art_loc_mansion(p, t):                     # gerbang besi mansion + lentera
    grad(p, (8, 10, 28), (40, 30, 50)); stars(p, t, 30); D.circle(p, (225, 225, 205), (120, 60), 26); house(p, 320, 250, .8, True, (10, 8, 12), t); D.rect(p, (6, 6, 8), (0, 250, 640, 110))
    for x in range(40, 620, 26): D.line(p, (20, 20, 26), (x, 360), (x, 190), 4); D.polygon(p, (20, 20, 26), [(x - 5, 190), (x + 5, 190), (x, 176)])
    D.line(p, (20, 20, 26), (0, 300), (640, 300), 5); D.line(p, (20, 20, 26), (0, 230), (640, 230), 5)
    for px in (20, 600): D.rect(p, (24, 22, 28), (px - 18, 150, 36, 210)); D.rect(p, (255, 220, 120) if int(t * 3) % 7 else (120, 90, 50), (px - 8, 120, 16, 30))

def art_loc_aula(p, t):                        # ruang utama: karpet merah, pilar, lampu gantung, Don Vargo di singgasana
    grad(p, (24, 16, 14), (60, 40, 30)); D.polygon(p, (46, 28, 20), [(250, 190), (390, 190), (640, 360), (0, 360)]); D.polygon(p, (130, 20, 30), [(300, 190), (340, 190), (470, 360), (170, 360)])
    for x, sc in ((80, 1.0), (180, .75), (255, .55)):
        for xx in (x, 640 - x): D.rect(p, (74, 58, 50), (xx - int(18 * sc), 60, int(36 * sc), int(240 * sc)))
    D.rect(p, (250, 230, 160), (230, 20, 180, 110)); D.circle(p, (255, 250, 220), (320, 70), 26)
    D.line(p, (170, 150, 90), (320, 0), (320, 60), 3); D.circle(p, (255, 220, 140), (320, 74, ), 16)
    for a in range(6): D.circle(p, (255, 200, 90) if (int(t * 6) + a) % 5 else (150, 110, 50), (320 + int(math.cos(a * 1.05) * 44), 74 + int(math.sin(a * 1.05) * 12)), 4)
    D.rect(p, (30, 18, 16), (296, 150, 48, 50)); D.polygon(p, (228, 228, 236), [(306, 162), (334, 162), (338, 196), (302, 196)]); D.circle(p, (205, 155, 120), (320, 153), 8); D.rect(p, (8, 8, 10), (313, 150, 14, 4)); D.line(p, (170, 20, 30), (320, 164), (320, 184), 2)
    for gx in (232, 396): D.rect(p, (8, 8, 10), (gx, 160, 14, 44)); D.circle(p, (8, 8, 10), (gx + 7, 154), 7)

LOCS = {"RUMAH": (art_loc_rumah, "RUMAH PERSEMBUNYIAN  |  22:10", "Titik pertama: rumah persembunyian anak buah Vargo di pinggir kota. Di dalamnya ada peta dan petunjuk jaringannya."),
        "PEDESAAN": (art_loc_desa, "DESA PASOKAN  |  01:30", "Di desa terpencil ini, komplotan menimbun senjata di rumah-rumah kayu dan lumbung. Para penjaga berjaga di setiap sudut."),
        "HUTAN": (art_loc_hutan, "HUTAN JALUR SELUNDUP  |  03:15", "Jalur penyelundupan melewati hutan lebat. Pepohonan menutup pandangan, jadi waspadai musuh di balik batang pohon."),
        "KOTA": (art_loc_kota, "DISTRIK KOTA  |  19:40", "Toko-toko di pusat kota hanyalah kedok transaksi gelap. Gunakan mobil dan sudut bangunan sebagai tempat berlindung."),
        "SEKOLAH": (art_loc_sekolah, "SEKOLAH TERBENGKALAI  |  21:05", "Sekolah kosong ini dipakai sebagai tempat pelatihan anak buah baru Vargo. Koridor panjang dan kelas-kelas penuh jebakan."),
        "BANDARA": (art_loc_bandara, "BANDARA PRIBADI  |  04:20", "Pesawat kargo Vargo siap lepas landas membawa senjata ke luar negeri. Hentikan pengirimannya sebelum fajar."),
        "MANSION": (art_loc_mansion, "MANSION VARGO  |  23:40", "Semua petunjuk berakhir di sini. Gerbang besi terbuka sedikit, seolah mereka sudah menunggumu."),
        "RUANG BOS": (art_loc_aula, "RUANG UTAMA  |  00:10", "Aula utama. Don Vargo menunggu di ujung karpet merah, dikelilingi pengawalnya. Tidak ada jalan mundur.")}

def begin_cutscene(kind):
    fl = DIFF.get("floors", 3)
    if kind == "intro":
        sc = [(art_night, "23:40  |  KEDIAMAN DON VARGO", "Pukul 23.40. Di balik pagar tinggi itu berdiri mansion DON VARGO, bos komplotan perdagangan senjata gelap.", None),
              (art_dosir, "ARSIP MARKAS PUSAT  |  DOSIR", "Bukti kejahatannya tersimpan di dalam mansion, dijaga puluhan anak buah bersenjata. Dia buronan nomor satu.", 1.2),
              (art_brief, "RUANG BRIEFING  |  SALURAN RADIO", f"Markas: Masuki mansion, telusuri jaringannya di {fl} lokasi, lalu hadapi Don Vargo di ruang utama mansionnya. Tingkat bahaya: {P.diff}.", None),
              (art_gate, "GERBANG UTAMA  |  23:58", "Tidak ada bala bantuan sampai misi selesai. Kamu Agen. Waktunya bertugas.", None)]
    elif kind == "loc": art, lab, tx_ = LOCS[P.stage]; sc = [(art, lab, tx_, None)]
    else:
        sc = [(art_down, "RUANG BOS  |  00:47", "Don Vargo tumbang. Anak buahnya yang tersisa kabur, dan tak seorang pun berani melawan lagi.", None),
              (art_docs, "BUKTI  |  KOPER VARGO", "Buku besar, daftar pembeli, dan rekening gelapnya kini ada di tanganmu.", 1.0),
              (art_dawn, "FAJAR  |  05:30", "Pasukan pendukung tiba saat fajar. Komplotan perdagangan senjata itu runtuh dalam semalam.", None),
              (art_walk, "KELUAR MANSION  |  06:02", "Misi selesai, Agen. Dunia sedikit lebih aman pagi ini.", None)]
    P.state = "cut"; P.cut = dict(kind=kind, sc=sc, i=0, t=0.0, chars=0, stamped=False, lines=wrap(sc[0][2], font, 740))

def cut_end():
    k = P.cut["kind"]
    if k == "intro": begin_cutscene("loc")                        # setelah intro: cutscene lokasi pertama
    elif k == "loc": P.state = "play"; P.inv = 2.0
    else: P.state = "ending"

def cut_next():                                # lanjut: pertama selesaikan teks, lalu panel berikutnya
    C = P.cut
    if C["chars"] < len(C["sc"][C["i"]][2]): C["chars"] = len(C["sc"][C["i"]][2]); return
    C["i"] += 1; play("clink")
    if C["i"] >= len(C["sc"]): return cut_end()
    C.update(t=0.0, chars=0, stamped=False, lines=wrap(C["sc"][C["i"]][2], font, 740))

def cut_event(e):
    if e.type == pg.KEYDOWN:
        if e.key == pg.K_ESCAPE: cut_end()
        elif e.key in (pg.K_RETURN, pg.K_SPACE): cut_next()
    elif e.type == pg.MOUSEBUTTONDOWN and e.button == 1: cut_next()

def draw_cut(dt):
    C = P.cut; C["t"] += dt; t = C["t"]; art, lab, text, st = C["sc"][C["i"]]; sw, sh = screen.get_size(); C["chars"] = max(C["chars"], int(t * 42))
    pic = pg.Surface((640, 360)); art(pic, t)
    if st and t > st and not C["stamped"]: C["stamped"] = True; play("thud")
    lb = small.render(lab, True, (235, 225, 190)); D.rect(pic, (0, 0, 0), (0, 0, lb.get_width() + 20, 26)); pic.blit(lb, (10, 5))      # keterangan foto
    for _ in range(40): D.circle(pic, (200, 190, 170), (random.randint(0, 639), random.randint(0, 359)), 1)                            # butiran film
    if random.random() < .3: x = random.randint(0, 639); D.line(pic, (190, 180, 160), (x, 0), (x, 359), 1)                              # goresan film
    pic.fill((255, 238, 212), special_flags=pg.BLEND_RGB_MULT)                                                                          # nuansa foto lama
    screen.fill((6, 5, 8)); z = 1 + .05 * min(1.0, t / 7); w2, h2 = int(640 * z), int(360 * z)
    D.rect(screen, (30, 26, 26), (146, 30, 668, 388)); D.rect(screen, (238, 232, 218), (150, 26, 660, 380))                                # bingkai foto
    screen.blit(pg.transform.scale(pic, (w2, h2)), (160, 36), pg.Rect((w2 - 640) // 2, (h2 - 360) // 2, 640, 360))
    D.rect(screen, (16, 12, 14), (90, 436, 780, 110)); D.rect(screen, (150, 120, 70), (90, 436, 780, 110), 2); n = C["chars"]
    for k, ln in enumerate(C["lines"]): txt(ln[:max(0, n)], (110, 450 + k * 30), font); n -= len(ln) + 1
    txt(f"{C['i'] + 1} / {len(C['sc'])}", (750, 410), small, (170, 150, 120)); center("ENTER / klik = lanjut     ESC = lewati", 560, small, (170, 150, 120))
    a = int(255 * max(0.0, 1 - t / .6))
    if a > 0: o = pg.Surface((sw, sh)); o.fill((0, 0, 0)); o.set_alpha(a); screen.blit(o, (0, 0))

def make_agent_art():                          # ilustrasi agen beraksi: melangkah, menembak, jas & dasi berkibar
    p = pg.Surface((330, 500)); grad(p, (8, 10, 26), (64, 34, 42), 0, 500); stars(p, 0, 40); D.circle(p, (60, 58, 80), (262, 70), 34); D.circle(p, (235, 235, 210), (262, 70), 24)
    house(p, 210, 400, .6, True, (10, 8, 12), 0); D.rect(p, (6, 6, 8), (0, 400, 330, 100))
    beam = pg.Surface((330, 500), pg.SRCALPHA); D.polygon(beam, (255, 245, 200, 40), [(20, 440), (0, 300), (170, 120), (260, 330)]); p.blit(beam, (0, 0))
    suit, suit2, skin = (14, 14, 20), (30, 30, 40), (212, 160, 126)
    D.polygon(p, suit, [(130, 380), (158, 380), (118, 470), (92, 466)]); D.polygon(p, suit, [(158, 380), (184, 378), (214, 448), (190, 456)])
    D.polygon(p, (6, 6, 8), [(84, 464), (122, 470), (116, 484), (80, 480)]); D.polygon(p, (6, 6, 8), [(188, 452), (226, 444), (232, 460), (192, 468)])
    D.polygon(p, suit2, [(126, 372), (196, 366), (214, 430), (116, 440)]); D.polygon(p, suit, [(124, 250), (188, 244), (200, 385), (130, 392)])
    D.polygon(p, (236, 236, 242), [(158, 254), (184, 250), (172, 304)]); D.polygon(p, (170, 20, 30), [(168, 262), (178, 262), (132, 322), (120, 310)])
    D.polygon(p, suit2, [(180, 256), (190, 274), (276, 252), (268, 234)]); D.polygon(p, suit, [(166, 262), (156, 284), (262, 254), (270, 240)])
    D.circle(p, skin, (278, 244), 9); D.polygon(p, (22, 22, 26), [(268, 226), (322, 226), (322, 242), (292, 244), (286, 266), (268, 266), (268, 242)])
    D.ellipse(p, skin, (146, 186, 52, 62)); D.ellipse(p, (24, 18, 14), (142, 172, 58, 36)); D.rect(p, (8, 8, 10), (158, 208, 38, 12)); D.line(p, (130, 80, 70), (170, 238), (184, 236), 2)
    for k in range(3): D.rect(p, (230, 190, 70), (232 - k * 16, 196 + k * 18, 8, 4))
    for x, y in ((126, 250), (198, 384)): D.line(p, (70, 90, 140), (x, y), (x + 6, y + 60), 2)
    return p
AGENT_ART = make_agent_art()

def star(cx, cy, r, col):
    D.polygon(screen, col, [(cx + math.cos(-math.pi / 2 + k * math.pi / 5) * (r if k % 2 == 0 else r * .45), cy + math.sin(-math.pi / 2 + k * math.pi / 5) * (r if k % 2 == 0 else r * .45)) for k in range(10)])

def card_icon(kind, cx, cy, on):               # gambar di bagian atas kartu mode
    g = (235, 200, 110) if on else (140, 120, 90); bg = (46, 24, 26) if on else (22, 16, 18)
    if kind == "campaign":
        for r_ in (46, 30): D.circle(screen, g, (cx, cy), r_, 3)
        D.circle(screen, (220, 50, 50), (cx, cy), 8); D.line(screen, g, (cx - 56, cy), (cx - 20, cy), 3); D.line(screen, g, (cx + 20, cy), (cx + 56, cy), 3); D.line(screen, g, (cx, cy - 56), (cx, cy - 20), 3); D.line(screen, g, (cx, cy + 20), (cx, cy + 56), 3)
    elif kind == "mp":
        for sx, col in ((-30, (70, 130, 230)), (30, (220, 70, 60))):
            D.circle(screen, col, (cx + sx, cy - 14), 14); D.polygon(screen, col, [(cx + sx - 22, cy + 34), (cx + sx - 16, cy + 6), (cx + sx + 16, cy + 6), (cx + sx + 22, cy + 34)])
        D.line(screen, g, (cx - 8, cy - 24), (cx + 8, cy - 4), 3); D.line(screen, g, (cx + 8, cy - 24), (cx - 8, cy - 4), 3)
    elif kind == "solo":
        D.circle(screen, (70, 130, 230), (cx, cy - 18), 15); D.polygon(screen, (70, 130, 230), [(cx - 26, cy + 40), (cx - 18, cy + 4), (cx + 18, cy + 4), (cx + 26, cy + 40)])
    elif kind == "split":
        for sx, col in ((-34, (70, 130, 230)), (34, (230, 190, 70))):
            D.rect(screen, g, (cx + sx - 30, cy - 36, 60, 76), 3); D.circle(screen, col, (cx + sx, cy - 12), 10); D.polygon(screen, col, [(cx + sx - 18, cy + 34), (cx + sx - 12, cy + 6), (cx + sx + 12, cy + 6), (cx + sx + 18, cy + 34)])
    elif kind == "settings":
        D.circle(screen, g, (cx, cy), 28)
        for k in range(8): D.circle(screen, g, (int(cx + math.cos(k * math.pi / 4) * 36), int(cy + math.sin(k * math.pi / 4) * 36)), 9)
        D.circle(screen, bg, (cx, cy), 12)
    elif kind == "quit":
        D.rect(screen, g, (cx - 30, cy - 44, 44, 88), 4); D.polygon(screen, (220, 70, 60), [(cx + 2, cy - 12), (cx + 30, cy - 12), (cx + 30, cy - 24), (cx + 54, cy), (cx + 30, cy + 24), (cx + 30, cy + 12), (cx + 2, cy + 12)])
    elif kind in ("easy", "medium", "hard"):
        n = ("easy", "medium", "hard").index(kind) + 1; col = ((90, 210, 110), (240, 200, 70), (230, 70, 60))[n - 1] if on else (110, 100, 80)
        for k in range(n): star(int(cx + (k - (n - 1) / 2) * 38), cy, 20, col)
    elif kind == "name":
        D.rect(screen, g, (cx - 38, cy - 26, 76, 52), 3); D.circle(screen, g, (cx - 18, cy - 6), 8, 3); D.rect(screen, g, (cx - 28, cy + 6, 20, 8), 3)
        for k in range(3): D.line(screen, g, (cx + 2, cy - 14 + k * 11), (cx + 28, cy - 14 + k * 11), 3)
    elif kind == "host":
        for k in range(3): D.rect(screen, g, (cx - 34, cy - 40 + k * 28, 68, 22), 3); D.circle(screen, (90, 230, 120), (cx + 22, cy - 29 + k * 28), 4)
    elif kind == "join":
        D.circle(screen, g, (cx - 16, cy), 26, 5); D.circle(screen, g, (cx + 16, cy), 26, 5)
    else:
        D.polygon(screen, g, [(cx - 40, cy), (cx - 8, cy - 32), (cx - 8, cy - 14), (cx + 38, cy - 14), (cx + 38, cy + 14), (cx - 8, cy + 14), (cx - 8, cy + 32)])

MAPS = ["RUMAH", "PEDESAAN", "HUTAN", "KOTA", "SEKOLAH", "BANDARA", "MANSION", "ARENA"]
MENUS = {"main": [("CAMPAIGN", "", "campaign"), ("CO-OP", "", "coop"), ("MULTIPLAYER", "", "mp"), ("SETTINGS", "", "settings"), ("QUIT", "", "quit")],
         "players": [("SOLO", "1 pemain", "solo"), ("CO-OP", "split screen", "split"), ("BACK", "", "back")],
         "mp": [("HOST", "buat match", "host"), ("JOIN", "masuk lewat IP", "join"), ("BACK", "", "back")]}
CARD_DESC = {"CAMPAIGN": "Misi: telusuri lokasi demi lokasi sampai ruang utama Don Vargo (main sendiri)", "SOLO": "Satu pemain, layar penuh", "CO-OP": "Split screen: dua pemain di satu layar: P1 keyboard + mouse, P2 controller (atau dua controller)", "MULTIPLAYER": "Deathmatch LAN 2-4 pemain, atau tim 5 VS 5 / 10 VS 10 tanpa friendly fire, dengan sampai 20 bot",
             "SETTINGS": "Atur kontrol, sensitivitas mouse, dan volume", "QUIT": "Keluar dari game", "HOST": "Buat match, teman bisa masuk dari WiFi mana pun lewat alamat internet di lobi", "USERNAME": "Nama yang tampil di atas kepala, papan skor, dan daftar kill",
             "JOIN": "Masuk ke match temanmu dengan alamat host (IP LAN atau alamat internet)", "BACK": "Kembali ke menu sebelumnya"}

def menu_items(S):
    if S["mode"] == "mp": return [("HOST", "buat match", "host"), ("JOIN", "masuk lewat IP", "join"), ("USERNAME", CFG["name"], "name"), ("BACK", "", "back")]
    if S["mode"] == "diff": return [(k, f"{len(v['stages'])} lokasi + bos", k.lower()) for k, v in DIFFS.items()] + [("BACK", "", "back")]
    return MENUS[S["mode"]]

# ================= MENU UTAMA ala "HQ": kartu bergambar + potret agen di kiri + judul di kiri bawah =================
# Semua gambar dibuat lewat kode. Mau pakai gambar sendiri? Buat folder "gambar" di samping file game ini lalu isi (png / jpg):
#   agent.png (potret kiri, tinggi ~560)  background.png  campaign.png  multiplayer.png  settings.png  quit.png  (kartu lain: host, join, name, back, solo, split, easy, medium, hard)
try: ART_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gambar")
except NameError: ART_DIR = "gambar"

def load_img(name, w, h, fit=False):           # gambar buatan sendiri (opsional); None jika tidak ada
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        fp = os.path.join(ART_DIR, name + ext)
        if not os.path.isfile(fp): continue
        try:
            im = pg.image.load(fp).convert_alpha(); iw, ih = im.get_size(); k = (h / ih) if fit else max(w / iw, h / ih)
            im = pg.transform.smoothscale(im, (max(1, int(iw * k)), max(1, int(ih * k))))
            if fit: return im
            out = pg.Surface((w, h)); out.blit(im, ((w - im.get_width()) // 2, (h - im.get_height()) // 2)); return out
        except Exception: return None
    return None

def vgrad(s, c1, c2, y0=0, y1=None):           # gradasi vertikal
    y1 = s.get_height() if y1 is None else y1; w = s.get_width()
    for y in range(y0, y1): k = (y - y0) / max(1, y1 - y0 - 1); D.line(s, tuple(int(a + (b - a) * k) for a, b in zip(c1, c2)), (0, y), (w, y))

def glow(s, cx, cy, r, col, a=90):             # cahaya bulat lembut
    o = pg.Surface((r * 2, r * 2), pg.SRCALPHA)
    for k in range(r, 0, -max(1, r // 20)): D.circle(o, (col[0], col[1], col[2], min(255, int(a * (1 - k / r) ** 1.5) + 1)), (r, r), k)
    s.blit(o, (cx - r, cy - r))

def shade_bottom(s, y0, a=215):                # bagian bawah kartu digelapkan agar teks terbaca
    W, H = s.get_size(); o = pg.Surface((W, H - y0), pg.SRCALPHA)
    for y in range(H - y0): D.line(o, (0, 0, 0, int(a * (y / max(1, H - y0 - 1)) ** 1.3)), (0, y), (W, y))
    s.blit(o, (0, y0))

def flash(s, x, y, r):                         # kilatan moncong senjata
    D.polygon(s, (255, 214, 90), [(x + math.cos(k * math.pi / 4) * (r if k % 2 == 0 else r * .4), y + math.sin(k * math.pi / 4) * (r if k % 2 == 0 else r * .4)) for k in range(8)]); D.circle(s, (255, 252, 230), (int(x), int(y)), max(2, int(r * .35)))

def agent_sil(s, x, base, hgt, col, rim, face=1, gun=True):      # siluet agen (jas): face = +1 menghadap kanan, -1 kiri
    u = hgt / 100.0; P = lambda *pts: [(int(x + face * px * u), int(base - py * u)) for px, py in pts]
    D.polygon(s, col, P((-9, 0), (-2, 0), (3, 44), (-10, 46))); D.polygon(s, col, P((2, 0), (11, 0), (11, 46), (0, 46)))
    D.polygon(s, col, P((-13, 44), (13, 44), (15, 79), (-15, 79))); D.circle(s, col, (int(x), int(base - 89 * u)), max(2, int(9 * u)))
    if gun:
        D.polygon(s, col, P((4, 77), (9, 73), (43, 80), (41, 84))); D.polygon(s, col, P((40, 79), (57, 82), (57, 86), (40, 85))); D.polygon(s, col, P((42, 80), (47, 80), (45, 72), (41, 72)))
    else: D.polygon(s, col, P((10, 76), (15, 72), (17, 50), (12, 50)))
    D.polygon(s, (150, 20, 28), P((0, 78), (3, 78), (2, 60), (0, 62)))
    D.line(s, rim, P((-15, 79))[0], P((-13, 44))[0], max(1, int(1.6 * u))); D.line(s, rim, P((-9, 96))[0], P((-4, 97))[0], max(1, int(1.6 * u)))

def art_campaign(s):                           # mansion malam hari, agen berjalan dengan senter
    W, H = s.get_size(); X = lambda v: int(W * v); Y = lambda v: int(H * v); r = random.Random(11); hz = Y(.63)
    vgrad(s, (5, 7, 18), (120, 34, 32), 0, hz); D.rect(s, (7, 5, 8), (0, hz, W, H - hz))
    for _ in range(28): D.circle(s, (200, 200, 225), (r.randint(0, W), r.randint(0, Y(.3))), max(1, W // 190))
    glow(s, X(.74), Y(.15), X(.34), (255, 225, 200), 120); D.circle(s, (242, 238, 222), (X(.74), Y(.15)), X(.07)); c = (6, 4, 8)
    D.rect(s, c, (X(.20), Y(.47), X(.60), hz - Y(.47) + 2)); D.polygon(s, c, [(X(.15), Y(.47)), (X(.5), Y(.37)), (X(.85), Y(.47))])
    D.rect(s, c, (X(.43), Y(.29), X(.14), Y(.12))); D.polygon(s, c, [(X(.41), Y(.29)), (X(.5), Y(.21)), (X(.59), Y(.29))])
    D.rect(s, c, (X(.04), Y(.53), X(.17), hz - Y(.53) + 2)); D.rect(s, c, (X(.79), Y(.53), X(.17), hz - Y(.53) + 2))
    D.polygon(s, c, [(X(.03), Y(.53)), (X(.125), Y(.47)), (X(.22), Y(.53))]); D.polygon(s, c, [(X(.78), Y(.53)), (X(.875), Y(.47)), (X(.97), Y(.53))])
    for wx in (.25, .35, .45, .55, .65, .72, .08, .15, .83, .90):
        for wy in (.505, .575): D.rect(s, (245, 185, 75) if r.random() < .45 else (22, 16, 20), (X(wx), Y(wy), X(.045), Y(.03)))
    D.rect(s, (250, 195, 90), (X(.48), Y(.315), X(.04), Y(.03)))
    for tx in (.0, .1, .9, 1.0): D.polygon(s, (4, 3, 5), [(X(tx - .09), hz + 4), (X(tx), Y(.5)), (X(tx + .09), hz + 4)])
    fog = pg.Surface((W, Y(.12)), pg.SRCALPHA); fog.fill((150, 60, 60, 38)); s.blit(fog, (0, Y(.56))); fog.fill((120, 60, 70, 55)); s.blit(fog, (0, Y(.62)))
    ax, ay, hg = X(.36), Y(.86), Y(.22); agent_sil(s, ax, ay, hg, (3, 3, 5), (190, 50, 50), 1)
    beam = pg.Surface((W, H), pg.SRCALPHA); D.polygon(beam, (255, 240, 190, 55), [(ax + int(.56 * hg), ay - int(.84 * hg)), (W, Y(.60)), (W, Y(.86))]); s.blit(beam, (0, 0))
    shade_bottom(s, Y(.50))

def art_mp(s):                                 # layar terbelah: agen biru vs agen merah saling tembak
    W, H = s.get_size(); X = lambda v: int(W * v); Y = lambda v: int(H * v)
    for y in range(H):
        k = y / H; xd = int(W * (.64 - .28 * k))
        D.line(s, (int(14 + 20 * k), int(34 + 28 * k), int(96 + 50 * (1 - k))), (0, y), (xd, y)); D.line(s, (int(110 - 30 * k), int(18 + 4 * k), int(24 + 6 * k)), (xd, y), (W, y))
    D.line(s, (255, 235, 200), (X(.64), 0), (X(.36), H), max(2, W // 60)); glow(s, X(.5), Y(.36), X(.4), (255, 220, 160), 60)
    hg = Y(.30); b1, b2 = (X(.27), Y(.58)), (X(.73), Y(.62)); agent_sil(s, b1[0], b1[1], hg, (6, 10, 22), (110, 170, 255), 1); agent_sil(s, b2[0], b2[1], hg, (22, 6, 8), (255, 110, 100), -1)
    t1 = (b1[0] + int(.57 * hg), b1[1] - int(.84 * hg)); t2 = (b2[0] - int(.57 * hg), b2[1] - int(.84 * hg)); mid = (X(.5), Y(.36))
    D.line(s, (255, 240, 170), t1, mid, max(2, W // 190)); D.line(s, (255, 190, 150), t2, mid, max(2, W // 190)); flash(s, t1[0], t1[1], X(.07)); flash(s, t2[0], t2[1], X(.07))
    D.circle(s, (255, 255, 255), mid, X(.07), max(2, W // 190)); D.line(s, (255, 255, 255), (mid[0] - X(.11), mid[1]), (mid[0] + X(.11), mid[1]), max(2, W // 190)); D.line(s, (255, 255, 255), (mid[0], mid[1] - X(.11)), (mid[0], mid[1] + X(.11)), max(2, W // 190))
    shade_bottom(s, Y(.48))

def art_settings(s):                           # roda gigi + slider di panel baja
    W, H = s.get_size(); X = lambda v: int(W * v); Y = lambda v: int(H * v); vgrad(s, (16, 18, 26), (44, 38, 34))
    cx, cy, R = X(.5), Y(.30), int(min(W, H) * .22)
    for k in range(10): a = k * math.pi / 5; D.circle(s, (150, 125, 80), (int(cx + math.cos(a) * R * 1.05), int(cy + math.sin(a) * R * 1.05)), int(R * .22))
    D.circle(s, (150, 125, 80), (cx, cy), R); D.circle(s, (92, 76, 52), (cx, cy), int(R * .66)); D.circle(s, (16, 18, 26), (cx, cy), int(R * .3)); D.circle(s, (210, 180, 120), (cx, cy), R, max(2, W // 80))
    for yy, kx in ((.52, .36), (.60, .66), (.68, .5)): D.line(s, (90, 80, 64), (X(.16), Y(yy)), (X(.84), Y(yy)), max(3, W // 60)); D.circle(s, (225, 190, 105), (X(kx), Y(yy)), max(4, X(.05)))
    shade_bottom(s, Y(.55))

def art_quit(s):                               # pintu keluar bercahaya, agen melangkah keluar
    W, H = s.get_size(); X = lambda v: int(W * v); Y = lambda v: int(H * v); vgrad(s, (34, 10, 12), (8, 6, 8)); fr = pg.Rect(X(.2), Y(.1), X(.6), Y(.46))
    D.rect(s, (16, 11, 11), fr.inflate(X(.07), Y(.04)))
    for y in range(fr.top, fr.bottom): k = (y - fr.top) / fr.h; D.line(s, (255, int(236 - 70 * k), int(176 - 100 * k)), (fr.left, y), (fr.right, y))
    glow(s, fr.centerx, fr.centery, int(W * .55), (255, 210, 140), 70); agent_sil(s, fr.centerx, fr.bottom, Y(.28), (4, 3, 5), (255, 200, 120), 1, False); shade_bottom(s, Y(.5))

def art_coop(s):                               # CO-OP: dua layar split screen (P1 biru, P2 emas) + dua agen satu regu menembak ke arah musuh
    W, H = s.get_size(); X = lambda v: int(W * v); Y = lambda v: int(H * v); lw = max(2, W // 95); vgrad(s, (8, 10, 22), (58, 18, 22)); glow(s, X(.5), Y(.22), X(.6), (255, 190, 130), 60)
    for px, col, rim in ((.04, (70, 130, 230), (150, 195, 255)), (.52, (232, 190, 70), (255, 228, 150))):
        r = pg.Rect(X(px), Y(.05), X(.44), Y(.31)); hz = r.top + int(r.h * .56)
        for y in range(r.top, r.bottom): k = (y - r.top) / r.h; D.line(s, (int(12 + 34 * k + col[0] * .10), int(12 + 18 * k + col[1] * .08), int(28 + 22 * k + col[2] * .12)), (r.left, y), (r.right, y))
        D.rect(s, (22, 16, 20), (r.left, hz, r.w, r.bottom - hz))
        for i in range(-3, 4): D.line(s, (74, 60, 66), (r.centerx + i * r.w // 14, hz), (r.centerx + i * r.w // 3, r.bottom), max(1, lw // 2))
        D.rect(s, (12, 9, 13), (r.centerx - r.w // 7, hz - r.h // 4, r.w * 2 // 7, r.h // 4))                       # pintu di ujung lorong
        ex = r.centerx + (r.w // 9 if px < .5 else -r.w // 9); ey = hz - r.h // 7                                  # musuh (siluet + mata merah)
        D.circle(s, (6, 5, 7), (ex, ey), max(3, r.w // 15)); D.rect(s, (6, 5, 7), (ex - r.w // 13, ey + r.w // 18, r.w * 2 // 13, r.h // 5))
        for dx in (-2, 2): D.circle(s, (255, 70, 60), (ex + dx * max(1, W // 120), ey), max(1, W // 160))
        cx_, cy_ = r.centerx, hz - r.h // 9; g_, l_ = X(.012), X(.05)                                              # crosshair mini
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)): D.line(s, (255, 255, 255), (cx_ + dx * g_, cy_ + dy * g_), (cx_ + dx * l_, cy_ + dy * l_), max(1, lw // 2))
        D.circle(s, rim, (r.left + X(.045), r.top + Y(.032)), max(3, W // 55)); D.rect(s, col, r, lw)
    D.line(s, (255, 235, 200), (X(.5), Y(.04)), (X(.5), Y(.37)), max(1, lw // 2))
    red = (X(.97), Y(.66)); glow(s, red[0], red[1], X(.30), (255, 60, 50), 110)
    for (ax, bs, hg, rim) in ((X(.27), Y(.93), Y(.34), (130, 180, 255)), (X(.56), Y(.88), Y(.30), (255, 215, 120))):
        agent_sil(s, ax, bs, hg, (4, 5, 10), rim, 1); u = hg / 100.0; tx, ty = ax + int(57 * u), bs - int(84 * u)
        D.line(s, (255, 240, 170), (tx, ty), red, max(1, lw // 2)); flash(s, tx, ty, X(.05))
    shade_bottom(s, Y(.50))

TINT = {"host": (20, 60, 50), "join": (22, 44, 80), "name": (70, 56, 22), "back": (46, 46, 52), "solo": (22, 44, 80), "split": (60, 44, 22), "easy": (22, 64, 36), "medium": (70, 60, 20), "hard": (80, 24, 24)}
def art_generic(s, kind):                      # latar kartu lain: gradasi warna + garis diagonal
    W, H = s.get_size(); c = TINT.get(kind, (46, 30, 30)); vgrad(s, tuple(min(255, int(v * 1.7)) for v in c), tuple(int(v * .3) for v in c))
    o = pg.Surface((W, H), pg.SRCALPHA)
    for x in range(-H, W, max(8, int(W * .16))): D.line(o, (255, 255, 255, 14), (x, H), (x + H, 0), max(2, W // 40))
    s.blit(o, (0, 0)); glow(s, W // 2, int(H * .3), int(W * .5), tuple(min(255, v * 3) for v in c), 80); shade_bottom(s, int(H * .5), 190)

ART_FILE = {"mp": "multiplayer"}
def art_diff(s, lv):                           # gambar kartu kesulitan: 0 = mudah (siang, 1 musuh), 1 = sedang (senja kota, 3 musuh), 2 = sulit (neraka, tengkorak, banyak musuh)
    W, H = s.get_size(); X = lambda v: int(W * v); Y = lambda v: int(H * v); r = random.Random(30 + lv); hz = Y(.60)
    vgrad(s, ((72, 150, 214), (66, 40, 96), (26, 4, 8))[lv], ((252, 226, 160), (252, 142, 72), (176, 26, 20))[lv], 0, hz)
    D.rect(s, ((46, 104, 56), (36, 26, 30), (18, 8, 10))[lv], (0, hz, W, H - hz))
    if lv == 0:
        glow(s, X(.72), Y(.18), X(.30), (255, 240, 170), 120); D.circle(s, (255, 248, 210), (X(.72), Y(.18)), X(.075))
        for cx_, cy_ in ((.2, .14), (.45, .24)):
            for dx, rr in ((-.05, .035), (0, .05), (.05, .035)): D.circle(s, (255, 255, 255), (X(cx_ + dx), Y(cy_)), X(rr))
        D.polygon(s, (60, 130, 70), [(0, hz), (X(.25), Y(.44)), (X(.6), hz)]); D.polygon(s, (74, 150, 82), [(X(.35), hz), (X(.7), Y(.47)), (W, hz)])
        D.rect(s, (150, 104, 62), (X(.66), Y(.47), X(.2), Y(.13))); D.polygon(s, (170, 54, 46), [(X(.63), Y(.47)), (X(.76), Y(.37)), (X(.89), Y(.47))]); D.rect(s, (255, 214, 120), (X(.72), Y(.51), X(.05), Y(.05)))
        for k in range(7): D.circle(s, (255, 90 + 20 * k % 80, 120), (r.randint(X(.03), X(.97)), r.randint(Y(.66), Y(.9))), max(2, W // 90))
    elif lv == 1:
        glow(s, X(.5), hz, X(.55), (255, 150, 70), 130); D.circle(s, (255, 190, 100), (X(.5), hz - Y(.02)), X(.13))
        x = 0
        while x < W:
            w_ = r.randint(X(.06), X(.11)); h_ = r.randint(Y(.12), Y(.34)); D.rect(s, (20, 14, 28), (x, hz - h_, w_, h_ + 2))
            for wy in range(hz - h_ + 8, hz - 6, 14):
                for wx in range(x + 5, x + w_ - 6, 11):
                    if r.random() < .4: D.rect(s, (250, 196, 96), (wx, wy, 5, 7))
            x += w_ + 3
        for bx, by in ((.08, .78), (.9, .74)): D.rect(s, (80, 56, 40), (X(bx), Y(by), X(.09), Y(.07))); D.rect(s, (130, 94, 60), (X(bx), Y(by), X(.09), Y(.07)), 2)
    else:
        glow(s, X(.5), Y(.24), X(.55), (255, 40, 30), 150); D.circle(s, (170, 20, 20), (X(.5), Y(.24)), X(.2)); D.circle(s, (232, 228, 220), (X(.5), Y(.23)), X(.15))
        D.rect(s, (232, 228, 220), (X(.42), Y(.31), X(.16), Y(.07))); D.circle(s, (20, 4, 6), (X(.44), Y(.22)), X(.04)); D.circle(s, (20, 4, 6), (X(.56), Y(.22)), X(.04))
        D.polygon(s, (20, 4, 6), [(X(.5), Y(.26)), (X(.47), Y(.31)), (X(.53), Y(.31))])
        for k in range(5): D.line(s, (20, 4, 6), (X(.44 + k * .03), Y(.32)), (X(.44 + k * .03), Y(.37)), max(2, W // 80))
        x = 0
        while x < W:
            w_ = r.randint(X(.05), X(.1)); h_ = r.randint(Y(.08), Y(.26)); D.polygon(s, (10, 4, 6), [(x, hz + 2), (x, hz - h_), (x + w_ // 2, hz - h_ - r.randint(0, Y(.05))), (x + w_, hz - h_ + r.randint(0, Y(.04))), (x + w_, hz + 2)]); x += w_ + 2
        for fx in (.12, .3, .72, .9):
            glow(s, X(fx), hz, X(.2), (255, 120, 20), 150)
            for k in range(3): D.polygon(s, (255, 150 + k * 35, 30 + k * 40), [(X(fx) - X(.03 - k * .008), hz), (X(fx), hz - Y(.09 - k * .02)), (X(fx) + X(.03 - k * .008), hz)])
    n = (1, 3, 6)[lv]; pos = ((.8,), (.62, .8, .95), (.5, .6, .72, .82, .9, .98))[lv]
    for k in range(n):                                         # musuh: siluet gelap bermata merah
        ex = X(pos[k]); eb = Y(.74 + (k % 2) * .05 + lv * .02); eh = Y(.15 + (k % 2) * .03); u = eh / 100.0
        agent_sil(s, ex, eb, eh, (6, 4, 8), (255, 90, 80) if lv else (150, 220, 150), -1)
        for dx in (-3, 3): D.circle(s, (255, 60, 50), (int(ex + dx * u), int(eb - 89 * u)), max(1, int(2 * u)))
    ax, ab, ah = X(.26), Y(.97), Y(.40); agent_sil(s, ax, ab, ah, (3, 3, 6), ((140, 255, 160), (255, 200, 120), (255, 110, 100))[lv], 1)
    u = ah / 100.0; tx, ty = ax + int(57 * u), ab - int(84 * u)
    if lv: D.line(s, (255, 240, 170), (tx, ty), (X(.8), Y(.80)), max(1, W // 190)); flash(s, tx, ty, X(.05))
    shade_bottom(s, Y(.50))

DIFF_ART = {"easy": 1, "medium": 2, "hard": 3}                 # jumlah bintang kecil di atas nama kesulitan
ART_FN = {"easy": lambda s: art_diff(s, 0), "medium": lambda s: art_diff(s, 1), "hard": lambda s: art_diff(s, 2), "campaign": art_campaign, "coop": art_coop, "mp": art_mp, "settings": art_settings, "quit": art_quit}
ARTC = {}
def card_art(kind, w, h, on):                  # gambar kartu (di-cache); kartu tidak terpilih dibuat lebih gelap
    key = (kind, w, h, on)
    if key in ARTC: return ARTC[key]
    base = ARTC.get((kind, w, h, True))
    if base is None:
        base = load_img(ART_FILE.get(kind, kind), w, h)
        if base is None:
            big = pg.Surface((w * 2, h * 2))                                # digambar 2x lalu dikecilkan = tepi halus
            if kind in ART_FN: ART_FN[kind](big)
            else: art_generic(big, kind)
            base = pg.transform.smoothscale(big, (w, h))
        ARTC[(kind, w, h, True)] = base
    if on: return base
    dim = base.copy(); dim.fill((92, 98, 118), special_flags=pg.BLEND_RGB_MULT); ARTC[key] = dim; return dim

def make_agent_big():                          # potret agen: jas gelap, dasi merah, kacamata hitam, earpiece, pistol di samping wajah
    FW, FH = 380, 580; W, H = FW * 2, FH * 2; s = pg.Surface((W, H), pg.SRCALPHA); X = lambda v: int(W * v); Y = lambda v: int(H * v)
    pts = lambda *p: [(X(a), Y(b)) for a, b in p]; lw = lambda n: max(1, int(n * 2))
    glow(s, X(.5), Y(.36), X(.62), (170, 22, 26), 150); glow(s, X(.3), Y(.72), X(.5), (120, 14, 18), 90)
    D.polygon(s, (16, 16, 22), pts((0, 1), (0, .76), (.10, .65), (.30, .585), (.62, .585), (.80, .64), (.94, .74), (.98, 1)))
    D.polygon(s, (30, 30, 40), pts((.30, .585), (.46, .84), (.40, 1), (.12, 1), (.10, .66))); D.polygon(s, (30, 30, 40), pts((.62, .585), (.46, .84), (.52, 1), (.78, 1), (.82, .66)))
    D.polygon(s, (232, 232, 240), pts((.34, .585), (.58, .585), (.46, .83))); D.polygon(s, (246, 246, 250), pts((.34, .585), (.41, .625), (.44, .585))); D.polygon(s, (246, 246, 250), pts((.58, .585), (.51, .625), (.48, .585)))
    D.polygon(s, (190, 24, 34), pts((.44, .62), (.48, .62), (.495, .665), (.425, .665))); D.polygon(s, (150, 16, 26), pts((.425, .665), (.495, .665), (.525, .81), (.46, .86), (.395, .81)))
    D.line(s, (70, 70, 90), (X(.30), Y(.585)), (X(.46), Y(.84)), lw(1.5)); D.line(s, (70, 70, 90), (X(.62), Y(.585)), (X(.46), Y(.84)), lw(1.5))
    D.polygon(s, (168, 116, 90), pts((.38, .50), (.54, .50), (.57, .595), (.35, .595)))                                         # leher
    for ex in (.262, .658): D.ellipse(s, (192, 138, 106), (X(ex - .02), Y(.355), X(.04), Y(.08)))                              # telinga
    D.ellipse(s, (214, 160, 126), (X(.27), Y(.20), X(.38), Y(.35))); D.polygon(s, (214, 160, 126), pts((.29, .40), (.63, .40), (.58, .53), (.46, .56), (.34, .53)))
    ov = pg.Surface((W, H), pg.SRCALPHA); D.polygon(ov, (70, 20, 20, 95), pts((.50, .20), (.66, .28), (.64, .46), (.58, .53), (.50, .56))); D.polygon(ov, (60, 40, 34, 70), pts((.31, .46), (.61, .46), (.58, .53), (.46, .56), (.34, .53))); s.blit(ov, (0, 0))
    D.polygon(s, (22, 16, 14), pts((.26, .34), (.27, .24), (.34, .17), (.48, .145), (.60, .17), (.66, .25), (.65, .34), (.62, .28), (.50, .24), (.38, .26), (.30, .30)))
    D.polygon(s, (186, 130, 100), pts((.46, .40), (.49, .46), (.44, .465)))
    D.polygon(s, (6, 6, 10), pts((.285, .352), (.64, .352), (.64, .372), (.285, .372))); D.polygon(s, (6, 6, 10), pts((.30, .345), (.45, .345), (.44, .405), (.32, .41))); D.polygon(s, (6, 6, 10), pts((.47, .345), (.62, .345), (.60, .41), (.48, .405)))
    D.line(s, (120, 132, 170), (X(.33), Y(.36)), (X(.38), Y(.348)), lw(2)); D.line(s, (120, 132, 170), (X(.50), Y(.36)), (X(.55), Y(.348)), lw(2))
    D.line(s, (120, 70, 64), (X(.42), Y(.505)), (X(.51), Y(.505)), lw(2))
    D.circle(s, (24, 24, 30), (X(.262), Y(.43)), X(.014)); D.lines(s, (215, 215, 228), False, pts((.262, .44), (.248, .50), (.27, .56), (.315, .60)), lw(1.4))
    D.polygon(s, (16, 16, 22), pts((.62, 1), (.64, .82), (.82, .78), (.96, .80), (.98, 1))); D.polygon(s, (240, 240, 246), pts((.64, .80), (.80, .77), (.81, .80), (.65, .83)))
    D.polygon(s, (28, 28, 34), pts((.69, .62), (.77, .62), (.76, .79), (.66, .79)))                                              # gagang pistol
    D.polygon(s, (196, 142, 110), pts((.64, .68), (.79, .66), (.80, .78), (.70, .84), (.62, .78))); D.ellipse(s, (206, 152, 118), (X(.62), Y(.64), X(.07), Y(.07)))
    D.polygon(s, (46, 48, 58), pts((.695, .36), (.765, .36), (.775, .64), (.685, .64))); D.polygon(s, (118, 124, 142), pts((.705, .37), (.72, .37), (.725, .63), (.71, .63)))
    D.polygon(s, (36, 38, 46), pts((.715, .325), (.745, .325), (.745, .36), (.715, .36)))
    for k in range(5): D.line(s, (24, 26, 32), (X(.735), Y(.54 + k * .018)), (X(.765), Y(.54 + k * .018)), lw(1))
    for a_, b_ in (((.02, .74), (.10, .65)), ((.10, .65), (.30, .585)), ((.275, .30), (.262, .40))): D.line(s, (214, 44, 48), (X(a_[0]), Y(a_[1])), (X(b_[0]), Y(b_[1])), lw(2))   # cahaya merah di tepi kiri
    out = pg.transform.smoothscale(s, (FW, FH))
    for x in range(FW - 90, FW): out.fill((255, 255, 255, int(255 * (FW - x) / 90)), (x, 0, 1, FH), special_flags=pg.BLEND_RGBA_MULT)      # memudar ke kanan
    return out

def make_menu_bg():                            # latar merah gelap berasap + noda cat di sudut (nuansa HQ)
    sw, sh = screen.get_size(); b = pg.Surface((sw, sh)); vgrad(b, (9, 6, 9), (22, 8, 10)); r = random.Random(7); sm = pg.Surface((sw // 4, sh // 4), pg.SRCALPHA)
    for _ in range(80): D.circle(sm, (r.randint(110, 190), r.randint(8, 22), r.randint(12, 26), r.randint(20, 58)), (r.randint(0, sw // 4), int(r.random() ** 2 * sh / 4 * 1.1)), r.randint(6, 28))
    b.blit(pg.transform.smoothscale(sm, (sw, sh)), (0, 0))
    for _ in range(36): x = r.randint(0, sw); L = r.randint(20, 150); D.line(b, (118, 12, 16), (x, 0), (x, L), r.randint(1, 3)); D.circle(b, (118, 12, 16), (x, L), r.randint(2, 4))
    for _ in range(140): D.circle(b, (r.randint(110, 170), 14, 18), (r.randint(sw // 3, sw), r.randint(0, sh // 2)), r.randint(1, 3))
    vg = pg.Surface((sw, sh), pg.SRCALPHA)
    for k in range(40): D.rect(vg, (0, 0, 0, int(150 * (1 - k / 40) ** 2)), (k * 3, k * 2, sw - 2 * k * 3, sh - 2 * k * 2), 3)
    b.blit(vg, (0, 0)); return b

def title_surf(s, size, c1, c2, ol=4):         # teks judul besar: gradasi warna + garis tepi hitam
    f = pg.font.Font(None, size); m = f.render(s, True, (255, 255, 255)); g = pg.Surface(m.get_size()); vgrad(g, c1, c2); m.blit(g, (0, 0), special_flags=pg.BLEND_RGB_MULT)
    k = f.render(s, True, (0, 0, 0)); o = pg.Surface((m.get_width() + ol * 2, m.get_height() + ol * 2), pg.SRCALPHA)
    for dx in range(-ol, ol + 1, 2):
        for dy in range(-ol, ol + 1, 2): o.blit(k, (ol + dx, ol + dy))
    o.blit(m, (ol, ol)); return o

def spaced(s, f, col, sp=3):                   # teks dengan jarak antar huruf
    ch = [f.render(c, True, col) for c in s]; o = pg.Surface((sum(c.get_width() + sp for c in ch), f.get_height()), pg.SRCALPHA); x = 0
    for c in ch: o.blit(c, (x, 0)); x += c.get_width() + sp
    return o

def make_shade():                              # bayangan gelap di kiri bawah agar judul terbaca
    o = pg.Surface((360, 600), pg.SRCALPHA)
    for y in range(600): D.line(o, (0, 0, 0, int(215 * min(1.0, max(0.0, (y - 300) / 260)))), (0, y), (360, y))
    for x in range(260, 360): o.fill((255, 255, 255, int(255 * (360 - x) / 100)), (x, 0, 1, 600), special_flags=pg.BLEND_RGBA_MULT)
    return o

def make_topbar(sw):
    o = pg.Surface((sw, 46), pg.SRCALPHA); o.fill((0, 0, 0, 150)); D.line(o, (110, 40, 40), (0, 45), (sw, 45), 1); return o

cardf, chipf = pg.font.Font(None, 38), pg.font.Font(None, 18)
TAB_OF = {"main": 0, "diff": 1, "players": 1, "mp": 2}
TABR = []                                      # rect tab BERANDA / KAMPANYE / MULTIPLAYER (diisi draw_cards tiap frame, dibaca saat klik)
SEC_TITLE = {"main": "PILIH MODE PERMAINAN", "diff": "PILIH TINGKAT KESULITAN", "mp": "MULTIPLAYER", "players": "JUMLAH PEMAIN"}
CHIPS = {"CAMPAIGN": ("SOLO", "STORY"), "CO-OP": ("SPLIT SCREEN", "2 PEMAIN"), "MULTIPLAYER": ("LAN", "5V5", "10V10")}
EMBERS = [(random.random() * 960, random.random() * 600, .3 + random.random() * .9, random.random() * 6.28, random.choice((1, 1, 2))) for _ in range(46)]
TINTC = {}

def hexagon(cx, cy, r): return [(cx + math.cos(math.pi / 6 + k * math.pi / 3) * r, cy + math.sin(math.pi / 6 + k * math.pi / 3) * r) for k in range(6)]

def emblem_icon(kind, cx, cy, col):            # lambang kecil di dalam segi enam
    if kind == "campaign":
        D.circle(screen, col, (cx, cy), 12, 2); D.circle(screen, (220, 50, 50), (cx, cy), 3)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)): D.line(screen, col, (cx + dx * 8, cy + dy * 8), (cx + dx * 19, cy + dy * 19), 2)
    elif kind == "mp":
        for sx, c in ((-10, (90, 150, 240)), (10, (230, 80, 70))): D.circle(screen, c, (cx + sx, cy - 6), 6); D.polygon(screen, c, [(cx + sx - 9, cy + 15), (cx + sx - 6, cy + 3), (cx + sx + 6, cy + 3), (cx + sx + 9, cy + 15)])
    elif kind == "coop":                                                   # dua agen bersebelahan (biru + emas) dibatasi garis layar terbelah
        for sx, c in ((-9, (90, 150, 240)), (9, (235, 195, 80))): D.circle(screen, c, (cx + sx, cy - 6), 6); D.polygon(screen, c, [(cx + sx - 8, cy + 15), (cx + sx - 5, cy + 3), (cx + sx + 5, cy + 3), (cx + sx + 8, cy + 15)])
        D.line(screen, col, (cx, cy - 16), (cx, cy + 16), 2)

def corner_btn(r, kind, on):                   # kotak kecil di pojok kanan atas: SETTINGS (roda gigi emas) dan QUIT (silang merah); terang saat dipilih
    acc = (235, 200, 110) if kind == "settings" else (240, 90, 80); bg = (62, 120, 168) if on else (26, 20, 22); ic = (255, 255, 255) if on else acc; cx, cy = r.center
    D.rect(screen, bg, r); D.rect(screen, (150, 200, 235) if on else acc, r, 2)
    if kind == "settings":
        for k in range(8): D.circle(screen, ic, (int(cx + math.cos(k * math.pi / 4) * 9), int(cy + math.sin(k * math.pi / 4) * 9)), 2)
        D.circle(screen, ic, (cx, cy), 6); D.circle(screen, bg, (cx, cy), 2)
    else: D.line(screen, ic, (cx - 7, cy - 7), (cx + 7, cy + 7), 3); D.line(screen, ic, (cx - 7, cy + 7), (cx + 7, cy - 7), 3)

def draw_cards(S, t):                          # menu bergaya HQ: potret agen kiri, judul kiri bawah, kartu bergambar di kanan
    sw, sh = screen.get_size(); mode = S["mode"]; screen.blit(BG, (0, 0))
    for x0, y0, sp, ph, sz in EMBERS:                                      # bara api melayang
        c = int(150 + 90 * math.sin(t * 3 + ph)); D.circle(screen, (min(255, c + 60), int(c * .45), 30), (int(x0 + math.sin(t * .7 + ph) * 14), int((y0 - t * sp * 30) % sh)), sz)
    screen.blit(AGENT_BIG, (-34, sh - AGENT_BIG.get_height() + 8)); screen.blit(LEFT_SHADE, (0, sh - 600))
    lb, s1, s2 = TITLE; y2 = 574 - s2.get_height(); y1 = y2 - s1.get_height() + 22; screen.blit(s2, (46, y2)); screen.blit(s1, (46, y1)); D.rect(screen, (200, 50, 46), (52, y1 - 20, 22, 4)); screen.blit(lb, (82, y1 - 26))
    screen.blit(TOPBAR, (0, 0)); screen.blit(LOGO, (18 if mode == "main" else 52, 15)); tw_ = 122; tx_ = (sw - 3 * tw_) // 2                      # bilah atas: logo, tab, nama pemain
    TABR.clear(); mp_ = mpos()
    for i, nm in enumerate(("BERANDA", "KAMPANYE", "MULTIPLAYER")):
        on = i == TAB_OF.get(mode, 0); r = pg.Rect(tx_ + i * tw_, 8, tw_ - 6, 30); TABR.append(r); hv = r.collidepoint(mp_) and not on
        D.rect(screen, (62, 120, 168) if on else (44, 70, 96) if hv else (26, 20, 22), r); D.rect(screen, (150, 200, 235) if on else (120, 170, 210) if hv else (70, 60, 60), r, 1)
        txt(nm, (r.centerx - small.size(nm)[0] // 2, r.y + 8), small, (255, 255, 255) if on or hv else (150, 140, 135))
    nm = CFG["name"]; cw_ = max(120, small.size(nm)[0] + 54); r = pg.Rect(sw - 16 - cw_ - (106 if mode == "main" else 0), 8, cw_, 30); D.rect(screen, (26, 20, 22), r); D.rect(screen, (120, 100, 80), r, 1)
    D.circle(screen, (70, 130, 230), (r.x + 18, r.centery - 3), 6); D.polygon(screen, (70, 130, 230), [(r.x + 8, r.bottom - 4), (r.x + 11, r.centery + 3), (r.x + 25, r.centery + 3), (r.x + 28, r.bottom - 4)]); txt(nm, (r.x + 38, r.y + 8), small, (235, 225, 205))
    items = menu_items(S); n = nb = len(items); gap = 12; hh = 372; y0 = 92
    if mode != "main": nb = n - 1                                          # BACK bukan kartu: jadi tombol panah di pojok kiri atas
    if mode == "main": nb = 3                                              # 3 kartu besar (CAMPAIGN, CO-OP, MULTIPLAYER); SETTINGS & QUIT = kotak kecil di pojok kanan atas
    ws = [188] * nb if mode == "main" else [min(204, (636 - gap * (nb - 1)) // nb)] * nb
    total = sum(ws) + gap * (nb - 1); x = 940 - total; xs = x; cxm = xs + total // 2; rects = []; pul = .75 + .25 * math.sin(t * 5)
    txt(SEC_TITLE.get(mode, ""), (xs, 62), small, (200, 180, 150))
    for i, (label, sub, kind) in enumerate(items[:nb]):
        w = ws[i]; on = i == S["sel"]; base = pg.Rect(x, y0, w, hh); rects.append(base); r = base.move(0, -10 if on else 0); cx = r.centerx
        screen.blit(card_art(kind, w, hh, on), r.topleft)
        if on:
            if (w, hh) not in TINTC: o = pg.Surface((w, hh), pg.SRCALPHA); o.fill((110, 170, 220, 34)); TINTC[(w, hh)] = o
            screen.blit(TINTC[(w, hh)], r.topleft)
        if kind in DIFF_ART:                                                   # tingkat kesulitan: gambar penuh + bintang kecil di atas nama
            sc_ = ((90, 210, 110), (240, 200, 70), (230, 70, 60))[DIFF_ART[kind] - 1] if on else (130, 124, 110); k_n = DIFF_ART[kind]
            for k_ in range(k_n): star(int(cx + (k_ - (k_n - 1) / 2) * 30), r.y + int(hh * .60) - 22, 12, sc_)
        elif kind in ART_FN:
            if w >= 150: ey = r.y + int(hh * .47); D.polygon(screen, (22, 14, 16), hexagon(cx, ey, 34)); D.polygon(screen, (235, 200, 110) if on else (150, 125, 95), hexagon(cx, ey, 34), 3); emblem_icon(kind, cx, ey, (255, 235, 180) if on else (170, 150, 120))
        else: card_icon(kind, cx, r.y + 112, on)
        f = cardf if cardf.size(label)[0] <= w - 14 else font; ly = r.y + int(hh * .60)
        txt(label, (cx - f.size(label)[0] // 2, ly), f, (255, 255, 255) if on else (150, 150, 162))
        cs = list(CHIPS.get(label, ())) if mode == "main" else []
        if cs:
            wd = [chipf.size(c)[0] + 10 for c in cs]
            while len(cs) > 1 and sum(wd) + 4 * (len(cs) - 1) > w - 8: cs.pop(); wd.pop()
            xx = cx - (sum(wd) + 4 * (len(cs) - 1)) // 2
            for c, ww in zip(cs, wd): D.rect(screen, (14, 16, 22), (xx, ly + 36, ww, 18)); D.rect(screen, (100, 112, 135), (xx, ly + 36, ww, 18), 1); screen.blit(chipf.render(c, True, (205, 210, 222)), (xx + 5, ly + 39)); xx += ww + 4
        elif sub: txt(sub, (cx - small.size(sub)[0] // 2, ly + 34), small, (230, 200, 120) if on else (130, 118, 100))
        if on:
            sb = pg.Rect(r.x, r.bottom - 30, w, 30); D.rect(screen, (62, 120, 168), sb); D.circle(screen, (235, 245, 255), (sb.x + 16, sb.centery), 8, 2); txt("PILIH", (sb.x + 32, sb.y + 8), small, (255, 255, 255))
            D.rect(screen, (int(150 + 90 * pul), int(190 + 50 * pul), 255), r, 3)
        else: D.rect(screen, (74, 66, 70), r, 1)
        x += w + gap
    for i in range(nb): D.rect(screen, (230, 240, 255) if i == S["sel"] else (90, 90, 100), (cxm - (nb * 28 - 6) // 2 + i * 28, y0 + hh + 12, 22, 4))        # indikator halaman
    if mode == "main":
        for j, (lab_, kd_) in enumerate((("SETTINGS", "settings"), ("QUIT", "quit"))):
            i = nb + j; on = S["sel"] == i; r = pg.Rect(sw - 16 - 44 - (44 + 8) * (1 - j), 8, 44, 30); rects.append(r); corner_btn(r, kd_, on)
            if on: txt(lab_, (r.right - small.size(lab_)[0], r.bottom + 12), small, (255, 235, 180))
    if mode != "main":                                                     # tombol kembali: kotak panah di pojok kiri atas (sama dengan di lobi)
        on = S["sel"] == nb; r = pg.Rect(10, 8, 30, 30); rects.append(r)
        D.rect(screen, (62, 120, 168) if on else (24, 26, 32), r); D.rect(screen, (150, 200, 235) if on else (150, 152, 160), r, 1); D.polygon(screen, (235, 235, 240), [(28, 16), (28, 30), (19, 23)])
    lab = items[S["sel"]][0]; ds = DIFFS[lab]["desc"] if mode == "diff" and lab in DIFFS else CARD_DESC.get(lab, "")
    if S.get("msg") and (mode in ("players", "mp") or (mode == "main" and S["sel"] == 1)): ds = S["msg"]
    for i_, ln in enumerate(wrap(ds, small, min(total, 600))): txt(ln, (cxm - small.size(ln)[0] // 2, 494 + i_ * 20), small, (240, 120, 100) if ds == S.get("msg") else (215, 195, 160))
    hint = "KIRI / KANAN = pilih     ENTER = konfirmasi     ESC = kembali"; txt(hint, (940 - small.size(hint)[0], 574), small, (150, 135, 110))
    return rects

AGENT_BIG = load_img("agent", 0, 560, True) or make_agent_big()
BG = load_img("background", *screen.get_size()) or make_menu_bg()
LEFT_SHADE, TOPBAR = make_shade(), make_topbar(screen.get_width())
LOGO = spaced("AGENT DUTY", font, (240, 200, 90), 3)
TITLE = (spaced("TACTICAL  FPS", small, (230, 205, 160), 4), title_surf("AGENT", 104, (255, 255, 255), (196, 198, 212)), title_surf("DUTY", 156, (255, 228, 150), (210, 48, 42)))
for _k, _w in (("campaign", 188), ("coop", 188), ("mp", 188)): card_art(_k, _w, 372, True); card_art(_k, _w, 372, False)       # siapkan gambar kartu utama di awal

def draw_settings_menu(S, t):                  # SETTINGS dari menu utama: latar HQ + bara api + panel pengaturan bertab (dipakai juga di menu pause)
    sw, sh = screen.get_size(); screen.blit(BG, (0, 0))
    for x0, y0, sp, ph, sz in EMBERS: c = int(150 + 90 * math.sin(t * 3 + ph)); D.circle(screen, (min(255, c + 60), int(c * .45), 30), (int(x0 + math.sin(t * .7 + ph) * 14), int((y0 - t * sp * 30) % sh)), sz)
    pause_settings(sw, sh, 1.0, t); return []

# ---------- AGEN MENEMBAK (gaya flat sama seperti potret menu): hadap kanan, tangan terulur memegang pistol ----------
def agent_fire_shapes():
    """daftar bentuk (jenis, warna, titik) dalam koordinat 0..1 pada kotak 440 x 560; ujung laras ada di (1.0, .535)"""
    S = []; poly = lambda c, *p: S.append(("poly", c, p)); line = lambda c, w, *p: S.append(("line", c, w, p))
    poly((16, 16, 22), (0, 1), (0, .80), (.10, .68), (.28, .62), (.52, .62), (.64, .70), (.70, 1))                       # jas
    poly((30, 30, 40), (.28, .62), (.43, .86), (.36, 1), (.10, 1), (.10, .70)); poly((30, 30, 40), (.52, .62), (.43, .86), (.50, 1), (.66, 1), (.66, .72))
    poly((232, 232, 240), (.31, .62), (.50, .62), (.43, .84)); poly((246, 246, 250), (.31, .62), (.37, .66), (.40, .62))      # kemeja + kerah
    poly((190, 24, 34), (.38, .645), (.43, .645), (.445, .69), (.375, .69)); poly((150, 16, 26), (.375, .69), (.445, .69), (.47, .82), (.41, .87), (.35, .82))   # dasi
    poly((168, 116, 90), (.30, .49), (.45, .49), (.48, .63), (.31, .63))                                                    # leher
    poly((192, 138, 106), (.215, .35), (.255, .345), (.26, .43), (.22, .43))                                                 # telinga
    poly((214, 160, 126), (.22, .22), (.30, .17), (.44, .17), (.52, .25), (.53, .34), (.565, .405), (.52, .43), (.535, .47), (.48, .52), (.37, .555), (.28, .51), (.22, .40))   # kepala (3/4 ke kanan)
    poly((176, 120, 94), (.42, .22), (.52, .26), (.53, .34), (.565, .405), (.52, .43), (.535, .47), (.48, .52), (.40, .54))   # sisi gelap wajah
    poly((22, 16, 14), (.19, .33), (.20, .21), (.28, .13), (.43, .105), (.53, .15), (.555, .25), (.47, .20), (.35, .21), (.25, .27))   # rambut
    poly((6, 6, 10), (.23, .318), (.55, .318), (.55, .338), (.23, .338)); poly((6, 6, 10), (.37, .315), (.555, .325), (.545, .405), (.40, .41), (.365, .37))   # kacamata hitam
    line((120, 132, 170), 3, (.40, .335), (.46, .322)); line((120, 132, 170), 3, (.49, .34), (.52, .332))
    line((90, 40, 40), 3, (.41, .495), (.50, .485)); line((240, 235, 230), 2, (.43, .492), (.485, .486))                 # mulut menggertak (gigi)
    line((30, 8, 8), 4, (.395, .295), (.50, .275))                                                                           # alis marah
    S.append(("circle", (24, 24, 30), (.232, .425), .014)); line((215, 215, 228), 2, (.232, .44), (.225, .51), (.25, .57), (.30, .62))   # earpiece + kabel
    poly((16, 16, 22), (.44, .64), (.60, .60), (.77, .535), (.79, .60), (.62, .76), (.48, .78))                               # lengan baju (terulur)
    poly((38, 38, 50), (.60, .60), (.77, .535), (.785, .565), (.62, .64))                                                     # sorot lipatan lengan
    poly((240, 240, 246), (.765, .53), (.805, .525), (.815, .60), (.775, .605))                                               # manset
    poly((200, 146, 114), (.805, .525), (.86, .52), (.875, .585), (.815, .60))                                                # tangan
    poly((34, 36, 44), (.83, .435), (1.0, .435), (1.0, .505), (.83, .515)); poly((120, 126, 144), (.84, .445), (.995, .445), (.995, .458), (.84, .458))   # slide pistol
    poly((28, 28, 34), (.835, .515), (.88, .51), (.86, .625), (.815, .62))                                                    # gagang
    for a_, b_ in (((.02, .78), (.10, .68)), ((.10, .68), (.28, .62)), ((.20, .22), (.19, .33))): line((214, 44, 48), 3, a_, b_)   # cahaya merah tepi kiri
    return S

def make_agent_fire():                         # ubah bentuk-bentuk di atas jadi gambar (digambar 2x lalu dikecilkan agar halus) + versi "terkena kilatan tembakan"
    FW, FH = 440, 560; s = pg.Surface((FW * 2, FH * 2), pg.SRCALPHA); P = lambda p: [(a * FW * 2, b * FH * 2) for a, b in p]
    for sh in agent_fire_shapes():
        if sh[0] == "poly": D.polygon(s, sh[1], P(sh[2]))
        elif sh[0] == "line": D.lines(s, sh[1], False, P(sh[3]), sh[2] * 2)
        else: D.circle(s, sh[1], P([sh[2]])[0], int(sh[3] * FW * 2))
    out = pg.transform.smoothscale(s, (FW, FH)); lit = out.copy(); lit.fill((95, 48, 18, 0), special_flags=pg.BLEND_RGB_ADD); return out, lit
AGENT_FIRE, AGENT_FIRE_LIT = make_agent_fire()

# ================= INTRO STARTUP: baku tembak bernuansa merah + logo AGENT-DUTY + agen yang sedang baku tembak (tanpa file gambar, semuanya dibuat lewat kode) =================
INTRO = {}
def make_intro_logo():                         # logo "AGENT-DUTY": huruf putih tebal bergradasi, tepi digemukkan, bayangan + halo gelap (gaya logo shooter modern)
    f = pg.font.Font(None, 220); f.set_bold(True); CAP = 78
    def grad_piece(m):
        g = pg.Surface(m.get_size()); vgrad(g, (255, 255, 255), (184, 188, 202)); m.blit(g, (0, 0), special_flags=pg.BLEND_RGB_MULT); return m
    def word(sx):
        m = f.render(sx, True, (255, 255, 255)); m = m.subsurface(m.get_bounding_rect()).copy(); k = CAP / m.get_height(); m = pg.transform.smoothscale(m, (int(m.get_width() * k * 1.06), CAP))
        t_ = pg.Surface((m.get_width() + 8, CAP + 8), pg.SRCALPHA)
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, 2), (-2, 2), (2, -2)): t_.blit(m, (4 + dx, 4 + dy))
        t_.blit(m, (4, 4)); return grad_piece(t_)
    a, d = word("AGENT"), word("DUTY"); hw, hh, gap = 26, 10, 12; hy = pg.Surface((hw + 8, hh + 8), pg.SRCALPHA); D.rect(hy, (255, 255, 255), (4, 4, hw, hh)); hy = grad_piece(hy)
    W_ = a.get_width() + hy.get_width() + d.get_width() + gap * 2; H_ = a.get_height(); lw, lh = W_ + 200, H_ + 160
    halo = pg.Surface((256, 256), pg.SRCALPHA); glow(halo, 128, 128, 128, (0, 0, 0), 175); lg = pg.Surface((lw, lh), pg.SRCALPHA); lg.blit(pg.transform.smoothscale(halo, (lw, lh)), (0, 0))
    x = (lw - W_) // 2; y = (lh - H_) // 2
    for piece, px, py in ((a, x, y), (hy, x + a.get_width() + gap, y + int(H_ * .43) - hy.get_height() // 2), (d, x + a.get_width() + hy.get_width() + gap * 2, y)):
        sh = piece.copy(); sh.fill((0, 0, 0), special_flags=pg.BLEND_RGB_MULT); lg.blit(sh, (px + 3, py + 5)); lg.blit(piece, (px, py))
    return lg

def make_smoke(seed, n, cols, amax):           # lapisan asap seamless (di-scroll mendatar)
    sm = pg.Surface((960, 600), pg.SRCALPHA); r = random.Random(seed)
    for _ in range(n):
        cx, cy, rad = r.randint(0, 959), r.randint(90, 540), r.randint(60, 170); col = r.choice(cols); a_ = r.randint(amax // 2, amax)
        for dx in (-960, 0, 960): glow(sm, cx + dx, cy, rad, col, a_)
    return sm

def build_intro():
    W2, H2 = 1920, 1200; sf = pg.Surface((W2, H2)); X = lambda v: int(W2 * v); Y = lambda v: int(H2 * v)
    vgrad(sf, (14, 6, 14), (76, 12, 18)); glow(sf, X(.5), Y(.42), X(.5), (200, 28, 36), 150); glow(sf, X(.5), Y(.12), X(.38), (118, 100, 130), 80); glow(sf, X(.5), Y(.72), X(.42), (160, 20, 28), 90)
    house(sf, X(.5), Y(.74), W2 / 640 * .9, True, (10, 4, 10), 0)                                    # mansion di kejauhan
    gy = Y(.76); D.rect(sf, (12, 4, 8), (0, gy, W2, H2 - gy))
    for i in range(-12, 13): D.line(sf, (66, 12, 18), (X(.5), gy), (X(.5) + i * X(.14), H2), 2)
    for j in range(1, 8): D.line(sf, (66, 12, 18), (0, gy + int((H2 - gy) * (j / 7) ** 2)), (W2, gy + int((H2 - gy) * (j / 7) ** 2)), 2)
    ET = []
    for ex, eb, eh in ((.30, .82, .20), (.40, .79, .15), (.50, .77, .12), (.60, .79, .15), (.70, .82, .20)):                      # musuh bersiluet (mata merah)
        h = Y(eh); fc = 1 if ex < .5 else -1; u = h / 100.0; agent_sil(sf, X(ex), Y(eb), h, (8, 3, 8), (210, 44, 48), fc, True)
        for dx in (3, 7): glow(sf, int(X(ex) + fc * dx * u), int(Y(eb) - 89 * u), max(8, int(7 * u)), (255, 50, 50), 150)
        ET.append((X(ex) / 2 + fc * 57 * u / 2, Y(eb) / 2 - 84 * u / 2))
    tips = []
    for ax, ab, ah, fc in ((.15, 1.06, .95, 1), (.85, 1.06, .88, -1)):                                  # dua agen di depan, menembak ke arah musuh
        if ax < .5: tips.append(None); continue                                                          # agen kiri = potret AGENT_BIG (digambar tiap frame)
        u = Y(ah) / 100.0; agent_sil(sf, X(ax), Y(ab), Y(ah), (5, 2, 6), (232, 52, 58), fc, True); hx, hy_ = X(ax), int(Y(ab) - 89 * u)
        for dx in (3, 7): glow(sf, int(hx + fc * dx * u), hy_ - int(u), int(7 * u), (255, 60, 60), 220); D.circle(sf, (255, 150, 140), (int(hx + fc * dx * u), hy_ - int(u)), max(3, int(1.3 * u)))      # kacamata night vision menyala
        tips.append(((X(ax) + fc * 57 * u) / 2, (Y(ab) - 84 * u) / 2))
    sf.fill((255, 176, 166), special_flags=pg.BLEND_RGB_MULT); shade_bottom(sf, Y(.80), 190)
    bg = pg.transform.smoothscale(sf, (960, 600)); vg = pg.Surface((960, 600), pg.SRCALPHA)
    for k in range(40): D.rect(vg, (0, 0, 0, int(175 * (1 - k / 40) ** 2)), (k * 3, k * 2, 960 - 2 * k * 3, 600 - 2 * k * 2), 3)
    bg.blit(vg, (0, 0)); gls = pg.Surface((180, 180), pg.SRCALPHA); glow(gls, 90, 90, 90, (255, 170, 70), 200)
    st = pg.Surface((1100, 60), pg.SRCALPHA)                                                          # kilatan garis merah horizontal (seperti lens flare)
    for dy in range(60): D.line(st, (255, 50, 50, int(210 * max(0.0, 1 - abs(dy - 30) / 30) ** 2.2)), (0, dy), (1100, dy))
    D.line(st, (255, 190, 180, 235), (0, 30), (1100, 30), 1)
    for x in range(150): st.fill((255, 255, 255, int(255 * x / 150)), (x, 0, 1, 60), special_flags=pg.BLEND_RGBA_MULT); st.fill((255, 255, 255, int(255 * x / 150)), (1099 - x, 0, 1, 60), special_flags=pg.BLEND_RGBA_MULT)
    white = pg.Surface((960, 600)); white.fill((255, 255, 255)); black = pg.Surface((960, 600)); black.fill((0, 0, 0))
    INTRO.update(bg=bg, logo=make_intro_logo(), gls=gls, streak=st, ET=ET, tips=tips, white=white, black=black, pf=pg.font.Font(None, 30),
                 smoke=[(make_smoke(5, 22, ((120, 100, 124), (150, 34, 44)), 46), 14, 255), (make_smoke(9, 18, ((90, 80, 100), (170, 30, 40)), 40), 30, 235)],
                 chest=((144, 636 - 60 * 5.7), (816, 636 - 60 * 5.28)))

def draw_intro(S, t):
    if not INTRO: build_intro()
    I = INTRO; sw, sh = screen.get_size(); screen.blit(I["bg"], (0, 0))
    for sm, sp, al in I["smoke"]: off = int((t * sp) % 960); sm.set_alpha(al); screen.blit(sm, (-off, 0)); screen.blit(sm, (960 - off, 0))
    for x0, y0, sp, ph, sz in EMBERS: c = int(150 + 90 * math.sin(t * 3 + ph)); D.circle(screen, (min(255, c + 60), int(c * .45), 30), (int(x0 + math.sin(t * .7 + ph) * 14), int((y0 - t * sp * 60) % sh)), sz)
    # --- agen kiri: karakter yang sama dengan potret menu, tapi sedang menembak dengan sengit (hentakan, wajah tersorot kilatan, selongsong peluru) ---
    ph_ = (t * 9) % 1; on0 = ph_ < .55 and (t * 1.15) % 1 < .6; kick = max(0.0, 1 - ph_ / .35) if on0 else 0.0
    AX, AY = -40 - int(kick * 7), sh - 560 + 4 + int(math.sin(t * 1.6) * 2) + int(kick * 2); screen.blit(AGENT_FIRE_LIT if on0 else AGENT_FIRE, (AX, AY))
    if on0: ce_ = (AX + 440 * .86 + 80 * ph_, AY + 560 * .44 - 90 * ph_ + 300 * ph_ * ph_); D.rect(screen, (230, 190, 80), (int(ce_[0]), int(ce_[1]), 5, 3))      # selongsong terlempar
    # --- baku tembak: agen kiri & kanan menembak ke arah musuh, musuh membalas ke agen kiri ---
    ET = I["ET"]; tip = [(AX + 440, AY + 560 * .47), I["tips"][1]]; chest_ = [(AX + 440 * .40, AY + 560 * .74), I["chest"][1]]; si = int(t * 9); tracers = []
    for who, (tp, ph0, gate) in enumerate(((tip[0], 0.0, 1.15), (tip[1], .3, 1.0))):
        if tp is None: continue
        ph = (t * 9 + ph0) % 1; on = ph < .55 and ((t * gate + ph0) % 1) < .6
        if on:
            screen.blit(I["gls"], (int(tp[0]) - 90, int(tp[1]) - 90)); flash(screen, tp[0], tp[1], random.uniform(24, 40)); tracers.append((tp, ET[(si + who * 2) % len(ET)], ph / .55, (255, 238, 176)))
            if S.get("si%d" % who) != si: S["si%d" % who] = si; play("m416" if who == 0 else "rifle", 15)
    for i, e in enumerate(ET):
        ph = (t * 5 + i * .37) % 1
        if ph < .26 and ((t * .8 + i * .21) % 1) < .7:
            screen.blit(I["gls"], (int(e[0]) - 90, int(e[1]) - 90)); flash(screen, e[0], e[1], random.uniform(8, 15))
            tracers.append((e, chest_[0 if e[0] < 480 else 1], ph / .26, (255, 128, 76)))
    for a_, b_, p_, col in tracers:
        p0 = max(0.0, p_ - .22); D.line(screen, col, (a_[0] + (b_[0] - a_[0]) * p0, a_[1] + (b_[1] - a_[1]) * p0), (a_[0] + (b_[0] - a_[0]) * p_, a_[1] + (b_[1] - a_[1]) * p_), 2)
    stk = I["streak"]; stk.set_alpha(int(150 + 90 * math.sin(t * 2.3))); screen.blit(stk, (-70 + int(math.sin(t * .6) * 40), 162 - 30))        # garis cahaya merah memanjang
    # --- logo & teks ---
    k = max(0.0, min(1.0, (t - .5) / 1.1)); lg = I["logo"]; lg.set_alpha(int(255 * k)); screen.blit(lg, (sw // 2 - lg.get_width() // 2, 240 - lg.get_height() // 2 + int((1 - k) * 26)))
    txt("AGEN:  " + CFG["name"], (48, 34), tiny, (206, 200, 212))
    if t > 1.7:
        pf = I["pf"]; kk = (.55 + .45 * (math.sin(t * 3.2) * .5 + .5)) * min(1.0, (t - 1.7) * 2); col = (int(240 * kk),) * 3; pad = bool(PADS); lab = "A" if pad else "ENTER"
        iw = 28 if pad else pf.size(lab)[0] + 22; wa, wb = pf.size("PRESS")[0], pf.size("TO START")[0]; x = sw // 2 - (wa + iw + wb + 24) // 2; y = 512
        txt("PRESS", (x, y), pf, col); x += wa + 12; ic = pg.Rect(x, y - 3, iw, 28); dk = (14, 14, 18)
        if pad: D.circle(screen, col, ic.center, 14)
        else: rrect(col, ic, 0, 5)
        lr = pf.render(lab, True, dk); screen.blit(lr, (ic.centerx - lr.get_width() // 2, ic.centery - lr.get_height() // 2)); txt("TO START", (x + iw + 12, y), pf, col)
    if .42 < t < .8: w_ = I["white"]; w_.set_alpha(int(170 * (1 - (t - .42) / .38))); screen.blit(w_, (0, 0))                       # kilatan saat logo muncul
    if t < .7: b_ = I["black"]; b_.set_alpha(int(255 * (1 - t / .7))); screen.blit(b_, (0, 0))                                      # fade dari hitam
    if t > .35 and not S.get("boom"): S["boom"] = True; play("boom")
    return []

def draw_menu(S, t=0.0):
    if S["mode"] == "intro": return draw_intro(S, t)
    if S["mode"] in ("main", "diff", "mp", "players"): return draw_cards(S, t)
    if S["mode"] == "mp_join": return draw_join(S, t)
    if S["mode"] == "mp_name": return draw_name(S, t)
    if S["mode"] == "lobby": return draw_lobby(S, t)
    return draw_settings_menu(S, t)

# ================= MULTIPLAYER: deathmatch LAN 2-4 pemain (TCP, host meneruskan pesan) =================
MP_PORT = 5050
LOB, LBY, RPS, MPS, MPSTART, LIP = {}, dict(map=0, lim=10, bots=2, mode=0, tm={}), {}, {}, None, [None]
MODES = (("FREE FOR ALL", 0), ("5 VS 5", 5), ("10 VS 10", 10))             # (nama, besar tim; 0 = semua lawan semua)
LIMS, LIM_DEF = {0: (5, 10, 20, 30), 5: (20, 30, 50), 10: (40, 60, 100)}, {0: 10, 5: 30, 10: 60}      # pilihan batas kill (mode tim: total kill satu tim)
TEAM, TSC, TSP = {}, [0, 0], {}                # TEAM: id peserta -> 0 (biru) / 1 (merah), kosong = free for all | TSC: skor kill tiap tim | TSP: titik lahir tiap tim
TNAME, TCOL, TJK = ("TIM BIRU", "TIM MERAH"), ((90, 150, 255), (255, 95, 85)), ((36, 74, 170), (176, 40, 40))     # nama, warna teks, warna jas
BOT_MAX, BOT_DMG, BOT_AIM = 20, (8, 12), .03   # jumlah bot maksimal | damage per peluru bot | sebaran bidik dasar (makin besar makin sering meleset)
def friendly(a, b): return a != b and a in TEAM and b in TEAM and TEAM[a] == TEAM[b]     # sekutu tidak bisa saling melukai (friendly fire mati)
MPD = dict(stages=[], floors=1, n=0, add=0, hp=1, dmg=1, spd=1, cd=1, spr=.06, sight=1, conts=999, items=26, mix=[1, 1, 1, 1], guards=0, gr=2, fb=2, desc="")
PCOL = ((200, 200, 210), (110, 160, 255), (255, 110, 100), (120, 220, 130))

def local_ip():
    if LIP[0] is None:
        try: z = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); z.connect(("10.255.255.255", 1)); LIP[0] = z.getsockname()[0]; z.close()
        except Exception: LIP[0] = "127.0.0.1"
    return LIP[0]

# ---- INTERNET: main beda WiFi / beda jaringan tanpa port-forward, tanpa kabel LAN ----
# Masalah lama: IP seperti 192.168.x.x hanya berlaku di dalam satu WiFi. Teman di WiFi lain mengetik IP itu -> menyambung ke jaringannya SENDIRI -> "ditolak" (WinError 10061).
# Solusi: host otomatis membuka "tunnel" keluar ke server bore (BORE_HOST). Server itu memberi alamat publik (mis. bore.pub:41234) yang bisa dipakai teman dari jaringan mana pun.
BORE_HOST, BORE_CTRL = "bore.pub", 7835       # server tunnel publik gratis (protokol "bore"). Boleh diganti ke server bore milik sendiri
def clip_set(t_):                              # salin teks ke clipboard (tkinter bawaan Python)
    try:
        import tkinter; r = tkinter.Tk(); r.withdraw(); r.clipboard_clear(); r.clipboard_append(t_); r.update(); r.destroy(); return True
    except Exception: return False
def clip_get():
    try:
        import tkinter; r = tkinter.Tk(); r.withdraw(); v = r.clipboard_get(); r.destroy(); return v
    except Exception: return ""
def addr_clean(t_): return "".join(ch for ch in (t_ or "").strip() if ch.isascii() and (ch.isalnum() or ch in ".:-"))[:48]
def is_private(h):
    try: return ipaddress.ip_address(h).is_private
    except ValueError: return False
def net_err(ex):                               # pesan galat jaringan yang mudah dipahami
    n = getattr(ex, "winerror", None) or getattr(ex, "errno", None)
    if isinstance(ex, ConnectionRefusedError) or n in (10061, 111): return "ditolak (host belum membuka lobi, atau alamat / port salah)"
    if isinstance(ex, (socket.timeout, TimeoutError)) or n in (10060, 110): return "tidak ada balasan (timeout)"
    if isinstance(ex, socket.gaierror): return "alamat tidak ditemukan, cek ejaannya"
    return str(ex) or "gagal"
def join_fail_msg(addr, ex):
    h = addr.split(":")[0]; m = f"Gagal terhubung ke {addr}: {net_err(ex)}"
    if is_private(h): m += ".  Itu IP LOKAL (hanya berlaku satu WiFi). Beda WiFi? Minta host mengirim ALAMAT INTERNET yang tampil di lobi (contoh bore.pub:41234)"
    return m

class Tunnel:                                  # klien bore: control connection ke server + satu koneksi data per pemain yang masuk, diteruskan ke port game lokal
    def __init__(s): s.state, s.port, s.err, s.gen = "off", 0, "", 0          # state: off | wait | ready | fail
    def addr(s): return f"{BORE_HOST}:{s.port}" if s.state == "ready" else ""
    def start(s, lport):
        s.gen += 1; s.state, s.port, s.err = "wait", 0, ""
        threading.Thread(target=s._run, args=(lport, s.gen), daemon=True).start()
    def close(s): s.gen += 1; s.state, s.port, s.err = "off", 0, ""
    def _run(s, lport, gen):
        tries = 0
        while gen == s.gen and tries < 5:
            ctl = None
            try:
                ctl = socket.create_connection((BORE_HOST, BORE_CTRL), timeout=10); ctl.sendall(b'{"Hello":0}\0'); ctl.settimeout(1.0); buf = b""; last = time.time()
                while gen == s.gen:
                    if b"\0" in buf:
                        raw, buf = buf.split(b"\0", 1)
                        try: m = json.loads(raw)
                        except ValueError: continue
                        last = time.time()
                        if isinstance(m, dict):
                            if "Hello" in m and s.state != "ready": s.port, s.state, s.err, tries = int(m["Hello"]), "ready", "", 0
                            elif "Connection" in m: threading.Thread(target=s._accept, args=(m["Connection"], lport), daemon=True).start()
                            elif "Error" in m: raise OSError(str(m["Error"]))
                            elif "Challenge" in m: raise OSError("server tunnel meminta password")
                        continue
                    try: d = ctl.recv(4096)
                    except socket.timeout:
                        if time.time() - last > 12: raise OSError("server tunnel tidak merespons")
                        continue
                    if not d: raise OSError("koneksi tunnel diputus server")
                    buf += d
            except OSError as ex:
                if gen != s.gen: return
                tries += 1; s.state, s.err = ("fail" if tries >= 5 else "wait"), net_err(ex)
                for _ in range(6):                                                 # jeda 3 detik sebelum coba lagi (tetap peka terhadap close())
                    if gen != s.gen: return
                    time.sleep(.5)
            finally:
                try:
                    if ctl: ctl.close()
                except OSError: pass
    def _accept(s, cid, lport):
        a = b = None
        try:
            a = socket.create_connection((BORE_HOST, BORE_CTRL), timeout=10); a.sendall(json.dumps({"Accept": cid}).encode() + b"\0")
            b = socket.create_connection(("127.0.0.1", lport), timeout=5); a.settimeout(None); b.settimeout(None)
            for z in (a, b):
                try: z.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except OSError: pass
            def pipe(src, dst):
                try:
                    while True:
                        d = src.recv(65536)
                        if not d: break
                        dst.sendall(d)
                except OSError: pass
                for z in (src, dst):
                    try: z.shutdown(socket.SHUT_RDWR)
                    except OSError: pass
            threading.Thread(target=pipe, args=(a, b), daemon=True).start(); pipe(b, a)
        except OSError: pass
        finally:
            for z in (a, b):
                try:
                    if z: z.close()
                except OSError: pass
TUN = Tunnel()

class Net:                                     # TCP: host menerima klien, pesan = satu baris JSON. Ada buffer kirim, TCP_NODELAY, dan deteksi koneksi mati
    def __init__(s): s.srv = s.sock = None; s.peers = {}; s.nid = 1; s.id = 0; s.host = s.active = False; s.cbuf = s.obuf = b""; s.last = 0.0; s.ping_t = 0.0
    def start_host(s, port=None):
        s.close(); s.srv = socket.socket(); s.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.srv.bind(("0.0.0.0", port or MP_PORT)); s.srv.listen(4); s.srv.setblocking(False)
        s.host, s.id, s.active = True, 0, True
    def connect(s, addr, port=None):           # addr boleh "192.168.1.5" atau "192.168.1.5:5050"
        s.close(); addr = addr_clean(addr).lower(); host, pt = addr, port or MP_PORT
        if addr.count(":") == 1:
            host, ps = addr.split(":"); pt = int(ps) if ps.isdigit() else pt
        if not host: raise OSError("alamat kosong")
        try: s.sock = socket.create_connection((host, pt), timeout=8)
        except (UnicodeError, ValueError) as ex: raise OSError(f"alamat tidak valid: {ex}")        # mis. "192..1" memicu UnicodeError, bukan OSError
        s._tune(s.sock); s.host, s.active = False, True; s.last = time.time()
    def _tune(s, sk):
        sk.setblocking(False)
        try: sk.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)               # tanpa penundaan Nagle: gerakan pemain tidak patah-patah
        except OSError: pass
    def close(s):
        for x in [s.srv, s.sock] + [p[0] for p in s.peers.values()]:
            try:
                if x: x.close()
            except OSError: pass
        if s.host: TUN.close()                                                   # hanya host yang punya tunnel
        s.srv = s.sock = None; s.peers = {}; s.nid = 1; s.id = 0; s.host = s.active = False; s.cbuf = s.obuf = b""
    def _tx(s, sock, data):                    # kirim; sisa yang belum terkirim ditahan di buffer dan dikirim ulang di poll() (tidak ada pesan terpotong)
        if sock is s.sock: s.obuf += data; return
        for p in s.peers.values():
            if p[0] is sock: p[2] += data; return
        try: sock.send(data)
        except OSError: pass
    def _flush(s):
        if s.sock and s.obuf:
            try: n = s.sock.send(s.obuf); s.obuf = s.obuf[n:]
            except (BlockingIOError, InterruptedError): pass
            except OSError: s.obuf = b""
            if len(s.obuf) > 1 << 20: s.obuf = b""
        for i, p in list(s.peers.items()):
            if p[2]:
                try: n = p[0].send(p[2]); p[2] = p[2][n:]
                except (BlockingIOError, InterruptedError): pass
                except OSError: p[2] = b""; p[3] = 0.0
                if len(p[2]) > 1 << 20: p[3] = 0.0                                  # klien terlalu lambat: lepas
    def send(s, msg, to=None):                 # host: ke semua / satu id. klien: lewat host (host meneruskan)
        if s.host: msg["f"] = 0
        elif to is not None: msg["to"] = to
        data = (json.dumps(msg, separators=(",", ":")) + "\n").encode()
        if s.host:
            for i, p in list(s.peers.items()):
                if to is None or to == i: p[2] += data
        elif s.sock: s.obuf += data
    def relay(s, m, only=None, skip=None):
        data = (json.dumps(m, separators=(",", ":")) + "\n").encode()
        for i, p in list(s.peers.items()):
            if (only is None or i == only) and i != skip: p[2] += data
    def _read(s, sock, buf):
        try:
            d = sock.recv(65536)
            if not d: return [], buf, False
            buf += d
        except (BlockingIOError, InterruptedError): pass
        except OSError: return [], buf, False
        out = []
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            try:
                m = json.loads(line)
                if isinstance(m, dict): out.append(m)
            except ValueError: pass
        if len(buf) > 1 << 20: buf = b""
        return out, buf, True
    def poll(s):
        out = []; now = time.time()
        if s.host:
            try:
                while True: c, _ = s.srv.accept(); s._tune(c); s.peers[s.nid] = [c, b"", b"", now]; s.nid += 1          # [socket, buffer baca, buffer kirim, terakhir terdengar]
            except OSError: pass
            for i, p in list(s.peers.items()):
                ms, p[1], ok = s._read(p[0], p[1])
                if ms: p[3] = now
                out += [(i, x) for x in ms if x.get("t") != "ping"]
                if not ok or now - p[3] > 10:                                       # putus / diam lebih dari 10 detik
                    try: p[0].close()
                    except OSError: pass
                    s.peers.pop(i, None); out.append((i, {"t": "bye"}))
        elif s.sock:
            ms, s.cbuf, ok = s._read(s.sock, s.cbuf)
            if ms: s.last = now
            out += [(None, x) for x in ms if x.get("t") != "ping"]
            if not ok or now - s.last > 10: out.append((None, {"t": "gone"}))
        if s.active and now - s.ping_t > 1.5: s.ping_t = now; s.send({"t": "ping"})         # detak jantung agar koneksi mati terdeteksi
        s._flush()
        return out
NET = Net()

class RP:                                      # pemain lain (remote)
    def __init__(s, i, name):
        s.id, s.name, s.k = i, name, "rp"; s.x = s.y = s.tx = s.ty = 3.5; s.a = s.z = s.ph = s.flash = s.mt = s.lph = 0.0; s.hp, s.al, s.wp, s.first = 100, True, 0, True
    def hit(s, d, h=.6):                       # peluru kita mengenai pemain lain: darah lokal + kirim damage ke korban
        s.flash = .12; bleed(s.x, s.y, h, min(18, 6 + int(d / 3)), 2)
        if P.time - P.sp_t > .05: play("splat", math.hypot(s.x - P.x, s.y - P.y)); P.sp_t = P.time
        if s.id >= 100 and NET.host: bot_hit(s.id, d, NET.id)
        else: NET.send({"t": "hit", "d": round(d, 1)}, to=s.id)

def targets():
    if getattr(P, "mode", "") != "mp": return enemies
    return enemies + [r for r in RPS.values() if not friendly(NET.id, r.id)]          # sekutu tidak bisa ditembak

def proj(x, y, h):                             # titik dunia -> koordinat layar internal (untuk nama pemain)
    rx, ry = x - P.x, y - P.y; inv = 1 / (P.plx * P.dy - P.dx * P.ply); ty = inv * (-P.ply * rx + P.plx * ry)
    if ty < .3: return None
    return W / 2 * (1 + inv * (P.dy * rx - P.dx * ry) / ty), P.hor + (.5 + EYE + P.z - h) * H / ty * P.zk, ty

def handle_kill(by, v):
    MPS.setdefault(v, [0, 0])[1] += 1; nm = lambda i: LOB.get(i, f"AGENT-{i + 1}"); real = by is not None and by >= 0 and by != v and not friendly(by, v)
    if real:
        MPS.setdefault(by, [0, 0])[0] += 1
        if by == NET.id: P.xpop.append(["+100 XP", 2.0]); hitmark(True)
    P.feed.append([f"{nm(by)}  >  {nm(v)}" if real else f"{nm(v)} tewas", 6.0, by if real else -1, v])
    if TEAM:                                                               # mode tim: yang dihitung total kill satu tim
        if real and by in TEAM:
            TSC[TEAM[by]] += 1
            if TSC[TEAM[by]] >= P.limit: P.state = "mpend"; P.winner = None; P.notice = f"{TNAME[TEAM[by]]} MENANG   {TSC[0]} - {TSC[1]}"
    elif real and MPS[by][0] >= P.limit: P.state = "mpend"; P.winner = by

def team_spawns(sp):                           # bagi titik lahir jadi dua sisi peta: tim biru dekat titik pertama, tim merah di sisi seberang
    a = sp[0]; b = max(sp, key=lambda c: math.hypot(c[0] - a[0], c[1] - a[1])); ax, ay = b[0] - a[0], b[1] - a[1]
    s2 = sorted(sp, key=lambda c: (c[0] - a[0]) * ax + (c[1] - a[1]) * ay); h = len(s2) // 2
    return {0: s2[:h] or s2, 1: s2[h:] or s2}

def rp_tex(r):                                 # tampilan pemain lain: jas biru / merah di mode tim, warna per pemain di free for all
    t_ = TEAM.get(r.id); key, jc = ("tm%d" % t_, TJK[t_]) if t_ is not None else ("pl%d" % (r.id % 4), PJ[r.id % 4])
    return char_tex(key, "agen", (jc, (20, 20, 26), (215, 170, 135)), r.a, r.x, r.y, r.ph, r.mt > 0, not r.al)

BFSC = {}
def bfs_c(src):                                # peta statis: arah menuju satu tujuan cukup dihitung sekali (20 bot berbagi hasilnya)
    if src not in BFSC: BFSC[src] = bfs(src)
    return BFSC[src]

def mp_die():
    P.state = "mpdead"; P.rt = 3.0; NET.send({"t": "kill", "by": P.last_by, "v": NET.id}); handle_kill(P.last_by, NET.id)

def mp_spawn():                                # titik lahir terjauh dari lawan (mode tim: dari sisi timnya sendiri)
    others = [(r.x, r.y) for r in RPS.values() if r.al and not friendly(NET.id, r.id)]; pool = TSP.get(TEAM.get(NET.id)) or P.spawns
    sp = max(pool, key=lambda c: min([math.hypot(c[0] + .5 - ox, c[1] + .5 - oy) for ox, oy in others] or [0]) + random.random() * 3) if others else pool[NET.id % len(pool)]
    P.x, P.y, P.a = sp[0] + .5, sp[1] + .5, random.uniform(0, 6.28)

def mp_respawn():
    P.hp, P.armor, P.state, P.cur, P.rl, P.inv = 100, 50, "play", 0, 0.0, 2.5; P.weap = [dict(w) for w in P.loadout0]; P.gr, P.fb = 2, 2; P.blind = P.hurt = P.ahit = 0.0; P.splats = []; mp_spawn()

def start_mp(seed, mapname, lim, players, teams=None):
    global RPS, MPS
    random.seed(seed); np.random.seed(seed % 4294967295)                  # peta & item sama di semua pemain
    start_game("MULTIPLAYER", dict(MPD, stages=["MANSION" if mapname == "ARENA" else mapname], floor=1 if mapname == "ARENA" else 0))
    cells = [(x, y) for y in range(N) for x in range(N) if DIST[y, x] < 9999]; random.shuffle(cells); sp = []
    for sep in (9, 7, 5, 4, 3, 2):                                         # sampai 20+ peserta butuh banyak titik lahir: jarak antar titik dilonggarkan bertahap
        for c in cells:
            if len(sp) >= 24: break
            if c not in sp and all(math.hypot(c[0] - o[0], c[1] - o[1]) > sep for o in sp): sp.append(c)
        if len(sp) >= 24: break
    if mapname == "ARENA": items[:] = [[x + .5, y + .5, random.choice(["health", "armor", "ammo", "ammo", "granat", "flash"])] for x, y in cells[:22]]
    random.seed(); P.mode, P.limit, P.spawns, P.winner, P.notice, P.rt = "mp", lim, sp or cells[:4], None, "", 0.0; cps.clear(); enemies.clear(); P.xpop = []
    RPS = {i: RP(i, n) for i, n in players.items() if i != NET.id}; MPS = {i: [0, 0] for i in players}; LOB.update(players)
    TEAM.clear(); TEAM.update(teams or {}); TSC[:] = [0, 0]; TSP.clear(); BFSC.clear()
    if TEAM: TSP.update(team_spawns(P.spawns))
    n_ = sum(1 for v in TEAM.values() if v == 0); n2_ = len(TEAM) - n_
    P.msg = (f"TEAM DEATHMATCH {n_} VS {n2_}  -  KAMU DI {TNAME[TEAM.get(NET.id, 0)]}" if TEAM else f"DEATHMATCH  -  {lim} KILL UNTUK MENANG", 3.5); mp_spawn(); P.inv = 2.5; P.mp_t0, P.mp_end = time.time(), None                  # jam match (untuk kotak skor)
    if TEAM:                                                               # tim berkumpul di sisinya masing-masing, menghadap markas lawan
        t_ = TEAM.get(NET.id, 0); mem = sorted(k for k in TEAM if TEAM[k] == t_); pool = TSP[t_]; c_ = pool[mem.index(NET.id) % len(pool)] if NET.id in mem else pool[0]
        foe = TSP[1 - t_]; P.x, P.y = c_[0] + .5, c_[1] + .5; P.a = math.atan2(sum(c[1] for c in foe) / len(foe) + .5 - P.y, sum(c[0] for c in foe) / len(foe) + .5 - P.x)
    if mapname == "ARENA": P.stage = "ARENA"
    BOTS.clear()
    if NET.host:                                                           # host menjalankan semua bot
        for j, i in enumerate(sorted(k for k in players if k >= 100)):
            BOTS[i] = Bot(i); r = RPS[i]
            if i in TEAM: mem = sorted(k for k in TEAM if TEAM[k] == TEAM[i]); pool = TSP[TEAM[i]]; sp_ = pool[mem.index(i) % len(pool)]
            else: sp_ = P.spawns[(j + 1) % len(P.spawns)]
            r.x = r.tx = sp_[0] + .5; r.y = r.ty = sp_[1] + .5; r.first = False

def bot_cap():                                 # batas bot: FFA = BOT_MAX; mode tim = sisa slot (2 x besar tim - jumlah pemain)
    size = MODES[LBY.get("mode", 0)][1]
    return min(BOT_MAX, max(0, size * 2 - len(LOB))) if size else BOT_MAX
def lobby_bots(d): LBY["bots"] = max(0, min(bot_cap(), LBY["bots"] + d)); lobby_cast()      # host: ubah jumlah bot (semua mode)

def lobby_fill_tm():                           # host: pastikan tiap pemain punya tim (pemain baru masuk ke tim yang lebih sedikit)
    tm = LBY["tm"]
    for i in [k for k in tm if k not in LOB]: tm.pop(i)
    for i in sorted(LOB):
        if i not in tm: tm[i] = 0 if sum(1 for v in tm.values() if v == 0) <= sum(1 for v in tm.values() if v == 1) else 1

def lobby_cast():
    LBY["bots"] = min(LBY["bots"], bot_cap()); lobby_fill_tm()
    NET.send({"t": "lobby", "p": {str(i): n for i, n in LOB.items()}, "map": LBY["map"], "lim": LBY["lim"], "bots": LBY["bots"], "mode": LBY["mode"], "tm": {str(i): v for i, v in LBY["tm"].items()}})

def lobby_toggle(k):                           # host: pindahkan pemain ke-k (urut id) ke tim lawan
    ids = sorted(LOB)
    if ids: i = ids[k % len(ids)]; lobby_fill_tm(); LBY["tm"][i] = 1 - LBY["tm"].get(i, 0); lobby_cast()

def lobby_mode(m):                             # ganti mode (host): batas kill ikut menyesuaikan
    LBY["mode"] = m % len(MODES); LBY["lim"] = LIM_DEF[MODES[LBY["mode"]][1]]; lobby_cast()

def lobby_plan():                              # susunan peserta dari lobi -> (players, teams). Jumlah bot diatur host di semua mode
    players, teams = dict(LOB), {}; size = MODES[LBY.get("mode", 0)][1]
    if size:
        for k, i in enumerate(sorted(LOB)): teams[i] = LBY.get("tm", {}).get(i, k % 2) % 2      # tim pemain diatur host (default: dibagi bergantian)
        cnt = [sum(1 for v in teams.values() if v == t_) for t_ in (0, 1)]; j = 0           # bot sesuai pengaturan host, masuk ke tim yang lebih sedikit (maks. sebesar tim)
        for _ in range(min(LBY["bots"], bot_cap())):
            t_ = 0 if cnt[0] <= cnt[1] else 1
            if cnt[t_] >= size: t_ = 1 - t_
            if cnt[t_] >= size: break
            players[100 + j] = f"BOT-{j + 1}"; teams[100 + j] = t_; cnt[t_] += 1; j += 1
    else:
        for j in range(min(LBY["bots"], bot_cap())): players[100 + j] = f"BOT-{j + 1}"
    return players, teams

def lobby_start():
    global MPSTART
    LBY["bots"] = min(LBY["bots"], bot_cap()); players, teams = lobby_plan()
    if len(players) < 2 or (teams and len(set(teams.values())) < 2): return False                 # mode tim: kedua tim harus ada isinya
    seed = random.randint(1, 10 ** 9); msg = {"t": "start", "seed": seed, "map": MAPS[LBY["map"]], "lim": LBY["lim"], "p": {str(i): n for i, n in players.items()}, "tm": {str(i): v for i, v in teams.items()}}
    NET.send(msg); MPSTART = (seed, msg["map"], msg["lim"], players, teams)

def net_msg(src, m):                           # satu pintu untuk semua pesan jaringan
    global MPSTART
    t_ = m.get("t")
    if NET.host and src is not None:                                       # pesan dari klien
        m["f"] = src
        if t_ == "join":
            if len(LOB) >= 4: NET._tx(NET.peers[src][0], b'{"t":"full"}\n'); return
            LOB[src] = uniq_name(clean_name(m.get("n") or "", f"AGENT-{src + 1}"), LOB.values()); NET.send({"t": "welcome", "id": src}, to=src); lobby_cast(); return
        if t_ == "bye": LOB.pop(src, None); RPS.pop(src, None); LBY["tm"].pop(src, None); lobby_cast(); NET.send({"t": "left", "id": src}); return
        to = m.get("to")
        if to is None: NET.relay(m, skip=src)
        elif to != 0 and to < 100: NET.relay(m, only=to); return
    if t_ == "welcome": NET.id = m["id"]
    elif t_ == "lobby": LOB.clear(); LOB.update({int(k): v for k, v in m["p"].items()}); LBY.update(map=m["map"], lim=m["lim"], bots=m.get("bots", 0), mode=m.get("mode", 0), tm={int(k): v for k, v in m.get("tm", {}).items()})
    elif t_ == "full": NET.close(); LOB.clear()
    elif t_ == "start": MPSTART = (m["seed"], m["map"], m["lim"], {int(k): v for k, v in m["p"].items()}, {int(k): v for k, v in m.get("tm", {}).items()})
    elif t_ == "left": RPS.pop(m["id"], None); LOB.pop(m["id"], None)
    elif t_ == "gone" and getattr(P, "mode", "") == "mp": P.state = "mpend"; P.winner = None; P.notice = "Koneksi ke host terputus"; NET.close()
    elif getattr(P, "mode", "") == "mp":
        if t_ == "s":
            r = RPS.get(m["f"])
            if r:
                r.tx, r.ty, r.a, r.z, r.wp, r.al, r.hp = m["x"], m["y"], m["a"], m["z"], m["w"], m["al"], (m["h"] if m["al"] else 0)
                if r.first or math.hypot(r.tx - r.x, r.ty - r.y) > 5: r.x, r.y, r.first = r.tx, r.ty, False
        elif t_ == "hit" and m.get("to", 0) >= 100:
            if NET.host: bot_hit(m["to"], m["d"], m["f"])
        elif t_ == "hit" and m.get("to", NET.id) == NET.id and P.state in ("play", "pause") and not friendly(m.get("by", m["f"]), NET.id): hurt(m["d"], m.get("by", m["f"]))
        elif t_ == "b":
            for i, x, y, a, al, hp in m["l"]:
                r = RPS.get(i)
                if r:
                    r.tx, r.ty, r.a, r.al, r.hp = x, y, a, al, (hp if al else 0)
                    if r.first or math.hypot(x - r.x, y - r.y) > 5: r.x, r.y, r.first = x, y, False
        elif t_ == "kill": handle_kill(m["by"], m["v"])
        elif t_ == "nade": nades.append(list(m["n"]) + [m["f"]])
        elif t_ == "shot" and m.get("bid", m["f"]) in RPS:
            r = RPS[m.get("bid", m["f"])]; d_ = math.hypot(r.x - P.x, r.y - P.y)
            if d_ < 26: play(P.loadout0[m["w"]]["snd"], d_)                  # tembakan yang terlalu jauh tidak perlu dimainkan (20 bot = banyak suara)

BOTS = {}
class Bot:                                     # bot: dikendalikan host, tampil sebagai pemain biasa di semua layar
    def __init__(s, i):
        s.id, s.hp, s.al, s.cd, s.rt, s.stun, s.n, s.sd, s.sdt, s.goal, s.flow, s.ft, s.last = i, 100, True, random.uniform(.6, 1.6), 0.0, 0.0, 0, 1, 0.0, None, None, 0.0, None
        s.tg, s.scan = None, random.uniform(0, .25)         # target yang sedang dibidik + jeda pencarian target (disebar agar 20 bot tidak mencari serentak)

def bot_move(r, vx, vy, st):
    n = math.hypot(vx, vy) or 1; mx, my = vx / n * st, vy / n * st
    if free(r.x + mx, r.y, .25): r.x += mx
    if free(r.x, r.y + my, .25): r.y += my
    r.tx, r.ty = r.x, r.y; r.ph += math.hypot(mx, my)

def bot_hit(i, d, by):                         # (host) bot terkena peluru / granat
    b = BOTS.get(i)
    if not b or not b.al or friendly(by, i): return
    b.hp -= d; RPS[i].flash = .12; b.stun = max(b.stun, .15)
    if b.hp <= 0: b.al = False; b.rt = 3.0; RPS[i].al = False; RPS[i].hp = 0; NET.send({"t": "kill", "by": by, "v": i}); handle_kill(by, i)

def bot_respawn(b, r):
    pts = [(o.x, o.y) for o in RPS.values() if o.al and o.id != b.id and not friendly(b.id, o.id)]
    if not friendly(b.id, NET.id): pts.append((P.x, P.y))
    pool = TSP.get(TEAM.get(b.id)) or P.spawns
    sp = max(pool, key=lambda c: min([math.hypot(c[0] + .5 - ox, c[1] + .5 - oy) for ox, oy in pts] or [0]) + random.random() * 3)
    b.hp, b.al, b.goal, b.last, b.flow, b.tg = 100, True, None, None, None, None; r.x = r.tx = sp[0] + .5; r.y = r.ty = sp[1] + .5; r.al = True; r.hp = 100

def bot_fire(b, r, ents, ang, d):              # hitscan bot: kena lawan pertama di garis tembak (sekutu dilewati, tidak pernah kena)
    ang += random.gauss(0, BOT_AIM + d * .004); dx, dy = math.cos(ang), math.sin(ang); wd = 0.0
    while wd < 30:
        wd += .1
        if MAP[int(r.y + dy * wd), int(r.x + dx * wd)]: break
    v, bd = None, wd
    for i, (x, y, al) in ents.items():
        rx, ry = x - r.x, y - r.y; f = rx * dx + ry * dy
        if i != b.id and al and 0 < f < bd and abs(rx * dy - ry * dx) < .35 and not friendly(b.id, i): v, bd = i, f
    dp = math.hypot(r.x - P.x, r.y - P.y)
    if dp < 26: play("pistol", dp)
    NET.send({"t": "shot", "w": 0, "bid": b.id}); dmg = random.uniform(*BOT_DMG)
    if v == 0: hurt(dmg, b.id)
    elif v in BOTS: bot_hit(v, dmg, b.id)
    elif v is not None: NET.send({"t": "hit", "d": round(dmg, 1), "by": b.id}, to=v)

def bots_tick(dt):
    ents = {0: (P.x, P.y, P.state != "mpdead")}; ents.update({r.id: (r.x, r.y, r.al) for r in RPS.values()})
    for b in BOTS.values():
        r = RPS[b.id]
        if not b.al:
            b.rt -= dt
            if b.rt <= 0: bot_respawn(b, r)
            continue
        if b.stun > 0: b.stun -= dt; continue
        b.cd -= dt; b.sdt -= dt; b.scan -= dt
        if b.sdt <= 0: b.sd = random.choice((-1, 1)); b.sdt = random.uniform(.8, 2.0)
        if b.scan <= 0:                                                # cari lawan terdekat yang terlihat (tidak tiap frame: 20 bot = banyak ray)
            b.scan = random.uniform(.14, .26)
            cand = sorted((math.hypot(x - r.x, y - r.y), i) for i, (x, y, al) in ents.items() if i != b.id and al and not friendly(b.id, i))
            b.tg = next((i for d_, i in cand if d_ < 28 and los(r.x, r.y, ents[i][0], ents[i][1])), None)
        tg = ents.get(b.tg) if b.tg is not None else None
        if tg is not None and not tg[2]: tg = None; b.tg = None
        if tg is not None:                                             # lihat lawan: maju / mundur sambil geser, lalu tembak
            tx, ty = tg[0], tg[1]; d = math.hypot(tx - r.x, ty - r.y); a = math.atan2(ty - r.y, tx - r.x); r.a = a; b.last = (tx, ty); k = 1 if d > 9 else -.6 if d < 4 else 0
            bot_move(r, math.cos(a) * k - math.sin(a) * b.sd * .8, math.sin(a) * k + math.cos(a) * b.sd * .8, 3.3 * dt)
            if b.cd <= 0 and d < 24: b.n += 1; bot_fire(b, r, ents, a, d); b.cd = .13 if b.n % 3 else .75
        else:                                                          # patroli: kejar posisi terakhir lawan, atau (mode tim) serbu sisi lawan, atau titik lahir acak
            if b.goal is None or math.hypot(b.goal[0] + .5 - r.x, b.goal[1] + .5 - r.y) < 1.5:
                if b.last: b.goal = (int(b.last[0]), int(b.last[1]))
                else: b.goal = random.choice((TSP.get(1 - TEAM[b.id]) if b.id in TEAM and random.random() < .7 else None) or P.spawns)
                b.last = None; b.flow = None
            if b.flow is None: b.flow = bfs_c(b.goal)
            cx, cy = int(r.x), int(r.y); nx, ny = min(((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)), key=lambda q: b.flow[q[1], q[0]])
            r.a = math.atan2(ny + .5 - r.y, nx + .5 - r.x); bot_move(r, nx + .5 - r.x, ny + .5 - r.y, 3.0 * dt)

def mp_tick(dt):
    if NET.host and BOTS and P.state != "mpend": bots_tick(dt)
    P.snd_t = getattr(P, "snd_t", 0.0) - dt
    if P.snd_t <= 0:
        P.snd_t = .05; NET.send({"t": "s", "x": round(P.x, 2), "y": round(P.y, 2), "a": round(P.a, 2), "z": round(P.z, 2), "w": P.cur, "h": int(P.hp), "al": P.state != "mpdead"})
        if NET.host and BOTS: NET.send({"t": "b", "l": [[b.id, round(RPS[b.id].x, 2), round(RPS[b.id].y, 2), round(RPS[b.id].a, 2), b.al, int(b.hp)] for b in BOTS.values()]})
    for r in RPS.values():                                                 # gerakan pemain lain dihaluskan
        k = min(1.0, dt * 16); dx, dy = (r.tx - r.x) * k, (r.ty - r.y) * k; r.x += dx; r.y += dy; r.ph += math.hypot(dx, dy); r.flash = max(0.0, r.flash - dt)
        r.mt = .25 if r.ph - r.lph > .001 else max(0.0, r.mt - dt); r.lph = r.ph
    for q in P.itemq[:]:                                                   # item muncul lagi setelah 20 detik
        q[1] -= dt
        if q[1] <= 0: items.append(q[0]); P.itemq.remove(q)
    for f in P.feed: f[1] -= dt
    P.feed = [f for f in P.feed if f[1] > 0]
    for f in P.xpop: f[1] -= dt
    P.xpop = [f for f in P.xpop if f[1] > 0]
    if P.state == "mpdead":
        P.rt -= dt
        if P.rt <= 0: mp_respawn()

def mp_top(rt):
    me = MPS.get(NET.id, [0, 0]); t_ = TEAM.get(NET.id)
    if t_ is None: rt(f"MULTIPLAYER   {P.stage}", 12); rt(f"KILLS  {me[0]} / {P.limit}", 32, font, (255, 220, 120)); rt(f"PESERTA {len(RPS) + 1}     MATI {me[1]}     TAB = skor", 60); return
    n_ = sum(1 for v in TEAM.values() if v == 0); n2_ = len(TEAM) - n_; rt(f"{n_} VS {n2_}   {P.stage}", 12); sw = screen.get_width()
    parts = [(str(TSC[0]), TCOL[0]), ("  -  ", (200, 190, 170)), (str(TSC[1]), TCOL[1]), (f"   / {P.limit}", (200, 190, 170))]; xx = sw - 92 - sum(font.size(p_)[0] for p_, _ in parts)
    for p_, c_ in parts: txt(p_, (xx, 32), font, c_); xx += font.size(p_)[0]
    rt(f"{TNAME[t_]}   KILL {me[0]}  MATI {me[1]}   TAB = skor", 60, small, TCOL[t_])

def board(x, y, w, rows, head, hc, rh, f):     # satu panel papan skor: rows = [(id, kill, mati)]
    hh = 34 + rh * len(rows) + 6; D.rect(screen, (14, 10, 12), (x, y, w, hh)); D.rect(screen, hc, (x, y, w, hh), 2)
    txt(head, (x + 12, y + 8), small, hc if hc != (150, 120, 70) else (200, 180, 150)); txt("KILL", (x + w - 130, y + 8), small, (200, 180, 150)); txt("MATI", (x + w - 62, y + 8), small, (200, 180, 150))
    for i, (pid, k_, d_) in enumerate(rows):
        c = (255, 225, 130) if pid == NET.id else TCOL[TEAM[pid]] if pid in TEAM else PCOL[pid % 4]; yy = y + 34 + i * rh
        txt(LOB.get(pid, f"AGENT-{pid + 1}") + ("  (KAMU)" if pid == NET.id else ""), (x + 12, yy), f, c); txt(str(k_), (x + w - 124, yy), f, c); txt(str(d_), (x + w - 56, yy), f, c)

def scoreboard(cx, y):
    rows = sorted(((i, v[0], v[1]) for i, v in MPS.items()), key=lambda r_: (-r_[1], r_[2]))
    if TEAM:                                                               # dua panel: biru kiri, merah kanan
        for t_ in (0, 1): board(cx - 390 + t_ * 400, y, 380, [r_ for r_ in rows if TEAM.get(r_[0]) == t_], f"{TNAME[t_]}   {TSC[t_]}", TCOL[t_], 26, small)
    elif len(rows) <= 10: board(cx - 230, y, 460, rows, "PEMAIN", (150, 120, 70), 34, font)
    else: h = (len(rows) + 1) // 2; board(cx - 350, y, 340, rows[:h], "PEMAIN", (150, 120, 70), 26, small); board(cx + 10, y, 340, rows[h:], "PEMAIN", (150, 120, 70), 26, small)

CARD8 = {0: "N", 45: "NE", 90: "E", 135: "SE", 180: "S", 225: "SW", 270: "W", 315: "NW"}
def mp_col(i): return (255, 225, 130) if i == NET.id else TCOL[TEAM[i]] if i in TEAM else PCOL[i % 4]      # warna peserta: kamu = kuning, tim / per pemain

def mp_compass(sw, seen):                      # kompas di tengah atas: derajat, arah mata angin, penanda musuh terlihat (belah ketupat merah)
    cx, y0, hw, ppd = sw // 2, 8, 230, 4.0; hd = (math.degrees(P.a) + 90) % 360
    o = pg.Surface((hw * 2, 34), pg.SRCALPHA); o.fill((0, 0, 0, 90)); screen.blit(o, (cx - hw, y0)); D.line(screen, (90, 96, 110), (cx - hw, y0 + 34), (cx + hw, y0 + 34), 1)
    for d in range(0, 360, 5):
        x = cx + ((d - hd + 180) % 360 - 180) * ppd
        if abs(x - cx) > hw - 8: continue
        col = tuple(int(v * max(.25, 1 - abs(x - cx) / hw)) for v in (225, 228, 236)); major = d % 15 == 0
        D.line(screen, col, (x, y0 + (24 if major else 28)), (x, y0 + 32), 2 if major else 1)
        if major and abs(x - cx) > 28:
            lab = CARD8.get(d, str(d)); f = small if d in CARD8 else tiny; txt(lab, (int(x) - f.size(lab)[0] // 2, y0 + (4 if d in CARD8 else 7)), f, col)
    for r in RPS.values():
        if r.id in seen:
            x = cx + (((math.degrees(math.atan2(r.y - P.y, r.x - P.x)) + 90) % 360 - hd + 180) % 360 - 180) * ppd
            if abs(x - cx) < hw - 10: D.polygon(screen, (232, 52, 48), [(x, y0 + 28), (x + 5, y0 + 34), (x, y0 + 40), (x - 5, y0 + 34)]); D.polygon(screen, (40, 8, 8), [(x, y0 + 28), (x + 5, y0 + 34), (x, y0 + 40), (x - 5, y0 + 34)], 1)
    bx = pg.Rect(cx - 24, y0 - 2, 48, 28); D.rect(screen, (12, 14, 18), bx); D.rect(screen, (255, 225, 90), bx, 1); s_ = f"{int(hd) % 360:03d}"; txt(s_, (cx - small.size(s_)[0] // 2, y0 + 4), small, (255, 225, 90))

def mp_pill(sw):                               # nama map (kuning) di bawah kompas
    txt(P.stage, (sw // 2 - small.size(P.stage)[0] // 2, 46), small, (255, 225, 90))

def mp_stats():                               # di bawah kotak skor: angka health besar + bar health
    x, y = 14, 202; hp = int(max(0, P.hp)); col = (255, 70, 60) if hp < 35 else (255, 255, 255)
    txt(str(hp), (x, y), mid, col); by = y + 48; D.rect(screen, (12, 14, 18), (x - 1, by - 1, 138, 9)); D.rect(screen, (230, 70, 60) if hp < 35 else (235, 238, 245), (x, by, int(136 * hp / 100), 7))

def draw_mp_score(sw, sh):                     # kotak skor di bawah minimap: lencana tengkorak, skor kita vs lawan, status (TIED / LEADING / TRAILING) + waktu
    x0, y0, w_, h_ = 11, 138, 176, 56; t_ = TEAM.get(NET.id)
    if t_ is not None: a, b, ca, cb = TSC[t_], TSC[1 - t_], TCOL[t_], TCOL[1 - t_]                  # mode tim: skor timku vs tim lawan
    else: a = MPS.get(NET.id, [0, 0])[0]; b = max([v[0] for i, v in MPS.items() if i != NET.id] or [0]); ca, cb = (255, 210, 90), (255, 95, 85)      # free for all: kill-ku vs kill tertinggi lawan
    if P.state == "mpend" and getattr(P, "mp_end", None) is None: P.mp_end = time.time()
    el = int((getattr(P, "mp_end", None) or time.time()) - getattr(P, "mp_t0", time.time()))
    o = pg.Surface((w_, h_), pg.SRCALPHA); o.fill((8, 7, 10, 185)); screen.blit(o, (x0, y0)); D.rect(screen, (95, 82, 62), (x0, y0, w_, h_), 1)
    cx, cy = x0 + 32, y0 + h_ // 2; dm = [(cx, cy - 24), (cx + 24, cy), (cx, cy + 24), (cx - 24, cy)]; dk = (30, 34, 42); sk = (226, 229, 236)
    D.polygon(screen, dk, dm); D.polygon(screen, ca, dm, 2)
    D.circle(screen, sk, (cx, cy - 4), 9); D.rect(screen, sk, (cx - 5, cy + 3, 10, 8)); D.circle(screen, dk, (cx - 4, cy - 4), 3); D.circle(screen, dk, (cx + 4, cy - 4), 3)
    D.line(screen, dk, (cx, cy), (cx, cy + 2)); D.line(screen, dk, (cx - 2, cy + 7), (cx - 2, cy + 10)); D.line(screen, dk, (cx + 2, cy + 7), (cx + 2, cy + 10))
    for k, (v, c) in enumerate(((a, ca), (b, cb))): yy = y0 + 8 + k * 24; D.rect(screen, c, (x0 + 68, yy + 2, 3, 18)); txt(str(v), (x0 + 78, yy + 2), font, (255, 255, 255))
    st, sc = ("TIED", (235, 235, 240)) if a == b else ("LEADING", (120, 230, 140)) if a > b else ("TRAILING", (255, 110, 100))
    txt(st, (x0 + 118, y0 + 12), small, sc); txt(f"{el // 60}:{el % 60:02d}", (x0 + 118, y0 + 32), small, (235, 225, 205))

def mp_markers(seen):                          # penanda di atas kepala: lawan = segi enam tengkorak + jarak, teman = nama + panah
    for r in RPS.values():
        if not r.al: continue
        ally = friendly(NET.id, r.id); p_ = proj(r.x, r.y, 1.12)
        if not p_ or not (0 <= p_[0] < W) or P.zb[int(p_[0])] <= p_[2]: continue
        d = math.hypot(r.x - P.x, r.y - P.y); c = mp_col(r.id); x, y = int(p_[0] * SC), int(p_[1] * SC) - 14
        if ally:
            if d < 24: txt(r.name, (x - small.size(r.name)[0] // 2, y - 16), small, c); D.polygon(screen, c, [(x - 6, y - 2), (x + 6, y - 2), (x, y + 6)])
        elif d < 40:
            cy = y - 10; D.polygon(screen, (34, 10, 12), hexagon(x, cy, 13)); D.polygon(screen, (235, 70, 64), hexagon(x, cy, 13), 2)
            D.circle(screen, (242, 242, 246), (x, cy - 2), 5); D.rect(screen, (242, 242, 246), (x - 3, cy + 2, 6, 5)); D.circle(screen, (34, 10, 12), (x - 2, cy - 2), 1); D.circle(screen, (34, 10, 12), (x + 2, cy - 2), 1)
            s_ = f"{int(d)}m"; txt(s_, (x - small.size(s_)[0] // 2, cy + 16), small, (255, 255, 255))
            if d < 14: txt(r.name, (x - small.size(r.name)[0] // 2, cy - 30), small, c)

def mp_feed(sh):                               # daftar kill kiri bawah: nama pembunuh + ikon senjata + nama korban, diwarnai per tim
    ln = P.feed[-6:]; y0 = sh - 84 - 20 * len(ln)
    for i, f in enumerate(ln):
        yy = y0 + i * 20; by = f[2] if len(f) > 3 else -1; v = f[3] if len(f) > 3 else -1
        if by >= 0:
            kn, vn = LOB.get(by, f"AGENT-{by + 1}"), LOB.get(v, f"AGENT-{v + 1}"); wd = small.size(kn)[0] + small.size(vn)[0] + 52
            if NET.id in (by, v): o = pg.Surface((wd + 12, 20), pg.SRCALPHA); o.fill((0, 0, 0, 120)); screen.blit(o, (10, yy - 1))
            x = 16; txt(kn, (x, yy), small, mp_col(by)); x += small.size(kn)[0] + 8
            D.rect(screen, (235, 238, 245), (x, yy + 6, 22, 4)); D.rect(screen, (235, 238, 245), (x + 5, yy + 10, 3, 5)); D.rect(screen, (235, 238, 245), (x - 6, yy + 5, 6, 3)); x += 30
            txt(vn, (x, yy), small, mp_col(v))
        else: txt(f[0], (16, yy), small, (170, 176, 190))

def mp_xp(sw, sh):                             # "+100 XP" melayang di dekat crosshair saat kamu membunuh
    for i, (s_, life) in enumerate(P.xpop[-3:]): txt(s_, (sw // 2 + 54, sh // 2 - 34 - i * 20 - int((2.0 - life) * 14)), small, (255, 225, 90))

def mp_reload(sw, sh, t):                      # petunjuk "R RELOAD" saat peluru menipis
    w = P.weap[P.cur]
    if P.state != "play" or P.rl > 0 or w["ammo"] > max(1, int(w["mag"] * .3)): return
    if w["mags"] > 0: lab, kn, c = "RELOAD", ("X" if uses_pad() else pg.key.name(CFG["keys"]["reload"]).upper()), (255, 255, 255)
    elif w["ammo"] > 0: lab, kn, c = "AMMO RENDAH", None, (255, 190, 80)
    else:
        if int(t * 4) % 2: return
        lab, kn, c = "AMUNISI HABIS", None, (255, 80, 70)
    kw = max(22, small.size(kn)[0] + 10) + 8 if kn else 0; x = sw // 2 - (kw + small.size(lab)[0]) // 2; y = sh // 2 + 74
    if kn: kbox(x, y, kn)
    txt(lab, (x + kw, y + 3), small, c)

def draw_mp_overlay(sw, sh):                   # seluruh HUD multiplayer
    seen = {r.id for r in RPS.values() if r.al and not friendly(NET.id, r.id) and math.hypot(r.x - P.x, r.y - P.y) < 28 and los(P.x, P.y, r.x, r.y)}
    for r in RPS.values():                                                 # titik pemain di minimap
        if r.al: D.rect(screen, mp_col(r.id), (12 + r.x * 3 - 2, 10 + r.y * 3 - 2, 4, 4))
    mp_markers(seen); mp_compass(sw, seen); mp_pill(sw); draw_mp_score(sw, sh); mp_feed(sh); mp_xp(sw, sh); mp_reload(sw, sh, P.time)
    if P.state == "play": kw = kbox(sw // 2 - 40, sh - 30, "TAB"); txt("SKOR", (sw // 2 - 40 + kw + 8, sh - 27), small, (170, 176, 190))
    if (pg.key.get_pressed()[pg.K_TAB] or any(p.bt["back"] for p in PADS)) and P.state != "mpend": scoreboard(sw // 2, 150)

MAPDESC = {"RUMAH": "Ruangan kecil, pertarungan jarak dekat", "PEDESAAN": "Rumah kayu & pagar, area terbuka", "HUTAN": "Pepohonan rapat, banyak sudut buta", "KOTA": "Jalan, toko & mobil sebagai pelindung",
           "SEKOLAH": "Koridor panjang & ruang kelas", "BANDARA": "Terminal & apron pesawat, jarak jauh", "MANSION": "Banyak ruangan & pintu", "ARENA": "Aula besar berpilar, tanpa tempat sembunyi"}
MAPPREV = {}
def map_preview(name):                         # pratinjau denah (dibangun sekali, 80x80)
    if name not in MAPPREV:
        random.seed(7); np.random.seed(7); m = build_arena() if name == "ARENA" else build_stage(name); random.seed()
        sfc = pg.Surface((80, 80)); sfc.fill(tuple(int(v * .5) for v in FLOORS[THEMES["MANSION" if name == "ARENA" else name]["floor"]].mean(axis=(0, 1))))
        for y in range(N):
            for x in range(N):
                if m[y, x]: D.rect(sfc, tuple(int(v) for v in WALLS[m[y, x] - 1].mean(axis=(0, 1))), (x * 2, y * 2, 2, 2))
        MAPPREV[name] = sfc
    return MAPPREV[name]

LSTART = [-1]                                  # indeks rect tombol START di lobi (dibaca go())
LBG, LCARD = [], {}
def make_lobby_bg():                           # latar hangar gelap: lampu langit-langit, lantai perspektif, kendaraan, kisi merah
    sw, sh = 960, 600; b = pg.Surface((sw, sh)); vgrad(b, (6, 8, 12), (22, 24, 29)); vx, vy = 560, 250
    for k in range(-14, 15): D.line(b, (30, 33, 40), (vx, vy), (vx + k * 150, sh), 1)
    for j in range(1, 9): y = vy + int((sh - vy) * (j / 8) ** 2); D.line(b, (26, 29, 35), (0, y), (sw, y), 1)
    D.rect(b, (14, 16, 20), (610, 214, 350, 84)); D.polygon(b, (18, 20, 25), [(640, 214), (700, 168), (860, 168), (920, 214)]); D.rect(b, (10, 11, 14), (610, 298, 350, 10))
    for wx in (680, 880): D.circle(b, (8, 9, 11), (wx, 300), 22)
    o = pg.Surface((sw, sh), pg.SRCALPHA)
    for row in range(1, 6):                                                # panel lampu: makin dekat makin besar
        k = row / 5; y = int(vy - (vy - 12) * k ** 1.4); h = int(4 + 26 * k); w = int(14 + 150 * k); sp = int(34 + 210 * k)
        for col in range(-6, 7): cx = vx + col * sp; D.polygon(o, (190, 200, 215, int(30 + 70 * k)), [(cx - w // 2, y), (cx + w // 2, y), (cx + w // 2 - 6, y + h), (cx - w // 2 + 6, y + h)])
    for x in range(0, 300, 24): D.line(o, (200, 30, 36, 34), (x, 330), (x, sh), 1)
    for y in range(330, sh, 24): D.line(o, (200, 30, 36, 34), (0, y), (300, y), 1)
    b.blit(o, (0, 0)); vg = pg.Surface((sw, sh), pg.SRCALPHA)
    for k in range(40): D.rect(vg, (0, 0, 0, int(160 * (1 - k / 40) ** 2)), (k * 3, k * 2, sw - 2 * k * 3, sh - 2 * k * 2), 3)
    b.blit(vg, (0, 0)); return b

def lpanel(r, a=190, edge=(112, 116, 128)):    # panel gelap setengah transparan
    o = pg.Surface(r.size, pg.SRCALPHA); o.fill((10, 12, 16, a)); screen.blit(o, r.topleft); D.rect(screen, edge, r, 1)

def lcard_img(nm, on):                         # gambar kartu map (pratinjau denah dipotong 76x102), di-cache
    k = (nm, on)
    if k not in LCARD:
        if nm not in MAPPREV: return None
        big_ = pg.transform.smoothscale(MAPPREV[nm], (102, 102)); im = big_.subsurface(pg.Rect(14, 0, 74, 102)).copy()
        if not on: im.fill((105, 110, 124), special_flags=pg.BLEND_RGB_MULT)
        LCARD[k] = im
    return LCARD[k]

def draw_lobby(S, t):
    if not LBG: LBG.append(make_lobby_bg())
    screen.blit(LBG[0], (0, 0)); host = NET.host; sw = 960; mode = LBY["mode"]; size = MODES[mode][1]; players, teams = lobby_plan(); nb = len(players) - len(LOB)
    ct = lambda s_, cx, y, f=small, c=(235, 235, 240): txt(s_, (cx - f.size(s_)[0] // 2, y), f, c)
    miss = next((nm for nm in MAPS if nm not in MAPPREV), None)
    if miss: map_preview(miss)                                              # satu pratinjau per frame agar tidak patah
    ag = AGENT_BIG; screen.blit(ag, (sw // 2 - ag.get_width() // 2 + 20, 30)); ct(f"{len(LOB)}   {CFG['name']}", sw // 2 + 20, 50, small, (255, 225, 130))
    # --- bilah atas: tombol kembali, tab, alamat host ---
    o = pg.Surface((sw, 44), pg.SRCALPHA); o.fill((0, 0, 0, 120)); screen.blit(o, (0, 0))
    bk = LSTART[0] >= 0 and S["sel"] == LSTART[0] + 1; D.rect(screen, (62, 120, 168) if bk else (24, 26, 32), (10, 8, 30, 30)); D.rect(screen, (150, 200, 235) if bk else (150, 152, 160), (10, 8, 30, 30), 1); D.polygon(screen, (235, 235, 240), [(28, 16), (28, 30), (19, 23)])
    tabs = ("PLAY", "WEAPONS", "OPERATORS", "CUSTOMIZE"); tw_ = 104; tx_ = (sw - len(tabs) * tw_) // 2
    for i, nm in enumerate(tabs):
        r = pg.Rect(tx_ + i * tw_, 12, tw_ - 4, 22); on = i == 0; D.rect(screen, (70, 130, 180) if on else (24, 26, 32), r); D.rect(screen, (150, 200, 235) if on else (66, 70, 80), r, 1)
        ct(nm, r.centerx, r.y + 4, small, (255, 255, 255) if on else (130, 134, 146))
    ad = f"HOST  {local_ip()}:{MP_PORT}" if host else f"TERHUBUNG  {CFG['ip']}:{MP_PORT}"; aw = small.size(ad)[0] + 28; r = pg.Rect(sw - 14 - aw, 8, aw, 30)
    D.rect(screen, (24, 26, 32), r); D.rect(screen, (112, 116, 128), r, 1); D.circle(screen, (90, 230, 120), (r.x + 12, r.centery), 4); txt(ad, (r.x + 22, r.y + 7), small, (215, 220, 230))
    if host:                                                                # alamat untuk teman beda WiFi
        bx = pg.Rect(46, 298, 228, 52); lpanel(bx); ct("ALAMAT INTERNET (BEDA WIFI)", bx.centerx, bx.y + 6, tiny, (140, 200, 235))
        if TUN.state == "ready": ct(TUN.addr(), bx.centerx, bx.y + 20, font, (255, 225, 130)); ct("kirim ke temanmu  |  C = salin", bx.centerx, bx.y + 40, tiny, (170, 176, 190))
        elif TUN.state == "fail":
            em = TUN.err or "gagal"
            while small.size(em)[0] > bx.w - 16 and len(em) > 4: em = em[:-4] + "..."
            ct("tunnel gagal: " + em, bx.centerx, bx.y + 22, small, (240, 120, 100)); ct("main satu WiFi (LAN) masih bisa", bx.centerx, bx.y + 40, tiny, (170, 176, 190))
        else: ct("menyiapkan tunnel" + "." * (int(t * 2) % 4), bx.centerx, bx.y + 24, small, (215, 200, 150))
    # --- panel kiri: pengaturan match (gaya "daily challenges") ---
    px, py, pw_ = 46, 56, 228; cap = size * 2 if size else len(LOB) + bot_cap(); lm = max(LIMS[size])
    rows = (("MODE", MODES[mode][0], (mode + 1) / 3), ("JUMLAH BOT", str(nb), nb / max(1, size * 2 if size else bot_cap())),
            ("BATAS KILL" if not size else "BATAS KILL TIM", str(LBY["lim"]), LBY["lim"] / lm), ("TOTAL PESERTA", f"{len(players)}/{cap}", len(players) / max(1, cap)))
    lpanel(pg.Rect(px, py, pw_, 234)); txt("PENGATURAN MATCH", (px + 14, py + 10), small, (235, 235, 240)); txt("LOBI", (px + pw_ - 14 - small.size("LOBI")[0], py + 10), small, (140, 200, 235)); D.line(screen, (70, 74, 84), (px + 10, py + 32), (px + pw_ - 10, py + 32), 1)
    for i, (a, b, fr) in enumerate(rows):
        yy = py + 42 + i * 40; D.circle(screen, (120, 124, 136), (px + 20, yy + 8), 5, 1); txt(a, (px + 34, yy), small, (210, 214, 224)); txt(b, (px + pw_ - 14 - small.size(b)[0], yy), small, (110, 190, 240))
        D.rect(screen, (40, 44, 52), (px + 34, yy + 22, pw_ - 48, 4)); D.rect(screen, (235, 235, 240), (px + 34, yy + 22, int((pw_ - 48) * max(0, min(1, fr))), 4))
    D.line(screen, (70, 74, 84), (px + 10, py + 204), (px + pw_ - 10, py + 204), 1)
    ff = "FRIENDLY FIRE  NONAKTIF" if size else "SEMUA LAWAN SEMUA"; D.circle(screen, (150, 150, 160), (px + 20, py + 219), 5, 1); txt(ff, (px + 34, py + 211), small, (150, 210, 255) if size else (170, 160, 140))
    # --- panel kanan: party ---
    qw = 300; qx = sw - 14 - qw; qy = 56; prects = []; order = sorted(LOB)
    if size: cols = ([i for i in order if teams[i] == 0], [i for i in order if teams[i] == 1]); qh = 86 + max(1, len(cols[0]), len(cols[1])) * 26 + (22 if host else 8)
    else: qh = 40 + max(1, len(LOB)) * 28 + (26 if nb else 8)
    lpanel(pg.Rect(qx, qy, qw, qh)); txt("PARTY", (qx + 14, qy + 10), small, (235, 235, 240)); lbl = f"{len(LOB)}/4"; txt(lbl, (qx + qw - 14 - small.size(lbl)[0], qy + 10), small, (235, 235, 240)); D.line(screen, (70, 74, 84), (qx + 10, qy + 32), (qx + qw - 10, qy + 32), 1)
    if size:                                                                # mode tim: dua kolom, host klik pemain (atau B) untuk memindahkan ke tim lawan
        cwid = (qw - 24) // 2; rect_of = {}
        for t_ in (0, 1):
            cx_ = qx + 8 + t_ * (cwid + 8); hm = len(cols[t_]); tc = TCOL[t_]
            D.rect(screen, tuple(v // 4 for v in tc), (cx_, qy + 38, cwid, 22)); D.rect(screen, tc, (cx_, qy + 38, cwid, 22), 1); ct(TNAME[t_], cx_ + cwid // 2, qy + 42, small, tc)
            ct(f"{hm} pemain + {sum(1 for k_, v_ in teams.items() if v_ == t_ and k_ >= 100)} bot", cx_ + cwid // 2, qy + 63, tiny, (170, 176, 190))
            for k, pid in enumerate(cols[t_]):
                r = pg.Rect(cx_, qy + 84 + k * 26, cwid, 24); rect_of[pid] = r; sel_ = host and order.index(pid) == S.get("psel", 0)
                D.rect(screen, (40, 52, 70) if sel_ else (18, 20, 26), r); D.rect(screen, (150, 200, 235) if sel_ else (60, 64, 74), r, 1)
                nm = LOB[pid]; D.circle(screen, tc, (r.x + 10, r.centery), 4); txt(nm, (r.x + 20, r.y + 4), small, tc); xx = r.x + 26 + small.size(nm)[0]
                for tg in (("HOST",) if pid == 0 else ()) + (("KAMU",) if pid == NET.id else ()):
                    if xx + tiny.size(tg)[0] < r.right - 22: txt(tg, (xx, r.y + 6), tiny, (170, 176, 190)); xx += tiny.size(tg)[0] + 6
                if host: cy_ = r.centery; D.polygon(screen, (235, 238, 245), [(r.right - 14, cy_ - 5), (r.right - 14, cy_ + 5), (r.right - 6, cy_)] if t_ == 0 else [(r.right - 6, cy_ - 5), (r.right - 6, cy_ + 5), (r.right - 14, cy_)])
        if host: prects = [rect_of[pid] for pid in order]; txt("Klik pemain / tekan B = pindah tim", (qx + 12, qy + qh - 18), tiny, (170, 176, 190))
    else:
        for i, pid in enumerate(order):
            yy = qy + 38 + i * 28; c = PCOL[pid % 4]; nm = LOB[pid]; D.circle(screen, c, (qx + 20, yy + 10), 5); txt(nm, (qx + 34, yy + 3), small, c); xx = qx + 34 + small.size(nm)[0] + 8
            for tg in (("HOST",) if pid == 0 else ()) + (("KAMU",) if pid == NET.id else ()): txt(tg, (xx, yy + 5), tiny, (170, 176, 190)); xx += tiny.size(tg)[0] + 8
        if nb: txt(f"+ {nb} BOT", (qx + 14, qy + 38 + max(1, len(LOB)) * 28 + 2), small, (170, 176, 190))
    # --- bawah kiri: tombol mulai (gaya "quick play / start") ---
    D.circle(screen, (24, 26, 32), (68, 373), 22); D.circle(screen, (200, 40, 44) if host else (110, 60, 62), (68, 373), 22, 4); D.polygon(screen, (245, 245, 250) if host else (150, 150, 158), [(61, 362), (61, 384), (80, 373)])
    txt("MULAI MATCH" if host else "MENUNGGU HOST", (98, 365), font, (245, 245, 250) if host else (150, 154, 166))
    sr = pg.Rect(46, 396, 228, 94); bx_ = pg.Surface(sr.size); vgrad(bx_, (22, 70, 92), (8, 30, 46)) if host else vgrad(bx_, (30, 34, 40), (16, 18, 22)); screen.blit(bx_, sr.topleft)
    pul = .75 + .25 * math.sin(t * 5); D.rect(screen, (int(90 + 80 * pul), int(160 + 70 * pul), 235) if host else (70, 74, 84), sr, 2)
    ct("START" if host else "LOBI", sr.centerx, sr.y + 12, mid, (120, 205, 235) if host else (130, 134, 146)); ct("FIND A MATCH" if host else "MENUNGGU...", sr.centerx, sr.y + 68, small, (210, 225, 240) if host else (130, 134, 146))
    # --- bawah: mode (chip) + kartu map ---
    txt("PILIH MAP", (322, 366), small, (235, 235, 240)); D.rect(screen, (235, 235, 240), (308, 371, 6, 6))
    mrects = []; mw = 118
    for i, (nm, sz) in enumerate(MODES):
        r = pg.Rect(420 + i * (mw + 6), 362, mw, 24); mrects.append(r); on = i == mode
        D.rect(screen, (46, 96, 140) if on else (22, 24, 30), r); D.rect(screen, (150, 200, 235) if on else (66, 70, 80), r, 1); ct(nm, r.centerx, r.y + 4, small, (255, 255, 255) if on else (140, 144, 156))
        if sz: D.rect(screen, TCOL[0], (r.x + 2, r.bottom - 3, mw // 2 - 2, 2)); D.rect(screen, TCOL[1], (r.centerx, r.bottom - 3, mw // 2 - 2, 2))
    n = len(MAPS); cw_, cg = 74, 5; cx0 = 300; crects = []
    for i, nm in enumerate(MAPS):
        on = i == LBY["map"]; r = pg.Rect(cx0 + i * (cw_ + cg), 396 - (6 if on else 0), cw_, 102); crects.append(pg.Rect(r.x, 390, cw_, 108)); im = lcard_img(nm, on)
        if im: screen.blit(im, r.topleft)
        else: D.rect(screen, (24, 26, 32), r)
        sh_ = pg.Surface((cw_, 30), pg.SRCALPHA)
        for y in range(30): D.line(sh_, (0, 0, 0, int(210 * (y / 29) ** 1.2)), (0, y), (cw_, y))
        screen.blit(sh_, (r.x, r.bottom - 30)); txt(nm, (r.x + 5, r.bottom - 18), tiny, (255, 255, 255) if on else (170, 174, 186))
        D.rect(screen, (235, 245, 255) if on else (66, 70, 80), r, 2 if on else 1)
        if on: D.rect(screen, (70, 130, 180), (r.x, r.bottom - 4, cw_, 4))
    sel = MAPS[LBY["map"]]; txt(f"{sel}  -  {MAPDESC[sel]}", (300, 510), small, (255, 220, 120))
    hint = (("KIRI / KANAN = map   T = mode   ATAS / BAWAH = pilih pemain   + / - = jumlah bot (SHIFT = 5)   B / klik = pindah tim   K = batas kill   ENTER = MULAI" if size else "KIRI / KANAN = map     T = mode     ATAS / BAWAH atau + / - = bot (SHIFT = 5)     K = batas kill     ENTER = MULAI") if host else "Menunggu host memulai match...")
    for j, ln in enumerate(wrap(hint, small, 880)): txt(ln, (46, 530 + j * 18), small, (190, 195, 208))
    txt("ESC = keluar dari lobi" + ("     C = salin alamat internet" if host and TUN.addr() else "") + "", (46, 566), small, (140, 146, 160))
    if S["msg"]: txt(S["msg"], (sw - 46 - small.size(S["msg"])[0], 566), small, (240, 120, 100))
    rects = crects + mrects + prects + [sr]; LSTART[0] = len(rects) - 1; rects.append(pg.Rect(10, 8, 30, 30))                    # urutan rect: map, mode, baris pemain, tombol mulai (dipakai go())
    return rects

CODENAMES = ("VIPER", "GHOST", "FALCON", "COBRA", "RAVEN", "WOLF", "SHADOW", "HAWK", "NOVA", "ROGUE", "TITAN", "DELTA")
TTLC = {}
def ttl(sx, size, c1, c2):                     # judul gradasi (di-cache)
    k = (sx, size, c1, c2)
    if k not in TTLC: TTLC[k] = title_surf(sx, size, c1, c2, 3)
    return TTLC[k]
def mpos():                                    # posisi mouse di layar virtual (untuk efek hover)
    x, y = pg.mouse.get_pos(); return (x - OX) / VK, (y - OY) / VK
def pbtn(r, label, on, c1, c2, f=font):        # tombol gradasi besar
    g = pg.Surface(r.size); k = 1.0 if on else .6; vgrad(g, tuple(int(v * k) for v in c1), tuple(int(v * k) for v in c2)); screen.blit(g, r.topleft)
    D.rect(screen, (235, 245, 255) if on else (110, 120, 140), r, 2); txt(label, (r.centerx - f.size(label)[0] // 2, r.centery - f.get_height() // 2 + 1), f, (255, 255, 255) if on else (200, 205, 215))
def wifi_icon(cx, cy, col):
    for r_ in (8, 16, 24): D.arc(screen, col, (cx - r_, cy + 12 - r_, 2 * r_, 2 * r_), math.pi * .27, math.pi * .73, 3)
    D.circle(screen, col, (cx, cy + 12), 3)
def globe_icon(cx, cy, col, r=15):
    D.circle(screen, col, (cx, cy), r, 2); D.ellipse(screen, col, (cx - r // 2, cy - r, r, 2 * r), 2); D.line(screen, col, (cx - r, cy), (cx + r, cy), 2); D.line(screen, col, (cx, cy - r), (cx, cy + r), 1)
def person_icon(cx, cy, col):
    D.circle(screen, col, (cx, cy - 7), 8, 2); D.polygon(screen, col, [(cx - 14, cy + 16), (cx - 10, cy + 5), (cx + 10, cy + 5), (cx + 14, cy + 16)], 2)
def net_bg():                                  # latar ala lobi (hangar gelap) + potret agen + bilah atas + tombol kembali; mengembalikan rect tombol kembali
    if not LBG: LBG.append(make_lobby_bg())
    sw, sh = screen.get_size(); screen.blit(LBG[0], (0, 0)); screen.blit(AGENT_BIG, (-34, sh - AGENT_BIG.get_height() + 8)); screen.blit(LEFT_SHADE, (0, sh - 600))
    screen.blit(TOPBAR, (0, 0)); screen.blit(LOGO, (52, 15)); r = pg.Rect(10, 8, 30, 30); on = r.collidepoint(mpos())
    D.rect(screen, (62, 120, 168) if on else (24, 26, 32), r); D.rect(screen, (150, 200, 235) if on else (150, 152, 160), r, 1); D.polygon(screen, (235, 235, 240), [(28, 16), (28, 30), (19, 23)])
    return r
def info_card(r, icon, head, body, col):
    lpanel(r, 170, col); icon(r.x + 34, r.y + 34, col); txt(head, (r.x + 66, r.y + 14), small, col)
    for i, ln in enumerate(wrap(body, small, r.w - 24)[:5]): txt(ln, (r.x + 12, r.y + 56 + i * 18), small, (190, 198, 212))
def input_box(r, t, icon, text, hint, cnt):    # kotak ketik besar: ikon, teks, kursor berkedip, penghitung
    pul = .6 + .4 * math.sin(t * 4); D.rect(screen, (10, 14, 20), r); D.rect(screen, (int(70 + 60 * pul), int(130 + 60 * pul), 235), r, 3); icon(r.x + 32, r.centery, (120, 200, 240))
    if text: txt(text + ("_" if int(t * 2) % 2 else ""), (r.x + 62, r.y + 17), font, (255, 235, 180))
    else: txt(hint, (r.x + 62, r.y + 20), small, (110, 120, 135))
    txt(cnt, (r.right - 12 - small.size(cnt)[0], r.bottom - 20), tiny, (130, 140, 156))

def draw_join(S, t):
    rb = net_bg(); mp = mpos(); px, py, pw, ph = 340, 62, 590, 480; lpanel(pg.Rect(px, py, pw, ph), 218, (120, 150, 190))
    screen.blit(ttl("JOIN MATCH", 84, (255, 255, 255), (150, 200, 240)), (px + 24, py + 8)); txt("Masuk ke match temanmu lewat alamat host", (px + 30, py + 80), small, (190, 200, 215))
    input_box(pg.Rect(px + 30, py + 108, pw - 60, 58), t, globe_icon, S["ip"], "192.168.1.5   atau   bore.pub:41234", f"{len(S['ip'])}/48")
    conn = pg.Rect(px + 30, py + 184, 300, 54); paste = pg.Rect(px + 346, py + 184, 214, 54)
    pbtn(conn, "SAMBUNG", not paste.collidepoint(mp), (36, 150, 96), (14, 80, 56)); pbtn(paste, "TEMPEL", paste.collidepoint(mp), (46, 110, 170), (20, 56, 100))
    cw = (pw - 60 - 16) // 2
    info_card(pg.Rect(px + 30, py + 262, cw, 122), wifi_icon, "SATU WIFI (LAN)", "Pakai IP LAN host, contoh 192.168.1.5. Kamu dan host harus ada di WiFi yang sama.", (120, 220, 150))
    info_card(pg.Rect(px + 46 + cw, py + 262, cw, 122), globe_icon, "BEDA WIFI (INTERNET)", "Minta host mengirim ALAMAT INTERNET yang tampil di lobi, contoh bore.pub:41234.", (255, 210, 110))
    txt(f"Tanpa :port, dipakai port {MP_PORT}", (px + 30, py + 394), small, (150, 160, 176))
    for i, ln in enumerate(wrap(S["msg"], small, pw - 60)[:3]): txt(ln, (px + 30, py + 418 + i * 18), small, (240, 120, 100))
    txt("ENTER = sambung     CTRL+V = tempel     ESC = kembali", (px, 566), small, (190, 195, 208))
    return [conn, rb, paste]

def draw_name(S, t):
    rb = net_bg(); mp = mpos(); px, py, pw, ph = 340, 62, 590, 480; lpanel(pg.Rect(px, py, pw, ph), 218, (120, 150, 190))
    screen.blit(ttl("USERNAME", 84, (255, 255, 255), (255, 214, 130)), (px + 24, py + 8)); txt("Nama ini tampil di atas kepalamu, papan skor, dan daftar kill", (px + 30, py + 80), small, (190, 200, 215))
    input_box(pg.Rect(px + 30, py + 108, pw - 60, 58), t, person_icon, S["nm"], "ketik namamu...", f"{len(S['nm'])}/12")
    save = pg.Rect(px + 30, py + 184, 300, 54); rnd = pg.Rect(px + 346, py + 184, 214, 54)
    pbtn(save, "SIMPAN", not rnd.collidepoint(mp), (36, 150, 96), (14, 80, 56)); pbtn(rnd, "ACAK", rnd.collidepoint(mp), (170, 120, 40), (96, 60, 16))
    pn = clean_name(S["nm"], "AGENT"); txt("TAMPILAN DI GAME", (px + 30, py + 256), small, (235, 235, 240)); D.line(screen, (70, 74, 84), (px + 30, py + 278), (px + pw - 30, py + 278), 1)
    cw = (pw - 60 - 24) // 3
    for i, cap in enumerate(("DI ATAS KEPALA", "PAPAN SKOR", "DAFTAR KILL")):
        r = pg.Rect(px + 30 + i * (cw + 12), py + 288, cw, 112); lpanel(r, 170, (90, 100, 120)); txt(cap, (r.x + 10, r.y + 8), tiny, (150, 160, 176)); screen.set_clip(r.inflate(-4, -4))
        if i == 0:
            txt(pn, (r.centerx - small.size(pn)[0] // 2, r.y + 44), small, (90, 150, 255)); D.polygon(screen, (90, 150, 255), [(r.centerx - 6, r.y + 64), (r.centerx + 6, r.y + 64), (r.centerx, r.y + 72)])
            D.circle(screen, (214, 160, 126), (r.centerx, r.y + 86), 8)
        elif i == 1:
            for j, (nm_, c_, k_) in enumerate(((pn, (255, 225, 130), "12"), ("BOT-1", (255, 95, 85), "9"))):
                y_ = r.y + 32 + j * 30; D.rect(screen, (40, 52, 70) if j == 0 else (18, 20, 26), (r.x + 8, y_, r.w - 16, 24)); D.circle(screen, c_, (r.x + 18, y_ + 12), 4); txt(nm_, (r.x + 28, y_ + 5), small, c_); txt(k_, (r.right - 22 - small.size(k_)[0] // 2, y_ + 5), small, c_)
        else:
            x_ = r.x + 8; txt(pn, (x_, r.y + 48), small, (255, 225, 130)); x_ += small.size(pn)[0] + 6; D.rect(screen, (235, 238, 245), (x_, r.y + 54, 16, 4)); D.rect(screen, (235, 238, 245), (x_ + 4, r.y + 58, 3, 5)); x_ += 22; txt("BOT-1", (x_, r.y + 48), small, (255, 95, 85))
            txt("tewas", (r.x + 8, r.y + 76), tiny, (170, 176, 190))
        screen.set_clip(None)
    ok = bool(S["nm"].strip()); txt("Maks. 12 karakter: huruf, angka, spasi, _ dan -" + ("" if ok else "     (kosong = AGENT)"), (px + 30, py + 418), small, (150, 160, 176))
    txt("ENTER = simpan     ESC = kembali", (px, 566), small, (190, 195, 208))
    return [save, rb, rnd]

WHEEL = hasattr(pg, "MOUSEWHEEL")
def switch_weapon(i):                         # dipakai tombol 1/2/3 dan roll mouse
    if i != P.cur: P.roll = 1.0 if (i - P.cur) % 3 == 1 else -1.0; P.cur = i; P.rl = 0; P.swap = .25; SND["rmag"].stop(); SND["rsg"].stop(); play("step", 5)

def set_mouse(on): pg.event.set_grab(on); pg.mouse.set_visible(not on); pg.mouse.get_rel()

def draw_co(t):                                # split screen: render tiap pemain ke separuh layar
    for i in (0, 1):
        with as_pl(i):
            set_view(i); render()
            if P.state in ("play", "wait"): draw_weapon(t)
            draw_scope(); draw_blood(); draw_danger(P.time); draw_hud(P.time); draw_flash()
    set_view(None); D.rect(DISP, (8, 6, 8), (476, 0, 8, 600))
    if PL[0].paused:
        o = pg.Surface(DISP.get_size(), pg.SRCALPHA); o.fill((0, 0, 0, 185)); DISP.blit(o, (0, 0)); draw_pause_menu()

def pad_events(S, dt):                         # ubah tombol controller menjadi event keyboard agar menu lama tetap dipakai
    ev = []; K = lambda k: pg.event.Event(pg.KEYDOWN, key=k, unicode="", mod=0)
    ing = S["mode"] == "play" and P.state in ("play", "down", "wait") and not getattr(P, "paused", False)
    for pad in PADS:
        if ing:
            if pad.pressed("start"): ev.append(K(pg.K_ESCAPE))
            continue
        if S["mode"] == "play" and P.state == "cut":
            if pad.pressed("a") or pad.pressed("start"): ev.append(K(pg.K_RETURN))
            if pad.pressed("b"): ev.append(K(pg.K_ESCAPE))
            continue
        for d in pad.dirs(dt): ev.append(K({"u": pg.K_UP, "d": pg.K_DOWN, "l": pg.K_LEFT, "r": pg.K_RIGHT}[d]))
        paused = S["mode"] == "play" and (P.state == "pause" or getattr(P, "paused", False))
        if pad.pressed("a"): ev.append(K(pg.K_RETURN))
        if pad.pressed("b"): ev.append(K(pg.K_ESCAPE))
        if pad.pressed("start"): ev.append(K(pg.K_ESCAPE if paused else pg.K_RETURN))
        if pad.pressed("back") and paused: ev.append(K(pg.K_m))
        if pad.pressed("y") and S["mode"] == "lobby": ev.append(K(pg.K_k))
        if pad.pressed("x") and S["mode"] == "lobby": ev.append(K(pg.K_t))
        if pad.pressed("rb") and S["mode"] == "lobby": ev.append(K(pg.K_b))
        if paused or S["mode"] == "settings":                                                  # LB / RB = ganti tab di pengaturan pause
            if pad.pressed("lb"): ev.append(K(pg.K_q))
            if pad.pressed("rb"): ev.append(K(pg.K_e))
    return ev

def menu_count(S): return len(menu_items(S)) if S["mode"] in ("main", "diff", "mp", "players") else len(menu_rows(S))

def main():
    global LIGHT, FLICK, MPSTART
    S = dict(mode="intro", sel=0, wait=None, ip=CFG["ip"], msg="", nm="", psel=0); rects = []
    set_mouse(False); ambient.set_volume(CFG["vol"] / 10); ambient.play(-1)
    t, run, frames = 0.0, True, 0; limit = int(os.environ.get("HG_FRAMES", 0))
    def to_menu(): NET.close(); LOB.clear(); RPS.clear(); TEAM.clear(); PL[:] = [PL[0]]; set_view(None); S.update(mode="main", sel=0, wait=None, msg="", co=False); set_mouse(False)
    def go(act):                                                  # aksi saat item menu dipilih
        m = S["mode"]
        if m == "main":
            if act == 0: S.update(mode="diff", sel=1, co=False, msg="")
            elif act == 1:                                                 # CO-OP (split screen)
                if len(PADS) < (2 if CFG["input"] == "pad" else 1): S["msg"] = "Split screen butuh controller: colokkan (P2 = controller; mode CONTROLLER butuh 2). Tunggu sekitar 1 detik lalu coba lagi."
                else: S.update(mode="diff", sel=1, co=True, msg="")
            elif act == 2: S.update(mode="mp", sel=0, msg="")
            elif act == 3: S.update(mode="settings", sel=0); pause_open(); PM.update(page=1, menu=True)                # pengaturan memakai tampilan bertab yang sama dengan menu pause
            else: return False
        elif m == "players":
            if act == 0: S.update(mode="diff", sel=1, co=False, msg="")
            elif act == 1:
                if len(PADS) < (2 if CFG["input"] == "pad" else 1): S["msg"] = "Split screen butuh controller: colokkan (P2 = controller; mode CONTROLLER butuh 2). Tunggu sekitar 1 detik lalu coba lagi."
                else: S.update(mode="diff", sel=1, co=True, msg="")
            else: S.update(mode="main", sel=0, msg="")
        elif m == "diff":
            if act < 3: start_game(list(DIFFS)[act], co=S.get("co", False)); S["mode"] = "play"; set_mouse(True); begin_cutscene("intro")
            else: S.update(mode="main", sel=1 if S.get("co") else 0)
        elif m == "mp":
            if act == 0:
                try: NET.start_host(); TUN.start(MP_PORT); LOB.clear(); LOB[0] = clean_name(CFG["name"], "AGENT-1"); MPSTART = None; LBY.update(map=0, lim=10, bots=2, mode=0, tm={}); S.update(mode="lobby", msg="")
                except OSError as ex: NET.close(); S["msg"] = f"Gagal membuka port {MP_PORT}: {ex}"
            elif act == 1: S.update(mode="mp_join", msg="")
            elif act == 2: S.update(mode="mp_name", nm=CFG["name"], msg="")
            else: S.update(mode="main", sel=2)
        elif m == "mp_name" and act == 1: S.update(mode="mp", sel=2, msg="")
        elif m == "mp_name" and act == 2: S["nm"] = clean_name(random.choice(CODENAMES) + str(random.randint(10, 99)), "AGENT")        # tombol ACAK
        elif m == "mp_name": CFG["name"] = clean_name(S["nm"], "AGENT"); save_cfg(); S.update(mode="mp", sel=2, msg="")
        elif m == "mp_join" and act == 1: S.update(mode="mp", sel=1, msg="")
        elif m == "mp_join" and act == 2: S["ip"] = addr_clean(clip_get())                                       # tombol TEMPEL
        elif m == "mp_join":
            try: NET.connect(S["ip"]); NET.send({"t": "join", "n": CFG["name"]}); CFG["ip"] = S["ip"]; save_cfg(); LOB.clear(); MPSTART = None; S.update(mode="lobby", msg="")
            except (OSError, ValueError, UnicodeError) as ex: NET.close(); S["msg"] = join_fail_msg(S["ip"], ex)
        elif m == "lobby" and act == LSTART[0] + 1: NET.close(); LOB.clear(); S.update(mode="mp", sel=0, msg="")        # tombol kembali di pojok kiri atas
        elif m == "lobby" and NET.host:
            if act == LSTART[0]:
                if lobby_start() is False: S["msg"] = "Butuh minimal 2 peserta (mode tim: kedua tim harus ada isinya). Tambah bot dengan + / - atau tunggu temanmu"
            elif act < len(MAPS): LBY["map"] = act; lobby_cast()
            elif act < len(MAPS) + 3: lobby_mode(act - len(MAPS))
            else: S["psel"] = act - len(MAPS) - 3; lobby_toggle(S["psel"])
        elif m == "settings":
            if act < len(KEYNAMES): S["wait"] = act
            elif act == I_BACK: S.update(mode="main", sel=3); save_cfg()
        return True
    while run:
        dt = min(clock.tick(45) / 1000, .05); t += dt; click_ev, act, adj = False, None, 0; kbp = kb_on()      # kbp: keyboard/mouse boleh dipakai bermain
        pads_poll(dt)
        for e in [ev_fix(x_) for x_ in pg.event.get()] + pad_events(S, dt):
            if e.type == pg.QUIT: run = False
            elif S["mode"] == "intro":                                                    # layar startup: tombol / klik apa saja = masuk ke menu utama
                if e.type in (pg.KEYDOWN, pg.MOUSEBUTTONDOWN) and t > .6: S.update(mode="main", sel=0, msg=""); play("pickup")
            elif S["mode"] == "play" and P.state == "cut": cut_event(e)
            elif S["mode"] == "play" and (P.state == "pause" or getattr(P, "paused", False)) and e.type in (pg.KEYDOWN, pg.MOUSEBUTTONDOWN, pg.MOUSEMOTION):
                r_ = pause_event(e)                                    # menu pause: lanjutkan / pengaturan / menu utama
                if r_ == "resume": pause_close()
                elif r_ == "menu": to_menu()
            elif S["mode"] == "play":
                if e.type == pg.MOUSEBUTTONDOWN and e.button == 1: click_ev = kbp
                elif not kbp and e.type in (pg.MOUSEWHEEL, pg.MOUSEBUTTONDOWN): pass
                elif WHEEL and e.type == pg.MOUSEWHEEL and P.state == "play": switch_weapon((P.cur - (1 if e.y > 0 else -1 if e.y < 0 else 0)) % 3)
                elif not WHEEL and e.type == pg.MOUSEBUTTONDOWN and e.button in (4, 5) and P.state == "play": switch_weapon((P.cur + (-1 if e.button == 4 else 1)) % 3)
                elif e.type == pg.KEYDOWN:
                    if e.key == pg.K_ESCAPE:
                        if CO() and P.paused: P.paused = False; set_mouse(True)
                        elif CO() and P.state in ("play", "down", "wait"): P.paused = True; set_mouse(False); pause_open()
                        elif P.state == "play": P.state = "pause"; set_mouse(False); pause_open()
                        elif P.state == "pause": P.state = "play"; set_mouse(True)
                        elif P.state != "mpdead": to_menu()
                    elif e.key == pg.K_RETURN:
                        if P.state == "dead": respawn()
                        elif P.state in ("over", "ending", "mpend"): to_menu()
                        elif P.state == "clear": next_floor(); begin_cutscene("loc")
                    elif e.key == pg.K_m and (P.state == "pause" or getattr(P, "paused", False)): to_menu()
                    elif not kbp or getattr(P, "paused", False): pass
                    elif P.state == "play" and e.key == CFG["keys"]["reload"]: start_reload()
                    elif P.state == "play" and e.key == CFG["keys"]["granat"]: throw("granat")
                    elif P.state == "play" and e.key == CFG["keys"]["flash"]: throw("flash")
                    elif P.state == "play" and e.key in (pg.K_1, pg.K_2, pg.K_3): switch_weapon(e.key - pg.K_1)
            elif S["mode"] == "settings" and e.type in (pg.KEYDOWN, pg.MOUSEBUTTONDOWN, pg.MOUSEMOTION):
                pause_event(e)                                                                         # tab TOMBOL / AUDIO & BIDIK / INPUT / LAYAR
                if PM["page"] == 0: S.update(mode="main", sel=3, msg=""); save_cfg()
            elif S["mode"] == "mp_join" and e.type == pg.KEYDOWN:
                if e.key == pg.K_ESCAPE: S.update(mode="mp", sel=1)
                elif e.key == pg.K_RETURN: act = 0
                elif e.key == pg.K_BACKSPACE: S["ip"] = S["ip"][:-1]
                elif e.key == pg.K_v and e.mod & pg.KMOD_CTRL: S["ip"] = addr_clean(clip_get())
                elif getattr(e, "unicode", "") and e.unicode.isascii() and (e.unicode.isalnum() or e.unicode in ".:-") and len(S["ip"]) < 48: S["ip"] += e.unicode
            elif S["mode"] == "mp_name" and e.type == pg.KEYDOWN:
                if e.key == pg.K_ESCAPE: S.update(mode="mp", sel=2)
                elif e.key in (pg.K_RETURN, pg.K_KP_ENTER): act = 0
                elif e.key == pg.K_BACKSPACE: S["nm"] = S["nm"][:-1]
                elif e.unicode and e.unicode.isascii() and e.unicode.isprintable() and (e.unicode.isalnum() or e.unicode in "_- ") and len(S["nm"]) < 12: S["nm"] += e.unicode
            elif S["mode"] == "lobby" and e.type == pg.KEYDOWN:
                if e.key == pg.K_ESCAPE: NET.close(); LOB.clear(); S.update(mode="mp", sel=0)
                elif NET.host and e.key == pg.K_RETURN:
                    if lobby_start() is False: S["msg"] = "Butuh minimal 2 peserta (mode tim: kedua tim harus ada isinya). Tambah bot dengan + / - atau tunggu temanmu"
                elif NET.host and e.key in (pg.K_LEFT, pg.K_RIGHT): LBY["map"] = (LBY["map"] + (1 if e.key == pg.K_RIGHT else -1)) % len(MAPS); lobby_cast()
                elif NET.host and e.key in (pg.K_UP, pg.K_DOWN):
                    if MODES[LBY["mode"]][1]: S["psel"] = (S["psel"] + (1 if e.key == pg.K_DOWN else -1)) % max(1, len(LOB))
                    else: lobby_bots((5 if pg.key.get_mods() & pg.KMOD_SHIFT else 1) * (1 if e.key == pg.K_UP else -1))
                elif NET.host and e.key == pg.K_k: lims = LIMS[MODES[LBY["mode"]][1]]; LBY["lim"] = lims[(lims.index(LBY["lim"]) + 1) % len(lims)] if LBY["lim"] in lims else lims[0]; lobby_cast()
                elif NET.host and e.key in (pg.K_EQUALS, pg.K_PLUS, pg.K_KP_PLUS, pg.K_MINUS, pg.K_KP_MINUS): lobby_bots((5 if pg.key.get_mods() & pg.KMOD_SHIFT else 1) * (1 if e.key in (pg.K_EQUALS, pg.K_PLUS, pg.K_KP_PLUS) else -1))
                elif NET.host and e.key == pg.K_t: lobby_mode(LBY["mode"] + 1)
                elif NET.host and e.key == pg.K_c and TUN.addr(): S["msg"] = "Alamat internet disalin: " + TUN.addr() if clip_set(TUN.addr()) else "Gagal menyalin, ketik manual: " + TUN.addr()
                elif NET.host and e.key == pg.K_b and MODES[LBY["mode"]][1]: lobby_toggle(S["psel"])
            elif e.type == pg.KEYDOWN and S["wait"] is not None:      # menunggu tombol baru
                if e.key != pg.K_ESCAPE: CFG["keys"][KEYNAMES[S["wait"]][1]] = e.key; save_cfg()
                S["wait"] = None
            elif e.type == pg.KEYDOWN:
                n = menu_count(S); card = S["mode"] in ("main", "diff", "mp", "players")
                if card and e.key in (pg.K_LEFT, pg.K_RIGHT): S["sel"] = (S["sel"] + (1 if e.key == pg.K_RIGHT else -1)) % n
                elif e.key == pg.K_DOWN: S["sel"] = (S["sel"] + 1) % n
                elif e.key == pg.K_UP: S["sel"] = (S["sel"] - 1) % n
                elif e.key == pg.K_LEFT: adj = -1
                elif e.key == pg.K_RIGHT: adj = 1
                elif e.key in (pg.K_RETURN, pg.K_SPACE): act = S["sel"]
                elif e.key == pg.K_ESCAPE:
                    if S["mode"] == "main": run = False
                    else: pm_ = S["mode"]; S.update(mode={"diff": "main", "players": "main", "mp": "main", "settings": "main"}[pm_], sel={"diff": 1 if S.get("co") else 0, "mp": 2, "settings": 3}.get(pm_, 0), msg=""); save_cfg()
            elif e.type == pg.MOUSEMOTION:
                for i, r in enumerate(rects):
                    if r.collidepoint(e.pos): S["sel"] = i
            elif e.type == pg.MOUSEBUTTONDOWN and e.button == 1:
                tb = next((i for i, r in enumerate(TABR) if r.collidepoint(e.pos)), -1) if S["mode"] in ("main", "diff", "mp", "players") else -1
                if tb >= 0: S.update(({"mode": "main", "sel": 0}, {"mode": "diff", "sel": 1}, {"mode": "mp", "sel": 0})[tb], co=False, msg="")        # klik tab di atas = pindah menu
                else:
                    for i, r in enumerate(rects):
                        if r.collidepoint(e.pos): S["sel"] = i; act = i; adj = 1 if e.pos[0] > r.centerx else -1
        if NET.active:
            for src, m_ in NET.poll():
                try:
                    if S["mode"] == "lobby" and not NET.host and m_.get("t") in ("gone", "full"):        # host hilang / lobi penuh saat masih di lobi
                        NET.close(); LOB.clear(); S.update(mode="mp", sel=1, msg="Koneksi ke host terputus" if m_["t"] == "gone" else "Lobi penuh (maksimal 4 pemain)"); break
                    net_msg(src, m_)
                except Exception: import traceback; traceback.print_exc()                           # satu pesan rusak tidak boleh mematikan game
        if MPSTART and S["mode"] in ("lobby", "play"): start_mp(*MPSTART); MPSTART = None; S["mode"] = "play"; set_mouse(True)
        if S["mode"] != "play":
            if S["mode"] == "settings" and act in (I_INP, I_RES): adj = adj or 1; act = None                     # ENTER / klik pada "Kontrol" = ganti pilihan
            if S["mode"] == "settings" and adj and S["sel"] in (I_SENS, I_VOL, I_PSENS):
                k = {I_SENS: "sens", I_VOL: "vol", I_PSENS: "psens"}[S["sel"]]; CFG[k] = max(0 if k == "vol" else 1, min(10, CFG[k] + adj)); ambient.set_volume(CFG["vol"] / 10); save_cfg()
            elif S["mode"] == "settings" and adj and S["sel"] == I_INP:
                modes = ["auto", "kbm", "pad"]; CFG["input"] = modes[(modes.index(CFG["input"]) + adj) % 3]; save_cfg()
            elif S["mode"] == "settings" and adj and S["sel"] == I_RES: res_step(adj)
            if act is not None and go(act) is False: run = False
        if S["mode"] == "play":
            rel = pg.mouse.get_rel(); mdx, mdy = rel[0], rel[1]
            FLICK = .4 if random.random() < .012 else max(0, FLICK - dt * 3); LIGHT = (.92 + .05 * math.sin(t * 11) - FLICK) if SKY is None else 1.0
            if P.mode == "mp": mp_tick(dt)
            if CO(): co_step(dt, rel, click_ev)
            elif P.state == "play": I = gather_input(0, rel, click_ev); pad_actions(0); update(dt, I)
            if P.state == "cut": set_view(None); draw_cut(dt)
            elif CO() and P.state != "ending": draw_co(P.time)
            else: set_view(None); render(); draw_weapon(t); draw_scope(); draw_blood(); draw_danger(P.time); draw_hud(P.time); draw_flash()
        else: rects = draw_menu(S, t)
        present(); frames += 1
        if limit and frames >= limit: break
    NET.close(); pg.quit()

if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback; traceback.print_exc()
        input("\nTerjadi error di atas. Tekan ENTER untuk menutup...")