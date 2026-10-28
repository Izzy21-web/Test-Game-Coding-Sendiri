"""
AGENT DUTY - game FPS agen rahasia di dalam mansion (raycasting) dengan Python
Instal : pip install pygame numpy
Jalan  : python agent_duty.py
Menu: START GAME > pilih difficulty. Kontrol bisa diatur di SETTINGS | Klik kiri tembak | R reload
         1/2/3 ganti senjata | Shift lari | ENTER ulang | ESC keluar
Semua grafik & suara dibuat lewat kode (tanpa file gambar/audio).
"""
import math, random, os, json
from collections import deque
from types import SimpleNamespace as NS
import numpy as np
import pygame as pg

SAVE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_duty_settings.json")
CFG = dict(sens=5, vol=8, keys=dict(maju=pg.K_w, mundur=pg.K_s, kiri=pg.K_a, kanan=pg.K_d, lari=pg.K_LSHIFT, reload=pg.K_r, lompat=pg.K_SPACE, granat=pg.K_g, flash=pg.K_f))
try:
    with open(SAVE) as f: _sv = json.load(f)
    CFG["sens"], CFG["vol"] = int(_sv["sens"]), int(_sv["vol"]); CFG["keys"].update({k: int(v) for k, v in _sv["keys"].items()})
except Exception: pass
def save_cfg():
    try:
        with open(SAVE, "w") as f: json.dump(CFG, f)
    except Exception: pass
SR = 22050
pg.mixer.pre_init(SR, -16, 2, 512)
pg.init()
MIX = pg.mixer.get_init()          # None jika tidak ada perangkat audio
W, H, SC = 320, 200, 3                      # resolusi render, skala jendela
screen = pg.display.set_mode((W * SC, H * SC))
pg.display.set_caption("AGENT DUTY")
canvas = pg.Surface((W, H))
clock = pg.time.Clock()
font, small, big, mid = pg.font.Font(None, 30), pg.font.Font(None, 22), pg.font.Font(None, 96), pg.font.Font(None, 66)
rng = np.random.default_rng(7)
D = pg.draw

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
    "boom": snd(boom(1.1, 60, .35, 22, .6), 1.0), "flashbang": snd(flash_snd(), 1.0), "clink": snd(click(1700, .06), .5),
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

WALLS = np.stack([tex_wallpaper(), tex_wood(), tex_plaster()]).clip(0, 255).astype(np.float32)
BASE_WALLS = WALLS.copy()
MAP_NAMES = ["Rumah", "Mansion", "Pedesaan", "Kota", "Bandara", "Hutan", "Sekolah"]
MAP_TINTS = {"Rumah": (1.02, 1.02, 0.92), "Mansion": (1.0, .92, .94), "Pedesaan": (.82, 1.04, .78), "Kota": (.78, .84, .96), "Bandara": (.90, .94, 1.05), "Hutan": (.70, .92, .68), "Sekolah": (1.05, 1.02, .84)}
FLOOR, CEIL = tex_floor().clip(0, 255), tex_ceil().clip(0, 255)
BASE_FLOOR, BASE_CEIL = FLOOR.copy(), CEIL.copy()

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

TYPES = {"preman": dict(hp=45, spd=2.1, dmg=10, rng=0, cd=1.0, snd="", c=((72, 74, 82), (46, 58, 96), (205, 160, 125))),
         "penjahat": dict(hp=60, spd=1.5, dmg=9, rng=11, cd=1.7, snd="pistol", c=((104, 64, 40), (40, 40, 48), (190, 140, 105))),
         "agen": dict(hp=90, spd=1.8, dmg=7, rng=12, cd=.85, snd="rifle", c=((24, 24, 30), (20, 20, 26), (215, 170, 135))),
         "bodyguard": dict(hp=160, spd=2.6, dmg=16, rng=0, cd=1.0, snd="", c=((18, 18, 22), (18, 18, 22), (170, 120, 90))),
         "boss": dict(hp=900, spd=2.0, dmg=9, rng=14, cd=.45, snd="rifle", c=((226, 226, 232), (30, 30, 36), (190, 140, 105)))}
TEX = {"fire": make_fire(), **{k: make_item(k) for k in ("health", "armor", "ammo", "granat", "flash")}}
for k, v in TYPES.items(): TEX[k] = make_enemy(k, *v["c"]); TEX[k + "_b"] = make_enemy(k, *v["c"], 1); TEX["dead_" + k] = make_dead(v["c"][0], v["c"][2])
TEX["cp0"], TEX["cp1"] = make_cp(False), make_cp(True)
TEX["boom"] = make_blast(((30, (200, 50, 10)), (22, (255, 140, 20)), (14, (255, 220, 90)), (7, (255, 255, 220))))
TEX["flashfx"] = make_blast(((30, (255, 255, 255)), (20, (255, 255, 255))))

# ================= PETA & UTILITAS =================
N = 40
def build_map():
    for _ in range(100):
        m = np.zeros((N, N), np.int8); m[0, :] = m[-1, :] = m[:, 0] = m[:, -1] = 1; doors = set()
        def split(x0, y0, x1, y1):                # bagi area jadi 2 ruangan, beri pintu selebar 2 sel
            w, h = x1 - x0, y1 - y0
            if w < 12 and h < 12: return
            vert = (w >= h) if (w >= 12 and h >= 12) else (w >= 12)
            a0, a1 = (x0, x1) if vert else (y0, y1)
            ends = lambda c: ((c, y0 - 1), (c, y1)) if vert else ((x0 - 1, c), (x1, c))
            cand = [c for c in range(a0 + 5, a1 - 5) if not any(e in doors for e in ends(c))]
            if not cand: return
            c = random.choice(cand); wt = random.choice((1, 1, 2, 3)); lo, hi = (y0, y1) if vert else (x0, x1)
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
        for _ in range(70):                       # perabot: lemari / meja dari balok kayu
            x, y = random.randint(2, N - 4), random.randint(2, N - 4); w, h = random.choice(((1, 1), (2, 1), (1, 2)))
            near = any((x + i, y + j) in doors for i in range(-2, w + 2) for j in range(-2, h + 2))
            if not m[y - 1:y + h + 1, x - 1:x + w + 1].any() and not near and not (x < 8 and y < 8): m[y:y + h, x:x + w] = 2
        seen = np.zeros((N, N), bool); seen[3, 3] = True; q = deque([(3, 3)])
        while q:
            x, y = q.popleft()
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if m[ny, nx] == 0 and not seen[ny, nx]: seen[ny, nx] = True; q.append((nx, ny))
        if seen.sum() > 650: break
    m[(m == 0) & ~seen] = 1                       # ruang yang tak terjangkau ditutup
    # Tiap lokasi mempunyai tata letak berbeda, bukan hanya perubahan warna.
    name = getattr(P, "map_name", "Mansion")
    if name != "Mansion":
        m[:] = 0; m[0, :] = m[-1, :] = m[:, 0] = m[:, -1] = 1
        def wall_h(y, x0, x1, typ=1, door=None):
            m[y, x0:x1] = typ
            if door is not None: m[y, door:door+2] = 0
        def wall_v(x, y0, y1, typ=1, door=None):
            m[y0:y1, x] = typ
            if door is not None: m[door:door+2, x] = 0
        if name == "Rumah":
            wall_v(13, 2, 25, 2, 8); wall_h(13, 13, 28, 2, 20); wall_v(28, 13, 37, 2, 24)
            wall_h(25, 2, 13, 3, 6); m[5:8, 19:22] = 3; m[30:33, 8:11] = 3
        elif name == "Pedesaan":
            # jalur tanah terbuka, rumah-rumah kecil dan pagar
            for x, y, w, h in ((10,8,5,4),(25,5,6,5),(8,25,6,5),(27,27,5,4)):
                m[y:y+h, x:x+w] = 2
            for x in range(4, 36, 6):
                if x not in (10, 28): m[18, x:x+3] = 3
            m[3:6, 3:6] = 0
        elif name == "Kota":
            # blok gedung dipisahkan jalan lurus
            for x, y, w, h in ((7,6,6,7),(19,5,7,8),(30,7,5,6),(6,24,7,8),(20,25,7,7),(31,24,4,7)):
                m[y:y+h, x:x+w] = 1
            m[12:15, 8:12] = 0; m[8:12, 21:24] = 0; m[27:30, 22:25] = 0
        elif name == "Bandara":
            # terminal panjang, lorong gerbang, dan runway terbuka
            wall_h(11, 5, 34, 2, 9); wall_h(20, 5, 34, 2, 15); wall_v(5, 5, 21, 1, 15)
            for x in (11, 17, 23, 29):
                m[6:10, x:x+2] = 3; m[22:26, x:x+2] = 3
            m[29:31, 2:38] = 3; m[3:5, 25:38] = 3
        elif name == "Hutan":
            # pohon berkelompok menyisakan jalur berkelok
            for x, y in ((8,7),(12,10),(22,6),(29,10),(7,20),(15,25),(25,22),(33,30),(19,34),(34,17)):
                m[y:y+2, x:x+2] = 3
                m[y+2:y+4, x+1:x+3] = 3
            m[3:9, 3:7] = 0
        elif name == "Sekolah":
            # koridor utama dan ruang kelas di kedua sisi
            wall_h(13, 3, 36, 2, 7); wall_h(26, 3, 36, 2, 30)
            for x in (10, 17, 24, 31):
                wall_v(x, 3, 13, 2, x-2); wall_v(x, 26, 37, 2, x+1 if x < 30 else 33)
                m[5:7, max(2,x-3):x] = 3; m[30:32, x+1:min(38,x+4)] = 3
            m[3:7, 3:6] = 0
    return m
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

P = NS(); MAP = DIST = MM = None; enemies, items, projs, cps = [], [], [], []; DIFF = {}; parts, decals, nades, blasts, SCENERY = [], [], [], [], []
LIGHT, FLICK = 1.0, 0.0

DIFFS = {
    "EASY": dict(floors=2, n=34, add=5, hp=.8, dmg=.7, spd=.9, cd=1.3, spr=.10, sight=14, conts=99, guards=4, gr=4, fb=3, items=34, mix=[45, 30, 20, 5],
                 desc="Musuh sedikit & lemah, 2 lantai + ruang bos, continue tak terbatas"),
    "MEDIUM": dict(floors=3, n=42, add=7, hp=1.0, dmg=1.0, spd=1.0, cd=1.0, spr=.06, sight=18, conts=5, guards=8, gr=3, fb=2, items=28, mix=[35, 30, 25, 10],
                   desc="Seimbang: 3 lantai + ruang bos, 5 continue"),
    "HARD": dict(floors=4, n=50, add=9, hp=1.5, dmg=1.4, spd=1.15, cd=.7, spr=.03, sight=22, conts=3, guards=12, gr=2, fb=2, items=22, mix=[20, 30, 35, 15],
                 desc="Musuh banyak, kuat & akurat, 4 lantai + ruang bos, hanya 3 continue")}

def save_cp(x, y):
    P.cp = dict(x=x, y=y, a=P.a, hp=P.hp, armor=P.armor, weap=[dict(w) for w in P.weap], cur=P.cur)

def start_game(key):
    global DIFF
    DIFF = DIFFS[key]; P.diff = key; P.map_name = getattr(P, "map_name", "Mansion"); P.floor = 0; P.hp, P.armor, P.kills, P.time = 100, 50, 0, 0.0
    P.conts, P.used, P.cur = DIFF["conts"], 0, 0; P.gr, P.fb = DIFF["gr"], DIFF["fb"]
    mk = lambda **k: k
    P.weap = [mk(name="Pistol", mag=12, ammo=12, mags=4, dmg=24, delay=.32, pel=1, spr=.012, auto=False, snd="pistol", rl=1.5, rsnd="rmag", ln=230, zoom=.5),
              mk(name="Rifle", mag=60, ammo=60, mags=3, reserve=200, dmg=24, delay=.075, pel=1, spr=.012, auto=True, snd="rifle", rl=1.35, rsnd="rmag", ln=360, zoom=.28),
              mk(name="Shotgun", mag=6, ammo=6, mags=3, dmg=13, delay=.85, pel=9, spr=.07, auto=False, snd="shotgun", rl=2.0, rsnd="rsg", ln=320, zoom=.52)]
    new_floor()

def next_floor():
    P.floor += 1; P.hp = min(100, P.hp + 30); P.armor = min(100, P.armor + 25)
    for w in P.weap: w["mags"] = min(9, w["mags"] + 1)
    new_floor()

def outdoor_textures(name):
    """Tekstur langit dan tanah khusus untuk lokasi luar ruang."""
    global FLOOR, CEIL
    yy, xx = np.mgrid[0:64, 0:64]
    if name in ("Pedesaan", "Hutan"):
        top = np.array((82, 155, 218), np.float32); bottom = np.array((190, 220, 238), np.float32)
        sky = top[None,None,:] * (1 - yy[...,None]/63) + bottom[None,None,:] * (yy[...,None]/63)
        clouds = ((np.sin(xx*.22 + yy*.12) + np.sin(xx*.11 - yy*.18)) > 1.35)
        sky[clouds] = np.minimum(255, sky[clouds] + 18)
        base = (88, 105, 56) if name == "Hutan" else (126, 116, 76)
        floor = noisy(base, 12)
        floor[(yy % 16 < 2)] = tuple(max(0,c-20) for c in base)
    elif name == "Kota":
        sky = np.zeros((64,64,3),np.float32)
        sky[:] = (105, 155, 205)
        sky = sky * (1 - yy[...,None]/190) + np.array((180,195,208),np.float32)[None,None,:] * (yy[...,None]/190)
        floor = noisy((70,72,76), 7); floor[(yy % 12 < 2)] = (48,50,54); floor[(xx % 16 < 1)] = (100,100,98)
    elif name == "Bandara":
        sky = np.zeros((64,64,3),np.float32)
        sky[:] = (105, 175, 224)
        sky = sky * (1 - yy[...,None]/190) + np.array((205,220,232),np.float32)[None,None,:] * (yy[...,None]/190)
        floor = noisy((118,122,126), 4); floor[(yy % 20 < 2)] = (230,210,90); floor[(xx % 32 < 2)] = (90,94,98)
    else:
        return
    CEIL = np.clip(sky,0,255).astype(np.float32)
    FLOOR = np.clip(floor,0,255).astype(np.float32)

def make_scenery(name):
    """Billboard dekorasi lokasi yang terlihat dari sudut pandang FPS."""
    out=[]
    if name == "Bandara":
        for x,y,flip in ((9.5,27.5,False),(30.5,27.5,True)):
            tex=pg.Surface((64,64),pg.SRCALPHA)
            D.polygon(tex,(225,229,234),[(4,30),(18,27),(28,18),(34,18),(31,28),(49,29),(60,32),(49,35),(31,36),(34,46),(29,46),(18,37),(4,34)])
            D.polygon(tex,(145,157,171),[(18,31),(31,28),(49,29),(60,32),(49,35),(31,36)],1)
            D.rect(tex,(45,95,160),(9,31,12,2)); D.line(tex,(90,95,105),(4,30),(4,34),2)
            if flip: tex=pg.transform.flip(tex,True,False)
            arr=pg.surfarray.array3d(tex).transpose(1,0,2).astype(np.float32); alpha=pg.surfarray.array_alpha(tex).T[...,None].astype(np.float32)
            out.append((x,y,np.dstack((arr,alpha)),1.5,0.7,False,False))
    elif name == "Hutan":
        for x,y in ((8.5,10.5),(15.5,7.5),(25.5,10.5),(33.5,8.5),(8.5,29.5),(16.5,32.5),(27.5,30.5),(34.5,24.5),(21.5,35.5)):
            tex=pg.Surface((64,64),pg.SRCALPHA)
            D.rect(tex,(75,53,34),(28,32,9,30)); D.polygon(tex,(15,70,37),[(32,1),(7,35),(19,34),(2,49),(61,49),(45,34),(57,35)])
            D.polygon(tex,(33,105,48),[(32,4),(15,31),(25,30),(8,44),(56,44),(39,30),(49,31)])
            arr=pg.surfarray.array3d(tex).transpose(1,0,2).astype(np.float32); alpha=pg.surfarray.array_alpha(tex).T[...,None].astype(np.float32)
            out.append((x,y,np.dstack((arr,alpha)),1.45,1.0,False,False))
    return out

def new_floor():
    global MAP, DIST, MM, WALLS, FLOOR, CEIL, enemies, items, projs, cps, parts, decals, nades, blasts, SCENERY
    map_name = getattr(P, "map_name", "Mansion")
    tint = MAP_TINTS.get(map_name, (1, 1, 1))
    tint_arr = np.array(tint, dtype=np.float32)
    WALLS = np.clip(BASE_WALLS * tint_arr[None, None, None, :], 0, 255)
    FLOOR = np.clip(BASE_FLOOR * (tint_arr * np.array((.92, 1.0, .84), dtype=np.float32))[None, None, :], 0, 255)
    CEIL = np.clip(BASE_CEIL * (tint_arr * np.array((.78, .82, .9), dtype=np.float32))[None, None, :], 0, 255)
    # Warna material khusus membantu setiap map terasa sesuai tempatnya.
    palette = {
        "Rumah": ((1.12, 1.02, .82), (1.15, 1.0, .82)),
        "Mansion": ((1.0, .88, .9), (1.0, .88, .9)),
        "Pedesaan": ((.76, 1.12, .72), (.78, 1.08, .70)),
        "Kota": ((.76, .82, .94), (.72, .78, .9)),
        "Bandara": ((.95, 1.02, 1.12), (.88, .98, 1.12)),
        "Hutan": ((.62, .88, .60), (.62, .92, .58)),
        "Sekolah": ((1.12, 1.08, .84), (1.10, 1.06, .82)),
    }
    wt, ft = palette.get(map_name, ((1,1,1),(1,1,1)))
    WALLS = np.clip(WALLS * np.array(wt, dtype=np.float32)[None, None, None, :], 0, 255)
    FLOOR = np.clip(FLOOR * np.array(ft, dtype=np.float32)[None, None, :], 0, 255)
    arena = P.floor == DIFF["floors"]                             # stage terakhir = ruang bos
    MAP = build_arena() if arena else build_map()
    SCENERY = [] if arena else make_scenery(map_name)
    if not arena and map_name in ("Pedesaan", "Kota", "Bandara", "Hutan"):
        outdoor_textures(map_name)
    sx, sy = (4.5, 19.5) if arena else (3.5, 3.5)
    DIST = bfs((int(sx), int(sy))); P.x, P.y = sx, sy; P.a = 0.0 if arena else .6
    P.cd = P.rl = P.flash = P.kick = P.hurt = P.bob = P.dtimer = 0.0; P.z = P.vz = P.scope = P.swap = P.pitch = P.off = P.shake = P.blind = P.tcd = 0.0; P.zk = 1.0; P.run = False; P.step = 0.0; P.inv = 2.0
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
        P.msg = (f"LANTAI {P.floor + 1} / {DIFF['floors']}", 3)
    save_cp(sx, sy)
    MM = pg.Surface((N * 3, N * 3)); MM.fill((10, 8, 8))
    for y in range(N):
        for x in range(N):
            if MAP[y, x]: D.rect(MM, (110, 90, 80), (x * 3, y * 3, 3, 3))

def respawn():                                                    # lanjut dari checkpoint terakhir
    c = P.cp; P.x, P.y, P.a = c["x"], c["y"], c["a"]; P.hp = max(c["hp"], 60); P.armor = c["armor"]
    P.weap = [dict(w) for w in c["weap"]]; P.cur = c["cur"]; P.cd = P.rl = P.hurt = 0.0; P.z = P.vz = P.scope = P.swap = P.pitch = P.blind = P.shake = 0.0; P.inv = 3.0
    P.conts -= 1; P.used += 1; P.state = "play"; projs.clear()
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
        x = random.choice((random.uniform(0, .25), random.uniform(.75, 1))) * W * SC if random.random() < .7 else random.uniform(.2, .8) * W * SC
        life = random.uniform(1.0, 1.8); P.splats.append([x, random.uniform(.05, .9) * H * SC, random.uniform(14, 38), life, life, random.uniform(30, 90)])
    del P.splats[:-30]

def hurt(d):
    if P.inv > 0: return
    a = min(P.armor, d * .5); P.armor -= a; P.hp -= d - a; P.hurt = .35; play(random.choice(("hurt", "hurt2"))); player_splats(d)
    if P.hp <= 0: P.hp = 0; P.state = "dead" if P.conts > 0 else "over"

class Enemy:
    def __init__(s, k, x, y):
        s.k, s.x, s.y = k, x, y; fl = 0 if k == "boss" else P.floor; s.hp = s.maxhp = TYPES[k]["hp"] * DIFF["hp"] * (1 + .12 * fl)
        s.dm = DIFF["dmg"] * (1 + .08 * fl); s.awake, s.cd, s.flash = False, random.uniform(.4, 1.4), 0
        s.wp, s.wt, s.n, s.sd, s.sdt = "rifle", 0.0, 0, 1, 0.0; s.stun = s.ph = 0.0
    def hit(s, d, h=.6):
        s.hp -= d; s.flash = .12; s.awake = True; dd = math.hypot(s.x - P.x, s.y - P.y)
        bleed(s.x, s.y, h, min(18, 6 + int(d / 3)), 2)                       # semprotan darah + bercak di lantai
        if P.time - P.sp_t > .05: play("splat", dd); P.sp_t = P.time
        if s.hp <= 0: P.kills += 1; bleed(s.x, s.y, .5, 26, 8, True); play("thud", dd)
    def fire(s, spread, dmg, snd_, n=1, cone=0.0):               # tembakan musuh (n > 1 = shotgun menyebar)
        a0 = math.atan2(P.y - s.y, P.x - s.x)
        for _ in range(n):
            a = a0 + random.gauss(0, spread) + (random.uniform(-cone, cone) if n > 1 else 0)
            projs.append([s.x, s.y, math.cos(a) * 14, math.sin(a) * 14, dmg * s.dm])
        play(snd_, math.hypot(P.x - s.x, P.y - s.y))
    def walk(s, dx, dy, sp, dt):                                 # gerak + geser di dinding
        n = math.hypot(dx, dy) or 1; mx, my = dx / n * sp * dt, dy / n * sp * dt
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
        if s.stun > 0: s.stun -= dt; return                    # terkena flashbang: diam tak berdaya
        c = TYPES[s.k]; d = math.hypot(P.x - s.x, P.y - s.y)
        seen = d < DIFF["sight"] and los(s.x, s.y, P.x, P.y)
        if seen and not s.awake: s.awake = True
        if not s.awake: return
        s.cd -= dt; s.flash -= dt
        if s.k == "boss": return s.boss_ai(dt, d, seen)
        if c["rng"] and seen and d < c["rng"]:                  # penjahat & agen menembak
            if s.cd <= 0:
                a = math.atan2(P.y - s.y, P.x - s.x) + random.gauss(0, DIFF["spr"]); projs.append([s.x, s.y, math.cos(a) * 14, math.sin(a) * 14, c["dmg"] * s.dm])
                s.cd = c["cd"] * DIFF["cd"]; play(c["snd"], d)
            if d < 4.5: return
        elif d < .85:                                           # cakar jarak dekat
            if s.cd <= 0: hurt(c["dmg"] * s.dm); s.cd = DIFF["cd"]
            return
        if seen: tx, ty = P.x, P.y
        else:                                                   # ikuti peta jarak (pathfinding)
            cx, cy = int(s.x), int(s.y)
            nx, ny = min(((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)), key=lambda q: DIST[q[1], q[0]])
            tx, ty = nx + .5, ny + .5
        a = math.atan2(ty - s.y, tx - s.x); mx, my = math.cos(a) * c["spd"] * DIFF["spd"] * dt, math.sin(a) * c["spd"] * DIFF["spd"] * dt
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
    for e in enemies:
        rx, ry = e.x - P.x, e.y - P.y; f = rx * dx + ry * dy
        if e.hp > 0 and 0 < f < bd and -.05 <= .5 + P.z + slope * f <= 1.05 and abs(rx * dy - ry * dx) < (.5 if e.k == "boss" else .35): best, bd = e, f
    if best: best.hit(dmg, max(.15, min(.9, .5 + P.z + slope * bd)))

def start_reload():
    w = P.weap[P.cur]
    if P.rl <= 0 and w["ammo"] < w["mag"] and (w.get("reserve", 9999) > 0 if "reserve" in w else w["mags"] > 0): P.rl = w["rl"]; play(w["rsnd"])

def throw(kind):                              # G = granat, F = flashbang
    if P.tcd > 0 or (P.gr if kind == "granat" else P.fb) <= 0: return
    if kind == "granat": P.gr -= 1
    else: P.fb -= 1
    P.tcd = .7; P.swap = .3; play("throw"); c_, s_ = math.cos(P.a), math.sin(P.a); sx, sy = P.x + c_ * .4, P.y + s_ * .4
    if MAP[int(sy), int(sx)]: sx, sy = P.x, P.y
    nades.append([sx, sy, .45 + P.z, c_ * 7.5, s_ * 7.5, 2.2 + P.pitch * 5, 2.0 if kind == "granat" else 1.6, kind])

def explode(n):
    x, y, kind = n[0], n[1], n[7]; d = math.hypot(P.x - x, P.y - y)
    if kind == "granat":                                                   # granat: ledakan, damage area
        play("boom", d); blasts.append([x, y, 0.0, .6, "boom"]); P.shake = max(P.shake, 1.4 / (1 + d * .4))
        for e in enemies:
            ed = math.hypot(e.x - x, e.y - y)
            if e.hp > 0 and ed < 4.5 and los(x, y, e.x, e.y): e.hit(170 * (1 - ed / 4.5) + 20, .5)
        if d < 4.5 and los(x, y, P.x, P.y): hurt(70 * (1 - d / 4.5) + 8)
    else:                                                                  # flashbang: membutakan musuh & pemain
        play("flashbang", d); blasts.append([x, y, 0.0, .35, "flashfx"])
        for e in enemies:
            ed = math.hypot(e.x - x, e.y - y)
            if e.hp > 0 and ed < 10 and los(x, y, e.x, e.y): e.stun = max(e.stun, 1.5 if e.k == "boss" else 4.5 * (1 - ed / 14)); e.awake = True
        if d < 13 and los(x, y, P.x, P.y):
            face = (math.cos(P.a) * (x - P.x) + math.sin(P.a) * (y - P.y)) / max(d, .1) > .1
            P.blind = max(P.blind, (3.2 if face else 1.2) * (1 - d / 13) + .4)

def update(dt, mdx, click_ev, mdy=0):
    global DIST
    k = pg.key.get_pressed()
    P.a += mdx * .0028 * CFG["sens"] / 5 * (1 - .6 * P.scope) + ((k[pg.K_RIGHT] or k[pg.K_e]) - (k[pg.K_LEFT] or k[pg.K_q])) * 2.2 * dt
    P.pitch = max(-.85, min(.85, P.pitch - mdy * .0028 * CFG["sens"] / 5 * (1 - .6 * P.scope) + (k[pg.K_UP] - k[pg.K_DOWN]) * 1.4 * dt))   # mouse / panah atas-bawah
    dx, dy = math.cos(P.a), math.sin(P.a); K = CFG["keys"]; fw, st = k[K["maju"]] - k[K["mundur"]], k[K["kanan"]] - k[K["kiri"]]
    vx, vy = dx * fw - dy * st, dy * fw + dx * st; n = math.hypot(vx, vy)
    if n:
        run = bool(k[K["lari"]] or (K["lari"] == pg.K_LSHIFT and k[pg.K_RSHIFT])); P.run = run          # SHIFT = lari
        sp = (6.5 if run else 3.6) * (1 - .45 * P.scope) * dt / n; P.bob += dt * (14 if run else 9)
        P.step -= dt
        if P.step <= 0 and P.z <= 0: play("step", 14); P.step = .27 if run else .45
        if free(P.x + vx * sp, P.y, .28): P.x += vx * sp
        if free(P.x, P.y + vy * sp, .28): P.y += vy * sp
    else: P.run = False
    P.cd -= dt; P.flash -= dt; P.hurt = max(0, P.hurt - dt); P.kick = max(0, P.kick - dt * 160); P.inv -= dt; P.time += dt; P.swap = max(0.0, P.swap - dt)
    P.shake = max(0.0, P.shake - dt * 2); P.blind = max(0.0, P.blind - dt); P.tcd -= dt
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
    for q in P.splats: q[3] -= dt
    P.splats = [q for q in P.splats if q[3] > 0]
    for p in parts[:]:                                                          # partikel darah jatuh dengan gravitasi
        p[0] += p[3] * dt; p[1] += p[4] * dt; p[2] += p[5] * dt; p[5] -= 9 * dt
        if MAP[int(p[1]), int(p[0])]: parts.remove(p)
        elif p[2] <= 0:
            parts.remove(p)
            if random.random() < .5: add_decal(p[0], p[1], random.uniform(.03, .09))
    tgt = 1.0 if (pg.mouse.get_pressed()[2] and P.rl <= 0) else 0.0           # tahan klik kanan = scope
    P.scope += (tgt - P.scope) * min(1.0, dt * 14); P.scope = 0.0 if P.scope < .01 else 1.0 if P.scope > .99 else P.scope
    if k[K["lompat"]] and P.z <= 0: P.vz = 2.4; play("step", 6)       # SPACE = lompat
    if P.z > 0 or P.vz > 0:
        P.vz -= 9 * dt; P.z = max(0.0, P.z + P.vz * dt)
        if P.z == 0: P.vz = 0.0; play("step", 8)
    P.msg = (P.msg[0], P.msg[1] - dt)
    if P.rl > 0:
        P.rl -= dt
        if P.rl <= 0:
            w = P.weap[P.cur]
            need = w["mag"] - w["ammo"]
            if "reserve" in w:
                take = min(need, w["reserve"]); w["ammo"] += take; w["reserve"] -= take
            elif w["mags"] > 0: w["mags"] -= 1; w["ammo"] = w["mag"]
    w = P.weap[P.cur]
    if (pg.mouse.get_pressed()[0] if w["auto"] else click_ev) and P.cd <= 0 and P.rl <= 0 and P.swap <= 0:
        if w["ammo"] > 0:
            w["ammo"] -= 1; P.cd = w["delay"]; P.flash = .07; P.kick = 28 if w["pel"] == 1 else 60; play(w["snd"])
            for _ in range(w["pel"]): shoot_ray(P.a + random.gauss(0, w["spr"] * (1 - .7 * P.scope)), w["dmg"], random.gauss(0, w["spr"] * (1 - .7 * P.scope)))
            for e in enemies:                                    # suara tembakan memancing musuh
                if e.hp > 0 and math.hypot(e.x - P.x, e.y - P.y) < 10: e.awake = True
        else: P.cd = .3; play("empty"); start_reload()
    P.dtimer = getattr(P, "dtimer", 0) - dt
    if P.dtimer <= 0: DIST = bfs((int(P.x), int(P.y))); P.dtimer = .4
    for e in enemies: e.update(dt)
    for p in projs[:]:
        p[0] += p[2] * dt; p[1] += p[3] * dt
        if MAP[int(p[1]), int(p[0])]: projs.remove(p)
        elif math.hypot(p[0] - P.x, p[1] - P.y) < .45 and P.z < .12: hurt(p[4]); projs.remove(p)
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
    for c in cps:
        if not c[2] and math.hypot(c[0] - P.x, c[1] - P.y) < .9:
            c[2] = True; P.hp = min(100, P.hp + 20); save_cp(c[0], c[1]); play("pickup"); P.msg = ("CHECKPOINT TERSIMPAN  (+20 HEALTH)", 2.5)
    boss = next((e for e in enemies if e.k == "boss"), None)
    if boss and boss.hp <= 0: begin_cutscene("outro")                  # boss tumbang = game tamat
    elif not boss and not any(e.hp > 0 for e in enemies): P.state = "clear"
    if boss and boss.hp > 0 and not P.wave and boss.hp < boss.maxhp * .5:      # fase 2: pasukan bantuan
        P.wave = True; P.msg = ("PASUKAN BANTUAN DATANG!", 3)
        spots = [(x + .5, y + .5) for y in range(9, 31) for x in range(26, 37) if MAP[y, x] == 0]; random.shuffle(spots)
        for x, y in spots[:DIFF["guards"] // 2 + 2]:
            e = Enemy(random.choice(("penjahat", "agen", "agen")), x, y); e.awake = True; enemies.append(e)

# ================= RENDER =================
CAMX = 2 * np.arange(W) / W - 1
ROWD = .5 * H / (np.arange(H // 2) + .5)
gy, gx = np.mgrid[0:H, 0:W]
VIG = np.clip(1.15 - .55 * (((gx - W / 2) / (W / 2)) ** 2 + ((gy - H / 2) / (H / 2)) ** 2), .3, 1).T[..., None].astype(np.float32)
GRADE = np.array([1.08, .94, .9], np.float32)

def draw_dot(frame, zb, x, y, h, r, col, flat=False):      # bercak/titik kecil di dunia 3D (r = jari-jari, satuan dunia)
    rx, ry = x - P.x, y - P.y; inv = 1 / (P.plx * P.dy - P.dx * P.ply); ty = inv * (-P.ply * rx + P.plx * ry)
    if ty < .25 or ty > 18: return
    sx = int(W / 2 * (1 + inv * (P.dy * rx - P.dx * ry) / ty)); sy = P.hor + int((.5 + P.z - h) * H / ty * P.zk)
    pw = max(1, int(r * H / ty * P.zk)); ph = max(1, pw // 3) if flat else pw
    x0, x1, y0, y1 = max(sx - pw, 0), min(sx + pw + 1, W), max(sy - ph, 0), min(sy + ph + 1, H)
    if x0 >= x1 or y0 >= y1: return
    m = (((np.arange(x0, x1) - sx) / pw) ** 2)[:, None] + (((np.arange(y0, y1) - sy) / ph) ** 2)[None, :] <= 1
    m &= (zb[x0:x1] > ty)[:, None]
    frame[x0:x1, y0:y1] = np.where(m[..., None], np.array(col, np.float32) * max(.3, min(1, 1.2 - ty / 14)) * LIGHT, frame[x0:x1, y0:y1])

def draw_sprite(frame, zb, x, y, tex, scale=1.0, low=1.0, glow=False, hit=False):
    rx, ry = x - P.x, y - P.y; inv = 1 / (P.plx * P.dy - P.dx * P.ply)
    ty = inv * (-P.ply * rx + P.plx * ry)
    if ty < .2 or ty > 22: return
    sx = int(W / 2 * (1 + inv * (P.dy * rx - P.dx * ry) / ty)); size = int(H / ty * P.zk); sw = int(size * scale)
    if sw < 2: return
    cy = P.hor + int(size * ((1 - scale) / 2 * low + P.z)); x0, y0 = sx - sw // 2, cy - sw // 2
    c0, c1, r0, r1 = max(x0, 0), min(x0 + sw, W), max(y0, 0), min(y0 + sw, H)
    if c0 >= c1 or r0 >= r1: return
    cols, rows = np.arange(c0, c1), np.arange(r0, r1)
    u, v = ((cols - x0) * 64 // sw).clip(0, 63), ((rows - y0) * 64 // sw).clip(0, 63)
    px = tex[v[None, :], u[:, None]]
    m = (px[..., 3] > 128) & (zb[cols] > ty)[:, None]
    b = 1.0 if glow else max(.12, min(1, 1.25 - ty / 13)) * LIGHT
    rgb = px[..., :3] * .5 + np.array((150, 8, 8), np.float32) if hit else px[..., :3]
    frame[c0:c1, r0:r1][m] = (rgb * b)[m]

def render():
    P.dx, P.dy = math.cos(P.a), math.sin(P.a); fov = .66 + (P.weap[P.cur]["zoom"] - .66) * P.scope; zk = P.zk = .66 / fov; P.plx, P.ply = -P.dy * fov, P.dx * fov
    rdx, rdy = P.dx + P.plx * CAMX, P.dy + P.ply * CAMX
    eh = 1 + 2 * P.z                                              # tinggi mata (naik saat lompat)
    off = int(max(-190, min(190, math.tan(P.pitch) * H * zk))) + int(random.uniform(-1, 1) * P.shake * 14); hor = P.hor = H // 2 + off; P.off = off   # cakrawala bergeser saat menengok atas/bawah
    nc = max(0, min(H, hor)); ic = hor - 1 - np.arange(nc); ifl = np.arange(nc, H) - hor
    fr = .5 * H / (ifl + .5) * eh / zk; cr = .5 * H / (ic + .5) * (2 - eh) / zk
    fx, fy = P.x + fr[None, :] * rdx[:, None], P.y + fr[None, :] * rdy[:, None]
    cx_, cy_ = (P.x + cr[None, :] * rdx[:, None]) * 64, (P.y + cr[None, :] * rdy[:, None]) * 64
    tx, ty = (fx * 64).astype(int) & 63, (fy * 64).astype(int) & 63
    fb = (np.clip(1.15 - fr / 11, .05, 1) * LIGHT)[None, :, None]; cb = (np.clip(1.15 - cr / 11, .05, 1) * LIGHT)[None, :, None]
    frame = np.empty((W, H, 3), np.float32)
    frame[:, nc:] = FLOOR[ty, tx] * fb; frame[:, :nc] = CEIL[cy_.astype(int) & 63, cx_.astype(int) & 63] * cb
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
    texx = (wx * 64).astype(int).clip(0, 63); lineh = H / perp * zk; top = hor - lineh * (.5 - P.z)
    texy = np.floor((np.arange(H)[None, :] - top[:, None]) * 64 / lineh[:, None]).astype(int)
    inw = (texy >= 0) & (texy < 64)
    wall = WALLS[(MAP[my, mx] - 1)[:, None], texy.clip(0, 63), texx[:, None]]
    wall *= (np.clip(1.25 - perp / 13, .06, 1) * np.where(side == 1, .72, 1) * LIGHT)[:, None, None]
    frame[inw] = wall[inw]
    # --- sprite (musuh, bola api, item) ---
    for dc in decals: draw_dot(frame, perp, dc[0], dc[1], .01, dc[2], (92, 6, 6), True)     # bercak darah di lantai
    sp = [(e.x, e.y, TEX[e.k + ("_b" if int(e.ph * 2.2) % 2 else "")] if e.hp > 0 else TEX["dead_" + e.k], 1.3 if e.k == "boss" else 1.0, 1.0, False, e.flash > 0) for e in enemies]
    sp += [(p[0], p[1], TEX["fire"], .12, .5, True, False) for p in projs]
    sp += [(i[0], i[1], TEX[i[2]], .38, 1.0, False, False) for i in items]
    sp += [(c[0], c[1], TEX["cp1" if c[2] else "cp0"], .55, 1.0, True, False) for c in cps]
    sp += [(f[0], f[1], TEX[f[4]], max(.05, 2.2 * math.sin(math.pi * min(1, f[2] / f[3])) ** .6), .6, True, False) for f in blasts]
    sp += list(globals().get("SCENERY", []))
    sp.sort(key=lambda o: -((o[0] - P.x) ** 2 + (o[1] - P.y) ** 2))
    for o in sp: draw_sprite(frame, perp, *o)
    for n in nades:
        draw_dot(frame, perp, n[0], n[1], n[2], .07, (70, 100, 55) if n[7] == "granat" else (205, 205, 210)); draw_dot(frame, perp, n[0], n[1], n[2] + .03, .03, (170, 190, 150))
    for p in parts: draw_dot(frame, perp, p[0], p[1], p[2], p[6], (175, 8, 8))              # percikan darah di udara
    # --- efek: cahaya moncong, darah, vignette, grain ---
    if P.flash > 0: frame *= (1 + P.flash * 8, 1 + P.flash * 6, 1 + P.flash * 2)
    frame *= GRADE * VIG; frame += (np.random.random((W, H, 1)) - .5) * 9
    if P.hurt > 0: frame[..., 0] += P.hurt * 220; frame[..., 1:] *= 1 - P.hurt
    pg.surfarray.blit_array(canvas, np.clip(frame, 0, 255).astype(np.uint8))
    screen.blit(pg.transform.scale(canvas, (W * SC, H * SC)), (0, 0))

SKIN, SLV, MET, DRK, WOOD = (212, 160, 126), (22, 22, 27), (62, 62, 70), (34, 34, 40), (118, 72, 40)
GUNS = {   # (jarak dasar, panjang ujung laras, [kotak: x0, x1, y0, y1, z0, z1, warna])  z = ke depan, y = ke bawah
    "PISTOL": (.85, .86, [(-.03, .03, -.045, .015, 0, .78, MET), (-.015, .015, -.03, -.005, .78, .86, DRK), (-.028, .028, .015, .045, 0, .5, DRK),
                          (-.027, .027, .045, .17, 0, .17, DRK), (-.045, .045, .05, .19, -.04, .2, SKIN), (-.04, .05, .1, .4, -.7, 0, SLV)]),
    "ASSAULT RIFLE": (1.0, 1.75, [(-.012, .012, -.03, -.005, .9, 1.75, DRK), (-.03, .03, -.04, .03, .5, 1.0, MET), (-.034, .034, -.05, .035, 0, .55, MET),
                                  (-.018, .018, .035, .15, .25, .4, DRK), (-.022, .022, .035, .13, 0, .1, DRK), (-.025, .025, -.04, .045, -.5, 0, DRK),
                                  (-.018, .018, -.056, -.045, .22, .5, MET), (-.026, .026, -.09, -.056, .3, .5, DRK), (-.026, .026, -.098, -.09, .3, .5, MET),
                                  (-.04, .04, .04, .14, -.06, .1, SKIN), (-.045, .03, .03, .1, .55, .8, SKIN),
                                  (-.04, .05, .08, .4, -.7, -.05, SLV), (-.095, -.04, .05, .4, -.3, .55, DRK),
                                  (-.025, .025, -.065, -.035, .45, .68, MET), (-.018, .018, -.09, -.06, .48, .62, DRK),
                                  (-.03, .03, .09, .17, .15, .32, DRK), (-.022, .022, .17, .20, .20, .27, MET)]),
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
    model_key = {"Pistol": "PISTOL", "Rifle": "ASSAULT RIFLE", "Shotgun": "SHOTGUN"}.get(nm, nm)
    zb, tip, boxes = GUNS[model_key]; sc = P.scope
    low = math.sin(math.pi * (1 - P.rl / w["rl"])) * .45 if P.rl > 0 else 0.0
    ox = (.25 + math.sin(P.bob) * .012) * (1 - .93 * sc)
    oy = .21 + abs(math.cos(P.bob)) * .01 + low + P.z * .7 + {"PISTOL": -.105, "ASSAULT RIFLE": -.135, "SHOTGUN": -.12}[model_key] * sc + P.swap / .25 * .5 - P.kick * .0015
    zb -= P.kick * .004
    for b in sorted(boxes, key=lambda q: -q[4]): gun_box(ox, oy, zb, b)
    if model_key == "ASSAULT RIFLE":
        # silencer on the end of the upgraded M416 barrel
        cx, cy = screen.get_width() // 2, screen.get_height() // 2
        D.rect(screen, (22, 25, 28), (cx + int(ox*500) - 5, cy + int((oy-.02)*500) - 5, 12, 38), border_radius=4)
        D.rect(screen, (70, 74, 78), (cx + int(ox*500) - 4, cy + int((oy-.02)*500) + 1, 10, 2))
    if P.flash > 0:                                          # kilatan moncong di ujung laras
        cx, cy = screen.get_width() // 2, screen.get_height() // 2; z = zb + tip; r = 640 / z * .12
        fx, fy = cx + ox / z * 640, cy + (oy - .02) / z * 640
        D.polygon(screen, (255, 200, 80), [(fx + math.cos(i * math.pi / 6) * r * (1.9 if i % 2 == 0 else .7), fy + math.sin(i * math.pi / 6) * r * (1.9 if i % 2 == 0 else .7)) for i in range(12)])
        D.circle(screen, (255, 245, 200), (int(fx), int(fy)), int(r * .7))

def txt(s, pos, f=font, col=(235, 225, 205)):
    screen.blit(f.render(s, True, (0, 0, 0)), (pos[0] + 2, pos[1] + 2)); screen.blit(f.render(s, True, col), pos)
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
    model_key = {"Pistol": "PISTOL", "Rifle": "ASSAULT RIFLE", "Shotgun": "SHOTGUN"}.get(nm, nm)
    if model_key == "ASSAULT RIFLE":                                  # red dot sight: bingkai kaca + titik merah
        a = min(1.0, P.scope * 1.5); fw, fh = 150, 104; o = pg.Surface((fw + 40, fh + 40), pg.SRCALPHA)
        D.rect(o, (10, 10, 12, int(235 * a)), (0, 0, fw + 40, fh + 40), 20); D.rect(o, (40, 70, 80, int(40 * a)), (20, 20, fw, fh))
        screen.blit(o, (cx - (fw + 40) // 2, cy - (fh + 40) // 2))
        D.circle(screen, (255, 40, 40), (cx, cy), 4); D.circle(screen, (255, 80, 80), (cx, cy), 24, 1)
    elif model_key == "PISTOL": D.circle(screen, (255, 50, 50), (cx, cy), 4); D.circle(screen, (255, 120, 120), (cx, cy), 9, 1)   # red dot
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

def draw_low_health():
    if P.hp >= 30 or P.state != "play": return
    sw, sh = screen.get_size(); strength = int(150 * (1 - max(0, P.hp) / 30))
    if strength <= 0: return
    overlay = pg.Surface((sw, sh), pg.SRCALPHA)
    # translucent red frame, stronger at critical health
    D.rect(overlay, (180, 0, 0, strength), (0, 0, sw, sh), max(12, int(min(sw, sh) * .09)))
    if P.hp < 15 and int(P.time * 3) % 2 == 0: overlay.fill((100, 0, 0, min(35, strength // 3)))
    screen.blit(overlay, (0, 0))

def draw_flash():                              # layar putih saat terkena flashbang
    if P.blind <= 0: return
    sw, sh = screen.get_size(); o = pg.Surface((sw, sh)); o.fill((255, 255, 255)); o.set_alpha(int(255 * min(1.0, P.blind / 1.6))); screen.blit(o, (0, 0))

def draw_throwables(sh):                       # ikon granat dan flashbang transparan
    base_x, y = 748, sh - 150
    for i, (kind, n) in enumerate((("granat", P.gr), ("flash", P.fb))):
        x = base_x + i * 78
        if kind == "granat":
            D.ellipse(screen, (70, 125, 65) if n else (55, 55, 52), (x+8, y+8, 16, 21)); D.rect(screen, (175,175,175), (x+13,y+3,6,7))
        else:
            D.rect(screen, (205,205,210) if n else (80,80,85), (x+10,y+4,13,26), border_radius=3); D.rect(screen, (240,190,50), (x+10,y+4,13,6))
        txt(str(n), (x+31, y+10), small, (245,225,180) if n else (120,110,100))

def gun_icon(x, y, kind, on):                 # ikon senjata (tampak samping) untuk HUD
    m, g, wd = ((205, 205, 215), (120, 120, 130), (170, 108, 60)) if on else ((112, 112, 122), (70, 70, 78), (96, 64, 40))
    if kind == 0:                             # 1 = pistol
        x += 8; D.rect(screen, m, (x + 14, y + 7, 34, 8)); D.rect(screen, g, (x + 44, y + 9, 6, 4))
        D.polygon(screen, g, [(x + 17, y + 15), (x + 29, y + 15), (x + 26, y + 29), (x + 15, y + 29)])
        D.line(screen, m, (x + 30, y + 16), (x + 38, y + 16), 2); D.line(screen, m, (x + 38, y + 16), (x + 36, y + 22), 2)
    elif kind == 1:                           # 2 = rifle
        D.polygon(screen, wd, [(x, y + 10), (x + 14, y + 9), (x + 14, y + 18), (x + 5, y + 22)])
        D.rect(screen, m, (x + 14, y + 8, 34, 8)); D.rect(screen, g, (x + 48, y + 10, 16, 3)); D.rect(screen, g, (x + 28, y + 4, 10, 4))
        D.polygon(screen, g, [(x + 26, y + 16), (x + 33, y + 16), (x + 35, y + 28), (x + 28, y + 28)]); D.rect(screen, g, (x + 18, y + 16, 5, 9))
    else:                                     # 3 = shotgun
        D.rect(screen, m, (x + 24, y + 8, 40, 4)); D.rect(screen, g, (x + 24, y + 12, 34, 3)); D.rect(screen, wd, (x + 34, y + 11, 14, 6))
        D.rect(screen, g, (x + 16, y + 8, 10, 9)); D.polygon(screen, wd, [(x, y + 11), (x + 16, y + 9), (x + 16, y + 17), (x + 3, y + 25)])

def draw_slots(sh):                           # slot senjata transparan
    labels = ("Pistol", "Rifle", "Shotgun")
    for i, w in enumerate(P.weap):
        x0, y0, on = 258 + i * 78, sh - 72, i == P.cur
        gun_icon(x0 + 5, y0 + 4, i, on)
        col = (255, 220, 120) if on else (180, 175, 165)
        txt(f"{i+1} {labels[i]}", (x0 + 2, y0 + 30), small, col)
        a = str(w["ammo"]); txt(a, (x0 + 68 - small.size(a)[0], y0 + 3), small, (255, 90, 80) if w["ammo"] == 0 else col)

def draw_face(x, y, t):                       # wajah agen di HUD, berubah sesuai kondisi
    skin = (222, 172, 136); ko = P.state in ("dead", "over"); ouch = P.hurt > 0
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

def draw_hud(t):
    sw, sh = screen.get_size(); w = P.weap[P.cur]
    # Armor vest silhouette on the left, no HUD panels/background.
    ax, ay = 28, sh-92
    vest = (55, 105, 150) if P.armor > 0 else (65, 68, 70)
    edge = (165, 205, 225) if P.armor > 0 else (110, 112, 115)
    # vest body, shoulders, side panels and neck opening
    D.polygon(screen, vest, [(ax+8,ay+8),(ax+15,ay+2),(ax+23,ay+2),(ax+30,ay+8),(ax+35,ay+18),(ax+31,ay+43),(ax+7,ay+43),(ax+3,ay+18)])
    D.polygon(screen, edge, [(ax+8,ay+8),(ax+14,ay+5),(ax+13,ay+17),(ax+10,ay+27),(ax+8,ay+39),(ax+4,ay+18)])
    D.polygon(screen, edge, [(ax+30,ay+8),(ax+24,ay+5),(ax+25,ay+17),(ax+28,ay+27),(ax+30,ay+39),(ax+34,ay+18)])
    D.polygon(screen, (20,27,34), [(ax+15,ay+4),(ax+23,ay+4),(ax+21,ay+12),(ax+17,ay+12)])
    for yy in (18, 25, 32):
        D.line(screen, (195,210,218) if P.armor > 0 else (100,100,100), (ax+13,ay+yy),(ax+25,ay+yy), 2)
    D.rect(screen, edge, (ax+14, ay+36, 10, 5), 1)
    # Small armor amount beside the vest icon.
    D.rect(screen, (60,65,70), (72, sh-64, 95, 7), 1)
    if P.armor > 0: D.rect(screen, (75,155,225), (73, sh-63, int(93*max(0,min(1,P.armor/100))), 5))
    txt(f"{int(P.armor)}", (72, sh-83), small, (170,210,255) if P.armor > 0 else (135,135,135))
    # Weapon list on the right: text and small weapon drawings float over the scene.
    labels = ("Pistol", "Rifle", "Shotgun")
    for i, wi in enumerate(P.weap):
        x, y = sw-194, sh-116+i*29; active = i == P.cur
        if active:
            D.line(screen, (245,205,110), (x-5,y+2),(x-5,y+23), 3)
        gun_icon(x, y-1, i, active)
        txt(labels[i], (x+70,y+3), small, (255,225,155) if active else (190,195,200))
    # Ammo indicator without a background: ammo count sits directly to the right of the bars.
    total = w.get("reserve", w.get("mags", 0)*w["mag"])
    bars = "|" * min(24, w["ammo"])
    ammo_text = f"{w['ammo']:02d}/{total:03d}"
    bars_width = small.size(bars)[0]
    ammo_width = small.size(ammo_text)[0]
    ammo_x = sw - 20 - ammo_width
    bars_x = max(12, ammo_x - bars_width - 10)
    txt(bars, (bars_x, sh-31), small, (245,205,105) if w["ammo"] else (240,65,65))
    txt(ammo_text, (ammo_x, sh-31), small, (255,215,120) if w["ammo"] else (255,70,70))
    draw_throwables(sh)
    # Statistik misi di kanan atas, foto agen tepat di bawahnya; semuanya tanpa panel latar.
    alive = sum(e.hp > 0 for e in enemies)
    stats = [f"KILLS {P.kills}  |  SISA {alive}", f"{getattr(P, 'map_name', 'Mansion').upper()}", f"{'RUANG BOS' if P.floor == DIFF['floors'] else 'LANTAI ' + str(P.floor+1) + '/' + str(DIFF['floors'])}  |  {P.diff.upper()}"]
    for si, line in enumerate(stats):
        surfline = small.render(line, True, (240, 230, 205))
        screen.blit(surfline, (sw - 10 - surfline.get_width(), 8 + si * 19))
    draw_face(sw-76, 8 + len(stats)*19 + 3, t)
    bs = next((e for e in enemies if e.k == "boss" and e.hp > 0 and e.awake), None)
    if bs:
        bx = sw // 2 - 220; bar(bx, 74, 440, 22, bs.hp / bs.maxhp, (200, 40, 40), f"DON VARGO  [{bs.wp.upper()}]    {int(bs.hp)} / {int(bs.maxhp)}")
        for q in (1, 2, 3): D.line(screen, (20, 8, 8), (bx + 110 * q, 72), (bx + 110 * q, 98), 2)
        txt(f"{int(bs.hp / bs.maxhp * 100)}%", (bx + 450, 76), small)
    if P.scope < .3: D.line(screen, (230, 230, 230), (sw // 2 - 8, sh // 2), (sw // 2 + 8, sh // 2)); D.line(screen, (230, 230, 230), (sw // 2, sh // 2 - 8), (sw // 2, sh // 2 + 8))
    if P.rl > 0 and int(t * 6) % 2: txt("RELOADING...", (sw // 2 - 70, sh // 2 + 40))
    if P.run: txt("RUN", (16, sh - 96), small, (255, 200, 90))
    if P.msg[1] > 0: txt(P.msg[0], (sw // 2 - 110, sh // 2 + 80), font, (255, 220, 120))
    if t < 6:
        txt("AGENT DUTY", (sw // 2 - big.size("AGENT DUTY")[0] // 2, 40), big, (240, 200, 90))
        txt(f"Misi: {getattr(P, 'map_name', 'Mansion')} - hentikan komplotan penjahat", (sw // 2 - 190, 112))
        center("WASD jalan | SHIFT lari | SPACE lompat | Klik kiri tembak | Klik kanan bidik", 150, small); center("1/2/3 atau roll mouse = senjata | G = granat | F = flashbang", 174, small)
    # minimap without a filled frame, upper-left
    mmx, mmy = 8, 8
    screen.blit(MM, (mmx, mmy))
    for e in enemies:
        if e.hp > 0: D.rect(screen, (230, 40, 40), (mmx + int(e.x * 3) - 1, mmy + int(e.y * 3) - 1, 3, 3))
    for c in cps: D.rect(screen, (90, 255, 140) if c[2] else (255, 170, 50), (mmx + int(c[0] * 3) - 2, mmy + int(c[1] * 3) - 2, 4, 4))
    D.circle(screen, (70, 255, 90), (int(mmx + P.x * 3), int(mmy + P.y * 3)), 3)
    if P.state != "play": draw_state()

# ================= LOOP UTAMA =================
def center(s, y, f=font, col=(235, 225, 205)): txt(s, (screen.get_width() // 2 - f.size(s)[0] // 2, y), f, col)

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
    sw, sh = screen.get_size(); st = P.state; my = sh // 2
    o = pg.Surface((sw, sh), pg.SRCALPHA)
    o.fill((110, 0, 0, 150) if st in ("dead", "over") else (0, 0, 0, 185) if st in ("pause", "ending") else (0, 50, 25, 150)); screen.blit(o, (0, 0))
    if st == "dead":
        center("MISSION FAILED", my - 80, big, (235, 70, 60)); center(f"ENTER = lanjut dari checkpoint terakhir  (sisa continue: {P.conts})", my + 20); center("ESC = menu utama", my + 56, small)
    elif st == "over": center("GAME OVER", my - 80, big, (235, 70, 60)); center("Continue habis.  ENTER = menu utama", my + 20)
    elif st == "clear":
        center("LANTAI BERSIH", my - 80, big, (120, 235, 150)); center(f"Lantai {P.floor + 1} dari {DIFF['floors']} selesai.  ENTER = " + ("masuk ke RUANG BOS" if P.floor + 1 == DIFF["floors"] else "naik ke lantai berikutnya"), my + 20)
        center("Bonus: +30 health, +25 armor, +1 magazine", my + 56, small)
    elif st == "pause": center("PAUSE", my - 80, big); center("ESC = lanjut   |   M = menu utama", my + 20)
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
KEYNAMES = [("Maju", "maju"), ("Mundur", "mundur"), ("Kiri (geser)", "kiri"), ("Kanan (geser)", "kanan"), ("Lari", "lari"), ("Reload", "reload"), ("Lompat", "lompat"), ("Granat", "granat"), ("Flashbang", "flash")]

def menu_rows(S):
    if S["mode"] == "main": return [("START GAME", ""), ("SETTINGS", ""), ("QUIT", "")]
    if S["mode"] == "map": return [(n, "PILIH MAP") for n in MAP_NAMES] + [("BACK", "")]
    if S["mode"] == "diff": return [(k, f"{v['floors']} lantai + bos") for k, v in DIFFS.items()] + [("BACK", "")]
    bar_ = lambda v: "<  " + "|" * v + "." * (10 - v) + "  >"
    rows = [(n, pg.key.name(CFG["keys"][k]).upper()) for n, k in KEYNAMES]
    rows += [("Sensitivitas mouse", bar_(CFG["sens"])), ("Volume", bar_(CFG["vol"])), ("KEMBALI", "")]
    if S["wait"] is not None: rows[S["wait"]] = (rows[S["wait"]][0], "tekan tombol...")
    return rows

def draw_menu(S):
    sw, sh = screen.get_size(); screen.blit(BG, (0, 0)); st = S["mode"] == "settings"
    center("AGENT DUTY", 30, big, (240, 200, 90))
    y0, sp = (132, 31) if st else (210, 46); rows = menu_rows(S); rects = []
    center({"main": "Pilih misi dan hentikan komplotan penjahat.", "map": "PILIH LOKASI MISI", "diff": "PILIH TINGKAT KESULITAN", "settings": "SETTINGS & KONTROL"}[S["mode"]], y0 - 40, font, (200, 180, 150))
    for i, (a, b) in enumerate(rows):
        r = pg.Rect(sw // 2 - 290, y0 + i * sp, 580, sp - 4); rects.append(r); on = i == S["sel"]
        if on: D.rect(screen, (95, 30, 30), r); D.rect(screen, (200, 150, 70), r, 2)
        txt(a, (r.x + 14, r.y + 6), font, (255, 235, 180) if on else (190, 175, 150)); txt(b, (r.right - 14 - font.size(b)[0], r.y + 6), font, (230, 200, 120))
    if S["mode"] == "diff" and S["sel"] < 3: center(DIFFS[list(DIFFS)[S["sel"]]]["desc"], y0 + 4 * sp + 16, small, (210, 190, 160))
    if st:
        for i, l in enumerate(("Tembak: klik kiri  |  Bidik (red dot): tahan klik kanan  |  Senjata: 1/2/3 atau roll mouse  |  Pause: ESC", "Melihat: mouse ke segala arah, atau panah (kiri/kanan/atas/bawah), Q / E  |  Checkpoint: dekati lampu",
                               "Ubah tombol: pilih baris lalu ENTER, kemudian tekan tombol baru   |   Slider: panah kiri-kanan")):
            center(l, y0 + len(rows) * sp + 10 + i * 22, small, (200, 185, 160))
    return rects

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

def art_map_scene(p, t, name, phase):
    """Ilustrasi cutscene khusus setiap map, dibuat dengan grafis Pygame."""
    # phase 0: lokasi, phase 1: pendekatan, phase 2: tujuan, phase 3: jalan keluar
    if name in ("Pedesaan", "Rumah", "Mansion"):
        grad(p,(20,35,42),(205,150,92),0,235); D.rect(p,(48,74,40),(0,245,640,115))
        if name == "Pedesaan":
            for hx,hy,sc in ((120,190,.75),(320,175,1.0),(500,205,.62)):
                D.rect(p,(112,75,48),(int(hx-65*sc),int(hy),int(130*sc),int(95*sc))); D.polygon(p,(90,35,28),[(int(hx-78*sc),int(hy)),(hx,int(hy-65*sc)),(int(hx+78*sc),int(hy))]); D.rect(p,(40,25,20),(int(hx-12*sc),int(hy+45*sc),int(24*sc),int(50*sc)))
            D.line(p,(190,165,105),(0,320),(640,280),8)
        else:
            house(p,320,275,1.0 if name=="Mansion" else .65,True,(20,15,18),t); fence(p,320,34,(5,5,8))
    elif name == "Kota":
        grad(p,(35,65,95),(165,190,200),0,240); D.rect(p,(55,59,65),(0,245,640,115))
        for x,w,h,col in ((25,80,190,(70,82,98)),(115,90,255,(85,98,115)),(225,78,205,(55,67,83)),(325,110,275,(90,100,115)),(460,95,220,(63,77,94)),(565,55,160,(90,100,110))):
            D.rect(p,col,(x,245-h,w,h)); D.rect(p,(35,45,58),(x+6,245-h+8,w-12,h-16),2)
            for wx in range(x+12,x+w-6,18):
                for wy in range(245-h+16,235,24): D.rect(p,(220,210,145),(wx,wy,8,11))
        D.polygon(p,(100,103,108),[(245,245),(395,245),(610,360),(25,360)])
    elif name == "Bandara":
        grad(p,(70,140,190),(200,215,220),0,210); D.rect(p,(118,125,130),(0,220,640,140)); D.polygon(p,(215,220,222),[(0,70),(450,70),(590,115),(640,140),(640,220),(0,220)])
        for x in (45,120,195,270,345,420): D.rect(p,(55,100,130),(x,85,5,115)); D.rect(p,(215,235,245),(x+6,85,54,115))
        for cx in (170,470):
            D.polygon(p,(238,240,242),[(cx-90,250),(cx-25,235),(cx+65,244),(cx+100,255),(cx+60,266),(cx-25,264)])
            D.polygon(p,(185,195,205),[(cx-10,244),(cx-50,202),(cx-35,200),(cx+8,243)]); D.polygon(p,(185,195,205),[(cx+10,246),(cx+40,216),(cx+52,217),(cx+40,250)])
        D.rect(p,(220,35,35),(565,155,75,65)); D.rect(p,(245,245,240),(575,165,55,12))
    elif name == "Hutan":
        grad(p,(20,65,75),(90,130,75),0,240); D.rect(p,(55,82,43),(0,250,640,110))
        for x,y,r in ((25,80,58),(90,125,48),(160,70,60),(230,110,55),(315,75,70),(390,120,55),(470,72,65),(565,112,58),(625,65,55)):
            D.rect(p,(75,49,30),(x-9,y+20,18,210)); D.polygon(p,(15,60,34),[(x,y-r),(x-r//2,y+20),(x+r//2,y+20)]); D.polygon(p,(25,95,42),[(x,y-r+20),(x-r//2,y+55),(x+r//2,y+55)])
        D.polygon(p,(115,105,70),[(280,360),(350,360),(380,240),(300,240)])
    else: # Sekolah
        grad(p,(90,155,195),(210,210,175),0,230); D.rect(p,(65,115,65),(0,260,640,100))
        D.rect(p,(180,170,140),(90,115,460,145)); D.polygon(p,(110,45,40),[(65,118),(320,40),(575,118)]); D.rect(p,(225,220,190),(110,140,420,120))
        for x in (135,205,275,345,415,485): D.rect(p,(55,115,150),(x,150,45,60)); D.rect(p,(225,220,190),(x-3,147,51,66),2)
        D.rect(p,(75,55,40),(300,200,40,60)); D.rect(p,(240,220,130),(319,228,4,4))
    if phase == 1:
        agent_back(p,320,340,0.8); stamp(p,"OPERASI",(235,205,130),(385,260),-8)
    elif phase == 2:
        D.rect(p,(12,16,20),(80,40,480,280),2)
        for i in range(5): D.line(p,(50,190,210),(100,80+i*35),(520,80+i*35),2)
        stamp(p,"TARGET",(235,65,55),(370,250),8)
    elif phase == 3:
        D.rect(p,(12,14,18),(0,300,640,60)); agent_back(p,320,342,0.9)
        stamp(p,"MISI SELESAI",(235,205,130),(365,265),-8)

def begin_cutscene(kind):
    fl = DIFF.get("floors", 3)
    name = getattr(P, "map_name", "Mansion")
    place_labels = {"Rumah":"KAWASAN RUMAH", "Mansion":"KEDIAMAN DON VARGO", "Pedesaan":"DESA TERPENCIL", "Kota":"PUSAT KOTA", "Bandara":"BANDARA INTERNASIONAL", "Hutan":"HUTAN LEBAT", "Sekolah":"KOMPLEKS SEKOLAH"}
    label = place_labels.get(name, name.upper())
    offset = 0 if kind == "intro" else 1
    art = [lambda p,t,n=name,k=(i+offset)%4: art_map_scene(p,t,n,k) for i in range(4)]
    if kind == "intro":
        descriptions = [
            (f"23:40  |  {label}", f"Malam ini operasi dimulai di {name.lower()}. Lingkungan sekitar menjadi jalur masuk dan tempat persembunyian kelompok bersenjata.", None),
            ("PENDEKATAN  |  AGEN DUTY", f"Agen mendekati lokasi dari luar. Perhatikan bangunan, jalur terbuka, dan sudut yang bisa dipakai musuh untuk berlindung.", 1.0),
            ("BRIEFING  |  TARGET MISI", f"Masuk ke area {name.lower()}, kalahkan penjaga di setiap lantai, kumpulkan perlengkapan, lalu temukan pemimpin komplotan. Tingkat bahaya: {P.diff}.", None),
            ("MULAI OPERASI  |  23:58", f"Pintu masuk menuju {name.lower()} sudah di depan mata. Periksa amunisi, siapkan armor, dan mulai operasi.", None)]
    else:
        descriptions = [
            (f"TARGET DITUMBANGKAN  |  {label}", f"Pemimpin kelompok berhasil dikalahkan di {name.lower()}. Perlawanan mulai berhenti dan area utama berhasil diamankan.", None),
            ("BUKTI DIAMANKAN  |  OPERASI", "Dokumen dan barang bukti berhasil ditemukan. Tim akan memeriksa lokasi untuk memastikan tidak ada ancaman tersisa.", 1.0),
            ("AREA AMAN  |  DUKUNGAN TIBA", f"Jalur keluar dari {name.lower()} sudah diperiksa. Tim pendukung tiba untuk mengambil alih pengamanan lokasi.", None),
            ("KELUAR DARI LOKASI  |  MISI SELESAI", "Operasi selesai, Agen. Lokasi berhasil diamankan dan semua bukti penting dibawa keluar.", None)]
    sc = [(art[i], lab, desc, stamp_time) for i, (lab, desc, stamp_time) in enumerate(descriptions)]
    P.state = "cut"; P.cut = dict(kind=kind, sc=sc, i=0, t=0.0, chars=0, stamped=False, lines=wrap(sc[0][2], font, 740))

def cut_end():
    if P.cut["kind"] == "intro": P.state = "play"; P.inv = 2.0
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

WHEEL = hasattr(pg, "MOUSEWHEEL")
def switch_weapon(i):                         # dipakai tombol 1/2/3 dan roll mouse
    if i != P.cur: P.cur = i; P.rl = 0; P.swap = .25; SND["rmag"].stop(); SND["rsg"].stop(); play("step", 5)

def set_mouse(on): pg.event.set_grab(on); pg.mouse.set_visible(not on); pg.mouse.get_rel()

def main():
    global LIGHT, FLICK
    S = dict(mode="main", sel=0, wait=None); rects = []
    set_mouse(False); ambient.set_volume(CFG["vol"] / 10); ambient.play(-1)
    t, run, frames = 0.0, True, 0; limit = int(os.environ.get("HG_FRAMES", 0))
    def to_menu(): S.update(mode="main", sel=0, wait=None); set_mouse(False)
    while run:
        dt = min(clock.tick(45) / 1000, .05); t += dt; click_ev, act, adj = False, None, 0
        for e in pg.event.get():
            if e.type == pg.QUIT: run = False
            elif S["mode"] == "play" and P.state == "cut": cut_event(e)
            elif S["mode"] == "play":
                if e.type == pg.MOUSEBUTTONDOWN and e.button == 1: click_ev = True
                elif WHEEL and e.type == pg.MOUSEWHEEL and P.state == "play": switch_weapon((P.cur - (1 if e.y > 0 else -1 if e.y < 0 else 0)) % 3)
                elif not WHEEL and e.type == pg.MOUSEBUTTONDOWN and e.button in (4, 5) and P.state == "play": switch_weapon((P.cur + (-1 if e.button == 4 else 1)) % 3)
                elif e.type == pg.KEYDOWN:
                    if e.key == pg.K_ESCAPE:
                        if P.state == "play": P.state = "pause"; set_mouse(False)
                        elif P.state == "pause": P.state = "play"; set_mouse(True)
                        else: to_menu()
                    elif e.key == pg.K_RETURN:
                        if P.state == "dead": respawn()
                        elif P.state in ("over", "ending"): to_menu()
                        elif P.state == "clear": next_floor()
                    elif e.key == pg.K_m and P.state == "pause": to_menu()
                    elif P.state == "play" and e.key == CFG["keys"]["reload"]: start_reload()
                    elif P.state == "play" and e.key == CFG["keys"]["granat"]: throw("granat")
                    elif P.state == "play" and e.key == CFG["keys"]["flash"]: throw("flash")
                    elif P.state == "play" and e.key in (pg.K_1, pg.K_2, pg.K_3): switch_weapon(e.key - pg.K_1)
            elif e.type == pg.KEYDOWN and S["wait"] is not None:      # menunggu tombol baru
                if e.key != pg.K_ESCAPE: CFG["keys"][KEYNAMES[S["wait"]][1]] = e.key; save_cfg()
                S["wait"] = None
            elif e.type == pg.KEYDOWN:
                n = len(menu_rows(S))
                if e.key == pg.K_DOWN: S["sel"] = (S["sel"] + 1) % n
                elif e.key == pg.K_UP: S["sel"] = (S["sel"] - 1) % n
                elif e.key == pg.K_LEFT: adj = -1
                elif e.key == pg.K_RIGHT: adj = 1
                elif e.key in (pg.K_RETURN, pg.K_SPACE): act = S["sel"]
                elif e.key == pg.K_ESCAPE:
                    if S["mode"] == "main": run = False
                    else: S.update(mode="main", sel=0); save_cfg()
            elif e.type == pg.MOUSEMOTION:
                for i, r in enumerate(rects):
                    if r.collidepoint(e.pos): S["sel"] = i
            elif e.type == pg.MOUSEBUTTONDOWN and e.button == 1:
                for i, r in enumerate(rects):
                    if r.collidepoint(e.pos): S["sel"] = i; act = i; adj = 1 if e.pos[0] > r.centerx else -1
        if S["mode"] != "play":
            m = S["mode"]
            if m == "settings" and adj and S["sel"] in (len(KEYNAMES), len(KEYNAMES) + 1):
                k = "sens" if S["sel"] == len(KEYNAMES) else "vol"; CFG[k] = max(1 if k == "sens" else 0, min(10, CFG[k] + adj))
                ambient.set_volume(CFG["vol"] / 10); save_cfg()
            if act is not None:
                if m == "main":
                    if act == 0: S.update(mode="map", sel=1)
                    elif act == 1: S.update(mode="settings", sel=0)
                    else: run = False
                elif m == "map":
                    if act < len(MAP_NAMES): P.map_name = MAP_NAMES[act]; S.update(mode="diff", sel=1)
                    else: S.update(mode="main", sel=0)
                elif m == "diff":
                    if act < 3: start_game(list(DIFFS)[act]); S["mode"] = "play"; set_mouse(True); begin_cutscene("intro")
                    else: S.update(mode="map", sel=0)
                elif act < len(KEYNAMES): S["wait"] = act
                elif act == len(KEYNAMES) + 2: S.update(mode="main", sel=1); save_cfg()
        if S["mode"] == "play":
            rel = pg.mouse.get_rel(); mdx, mdy = rel[0], rel[1]
            FLICK = .4 if random.random() < .012 else max(0, FLICK - dt * 3); LIGHT = .92 + .05 * math.sin(t * 11) - FLICK
            if P.state == "play": update(dt, mdx, click_ev, mdy)
            if P.state == "cut": draw_cut(dt)
            else: render(); draw_weapon(t); draw_scope(); draw_blood(); draw_hud(P.time); draw_low_health(); draw_flash()
        else: rects = draw_menu(S)
        pg.display.flip(); frames += 1
        if limit and frames >= limit: break
    pg.quit()

if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback; traceback.print_exc()
        input("\nTerjadi error di atas. Tekan ENTER untuk menutup...")