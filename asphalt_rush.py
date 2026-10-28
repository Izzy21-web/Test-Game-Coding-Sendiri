"""ASPHALT RUSH 3D - Python/pygame.  Jalankan: pip install pygame  lalu  python asphalt_rush.py
Kontrol: Panah/WASD (gas, rem, belok) | SPASI/SHIFT = nitro | R = ulangi | ESC = kembali"""
import math, random, json, os

try:
    import pygame
except ImportError:
    raise SystemExit(
        "Pygame belum terpasang. Buka terminal VS Code lalu jalankan:\n"
        "python -m pip install pygame"
    )

W, H, HY, D, RW, LAPS = 960, 540, 230, 110, 400, 2
pygame.init()
scr = pygame.display.set_mode((W, H)); pygame.display.set_caption("Asphalt Rush 3D - GT-R R34 Edition")
clock = pygame.time.Clock(); scene = pygame.Surface((W, H))
def F(s): return pygame.font.SysFont("arial,helvetica,dejavusans", s, True)
f16, f22, f30, f56, f100 = F(16), F(22), F(30), F(56), F(100)
def txt(s, f, c, x, y, a="l", sf=None):
    im = f.render(s, True, c); r = im.get_rect()
    if a == "c": r.midtop = (x, y)
    elif a == "r": r.topright = (x, y)
    else: r.topleft = (x, y)
    (sf or scr).blit(im, r)
def panel(x, y, w, h, a=140):
    p = pygame.Surface((w, h), pygame.SRCALPHA); p.fill((0, 0, 0, a)); scr.blit(p, (x, y))
def hs(n): return ((n * 2654435761 + 7) & 0xffffffff) % 1000 / 1000

# ------------------------------------------------------------------ DATA
MODES = {"EASY": (5, .72, .84, 1), "MEDIUM": (10, .82, .93, 1.5), "HARD": (15, .92, 1.02, 2)}
LIV = [dict(name="Bayside Blue", body=(20, 70, 200), stripe=(245, 245, 245), accent=(255, 205, 0), pat=0),
       dict(name="Midnight Purple", body=(70, 25, 120), stripe=(255, 190, 0), accent=(0, 210, 255), pat=1),
       dict(name="Millennium Jade", body=(105, 150, 130), stripe=(25, 25, 25), accent=(255, 255, 255), pat=2),
       dict(name="Sparkling Silver", body=(172, 176, 186), stripe=(200, 25, 30), accent=(25, 25, 30), pat=3),
       dict(name="Racing Red", body=(205, 20, 30), stripe=(250, 250, 250), accent=(20, 20, 20), pat=4),
       dict(name="Black Ops", body=(28, 28, 34), stripe=(255, 120, 0), accent=(255, 120, 0), pat=5)]
BODY = [(20, 70, 200), (205, 20, 30), (255, 190, 0), (30, 170, 90), (240, 240, 240), (255, 105, 180), (255, 120, 0), (25, 25, 30)]
NAMES = "Rizky Dewi Budi Sari Agus Maya Tono Lina Joko Nina Dimas Rani Eko Putri Bayu".split()
T = [("Neon Downtown", "c", "#1a0b3d", "#ff5fa2", .6, 2200), ("Skyline Boulevard", "c", "#0d2a5c", "#7fc8ff", .5, 2400),
     ("Harbor District", "c", "#2b2b3a", "#ffb27a", .8, 2300), ("Midnight Metro", "c", "#05050f", "#3b2a7a", .9, 2600),
     ("Old Town Dash", "c", "#4a2a1a", "#ffd08a", 1, 2500), ("Sunset Coast", "b", "#ff6a3d", "#ffd27a", .6, 2400),
     ("Palm Bay", "b", "#1e90ff", "#bfeaff", .5, 2300), ("Coral Highway", "b", "#ff7eb3", "#ffe0c2", .7, 2600),
     ("Lagoon Cruise", "b", "#0a6e8a", "#aef0e0", .85, 2500), ("Pacific Drift", "b", "#3a1c71", "#ffaf7b", 1, 2700)]
SAVE = os.path.join(os.path.expanduser("~"), ".asphalt_rush.json")
G = dict(cr=3000, liv=0, col=-1, e=0, t=0, n=0)
try:
    with open(SAVE, "r", encoding="utf-8") as file:
        saved_data = json.load(file)
    if isinstance(saved_data, dict):
        G.update(saved_data)
except (OSError, json.JSONDecodeError, TypeError):
    pass

def save():
    try:
        with open(SAVE, "w", encoding="utf-8") as file:
            json.dump(G, file, indent=2)
    except OSError:
        pass
def my_liv():
    L = dict(LIV[G["liv"]])
    if G["col"] >= 0: L["body"] = BODY[G["col"]]
    return L

# ------------------------------------------------------------------ MODEL 3D NISSAN GT-R R34 (low-poly, loft)
Z = [-2.35, -2.2, -1.8, -1.2, -.7, -.2, .5, 1.1, 1.5, 1.9, 2.2, 2.35]
WB = [.82, .88, .9, .9, .88, .88, .88, .88, .88, .86, .8, .7]
YS = [.85, .88, .9, .92, .9, .9, .88, .84, .78, .72, .62, .55]
YR = [.88, .92, .95, 1.25, 1.38, 1.4, 1.35, 1.0, .82, .74, .66, .6]
WR = [.76, .78, .78, .68, .62, .62, .62, .68, .8, .8, .74, .64]
def side_col(p, i, k, body, acc):
    low = k in (0, 8)
    on = [low, (not low) and 3 <= i <= 6, (not low) and i <= 4, i >= 7, low or 4 <= i <= 5, (not low) and i % 3 == 0][p]
    return acc if on else body
_mc = {}
def mesh(L):
    key = (L["body"], L["stripe"], L["accent"], L["pat"])
    if key in _mc: return _mc[key]
    V, Fs = [], []
    def v(*p): V.append(p); return len(V) - 1
    body, stripe, acc, pat = key; GL = (22, 32, 48); dark = tuple(int(c * .7) for c in body)
    def quad(pts, col, tag=""): Fs.append(([v(*p) for p in pts], col, tag))
    def box(x0, x1, y0, y1, z0, z1, col):
        for fc in [[(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0)], [(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)],
                   [(x0,y0,z0),(x0,y0,z1),(x0,y1,z1),(x0,y1,z0)], [(x1,y0,z0),(x1,y0,z1),(x1,y1,z1),(x1,y1,z0)],
                   [(x0,y1,z0),(x1,y1,z0),(x1,y1,z1),(x0,y1,z1)], [(x0,y0,z0),(x1,y0,z0),(x1,y0,z1),(x0,y0,z1)]]: quad(fc, col)
    rings = []
    for i in range(12):
        z, wb, ys, yr, wr = Z[i], WB[i], YS[i], YR[i], WR[i]; yb = .28; ym = (yb + ys) / 2; ws = .16
        rings.append([v(-wb, yb, z), v(-wb, ym, z), v(-wb, ys, z), v(-wr, yr, z), v(-ws, yr, z), v(ws, yr, z), v(wr, yr, z), v(wb, ys, z), v(wb, ym, z), v(wb, yb, z)])
    for i in range(11):
        a, b = rings[i], rings[i + 1]
        for k in range(9):
            if k in (0, 1, 7, 8): c = side_col(pat, i, k, body, acc)
            elif k in (2, 6): c = GL if 2 <= i <= 6 else body
            else:
                if i in (2, 6): c = GL
                else: c = stripe if k == 4 else body
            Fs.append(([a[k], a[k + 1], b[k + 1], b[k]], c, ""))
    Fs.append((rings[0][:], dark, "")); Fs.append((rings[11][:], (25, 25, 28), ""))
    for sx in (-1, 1):
        x0, x1 = sorted((sx * .5, sx * .8))
        quad([(x0, .62, -2.37), (x1, .62, -2.37), (x1, .78, -2.37), (x0, .78, -2.37)], (210, 10, 25), "tail")
        quad([(x0, .4, 2.37), (x1, .4, 2.37), (x1, .52, 2.37), (x0, .52, 2.37)], (255, 250, 200), "lamp")
    quad([(-.25, .4, -2.37), (.25, .4, -2.37), (.25, .55, -2.37), (-.25, .55, -2.37)], (235, 235, 235), "lamp")
    box(-.87, .87, 1.12, 1.18, -2.32, -1.95, acc if sum(acc) < 600 else (30, 30, 30))
    for sx in (-1, 1):
        box(sx * .4 - .03, sx * .4 + .03, .94, 1.12, -2.2, -2.1, (25, 25, 25)); box(sx * .87 - .02, sx * .87 + .02, 1.0, 1.25, -2.32, -1.95, (25, 25, 25))
    for wx in (-.86, .86):
        for wz in (-1.55, 1.5):
            x0, x1 = wx - .14, wx + .14; rg0, rg1 = [], []
            for j in range(10):
                an = j * math.pi / 5; y = .36 + .36 * math.sin(an); z = wz + .36 * math.cos(an); rg0.append(v(x0, y, z)); rg1.append(v(x1, y, z))
            for j in range(10): Fs.append(([rg0[j], rg0[(j + 1) % 10], rg1[(j + 1) % 10], rg1[j]], (18, 18, 18), ""))
            Fs.append((rg0, (150, 150, 162) if wx < 0 else (18, 18, 18), "")); Fs.append((rg1, (150, 150, 162) if wx > 0 else (18, 18, 18), ""))
    _mc[key] = (V, Fs); return _mc[key]

def render_car(sf, cx, gy, sc, yaw, L, brake=False, pitch=.22):
    V, Fs = mesh(L); cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch); P = []
    for x, y, z in V:
        x2 = x * cy + z * sy; z2 = -x * sy + z * cy; yv = y * cp + z2 * sp; d = z2 * cp - y * sp; k = 1 / (1 + d * .045)
        P.append((cx + x2 * sc * k, gy - yv * sc * k, d, x2, yv))
    order = sorted(((sum(P[i][2] for i in ids) / len(ids), ids, col, tag) for ids, col, tag in Fs), key=lambda o: -o[0])
    for dd, ids, col, tag in order:
        if tag == "tail": c = (255, 50, 50) if brake else (160, 10, 25)
        elif tag == "lamp": c = col
        else:
            p0, p1, p2 = P[ids[0]], P[ids[1]], P[ids[2]]
            ax, ay, az, bx, by, bz = p1[3]-p0[3], p1[4]-p0[4], p1[2]-p0[2], p2[3]-p0[3], p2[4]-p0[4], p2[2]-p0[2]
            nx, ny, nz = ay*bz - az*by, az*bx - ax*bz, ax*by - ay*bx; m = math.sqrt(nx*nx + ny*ny + nz*nz) or 1
            sh = .5 + .5 * abs((nx * -.35 + ny * .8 + nz * -.5) / m)
            c = (min(255, int(col[0] * sh)), min(255, int(col[1] * sh)), min(255, int(col[2] * sh)))
        pygame.draw.polygon(sf, c, [(P[i][0], P[i][1]) for i in ids])

_ac = {}
def ai_sprite(L):
    key = (L["body"], L["stripe"], L["accent"], L["pat"])
    if key not in _ac:
        s = pygame.Surface((180, 140), pygame.SRCALPHA); render_car(s, 90, 112, 55, 0, L); _ac[key] = s
    return _ac[key]

# ------------------------------------------------------------------ RACE
def stats(): return dict(vmax=235 + 14 * G["e"], acc=52 * (1 + .08 * G["e"]), tm=1 + .1 * G["t"], nit=1 + .3 * G["n"])
def new_race(mode, tr):
    t = T[tr]; N = t[5]; rnd = random.Random(tr * 977 + 13); cur = [0.0] * N; i = 0
    while i < N:
        ln = 40 + int(rnd.random() * 70); k = (rnd.random() * 2 - 1) * t[4]
        if rnd.random() < .3: k = 0
        for j in range(ln):
            if i >= N: break
            cur[i] = k * min(j, ln - j, 12) / 12; i += 1
    n, lo, hi, m = MODES[mode]; ai = []
    for i in range(n):
        L = dict(LIV[rnd.randrange(6)])
        if rnd.random() < .5: L["body"] = rnd.choice(BODY)
        ai.append(dict(d=3 + (i >> 1) * 3, bx=.45 if i % 2 else -.45, x=0, v=0, t=255 * (lo + (hi - lo) * rnd.random()), f=.5 + rnd.random(), ph=rnd.random() * 6, L=L, name=NAMES[i]))
    sky = pygame.Surface((W, HY + 2)); c0, c1 = pygame.Color(t[2]), pygame.Color(t[3])
    for y in range(HY + 2): sky.fill(c0.lerp(c1, y / HY), (0, y, W, 1))
    return dict(tk=t, N=N, cur=cur, ai=ai, m=m, sky=sky, mode=mode, d=0.0, x=0.0, v=0.0, n=1.0, fin=False, time=0.0, cd=3.2, crash=-1.0,
                parts=[], bg=0.0, steer=0, brake=False, nos=False, reason="", paid=False, st=stats(), endt=0.0, flash=0.0)
def rank(R): return 1 + sum(1 for a in R["ai"] if a["d"] > R["d"])
def explode(R, why):
    R["crash"] = 0.0; R["reason"] = why; R["v"] = 0; R["flash"] = 1.0
    for _ in range(140):
        an = random.random() * 6.28; sp = random.random() * 330
        R["parts"].append([W / 2 + random.uniform(-40, 40), H - 100, math.cos(an) * sp, math.sin(an) * sp - 160, random.uniform(.6, 1.8), 1.8, random.uniform(8, 34), 0])
    for _ in range(25):
        an = random.random() * 6.28; sp = 150 + random.random() * 300
        R["parts"].append([W / 2, H - 100, math.cos(an) * sp, math.sin(an) * sp - 250, random.uniform(1, 2), 2, random.uniform(5, 12), 1])

def update(R, dt, k):
    R["bg"] += 0; N = R["N"]; city = R["tk"][1] == "c"
    if R["crash"] >= 0:
        R["crash"] += dt
        for p in R["parts"]:
            p[0] += p[2] * dt; p[1] += p[3] * dt; p[3] += (400 if p[7] else -60) * dt; p[4] -= dt
        R["flash"] = max(0, R["flash"] - dt * 1.6); return
    R["time"] += dt if R["cd"] <= 0 else 0
    if R["cd"] > 0:
        R["cd"] -= dt; return
    st = R["st"]; cur = R["cur"][int(R["d"]) % N]; v = R["v"]
    L = k[pygame.K_LEFT] or k[pygame.K_a]; Rt = k[pygame.K_RIGHT] or k[pygame.K_d]; up = k[pygame.K_UP] or k[pygame.K_w]
    R["brake"] = bool(k[pygame.K_DOWN] or k[pygame.K_s]); R["steer"] = (1 if Rt else 0) - (1 if L else 0)
    nos = (k[pygame.K_SPACE] or k[pygame.K_LSHIFT]) and R["n"] > 0 and v > 40 and not R["fin"]; R["nos"] = bool(nos)
    vm = st["vmax"] * (1.18 if nos else 1)
    if R["fin"]: up = False
    if R["brake"]: v -= 150 * dt
    elif up or nos:
        v += st["acc"] * (1.6 if nos else 1) * max(0, 1 - (v / vm) ** 1.6) * dt * 1.6
        if v > vm: v -= 25 * dt
    else: v -= (10 + v * v / 9000) * dt
    R["n"] = max(0, R["n"] - dt * .25 / st["nit"]) if nos else min(1, R["n"] + dt * .04)
    if abs(R["x"]) > 1.05 and v > 70: v -= 130 * dt
    v = max(0, v); sps = v * .25
    R["x"] += R["steer"] * dt * 1.8 * st["tm"] * min(1, .25 + v / 120) * (1 - v / 700)
    R["x"] -= cur * dt * (v / 264) * 1.1 / st["tm"]; R["x"] = max(-2.5, min(2.5, R["x"]))
    for a in R["ai"]:
        dd = a["d"] - R["d"]
        if 0 < dd < 1.6 and abs(a["x"] - R["x"]) < .38:
            v = min(v, a["v"] * .9); R["d"] = a["d"] - 1.6; R["x"] += .05 if R["x"] > a["x"] else -.05
    R["v"] = v; R["d"] += sps * dt; R["bg"] += cur * sps * dt * .5
    od = round(R["d"] / 6) * 6
    if v > 5:
        if abs(R["d"] - od) < .9 and abs(R["x"]) > 1.4: explode(R, "Mobil menabrak bangunan!"); return
        if not city and R["x"] < -1.9: explode(R, "Mobil tercebur ke laut!"); return
    for a in R["ai"]:
        a["v"] += (a["t"] - a["v"]) * dt * .6; a["d"] += a["v"] * .25 * dt; a["x"] = a["bx"] + math.sin(R["time"] * a["f"] + a["ph"]) * .2
    if not R["fin"] and R["d"] >= LAPS * N: R["fin"] = True; R["pos"] = rank(R); R["ft"] = R["time"]
    if R["fin"]: R["endt"] += dt

def draw_world(R):
    t = R["tk"]; city = t[1] == "c"; d = R["d"]; base = int(d); fr = d - base; N = R["N"]; cur = R["cur"]; off = R["bg"]
    scene.blit(R["sky"], (0, 0))
    if city:
        for j in range(-1, W // 34 + 2):
            q = j + int(off // 34); hh = 25 + hs(q) * 80
            pygame.draw.rect(scene, (16, 18, 42) if hs(q + 99) < .5 else (25, 28, 58), (j * 34 - off % 34, HY - hh, 32, hh + 2))
    else:
        pygame.draw.circle(scene, (255, 240, 200), (int(W * .5 - off * .1 % W), HY - 50), 34); pygame.draw.rect(scene, (27, 143, 209), (0, HY - 14, W, 16))
    pts = []; x = 0.0; dx = -cur[base % N] * fr
    for i in range(D + 1):
        s = 1 / (i - fr + 1.2); pts.append((W / 2 + (x * .025 - R["x"]) * RW * s, HY + (H - HY) * s, RW * s)); x += dx; dx += cur[(base + i) % N]
    B = {}
    for a in R["ai"]:
        di = (a["d"] - d) % N
        if 1.2 < di < D - 1: B.setdefault(int(di + fr), []).append(a)
    gcol = ((35, 38, 58), (42, 46, 68)) if city else ((232, 210, 143), (223, 198, 124)); wcol = ((27, 143, 209), (42, 160, 230))
    rc = ((58, 61, 77), (66, 70, 90)) if city else ((74, 74, 82), (82, 82, 92)); rum = ((255, 255, 255), (230, 57, 70))
    def quad(a, b, k, c): pygame.draw.polygon(scene, c, [(a[0] - a[2] * k, a[1]), (a[0] + a[2] * k, a[1]), (b[0] + b[2] * k, b[1]), (b[0] - b[2] * k, b[1])])
    for i in range(D - 1, -1, -1):
        a, b = pts[i + 1], pts[i]; idd = base + i; alt = (idd >> 2) & 1
        if b[1] <= a[1]: continue
        scene.fill(gcol[alt], (0, int(a[1]), W, int(b[1] - a[1]) + 1))
        if not city: pygame.draw.polygon(scene, wcol[alt], [(0, a[1]), (a[0] - a[2] * 2.2, a[1]), (b[0] - b[2] * 2.2, b[1] + 1), (0, b[1] + 1)])
        quad(a, b, 1.12, rum[alt]); quad(a, b, 1, rc[alt])
        if alt: quad(a, b, .025, (220, 220, 220))
        if idd % 6 == 0:
            for q in ((-1, 1) if city else (1,)):
                bx = b[0] + q * b[2] * 2.1; w = b[2]; y = b[1]
                if city:
                    hh = w * (1.5 + hs(idd) * 2.2); ww = w * 1.1
                    pygame.draw.rect(scene, [(43, 48, 85), (58, 45, 85), (36, 74, 102), (74, 51, 68)][int(hs(idd + 5) * 4)], (bx - ww / 2, y - hh, ww, hh))
                    for r in range(1, 5): pygame.draw.rect(scene, (255, 230, 120), (bx - ww * .4, y - hh + hh * r / 5.3, ww * .8, max(1, hh * .05)))
                elif (idd // 6) % 2:
                    pygame.draw.rect(scene, (240, 225, 190), (bx - w * .45, y - w * .8, w * .9, w * .8)); pygame.draw.polygon(scene, (200, 70, 50), [(bx - w * .55, y - w * .8), (bx + w * .55, y - w * .8), (bx, y - w * 1.25)])
                else:
                    pygame.draw.rect(scene, (107, 74, 42), (bx - w * .04, y - w * 1.3, w * .08, w * 1.3)); pygame.draw.ellipse(scene, (31, 143, 58), (bx - w * .4, y - w * 1.5, w * .8, w * .32))
        for ai in B.get(i, []):
            wpx = int(b[2] * .42); px = b[0] + ai["x"] * b[2]
            if wpx < 8: pygame.draw.rect(scene, ai["L"]["body"], (px - wpx / 2, b[1] - wpx * .6, wpx, wpx * .6))
            else:
                f = wpx / 99; sp = pygame.transform.scale(ai_sprite(ai["L"]), (int(180 * f), int(140 * f))); scene.blit(sp, (px - 90 * f, b[1] - 112 * f))

def hud(R):
    v = R["v"]; cx, cy, r = W - 140, H - 140, 110
    p = pygame.Surface((2 * r + 10, 2 * r + 10), pygame.SRCALPHA); pygame.draw.circle(p, (0, 0, 0, 160), (r + 5, r + 5), r + 4); scr.blit(p, (cx - r - 5, cy - r - 5))
    for k in range(0, 301, 20):
        a = math.radians(135 + 270 * k / 300); c = (255, 80, 60) if k >= 240 else (230, 230, 230); l = 14 if k % 40 == 0 else 8
        pygame.draw.line(scr, c, (cx + (r - 4) * math.cos(a), cy + (r - 4) * math.sin(a)), (cx + (r - 4 - l) * math.cos(a), cy + (r - 4 - l) * math.sin(a)), 3 if k % 40 == 0 else 1)
        if k % 40 == 0: txt(str(k), f16, c, cx + (r - 34) * math.cos(a), cy + (r - 34) * math.sin(a) - 9, "c")
    a = math.radians(135 + 270 * min(v, 300) / 300)
    pygame.draw.line(scr, (255, 60, 40), (cx, cy), (cx + (r - 18) * math.cos(a), cy + (r - 18) * math.sin(a)), 4); pygame.draw.circle(scr, (40, 40, 40), (cx, cy), 10)
    txt(str(int(v)), f30, (255, 255, 255), cx, cy + 22, "c"); txt("km/h  G%d" % min(6, 1 + int(v / 45)), f16, (180, 180, 180), cx, cy + 54, "c")
    bx, by, bh = cx - r - 38, cy - r, 2 * r
    pygame.draw.rect(scr, (0, 0, 0), (bx, by, 24, bh)); pygame.draw.rect(scr, (60, 90, 110), (bx, by, 24, bh), 2)
    fh = int((bh - 4) * R["n"]); pygame.draw.rect(scr, (40, 200, 255) if not R["nos"] else (255, 255, 255), (bx + 2, by + bh - 2 - fh, 20, fh))
    txt("NITRO", f16, (120, 220, 255), bx + 12, by - 22, "c")
    tm = R["time"]; panel(W // 2 - 90, 8, 180, 62)
    txt("%02d:%05.2f" % (tm // 60, tm % 60), f30, (255, 255, 255), W // 2, 10, "c"); txt("LAP %d/%d" % (min(LAPS, int(R["d"] / R["N"]) + 1), LAPS), f16, (255, 200, 80), W // 2, 46, "c")
    ent = [("KAMU", R["d"], True, my_liv()["body"])] + [(a["name"], a["d"], False, a["L"]["body"]) for a in R["ai"]]
    ent.sort(key=lambda e: -e[1]); rows = ent[:8]
    me = [i for i, e in enumerate(ent) if e[2]][0]
    if me >= 8: rows.append(ent[me])
    panel(8, 8, 190, 14 + 26 * len(rows) + 22)
    txt("KLASEMEN", f16, (255, 200, 80), 16, 12)
    for j, e in enumerate(rows):
        y = 34 + j * 26; pos = ent.index(e) + 1
        if e[2]: pygame.draw.rect(scr, (255, 122, 26), (10, y - 2, 186, 24), 0, 4)
        txt(str(pos), f22, (255, 255, 255), 16, y - 2); pygame.draw.rect(scr, e[3], (46, y + 3, 16, 12), 0, 2); txt(e[0], f16, (255, 255, 255), 70, y + 1)

def draw_race(R):
    draw_world(R); k = int(min(R["v"], 300))
    if R["v"] > 100:
        a = min(110, int((R["v"] - 100) * .75)); tmp = pygame.transform.scale(scene, (int(W * 1.06), int(H * 1.06))); tmp.set_alpha(a)
        scr.blit(scene, (0, 0)); scr.blit(tmp, (-W * .03, -H * .03 - 4))
    else: scr.blit(scene, (0, 0))
    sh = (random.randint(-8, 8), random.randint(-8, 8)) if 0 <= R["crash"] < .6 else (0, 0)
    if R["crash"] < 0:
        wob = random.uniform(-2, 2) if R["v"] > 200 else 0
        render_car(scr, W / 2 + wob, H - 42, 100, R["steer"] * .22, my_liv(), R["brake"])
        if R["nos"]:
            for sx in (-1, 1):
                pygame.draw.polygon(scr, (255, 180, 40), [(W / 2 + sx * 45 - 10, H - 62), (W / 2 + sx * 45 + 10, H - 62), (W / 2 + sx * 45, H - 62 + random.randint(30, 60))])
    for p in R["parts"]:
        if p[4] <= 0: continue
        f = p[4] / p[5]
        if p[7]: pygame.draw.rect(scr, (30, 30, 30), (p[0], p[1], p[6], p[6] * .5))
        else: pygame.draw.circle(scr, (255, int(60 + 190 * f), int(40 * f)) if f > .45 else (int(80 * f + 30),) * 3, (int(p[0]), int(p[1])), int(p[6] * (1.3 - f * .5)))
    if R["flash"] > 0:
        fs = pygame.Surface((W, H)); fs.fill((255, 240, 200)); fs.set_alpha(int(220 * R["flash"])); scr.blit(fs, (0, 0))
    if sh != (0, 0): scr.blit(scr.copy(), sh)
    hud(R)
    if R["cd"] > 0: txt(str(math.ceil(R["cd"] - .2)) if R["cd"] > .2 else "GO!", f100, (255, 214, 10), W // 2, 150, "c")
    if R["crash"] > 1.2:
        panel(0, 130, W, 210, 170); txt("GAME OVER", f100, (255, 50, 40), W // 2, 135, "c"); txt(R["reason"], f30, (255, 255, 255), W // 2, 250, "c")
        txt("R = Ulangi    ESC = Pilih track", f22, (200, 200, 200), W // 2, 295, "c")
    if R["fin"] and R["endt"] > 1.5: pass

# ------------------------------------------------------------------ MENUS
def bg(t):
    for y in range(0, H, 6): pygame.draw.rect(scr, (12 + y // 30, 14 + y // 40, 28 + y // 20), (0, y, W, 6))
    txt("ASPHALT RUSH 3D", f56, (255, 122, 26), 30, 14); txt("Kredit: %d" % G["cr"], f22, (255, 214, 10), W - 30, 22, "r")
def screen_mode(sel, t):
    bg(t); txt("PILIH MODE", f30, (255, 255, 255), W // 2, 100, "c")
    info = {"EASY": "5 lawan - AI lambat - hadiah x1", "MEDIUM": "10 lawan - AI seimbang - hadiah x1.5", "HARD": "15 lawan - AI cepat & agresif - hadiah x2"}
    for i, m in enumerate(MODES):
        y = 170 + i * 90; pygame.draw.rect(scr, (255, 122, 26) if i == sel else (40, 44, 66), (W // 2 - 260, y, 520, 74), 0, 10)
        txt(m, f30, (255, 255, 255), W // 2, y + 6, "c"); txt(info[m], f16, (240, 240, 240), W // 2, y + 44, "c")
    txt("Panah atas/bawah + ENTER", f16, (160, 165, 190), W // 2, H - 40, "c")
def bar(x, y, v, mx, label):
    txt(label, f16, (200, 205, 230), x, y); pygame.draw.rect(scr, (40, 44, 66), (x + 110, y + 4, 200, 10), 0, 4); pygame.draw.rect(scr, (255, 122, 26), (x + 110, y + 4, int(200 * min(1, v / mx)), 10), 0, 4)
def screen_garage(t):
    bg(t); L = my_liv(); txt("GARASI - Nissan GT-R R34", f30, (255, 255, 255), 30, 80)
    pygame.draw.ellipse(scr, (0, 0, 0), (50, 400, 400, 40)); render_car(scr, 250, 410, 150, t * .9, L, False, .3)
    txt("< %s >" % L["name"], f30, (255, 214, 10), 250, 450, "c")
    s = stats(); x = 520
    bar(x, 130, s["vmax"], 330, "Kecepatan"); bar(x, 160, s["acc"], 90, "Akselerasi"); bar(x, 190, s["tm"], 1.5, "Handling"); bar(x, 220, s["nit"], 2, "Nitro")
    txt("KOSTUMISASI", f22, (255, 122, 26), x, 270); txt("[</>] Ganti livery    [C] Warna bodi", f16, (230, 230, 240), x, 300)
    txt("MODIFIKASI (biaya = (level+1) x 600)", f22, (255, 122, 26), x, 340)
    for i, (k, n) in enumerate((("e", "[E] Mesin"), ("t", "[T] Ban & handling"), ("n", "[N] Nitro"))):
        txt("%s  Lv %d/3  %s" % (n, G[k], "MAX" if G[k] >= 3 else str((G[k] + 1) * 600)), f16, (230, 230, 240), x, 372 + i * 26)
    txt("ENTER = Pilih track    ESC = Kembali", f16, (160, 165, 190), W // 2, H - 34, "c")
def screen_track(sel, t):
    bg(t); txt("PILIH TRACK", f30, (255, 255, 255), W // 2, 80, "c")
    for i, tk in enumerate(T):
        col, rw = i // 5, i % 5; x = 60 + col * 450; y = 140 + rw * 66
        pygame.draw.rect(scr, (255, 122, 26) if i == sel else (40, 44, 66), (x, y, 420, 56), 0, 8)
        txt("%d. %s" % (i + 1, tk[0]), f22, (255, 255, 255), x + 12, y + 4); txt(("Kota" if tk[1] == "c" else "Pantai") + " - %.1f km - tikungan %s" % (tk[5] * LAPS / 1000, "*" * math.ceil(tk[4] * 3)), f16, (235, 235, 245), x + 12, y + 32)
    txt("Panah + ENTER    ESC = Garasi", f16, (160, 165, 190), W // 2, H - 34, "c")
def screen_result(R, t):
    bg(t); pos = R["pos"]; txt("JUARA 1!" if pos == 1 else "POSISI %d / %d" % (pos, len(R["ai"]) + 1), f100, (255, 214, 10), W // 2, 120, "c")
    txt("Waktu %02d:%05.2f   -   Hadiah +%d kredit" % (R["ft"] // 60, R["ft"] % 60, R["reward"]), f30, (255, 255, 255), W // 2, 270, "c")
    txt("R = Ulangi    ENTER/ESC = Pilih track", f22, (200, 200, 220), W // 2, 340, "c")

# ------------------------------------------------------------------ MAIN
state, sm, st_, R, tt, modes = "mode", 0, 0, None, 0.0, list(MODES)
def go():
    global R, state
    R = new_race(modes[sm], st_); state = "race"
run = True
while run:
    dt = min(.05, clock.tick(60) / 1000); tt += dt
    for e in pygame.event.get():
        if e.type == pygame.QUIT: run = False
        elif e.type == pygame.KEYDOWN:
            k = e.key
            if state == "mode":
                if k == pygame.K_UP: sm = (sm - 1) % 3
                elif k == pygame.K_DOWN: sm = (sm + 1) % 3
                elif k == pygame.K_RETURN: state = "garage"
            elif state == "garage":
                if k == pygame.K_LEFT: G["liv"] = (G["liv"] - 1) % 6; G["col"] = -1
                elif k == pygame.K_RIGHT: G["liv"] = (G["liv"] + 1) % 6; G["col"] = -1
                elif k == pygame.K_c: G["col"] = (G["col"] + 2) % (len(BODY) + 1) - 1
                elif k in (pygame.K_e, pygame.K_t, pygame.K_n):
                    kk = {pygame.K_e: "e", pygame.K_t: "t", pygame.K_n: "n"}[k]; cost = (G[kk] + 1) * 600
                    if G[kk] < 3 and G["cr"] >= cost: G["cr"] -= cost; G[kk] += 1
                elif k == pygame.K_RETURN: state = "track"
                elif k == pygame.K_ESCAPE: state = "mode"
                save()
            elif state == "track":
                if k == pygame.K_UP: st_ = (st_ - 1) % 10
                elif k == pygame.K_DOWN: st_ = (st_ + 1) % 10
                elif k in (pygame.K_LEFT, pygame.K_RIGHT): st_ = (st_ + 5) % 10
                elif k == pygame.K_RETURN: go()
                elif k == pygame.K_ESCAPE: state = "garage"
            elif state == "race":
                if k == pygame.K_ESCAPE: state = "track"
                elif k == pygame.K_r and (R["crash"] >= 0 or R["fin"]): go()
            elif state == "result":
                if k == pygame.K_r: go()
                elif k in (pygame.K_RETURN, pygame.K_ESCAPE): state = "track"
    if state == "mode": screen_mode(sm, tt)
    elif state == "garage": screen_garage(tt)
    elif state == "track": screen_track(st_, tt)
    elif state == "race":
        update(R, dt, pygame.key.get_pressed()); draw_race(R)
        if R["fin"] and R["endt"] > 2 and not R["paid"]:
            R["paid"] = True; n = len(R["ai"]) + 1; R["reward"] = int(((n - R["pos"] + 1) * 90 + (400 if R["pos"] == 1 else 0)) * R["m"]); G["cr"] += R["reward"]; save(); state = "result"
    elif state == "result": screen_result(R, tt)
    pygame.display.flip()
pygame.quit()