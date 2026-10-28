"""
HELLGATE - game FPS ala DOOM (raycasting) dengan Python
Instal : pip install pygame numpy
Jalan  : python hellgate.py
Kontrol: WASD jalan | SHIFT lari | Mouse lihat (Q/E juga bisa) | Klik kiri tembak | R reload
         1/2/3 ganti senjata | Shift lari | ENTER ulang | ESC keluar
Semua grafik & suara dibuat lewat kode (tanpa file gambar/audio).
"""
import math, random, os
from collections import deque
from types import SimpleNamespace as NS
import numpy as np
import pygame as pg

SR = 22050
pg.mixer.pre_init(SR, -16, 2, 512)
pg.init()
MIX = pg.mixer.get_init()          # None jika tidak ada perangkat audio
W, H, SC = 320, 200, 3                      # resolusi render, skala jendela
screen = pg.display.set_mode((W * SC, H * SC))
pg.display.set_caption("HELLGATE")
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
    "empty": snd(click(1000), .6), "step": snd(thud(.1, 70), .35), "hurt": snd(growl(.3, 110, 0, .12)), "growl": snd(growl(.9, 70, 6)),
    "die": snd(growl(.8, 60, 3, .3)), "fire": snd(lp(nz(.5), 10) * np.exp(-T(.5) / .2), .6),
    "pickup": snd(np.concatenate([np.sin(2 * np.pi * 660 * T(.08)), np.sin(2 * np.pi * 990 * T(.1))]) * .6, .5),
}
t6 = T(6)   # dengung latar yang mencekam (loop mulus)
ambient = snd((np.sin(2 * np.pi * 55 * t6) + np.sin(2 * np.pi * 55.5 * t6) + .6 * np.sin(2 * np.pi * 82.5 * t6))
              * (.7 + .3 * np.sin(2 * np.pi * .5 * t6)), .35)
def play(name, d=0):
    s = SND[name]; s.set_volume(max(.05, 1 - d / 22)); s.play()

# ================= TEKSTUR (dibuat prosedural) =================
YY, XX = np.mgrid[0:64, 0:64]
def noisy(base, amp=14):
    t = np.empty((64, 64, 3), np.float32); t[:] = base
    return t + rng.integers(-amp, amp, (64, 64, 1))
def blobs(k):
    a = rng.random((64, 64))
    b = sum(np.roll(np.roll(a, i, 0), j, 1) for i in range(k) for j in range(k))
    return (b - b.mean()) / b.std()
def tex_brick():
    t = noisy((125, 55, 45), 16); t[(YY % 16 < 2) | ((XX + (YY // 16 % 2) * 16) % 32 < 2)] = (36, 32, 32)
    return t * (1 + .16 * blobs(9))[..., None]
def tex_metal():
    t = noisy((78, 70, 66), 10); t[(XX % 32 < 2) | (YY % 32 < 2)] = (26, 24, 24)
    t[((XX % 32 - 6) ** 2 + (YY % 32 - 6) ** 2 < 5) | ((XX % 32 - 26) ** 2 + (YY % 32 - 6) ** 2 < 5)] = (130, 125, 120)
    r = blobs(11) > .9; t[r] = t[r] * (1.6, .8, .5)
    return t
def tex_stone():
    t = noisy((92, 92, 98), 18); t[(YY % 21 < 1) | ((XX + YY // 21 * 11) % 27 < 1)] = (40, 40, 44)
    for cx in rng.integers(0, 62, 5):                         # noda darah menetes
        n = int(rng.integers(14, 50))
        for y in range(n): t[y, cx:cx + 2] = (150 * (1 - y / n) + 50, 8, 8)
    return t
def tex_floor():
    t = noisy((54, 50, 48), 10); t[(XX % 32 < 1) | (YY % 32 < 1)] = (20, 18, 18)
    t *= (1 + .2 * blobs(7))[..., None]; t[blobs(9) > 1.7] = (95, 12, 12)
    return t
def tex_ceil():
    t = noisy((34, 30, 34), 8); t[(XX % 16 < 1) | (YY % 16 < 1)] = (14, 12, 14); return t

WALLS = np.stack([tex_brick(), tex_metal(), tex_stone()]).clip(0, 255).astype(np.float32)
FLOOR, CEIL = tex_floor().clip(0, 255), tex_ceil().clip(0, 255)

def to_tex(s):
    rgb = pg.surfarray.array3d(s).transpose(1, 0, 2).astype(np.float32) * (.85 + .3 * rng.random((64, 64, 1)))
    return np.dstack([rgb, pg.surfarray.array_alpha(s).T.astype(np.float32)])
def surf(): return pg.Surface((64, 64), pg.SRCALPHA)
def make_enemy(body, skin, eye):
    s = surf(); dark = tuple(c // 2 for c in body); bone = (205, 195, 175)
    D.rect(s, dark, (20, 44, 9, 18)); D.rect(s, dark, (35, 44, 9, 18))
    D.ellipse(s, body, (16, 22, 32, 32))
    for i in range(3): D.line(s, dark, (23, 32 + i * 5), (41, 32 + i * 5), 1)
    D.line(s, skin, (18, 28), (5, 42), 5); D.line(s, skin, (46, 28), (59, 42), 5)
    for cx in (5, 59): D.polygon(s, bone, [(cx - 4, 41), (cx, 52), (cx + 4, 41)])
    D.circle(s, skin, (32, 15), 11)
    D.polygon(s, bone, [(23, 9), (19, 0), (28, 6)]); D.polygon(s, bone, [(41, 9), (45, 0), (36, 6)])
    D.circle(s, eye, (28, 14), 2); D.circle(s, eye, (36, 14), 2); D.line(s, (50, 0, 0), (26, 21), (38, 21), 2)
    for _ in range(7): D.circle(s, (110, 10, 10), (random.randint(20, 44), random.randint(24, 50)), 2)
    return to_tex(s)
def make_dead(body, skin):
    s = surf(); D.ellipse(s, (95, 8, 8), (4, 50, 56, 12)); D.ellipse(s, body, (12, 46, 40, 13))
    D.circle(s, skin, (48, 52), 6); D.line(s, skin, (10, 52), (2, 57), 3); return to_tex(s)
def make_fire():
    s = surf()
    for r, c in ((30, (200, 60, 0)), (22, (255, 140, 10)), (12, (255, 235, 130))): D.circle(s, c, (32, 32), r)
    return to_tex(s)
def make_item(kind):
    s = surf()
    if kind == "health":
        D.rect(s, (230, 230, 230), (14, 24, 36, 26)); D.rect(s, (200, 20, 20), (28, 27, 8, 20)); D.rect(s, (200, 20, 20), (22, 33, 20, 8))
    elif kind == "armor":
        D.polygon(s, (40, 90, 210), [(16, 24), (48, 24), (52, 50), (12, 50)]); D.line(s, (120, 170, 255), (20, 28), (44, 28), 3)
    else:
        D.rect(s, (80, 86, 50), (12, 30, 40, 22))
        for i in range(5): D.rect(s, (215, 175, 45), (16 + i * 7, 22, 5, 11))
    return to_tex(s)

TYPES = {"zombi": dict(hp=40, spd=1.3, dmg=8, rng=0, c=((62, 72, 54), (122, 134, 102), (255, 40, 20))),
         "imp": dict(hp=70, spd=1.8, dmg=10, rng=10, c=((96, 48, 30), (150, 84, 54), (255, 220, 40))),
         "iblis": dict(hp=180, spd=2.7, dmg=18, rng=0, c=((120, 20, 20), (175, 40, 40), (255, 190, 0)))}
TEX = {"fire": make_fire(), **{k: make_item(k) for k in ("health", "armor", "ammo")}}
for k, v in TYPES.items(): TEX[k] = make_enemy(*v["c"]); TEX["dead_" + k] = make_dead(*v["c"][:2])

# ================= PETA & UTILITAS =================
N = 40
def build_map():
    m = np.zeros((N, N), np.int8); m[0, :] = m[-1, :] = m[:, 0] = m[:, -1] = 2
    for _ in range(85):
        w, h = random.choice([(1, 1), (2, 2), (1, 4), (4, 1), (3, 1), (1, 3), (2, 1)])
        x, y = random.randint(2, N - 6), random.randint(2, N - 6); m[y:y + h, x:x + w] = random.randint(1, 3)
    m[1:7, 1:7] = 0; return m
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

P = NS(); MAP = DIST = MM = None; enemies, items, projs = [], [], []
LIGHT, FLICK = 1.0, 0.0

def reset():
    global MAP, DIST, MM, enemies, items, projs
    MAP = build_map(); DIST = bfs((3, 3))
    P.x = P.y = 3.5; P.a = .6; P.hp, P.armor, P.kills = 100, 50, 0
    P.cd = P.rl = P.flash = P.kick = P.hurt = P.bob = 0.0; P.cur = 0; P.msg = ("", 0); P.state = "play"; P.run = False; P.step = 0.0
    mk = lambda **k: k
    P.weap = [mk(name="PISTOL", mag=12, ammo=12, mags=4, dmg=24, delay=.32, pel=1, spr=.012, auto=False, snd="pistol", rl=1.5, rsnd="rmag", ln=230),
              mk(name="ASSAULT RIFLE", mag=30, ammo=30, mags=3, dmg=15, delay=.09, pel=1, spr=.03, auto=True, snd="rifle", rl=1.7, rsnd="rmag", ln=300),
              mk(name="SHOTGUN", mag=6, ammo=6, mags=3, dmg=13, delay=.85, pel=9, spr=.07, auto=False, snd="shotgun", rl=2.0, rsnd="rsg", ln=320)]
    cells = [(x, y) for y in range(N) for x in range(N) if DIST[y, x] < 9999]
    far = [c for c in cells if math.hypot(c[0] - 3, c[1] - 3) > 9]; random.shuffle(far); random.shuffle(cells)
    enemies = [Enemy(random.choices(list(TYPES), [50, 35, 15])[0], x + .5, y + .5) for x, y in far[:60]]
    items = [[x + .5, y + .5, random.choice(["health", "armor", "ammo", "ammo"])] for x, y in cells[:32]]
    projs = []
    MM = pg.Surface((N * 3, N * 3)); MM.fill((10, 8, 8))
    for y in range(N):
        for x in range(N):
            if MAP[y, x]: D.rect(MM, (110, 90, 80), (x * 3, y * 3, 3, 3))

def hurt(d):
    a = min(P.armor, d * .5); P.armor -= a; P.hp -= d - a; P.hurt = .35; play("hurt")
    if P.hp <= 0: P.hp = 0; P.state = "dead"

class Enemy:
    def __init__(s, k, x, y):
        s.k, s.x, s.y, s.hp = k, x, y, TYPES[k]["hp"]; s.awake, s.cd, s.flash = False, random.uniform(.4, 1.4), 0
    def hit(s, d):
        s.hp -= d; s.flash = .12; s.awake = True
        if s.hp <= 0: P.kills += 1; play("die", math.hypot(s.x - P.x, s.y - P.y))
    def update(s, dt):
        if s.hp <= 0: return
        c = TYPES[s.k]; d = math.hypot(P.x - s.x, P.y - s.y)
        seen = d < 20 and los(s.x, s.y, P.x, P.y)
        if seen and not s.awake: s.awake = True; play("growl", d)
        if not s.awake: return
        s.cd -= dt; s.flash -= dt
        if c["rng"] and seen and d < c["rng"]:                  # imp: tembak bola api
            if s.cd <= 0:
                a = math.atan2(P.y - s.y, P.x - s.x); projs.append([s.x, s.y, math.cos(a) * 5.5, math.sin(a) * 5.5, c["dmg"]])
                s.cd = 1.7; play("fire", d)
            if d < 4.5: return
        elif d < .85:                                           # cakar jarak dekat
            if s.cd <= 0: hurt(c["dmg"]); s.cd = 1.0
            return
        if seen: tx, ty = P.x, P.y
        else:                                                   # ikuti peta jarak (pathfinding)
            cx, cy = int(s.x), int(s.y)
            nx, ny = min(((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)), key=lambda q: DIST[q[1], q[0]])
            tx, ty = nx + .5, ny + .5
        a = math.atan2(ty - s.y, tx - s.x); mx, my = math.cos(a) * c["spd"] * dt, math.sin(a) * c["spd"] * dt
        for o in enemies:                                       # jangan menumpuk
            ox, oy = s.x - o.x, s.y - o.y
            if o is not s and o.hp > 0 and abs(ox) < .6 and abs(oy) < .6: mx += ox * dt * 1.2; my += oy * dt * 1.2
        if free(s.x + mx, s.y, .22): s.x += mx
        if free(s.x, s.y + my, .22): s.y += my

def shoot_ray(ang, dmg):
    dx, dy = math.cos(ang), math.sin(ang); d = 0.0
    while d < 30:
        d += .05
        if MAP[int(P.y + dy * d), int(P.x + dx * d)]: break
    best, bd = None, d
    for e in enemies:
        rx, ry = e.x - P.x, e.y - P.y; f = rx * dx + ry * dy
        if e.hp > 0 and 0 < f < bd and abs(rx * dy - ry * dx) < .35: best, bd = e, f
    if best: best.hit(dmg)

def start_reload():
    w = P.weap[P.cur]
    if P.rl <= 0 and w["mags"] > 0 and w["ammo"] < w["mag"]: P.rl = w["rl"]; play(w["rsnd"])

def update(dt, mdx, click_ev):
    global DIST
    k = pg.key.get_pressed()
    P.a += mdx * .0028 + ((k[pg.K_RIGHT] or k[pg.K_e]) - (k[pg.K_LEFT] or k[pg.K_q])) * 2.2 * dt
    dx, dy = math.cos(P.a), math.sin(P.a); fw, st = k[pg.K_w] - k[pg.K_s], k[pg.K_d] - k[pg.K_a]
    vx, vy = dx * fw - dy * st, dy * fw + dx * st; n = math.hypot(vx, vy)
    if n:
        run = bool(k[pg.K_LSHIFT] or k[pg.K_RSHIFT]); P.run = run          # SHIFT = lari
        sp = (6.5 if run else 3.6) * dt / n; P.bob += dt * (14 if run else 9)
        P.step -= dt
        if P.step <= 0: play("step", 14); P.step = .27 if run else .45
        if free(P.x + vx * sp, P.y, .28): P.x += vx * sp
        if free(P.x, P.y + vy * sp, .28): P.y += vy * sp
    else: P.run = False
    P.cd -= dt; P.flash -= dt; P.hurt = max(0, P.hurt - dt); P.kick = max(0, P.kick - dt * 160)
    P.msg = (P.msg[0], P.msg[1] - dt)
    if P.rl > 0:
        P.rl -= dt
        if P.rl <= 0: w = P.weap[P.cur]; w["mags"] -= 1; w["ammo"] = w["mag"]
    w = P.weap[P.cur]
    if (pg.mouse.get_pressed()[0] if w["auto"] else click_ev) and P.cd <= 0 and P.rl <= 0:
        if w["ammo"] > 0:
            w["ammo"] -= 1; P.cd = w["delay"]; P.flash = .07; P.kick = 28 if w["pel"] == 1 else 60; play(w["snd"])
            for _ in range(w["pel"]): shoot_ray(P.a + random.gauss(0, w["spr"]), w["dmg"])
            for e in enemies:                                    # suara tembakan memancing musuh
                if e.hp > 0 and math.hypot(e.x - P.x, e.y - P.y) < 10: e.awake = True
        else: P.cd = .3; play("empty"); start_reload()
    P.dtimer = getattr(P, "dtimer", 0) - dt
    if P.dtimer <= 0: DIST = bfs((int(P.x), int(P.y))); P.dtimer = .4
    for e in enemies: e.update(dt)
    for p in projs[:]:
        p[0] += p[2] * dt; p[1] += p[3] * dt
        if MAP[int(p[1]), int(p[0])]: projs.remove(p)
        elif math.hypot(p[0] - P.x, p[1] - P.y) < .45: hurt(p[4]); projs.remove(p)
    for it in items[:]:
        if math.hypot(it[0] - P.x, it[1] - P.y) < .7:
            if it[2] == "health" and P.hp < 100: P.hp = min(100, P.hp + 30); m = "+30 HEALTH"
            elif it[2] == "armor" and P.armor < 100: P.armor = min(100, P.armor + 30); m = "+30 ARMOR"
            elif it[2] == "ammo":
                for q in P.weap: q["mags"] = min(9, q["mags"] + 1)
                m = "+1 MAGAZINE (SEMUA SENJATA)"
            else: continue
            items.remove(it); play("pickup"); P.msg = (m, 2)
    if not any(e.hp > 0 for e in enemies): P.state = "won"

# ================= RENDER =================
CAMX = 2 * np.arange(W) / W - 1
ROWD = .5 * H / (np.arange(H // 2) + .5)
gy, gx = np.mgrid[0:H, 0:W]
VIG = np.clip(1.15 - .55 * (((gx - W / 2) / (W / 2)) ** 2 + ((gy - H / 2) / (H / 2)) ** 2), .3, 1).T[..., None].astype(np.float32)
GRADE = np.array([1.08, .94, .9], np.float32)

def draw_sprite(frame, zb, x, y, tex, scale=1.0, low=1.0, glow=False, hit=False):
    rx, ry = x - P.x, y - P.y; inv = 1 / (P.plx * P.dy - P.dx * P.ply)
    ty = inv * (-P.ply * rx + P.plx * ry)
    if ty < .2 or ty > 22: return
    sx = int(W / 2 * (1 + inv * (P.dy * rx - P.dx * ry) / ty)); size = int(H / ty); sw = int(size * scale)
    if sw < 2: return
    cy = H // 2 + int(size * (1 - scale) / 2 * low); x0, y0 = sx - sw // 2, cy - sw // 2
    c0, c1, r0, r1 = max(x0, 0), min(x0 + sw, W), max(y0, 0), min(y0 + sw, H)
    if c0 >= c1 or r0 >= r1: return
    cols, rows = np.arange(c0, c1), np.arange(r0, r1)
    u, v = ((cols - x0) * 64 // sw).clip(0, 63), ((rows - y0) * 64 // sw).clip(0, 63)
    px = tex[v[None, :], u[:, None]]
    m = (px[..., 3] > 128) & (zb[cols] > ty)[:, None]
    b = 1.0 if glow else max(.12, min(1, 1.25 - ty / 13)) * LIGHT
    rgb = px[..., :3] * .4 + 150 if hit else px[..., :3]
    frame[c0:c1, r0:r1][m] = (rgb * b)[m]

def render():
    P.dx, P.dy = math.cos(P.a), math.sin(P.a); P.plx, P.ply = -P.dy * .66, P.dx * .66
    rdx, rdy = P.dx + P.plx * CAMX, P.dy + P.ply * CAMX
    fx, fy = P.x + ROWD[None, :] * rdx[:, None], P.y + ROWD[None, :] * rdy[:, None]
    tx, ty = (fx * 64).astype(int) & 63, (fy * 64).astype(int) & 63
    fb = (np.clip(1.15 - ROWD / 11, .05, 1) * LIGHT)[None, :, None]
    frame = np.empty((W, H, 3), np.float32)
    frame[:, H // 2:] = FLOOR[ty, tx] * fb; frame[:, :H // 2] = (CEIL[ty, tx] * fb)[:, ::-1]
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
    texx = (wx * 64).astype(int).clip(0, 63); lineh = H / perp; top = H / 2 - lineh / 2
    texy = np.floor((np.arange(H)[None, :] - top[:, None]) * 64 / lineh[:, None]).astype(int)
    inw = (texy >= 0) & (texy < 64)
    wall = WALLS[(MAP[my, mx] - 1)[:, None], texy.clip(0, 63), texx[:, None]]
    wall *= (np.clip(1.25 - perp / 13, .06, 1) * np.where(side == 1, .72, 1) * LIGHT)[:, None, None]
    frame[inw] = wall[inw]
    # --- sprite (musuh, bola api, item) ---
    sp = [(e.x, e.y, TEX[e.k] if e.hp > 0 else TEX["dead_" + e.k], 1.0, 1.0, False, e.flash > 0) for e in enemies]
    sp += [(p[0], p[1], TEX["fire"], .35, .55, True, False) for p in projs]
    sp += [(i[0], i[1], TEX[i[2]], .38, 1.0, False, False) for i in items]
    sp.sort(key=lambda o: -((o[0] - P.x) ** 2 + (o[1] - P.y) ** 2))
    for o in sp: draw_sprite(frame, perp, *o)
    # --- efek: cahaya moncong, darah, vignette, grain ---
    if P.flash > 0: frame *= (1 + P.flash * 8, 1 + P.flash * 6, 1 + P.flash * 2)
    frame *= GRADE * VIG; frame += (np.random.random((W, H, 1)) - .5) * 9
    if P.hurt > 0: frame[..., 0] += P.hurt * 220; frame[..., 1:] *= 1 - P.hurt
    pg.surfarray.blit_array(canvas, np.clip(frame, 0, 255).astype(np.uint8))
    screen.blit(pg.transform.scale(canvas, (W * SC, H * SC)), (0, 0))

def draw_weapon(t):
    w = P.weap[P.cur]; sw, sh = screen.get_size()
    low = math.sin(math.pi * (1 - P.rl / w["rl"])) * 170 if P.rl > 0 else 0
    cx = sw // 2 + int(math.sin(P.bob) * 9); b = int(sh + 20 - abs(math.cos(P.bob)) * 7 + P.kick + low); ln = w["ln"]
    if w["name"] == "PISTOL":
        D.rect(screen, (44, 44, 50), (cx - 28, b - 230, 56, 140)); D.rect(screen, (95, 95, 105), (cx - 28, b - 230, 56, 9))
        D.rect(screen, (30, 30, 34), (cx - 24, b - 100, 48, 110)); D.rect(screen, (150, 108, 88), (cx - 36, b - 70, 72, 90))
    elif w["name"] == "SHOTGUN":
        D.rect(screen, (28, 28, 32), (cx - 28, b - ln, 22, ln - 20)); D.rect(screen, (28, 28, 32), (cx + 6, b - ln, 22, ln - 20))
        D.rect(screen, (80, 80, 88), (cx - 28, b - ln, 56, 6)); D.rect(screen, (112, 70, 38), (cx - 36, b - 170, 72, 80))
        D.rect(screen, (150, 108, 88), (cx - 42, b - 100, 84, 120))
    else:
        D.rect(screen, (36, 36, 40), (cx - 22, b - ln, 44, ln)); D.rect(screen, (80, 80, 88), (cx - 22, b - ln, 44, 8))
        D.rect(screen, (60, 56, 40), (cx - 14, b - 140, 28, 70)); D.rect(screen, (150, 108, 88), (cx - 34, b - 90, 68, 110))
    if P.flash > 0:
        tip = b - ln
        D.polygon(screen, (255, 200, 80), [(cx - 38, tip + 6), (cx - 14, tip - 44), (cx, tip - 110), (cx + 14, tip - 44), (cx + 38, tip + 6), (cx, tip + 14)])
        D.polygon(screen, (255, 250, 210), [(cx - 16, tip + 4), (cx, tip - 60), (cx + 16, tip + 4)])

def txt(s, pos, f=font, col=(235, 225, 205)):
    screen.blit(f.render(s, True, (0, 0, 0)), (pos[0] + 2, pos[1] + 2)); screen.blit(f.render(s, True, col), pos)
def bar(x, y, w, h, frac, col, label):
    D.rect(screen, (14, 8, 8), (x - 2, y - 2, w + 4, h + 4)); D.rect(screen, col, (x, y, int(w * max(0, min(1, frac))), h))
    D.rect(screen, (130, 115, 105), (x - 2, y - 2, w + 4, h + 4), 1); txt(label, (x + 6, y + 1), small)

def draw_hud(t):
    sw, sh = screen.get_size(); w = P.weap[P.cur]
    s = pg.Surface((sw, 78), pg.SRCALPHA); s.fill((18, 6, 6, 190)); screen.blit(s, (0, sh - 78))
    bar(16, sh - 66, 250, 26, P.hp / 100, (185, 28, 28), f"HEALTH  {int(P.hp)}")
    bar(16, sh - 32, 250, 20, P.armor / 100, (50, 110, 215), f"ARMOR  {int(P.armor)}")
    txt(w["name"], (300, sh - 68)); txt(f"[{P.cur + 1}] PISTOL  [2] RIFLE  [3] SHOTGUN".replace(f"[{P.cur + 1}]", f"> {P.cur + 1}"), (300, sh - 28), small)
    txt(f"{w['ammo']:02d}", (555, sh - 68), mid, (255, 200, 90) if w["ammo"] > 0 else (255, 60, 60))
    txt(f"/ {w['mag']}", (630, sh - 52)); txt(f"MAGAZINE x{w['mags']}", (630, sh - 28), small)
    alive = sum(e.hp > 0 for e in enemies); txt(f"KILLS {P.kills}   SISA {alive}", (790, sh - 46), small)
    D.line(screen, (230, 230, 230), (sw // 2 - 8, sh // 2), (sw // 2 + 8, sh // 2)); D.line(screen, (230, 230, 230), (sw // 2, sh // 2 - 8), (sw // 2, sh // 2 + 8))
    if P.rl > 0 and int(t * 6) % 2: txt("RELOADING...", (sw // 2 - 70, sh // 2 + 40))
    if P.run: txt("RUN", (16, sh - 96), small, (255, 200, 90))
    if P.msg[1] > 0: txt(P.msg[0], (sw // 2 - 110, sh // 2 + 80), font, (255, 220, 120))
    if t < 7: txt("WASD jalan | Mouse lihat | Klik tembak | R reload | 1/2/3 senjata | Shift lari", (130, 12), small)
    screen.blit(MM, (sw - 128, 8))
    for e in enemies:
        if e.hp > 0: D.rect(screen, (230, 40, 40), (sw - 128 + e.x * 3 - 1, 8 + e.y * 3 - 1, 3, 3))
    D.circle(screen, (70, 255, 90), (int(sw - 128 + P.x * 3), int(8 + P.y * 3)), 3)
    if P.state != "play":
        o = pg.Surface((sw, sh), pg.SRCALPHA); o.fill((120, 0, 0, 140) if P.state == "dead" else (0, 60, 20, 140)); screen.blit(o, (0, 0))
        m = "YOU DIED" if P.state == "dead" else "AREA BERSIH"
        txt(m, (sw // 2 - big.size(m)[0] // 2, sh // 2 - 60), big); txt("Tekan ENTER untuk main lagi", (sw // 2 - 130, sh // 2 + 20))

# ================= LOOP UTAMA =================
def main():
    global LIGHT, FLICK
    reset(); ambient.play(-1); pg.event.set_grab(True); pg.mouse.set_visible(False); pg.mouse.get_rel()
    t, run, frames = 0.0, True, 0; limit = int(os.environ.get("HG_FRAMES", 0))
    while run:
        dt = min(clock.tick(45) / 1000, .05); t += dt; click_ev = False
        for e in pg.event.get():
            if e.type == pg.QUIT: run = False
            elif e.type == pg.MOUSEBUTTONDOWN and e.button == 1: click_ev = True
            elif e.type == pg.KEYDOWN:
                if e.key == pg.K_ESCAPE: run = False
                elif e.key == pg.K_RETURN and P.state != "play": reset()
                elif P.state == "play" and e.key == pg.K_r: start_reload()
                elif P.state == "play" and e.key in (pg.K_1, pg.K_2, pg.K_3) and P.cur != e.key - pg.K_1:
                    P.cur = e.key - pg.K_1; P.rl = 0; SND["rmag"].stop(); SND["rsg"].stop()
        mdx = pg.mouse.get_rel()[0]
        FLICK = .4 if random.random() < .012 else max(0, FLICK - dt * 3); LIGHT = .92 + .05 * math.sin(t * 11) - FLICK
        if P.state == "play": update(dt, mdx, click_ev)
        render(); draw_weapon(t); draw_hud(t); pg.display.flip()
        frames += 1
        if limit and frames >= limit: break
    pg.quit()

if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback; traceback.print_exc()
        input("\nTerjadi error di atas. Tekan ENTER untuk menutup...")