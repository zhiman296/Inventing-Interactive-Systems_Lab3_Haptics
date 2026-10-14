"""
Snow + Rain Walk
"""

import bisect
import math
import os
import random
import time

import pygame
import serial
import serial.tools.list_ports

# SETTINGS 
PORT = "/dev/cu.usbserial-0001"       
BAUD = 115200
JOY_AXIS = "x"        
INVERT_AXIS = False    

# Font
FONT_NAMES = "markerfelt,chalkboardse,bradleyhand,noteworthy,comicsansms,comicneue,inkfree,segoeprint,kristenitc"
FONT_FILE = None       # or put a handwriting .ttf next to this script, e.g. "PatrickHand-Regular.ttf"

# Sound
SNOW_SOUND_FILE = "snow.mp3"
RAIN_SOUND_FILE = "rain.mp3"
SNOW_VOLUME = 0.8                  
RAIN_VOLUME = 0.6                   

# Footsteps measured from snow.mp3
# H = hard, S = normal, L = light
SNOW_FOOTSTEPS = [
    (0.25, "S"), (1.15, "L"), (2.02, "H"), (2.85, "S"), (3.49, "S"),
    (4.56, "S"), (5.34, "H"), (6.06, "S"), (6.77, "H"), (7.37, "L"),
]
VIB_LEAD = 0.03       
STEP_LEN = 1.2        

# Rain drop timing
DROP_MIN = 0.10
DROP_MEAN = 0.35
DROP_MAX = 1.20

# World
WIDTH, HEIGHT = 900, 500
SECTION_LEN = 30.0     
WORLD_LEN = SECTION_LEN * 6   
SPEED = 2.0           
DEADZONE = 0.2
JOY_RANGE = 1800.0

# Floor view 
Y_REF = 430.0          
PPU = 110.0           
K = 0.12               
FAR_D = 12.5           
NEAR_D = -1.2
FLAT = 0.62            

# Boots
FOOT_X = (WIDTH // 2 - 105, WIDTH // 2 + 105)
BOOT_TOP = 320         
BOOT_SCALE = 0.62
PRINT_SY = 270         
PRINT_W = 0.69        

# Colors 
SNOW_BASE = (209, 225, 233)
SNOW_CREAM = (255, 251, 240)
SNOW_SHADE = (138, 163, 190)
PRINT_FILL = (178, 210, 234)   
PRINT_SHADE = (120, 152, 184)  
RAIN_BASE = (58, 98, 128)
PUDDLE = (78, 130, 168)
PUDDLE_HI = (96, 150, 188)
RING = (212, 232, 247)
DROPLET = (156, 208, 234)
OUT = (24, 26, 38)
TEXT_COL = (255, 251, 240)
TEXT_EDGE = (40, 58, 90)


# ---------------- SMALL HELPERS ----------------
def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def lerp_color(a, b, t):
    t = clamp(t)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def ell(surf, color, cx, cy, w, h, width=0):
    if w < 1 or h < 1:
        return
    pygame.draw.ellipse(surf, color, (int(cx - w / 2), int(cy - h / 2), int(w), int(h)), width)


def next_drop_delay():
    extra = random.expovariate(1.0 / (DROP_MEAN - DROP_MIN))
    return DROP_MIN + min(extra, DROP_MAX - DROP_MIN)


def crossed(onset, prev_t, cur_t):
    if prev_t <= cur_t:
        return prev_t < onset <= cur_t
    return onset > prev_t or onset <= cur_t


def is_rain(y):
    """Is the path at distance y a rain section?"""
    if y < 0:
        return False
    return int(y // SECTION_LEN) % 2 == 1


def boundary_gap(y):
    pos = y % SECTION_LEN
    return min(pos, SECTION_LEN - pos)


def depth_scale(d):
    return 1.0 / (1.0 + K * d)


def depth_y(d):
    return Y_REF - PPU * d / (1.0 + K * d)


def d_from_sy(sy):
    a = (Y_REF - sy) / PPU
    return a / (1.0 - K * a)


def to_screen(x, y_w, dist, bob=0.0):
    d = y_w - dist
    sc = depth_scale(d)
    return WIDTH / 2 + x * sc, depth_y(d) + bob, sc


D_PRINT = d_from_sy(PRINT_SY)
FEET_D = d_from_sy(350)       # the weather changes when the section edge reaches your boots
X_LAND = (FOOT_X[1] - FOOT_X[0]) / 2 / depth_scale(D_PRINT)   # sideways spot of each boot print


# FONT
FONT_PATHS = [
    # Mac
    "/System/Library/Fonts/Supplemental/Chalkboard.ttc",
    "/System/Library/Fonts/Supplemental/ChalkboardSE.ttc",
    "/System/Library/Fonts/Supplemental/MarkerFelt.ttc",
    "/System/Library/Fonts/MarkerFelt.ttc",
    "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf",
    "/System/Library/Fonts/Supplemental/Noteworthy.ttc",
    "/System/Library/Fonts/Supplemental/Comic Sans MS Bold.ttf",
]


def load_font(size):
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = ([os.path.join(here, FONT_FILE)] if FONT_FILE else []) + FONT_PATHS
    for path in candidates:
        if os.path.exists(path):
            try:
                return pygame.font.Font(path, size)
            except (pygame.error, OSError):
                pass
    return pygame.font.SysFont(FONT_NAMES, size, bold=True)


def draw_text(screen, font, text, pos, color=TEXT_COL, edge=TEXT_EDGE, edge_w=3):
    """Sticker-style text: a dark outline around light letters."""
    x, y = pos
    outline = font.render(text, True, edge)
    for dx in range(-edge_w, edge_w + 1):
        for dy in range(-edge_w, edge_w + 1):
            if dx * dx + dy * dy <= edge_w * edge_w + 1:
                screen.blit(outline, (x + dx, y + dy))
    screen.blit(font.render(text, True, color), (x, y))


# SOUND
def sound_path(filename):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


def load_sound(filename):
    try:
        return pygame.mixer.Sound(sound_path(filename))
    except (pygame.error, FileNotFoundError) as e:
        print("Could not load sound", filename, "-", e)
        return None


def start_rain_music(filename):
    try:
        pygame.mixer.music.load(sound_path(filename))
        pygame.mixer.music.set_volume(0.0)
        pygame.mixer.music.play(loops=-1)
        return True
    except (pygame.error, FileNotFoundError) as e:
        print("Could not load sound", filename, "-", e)
        return False


# ESP32 CONNECTION
def find_port():
    if PORT:
        return PORT
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "").lower()
        if any(k in desc for k in ("cp210", "ch340", "ch910", "usb serial", "usb-serial", "uart")):
            return p.device
    return None


class Board:
    def __init__(self):
        self.ser = None
        self.buf = ""
        self.x = 0
        self.y = 0
        self.button = False
        port = find_port()
        if port:
            try:
                self.ser = serial.Serial(port, BAUD, timeout=0)
                pygame.time.wait(2000)  # ESP32 resets when the port opens
                print("Connected to", port)
            except serial.SerialException as e:
                print("Could not open", port, "-", e)
        else:
            print("No ESP32 found. Using keyboard.")

    @property
    def connected(self):
        return self.ser is not None

    def update(self):
        if not self.ser:
            return
        try:
            data = self.ser.read(self.ser.in_waiting or 1)
            self.buf += data.decode(errors="ignore")
        except (serial.SerialException, OSError):
            print("Lost connection to the ESP32. Using keyboard.")
            self.ser = None
            return

        lines = self.buf.split("\n")
        self.buf = lines[-1]
        for line in lines[:-1]:
            parts = line.strip().split(",")
            if len(parts) == 4 and parts[0] == "J":
                try:
                    self.x = int(parts[1])
                    self.y = int(parts[2])
                    self.button = parts[3] == "1"
                except ValueError:
                    pass

    def send(self, letter):
        if self.ser:
            try:
                self.ser.write(letter.encode())
            except (serial.SerialException, OSError):
                self.ser = None


# THE GROUND
def make_blob(rng, n=16, rough=0.22):
    pts = []
    for k in range(n):
        a = 2 * math.pi * k / n
        r = 1.0 + rng.uniform(-rough, rough)
        pts.append((math.cos(a) * r, math.sin(a) * r))
    return pts


def build_scene():
    """Every object: [distance along path, sideways, kind, size, squash, blob shape, seed]."""
    rng = random.Random(8)
    objs = []
    end = WORLD_LEN + FAR_D + 2

    # snow sections: only a few small things, and the middle of the path stays clear
    y = 0.0
    while y < end:
        y += 0.25
        if is_rain(y) or rng.random() > 0.26:
            continue
        r = rng.random()
        side = rng.choice((-1, 1))
        if r < 0.16:
            kind, size, asp, rough = "drift", rng.uniform(46, 100), rng.uniform(0.7, 1.1), 0.2
            x = side * rng.uniform(330, 650)
        elif r < 0.50:
            kind, size, asp, rough = "shard", rng.uniform(10, 22), rng.uniform(0.5, 0.9), 0.4
            x = rng.uniform(-650, 650)
        elif r < 0.62:
            kind, size, asp, rough = "pebble", rng.uniform(11, 20), 1.0, 0.15
            x = side * rng.uniform(220, 650)
        elif r < 0.76:
            kind, size, asp, rough = "tuft", rng.uniform(24, 36), 1.0, 0.1
            x = side * rng.uniform(260, 650)
        elif r < 0.88:
            kind, size, asp, rough = "twig", rng.uniform(38, 60), 1.0, 0.1
            x = side * rng.uniform(260, 650)
        else:
            kind, size, asp, rough = "tracks", rng.uniform(24, 30), 1.0, 0.1
            x = side * rng.uniform(300, 650)
        if boundary_gap(y) < size * FLAT * asp / PPU * 1.3 + 0.7:
            continue
        objs.append([y, x, kind, size, asp, make_blob(rng, 16, rough), rng.random()])

    # rain sections: puddles
    y = 0.0
    while y < end:
        y += 0.45
        if not is_rain(y) or rng.random() > 0.55:
            continue
        x = rng.uniform(-650, 650)
        size = rng.uniform(60, 170) if rng.random() < 0.65 else rng.uniform(14, 32)
        asp = rng.uniform(0.8, 1.1)
        if boundary_gap(y) < size * FLAT * asp / PPU * 1.3 + 0.7:
            continue
        objs.append([y, x, "puddle", size, asp, None, rng.random()])

    objs.sort(key=lambda o: o[0])
    return objs


GROUND = build_scene()
GROUND_Y = [o[0] for o in GROUND]
PUDDLES = [o for o in GROUND if o[2] == "puddle" and o[3] > 50]
PUDDLE_Y = [o[0] for o in PUDDLES]


def build_grain():
    rng = random.Random(2)
    surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    for _ in range(9000):
        x, y = rng.randrange(WIDTH), rng.randrange(HEIGHT)
        if rng.random() < 0.5:
            surf.set_at((x, y), (40, 60, 90, rng.randint(10, 24)))
        else:
            surf.set_at((x, y), (255, 255, 255, rng.randint(10, 24)))
    return surf


# FOOTPRINT
def egg_points(cx, cy, A, B, k, n=72):
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        pts.append((cx + A * math.cos(a) * (1 + k * math.sin(a)), cy + B * math.sin(a)))
    return pts


def build_print_images():
    s = pygame.Surface((300, 620), pygame.SRCALPHA)
    cx = 150

    def piece_points(y0, y1, w_out, w_in, cx_p, n=48):
        left, right = [], []
        for i in range(n + 1):
            u = -1 + 2 * i / n
            y = y0 + (y1 - y0) * (u + 1) / 2
            s_ = math.sqrt(max(0.0, 1 - u * u)) ** 0.85
            f = 1 - 0.10 * u
            left.append((cx_p - w_out * s_ * f, y))
            right.append((cx_p + w_in * s_ * f, y))
        return left + right[::-1]

    def draw_dent(pts):
        mx = sum(p[0] for p in pts) / len(pts)
        my = sum(p[1] for p in pts) / len(pts)
        # 0) raised snow rim: a slightly bigger cream shape shifted down-right
        rim = [(mx + (x - mx) * 1.05 + 9, my + (y - my) * 1.05 + 13) for x, y in pts]
        pygame.draw.polygon(s, SNOW_CREAM, rim)
        # 1) dark shape = inner wall of the dent
        pygame.draw.polygon(s, PRINT_SHADE, pts)
        # 2) lighter floor of the dent, leaves a dark crescent on the top-left
        inner = [(mx + (x - mx) * 0.90 + 7, my + (y - my) * 0.94 + 12) for x, y in pts]
        pygame.draw.polygon(s, PRINT_FILL, inner)
        # 3) small shine
        sx = sum(p[0] for p in inner) / len(inner)
        sy = max(p[1] for p in inner)
        ell(s, (214, 234, 248), sx + 18, sy - 34, 46, 14)

    draw_dent(piece_points(30, 372, 102, 88, cx))      # forefoot
    draw_dent(piece_points(414, 590, 70, 62, cx - 3))  # heel

    # smaller angle: the ground squash makes the tilt look bigger on screen
    left = pygame.transform.rotozoom(s, 6, 1.0)
    right = pygame.transform.rotozoom(pygame.transform.flip(s, True, False), -6, 1.0)
    return left, right


_print_cache = {}


def scaled_print(images, foot, sc, grow=1.0):
    q = int(sc * 120)                 # fine steps, so no visible size jumps
    g = int(grow * 20)
    key = (foot, q, g)
    img = _print_cache.get(key)
    if img is None:
        if len(_print_cache) > 600:
            _print_cache.clear()
        base = images[foot]
        k = max(0.05, q / 120.0) * (g / 20.0) * PRINT_W
        img = pygame.transform.smoothscale(
            base, (max(2, int(base.get_width() * k)),
                   max(2, int(base.get_height() * k * FLAT))))   # FLAT = lies on the ground
        _print_cache[key] = img
    return img


# BOOTS
def build_boot():
    BW, BH = 260, 440
    s = pygame.Surface((BW, BH), pygame.SRCALPHA)
    blue = (44, 122, 178)
    toe, toe_hi = (118, 190, 224), (168, 218, 240)
    sole = (92, 106, 120)

    # sole: egg shaped, like the print
    pts = egg_points(130, 190, 112, 188, 0.14)
    pygame.draw.polygon(s, sole, pts)
    pygame.draw.polygon(s, OUT, pts, 8)
    # padded upper
    pygame.draw.rect(s, blue, (46, 150, 168, 290), border_radius=50)
    pygame.draw.rect(s, OUT, (46, 150, 168, 290), 8, border_radius=50)
    for y in (322, 394):
        pygame.draw.arc(s, OUT, (50, y - 36, 160, 72), 0.25, math.pi - 0.25, 7)
    # light-blue toe cap
    pts = egg_points(130, 140, 92, 114, 0.12)
    pygame.draw.polygon(s, toe, pts)
    pygame.draw.polygon(s, OUT, pts, 8)
    ell(s, toe_hi, 92, 80, 70, 32)
    ell(s, toe_hi, 66, 112, 20, 14)
    # drawstring
    for p in ([(120, 286), (106, 322), (100, 360)], [(140, 286), (154, 326), (160, 360)]):
        pygame.draw.lines(s, OUT, False, p, 8)
    for tx, ty in ((100, 360), (160, 360)):
        pygame.draw.rect(s, (240, 190, 60), (tx - 8, ty, 16, 30), border_radius=5)
        pygame.draw.rect(s, OUT, (tx - 8, ty, 16, 30), 4, border_radius=5)
    ell(s, (34, 100, 150), 130, 272, 52, 22)
    ell(s, OUT, 130, 272, 52, 22, 5)
    return s


def draw_boots(screen, st, boot_img):
    rm = st.rain_mix
    shadow = lerp_color((176, 198, 216), (42, 72, 96), rm)
    tops = []
    for i in (0, 1):
        lift, press = st.feet.lift[i], st.feet.press[i]
        top = BOOT_TOP - lift * 40 + press * 5
        tops.append(top)
        ell(screen, shadow, FOOT_X[i] + 10 + 20 * lift, top + 120, 164 * (1 + 0.1 * lift), 250)
    for i in (0, 1):
        lift, press = st.feet.lift[i], st.feet.press[i]
        scale = BOOT_SCALE * (1 + 0.10 * lift - 0.03 * press)
        angle = 4 if i == 0 else -4
        img = pygame.transform.rotozoom(boot_img, angle, scale)
        screen.blit(img, img.get_rect(midtop=(FOOT_X[i], tops[i])))


# STATE
class Feet:
    def __init__(self):
        self.press = [0.0, 0.0]
        self.lift = [0.0, 0.0]
        self.next = 0               # the boot that will land on the next step

    def step(self):
        i = self.next
        self.press[i] = 1.0
        self.next = 1 - i
        return i

    def update(self, dt, walking):
        for i in (0, 1):
            self.press[i] = max(0.0, self.press[i] - dt * 3.5)
            target = 1.0 if (walking and i == self.next) else 0.0
            self.lift[i] += (target - self.lift[i]) * min(1.0, dt * 8.0)


class Ripple:
    def __init__(self, maxr, x=0.0, y_w=0.0, obj=None, u=0.0, v=0.0, rings=2):
        self.maxr, self.x, self.y_w = maxr, x, y_w
        self.obj, self.u, self.v = obj, u, v
        self.rings = rings
        self.age = 0.0


class State:
    def __init__(self):
        rng = random.Random(5)
        self.dist = 0.0
        self.rain_mix = 0.0         # 0 = snowing, 1 = raining
        self.bob = 0.0
        self.t = 0.0
        self.feet = Feet()
        self.footprints = []        
        self.ripples = []
        self.puffs = []             # snow puffs  [x, y, vx, vy, age, life, size]
        self.droplets = []          # water splashes [x, y, vx, vy, age, life, size]
        self.flakes = [[rng.uniform(0, WIDTH), rng.uniform(0, HEIGHT), rng.uniform(40, 100),
                        rng.uniform(2, 5), rng.uniform(0, 6.28)] for _ in range(90)]
        self.rain = [[rng.uniform(0, WIDTH + 200), rng.uniform(0, HEIGHT), rng.uniform(600, 900),
                      rng.uniform(40, 110)] for _ in range(70)]


def spawn_puffs(st, x, y, n):
    for _ in range(n):
        st.puffs.append([x + random.uniform(-40, 40), y + random.uniform(-10, 10),
                         random.uniform(-70, 70), random.uniform(-90, -10),
                         0.0, random.uniform(0.35, 0.65), random.uniform(4, 10)])
    del st.puffs[:-100]


def spawn_droplets(st, x, y, n):
    for _ in range(n):
        st.droplets.append([x + random.uniform(-14, 14), y, random.uniform(-80, 80),
                            random.uniform(-260, -120), 0.0, random.uniform(0.35, 0.6),
                            random.uniform(3, 5.5)])
    del st.droplets[:-80]


def add_ripple(st, x, y_w, maxr, rings=3):
    st.ripples.append(Ripple(maxr, x=x, y_w=y_w, rings=rings))
    del st.ripples[:-80]


def update_effects(st, dt, walking):
    st.t += dt
    st.feet.update(dt, walking)

    for f in st.flakes:
        f[1] += f[2] * dt
        f[0] += math.sin(st.t * 1.5 + f[4]) * 20 * dt
        if f[1] > HEIGHT + 8:
            f[1] = -8
            f[0] = random.uniform(0, WIDTH)
    for r in st.rain:
        r[1] += r[2] * dt
        r[0] -= r[2] * 0.5 * dt
        if r[1] > HEIGHT + 20 or r[0] < -120:
            r[1] = random.uniform(-120, -20)
            r[0] = random.uniform(0, WIDTH + 260)

    for lst, g in ((st.puffs, 150), (st.droplets, 650)):
        for p in lst:
            p[4] += dt
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += g * dt
        lst[:] = [p for p in lst if p[4] < p[5]]

    for r in st.ripples:
        r.age += dt
    st.ripples = [r for r in st.ripples if r.age < 1.0]

    # ripples in every puddle
    if PUDDLES and random.random() < dt * 14:
        lo = bisect.bisect_left(PUDDLE_Y, st.dist + 0.3)
        hi = bisect.bisect_right(PUDDLE_Y, st.dist + 9.0)
        if hi > lo:
            o = PUDDLES[random.randrange(lo, hi)]
            ang = random.uniform(0, 6.28)
            rad = math.sqrt(random.random()) * 0.7
            st.ripples.append(Ripple(random.uniform(0.24, 0.42) * o[3], obj=o,
                                     u=math.cos(ang) * rad, v=math.sin(ang) * rad, rings=2))
            del st.ripples[:-80]

    # footprints: age them (for the "settle into the snow" effect), then drop old ones
    for fp in st.footprints:
        fp[3] += dt
    st.footprints = [fp for fp in st.footprints if fp[1] - st.dist > -2.0]


# DRAWING: FLOOR
def draw_floor(screen, st):
    """Fill the screen with the section you are standing on, then paint each
    section edge that is ahead of you as a wavy line."""
    y0 = st.dist + NEAR_D
    screen.fill(RAIN_BASE if is_rain(y0) else SNOW_BASE)

    b = int(math.floor(y0 / SECTION_LEN)) + 1
    while b * SECTION_LEN < st.dist + FAR_D + 4:
        yb = b * SECTION_LEN
        next_rain = is_rain(yb + 0.01)
        pts = []
        for x in range(-40, WIDTH + 61, 30):
            wave = 0.34 * math.sin(x * 0.021 + b * 1.7) + 0.18 * math.sin(x * 0.053 + b)
            pts.append((x, depth_y(yb + wave - st.dist) + st.bob))
        poly = [(pts[0][0], -200)] + pts + [(pts[-1][0], -200)]
        pygame.draw.polygon(screen, RAIN_BASE if next_rain else SNOW_BASE, poly)

        # cream snow edge on the snow side of the line
        sc = depth_scale(yb - st.dist)
        w = max(4, int(18 * sc))
        off = w / 2 if next_rain else -w / 2        # snow is below the line if rain comes next
        pygame.draw.lines(screen, SNOW_CREAM, False, [(x, y + off) for x, y in pts], w)
        b += 1


def draw_blob(screen, color, pts, cx, cy, rx, ry):
    pygame.draw.polygon(screen, color, [(cx + px * rx, cy + py * ry) for px, py in pts])


def draw_ground_object(screen, o, st):
    d = o[0] - st.dist
    if d < NEAR_D or d > FAR_D:
        return
    sx, sy, sc = to_screen(o[1], o[0], st.dist, st.bob)
    kind, size, asp, blob, seed = o[2], o[3], o[4], o[5], o[6]
    rx = size * sc
    ry = rx * FLAT * asp

    if kind == "drift":
        draw_blob(screen, SNOW_SHADE, blob, sx, sy + ry * 0.38, rx, ry)
        draw_blob(screen, SNOW_CREAM, blob, sx, sy, rx, ry)
    elif kind == "shard":
        draw_blob(screen, SNOW_CREAM, blob, sx, sy, rx * 1.6, ry * 0.8)
    elif kind == "pebble":
        ell(screen, SNOW_SHADE, sx, sy + ry * 0.3, rx * 2.2, ry * 1.6)
        ell(screen, (112, 128, 150), sx, sy, rx * 2.0, ry * 1.5)
        ell(screen, SNOW_CREAM, sx - rx * 0.1, sy - ry * 0.35, rx * 1.2, ry * 0.7)
    elif kind == "tuft":
        w = max(1, int(2.5 * sc))
        for k in range(6):
            a = -math.pi / 2 + (k - 2.5) * 0.45
            pygame.draw.line(screen, (158, 128, 92), (sx, sy),
                             (sx + math.cos(a) * rx, sy + math.sin(a) * rx * 0.9), w)
    elif kind == "twig":
        w = max(1, int(3 * sc))
        ang = (seed - 0.5) * 1.2
        ex, ey = sx + math.cos(ang) * rx, sy + math.sin(ang) * rx * FLAT
        pygame.draw.line(screen, (120, 100, 90), (sx - (ex - sx), sy - (ey - sy)), (ex, ey), w)
        pygame.draw.line(screen, (120, 100, 90), (sx, sy), (sx + rx * 0.3, sy - rx * 0.35), max(1, w - 1))
    elif kind == "tracks":
        w = max(1, int(2 * sc))
        for k in range(3):
            bx, by = sx + (k - 1) * rx * 1.1, sy + (k % 2) * rx * 0.5
            for a in (-0.7, 0.0, 0.7):
                pygame.draw.line(screen, (150, 172, 198), (bx, by),
                                 (bx + math.sin(a) * rx * 0.7, by - math.cos(a) * rx * 0.7), w)
            pygame.draw.line(screen, (150, 172, 198), (bx, by), (bx, by + rx * 0.3), w)
    elif kind == "puddle":
        if rx < 2:
            return
        ell(screen, PUDDLE, sx, sy, 2 * rx, 2 * ry)
        if size > 50:
            ell(screen, PUDDLE_HI, sx - rx * 0.12, sy - ry * 0.12, rx * 1.5, ry * 1.4)
            ell(screen, PUDDLE, sx - rx * 0.12, sy - ry * 0.12, rx * 1.3, ry * 1.2)


def draw_footprints(screen, st, print_images):
    for x, y_w, foot, age in st.footprints:
        sx, sy, sc = to_screen(x, y_w, st.dist, st.bob)
        t = min(1.0, age / 0.15)
        ease = 1 - (1 - t) ** 2
        img = scaled_print(print_images, foot, sc, 0.85 + 0.15 * ease)
        if t < 1.0:
            img = img.copy()
            img.set_alpha(int(110 + 145 * ease))
        if sy + img.get_height() / 2 < 0 or sy - img.get_height() / 2 > HEIGHT:
            continue
        screen.blit(img, img.get_rect(center=(int(sx), int(sy))))


def draw_ripples(screen, st):
    for r in st.ripples:
        if r.obj is not None:
            o = r.obj
            sx, sy, sc = to_screen(o[1], o[0], st.dist, st.bob)
            sx += r.u * o[3] * sc
            sy += r.v * o[3] * sc * FLAT * o[4]
        else:
            sx, sy, sc = to_screen(r.x, r.y_w, st.dist, st.bob)
        if sy < -40 or sy > HEIGHT + 60:
            continue
        for k in range(r.rings):
            p = r.age - k * 0.16
            if p <= 0:
                continue
            p = clamp(p)
            rad = r.maxr * p * sc
            if rad < 2:
                continue
            col = lerp_color(RING, PUDDLE, p ** 1.4)
            ell(screen, col, sx, sy, 2 * rad, rad, 2)


# DRAWING: EVERYTHING
def render(screen, overlay, st, boot_img, print_images, grain):
    rm = st.rain_mix
    draw_floor(screen, st)

    lo = bisect.bisect_left(GROUND_Y, st.dist + NEAR_D)
    hi = bisect.bisect_right(GROUND_Y, st.dist + FAR_D)
    for o in reversed(GROUND[lo:hi]):
        draw_ground_object(screen, o, st)
    draw_footprints(screen, st, print_images)
    draw_ripples(screen, st)

    screen.blit(grain, (0, 0))
    draw_boots(screen, st, boot_img)

    # weather and puffs (drawn with transparency on top)
    overlay.fill((0, 0, 0, 0))
    snow_a = int(240 * (1 - rm))
    if snow_a > 8:
        for x, y, _, size, _ in st.flakes:
            pygame.draw.circle(overlay, SNOW_CREAM + (snow_a,), (int(x), int(y)), int(size))
    rain_a = int(150 * rm)
    if rain_a > 8:
        for x, y, _, ln in st.rain:
            pygame.draw.line(overlay, (190, 222, 244, rain_a), (x, y), (x - ln * 0.5, y + ln), 2)
    for x, y, _, _, age, life, size in st.puffs:
        a = int(240 * (1 - age / life))
        pygame.draw.circle(overlay, SNOW_CREAM + (a,), (int(x), int(y)), int(size * (0.8 + age / life)))
    for x, y, _, _, age, life, size in st.droplets:
        a = int(255 * (1 - age / life))
        c = DROPLET + (a,)
        r = int(size)
        pygame.draw.circle(overlay, c, (int(x), int(y)), r)
        pygame.draw.polygon(overlay, c, [(x - r * 0.9, y - r * 0.3), (x + r * 0.9, y - r * 0.3), (x, y - r * 2.6)])
    screen.blit(overlay, (0, 0))


# MAIN
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Snow + Rain Walk")
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    clock = pygame.time.Clock()
    big_font = load_font(46)
    small_font = load_font(26)
    boot_img = build_boot()
    print_images = build_print_images()
    grain = build_grain()

    board = Board()

    # sounds
    rain_ok = start_rain_music(RAIN_SOUND_FILE)
    snow_sound = load_sound(SNOW_SOUND_FILE)
    snow_len = snow_sound.get_length() if snow_sound else 1.0
    snow_onsets = [((t - VIB_LEAD) % snow_len, level) for t, level in SNOW_FOOTSTEPS]
    snow_start = time.perf_counter()
    prev_loop_t = 0.0
    snow_idle = 0.0
    snow_needs_restart = True
    if snow_sound:
        snow_sound.set_volume(0.0)
        snow_sound.play(loops=-1)
        snow_start = time.perf_counter()

    st = State()
    walk_phase = 0.0
    step_accum = 0.0
    snow_vol = 0.0
    next_drop = 0.0
    last_button = False
    was_rain = False

    def do_step(snowy, strength=1.0):
        """One footstep: move the boots, leave a boot print or a splash."""
        i = st.feet.step()
        x_land = -X_LAND if i == 0 else X_LAND
        if snowy:
            st.footprints.append([x_land, st.dist + D_PRINT, i, 0.0])
            del st.footprints[:-30]
            spawn_puffs(st, FOOT_X[i], BOOT_TOP + 20, int(6 * strength) + 3)
        else:
            add_ripple(st, x_land, st.dist + D_PRINT, 120, rings=3)
            spawn_droplets(st, FOOT_X[i], BOOT_TOP + 30, 6)

    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        now = pygame.time.get_ticks() / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                st.dist = 0.0

        # input: forward = positive
        board.update()
        if board.connected:
            raw = board.x if JOY_AXIS == "x" else board.y
            jx = max(-1.0, min(1.0, raw / JOY_RANGE))
            if INVERT_AXIS:
                jx = -jx
            if abs(jx) < DEADZONE:
                jx = 0.0
            if board.button and not last_button:
                st.dist = 0.0
            last_button = board.button
        else:
            keys = pygame.key.get_pressed()
            fwd = keys[pygame.K_UP] or keys[pygame.K_RIGHT]
            back = keys[pygame.K_DOWN] or keys[pygame.K_LEFT]
            jx = float(fwd) - float(back)

        # movement
        old_dist = st.dist
        st.dist = clamp(st.dist + jx * SPEED * dt, 0.0, WORLD_LEN)
        moved = abs(st.dist - old_dist)
        walking = moved > 1e-6

        # which section are your boots on?
        rain_zone = is_rain(st.dist + FEET_D)
        zone_name = "RAIN" if rain_zone else "SNOW"
        walking_in_snow = (not rain_zone) and walking
        if rain_zone != was_rain:
            step_accum = 0.0
            was_rain = rain_zone
        st.rain_mix += ((1.0 if rain_zone else 0.0) - st.rain_mix) * min(1.0, dt * 3.0)

        walk_phase += moved * math.pi / STEP_LEN
        bob_target = abs(math.sin(walk_phase)) * 3 if walking else 0.0
        st.bob += (bob_target - st.bob) * min(1.0, dt * 10)

        # SNOW: footsteps follow the recording
        if snow_sound:
            loop_t = (time.perf_counter() - snow_start) % snow_len
            if walking_in_snow:
                snow_idle = 0.0
                snow_needs_restart = True
                for onset, level in snow_onsets:
                    if crossed(onset, prev_loop_t, loop_t):
                        board.send(level)
                        do_step(True, {"H": 1.4, "S": 1.0, "L": 0.6}[level])
            else:
                snow_idle += dt
                if snow_idle > 0.6 and snow_needs_restart:
                    snow_sound.stop()
                    snow_sound.play(loops=-1)
                    snow_start = time.perf_counter()
                    loop_t = 0.0
                    snow_needs_restart = False
            prev_loop_t = loop_t
        elif not rain_zone:
            step_accum += moved
            if step_accum >= STEP_LEN:
                step_accum -= STEP_LEN
                board.send("S")
                do_step(True)

        # RAIN: random taps, footsteps splash
        if rain_zone:
            if walking:
                step_accum += moved
                if step_accum >= STEP_LEN:
                    step_accum -= STEP_LEN
                    do_step(False)
            if now >= next_drop:
                roll = random.random()
                board.send("r" if roll < 0.55 else ("m" if roll < 0.85 else "R"))
                rx = random.uniform(-170, 170)
                ry = st.dist + random.uniform(0.3, 3.0)
                add_ripple(st, rx, ry, random.uniform(50, 90), rings=2)
                sx, sy, _ = to_screen(rx, ry, st.dist)
                spawn_droplets(st, sx, sy, 3)
                next_drop = now + next_drop_delay()

        # sound volumes
        if rain_ok:
            pygame.mixer.music.set_volume(st.rain_mix * RAIN_VOLUME)
        if snow_sound:
            snow_target = 1.0 if walking_in_snow else 0.0
            snow_vol += (snow_target - snow_vol) * min(1.0, dt * 8.0)
            snow_sound.set_volume(snow_vol * SNOW_VOLUME * (1 - st.rain_mix))

        # animate + draw
        update_effects(st, dt, walking)
        render(screen, overlay, st, boot_img, print_images, grain)

        # HUD
        draw_text(screen, big_font, "Rain" if rain_zone else "Snow", (20, 12))
        mode = "Joystick connected" if board.connected else "Keyboard mode (arrow keys)"
        draw_text(screen, small_font, mode, (22, 62), edge_w=2)

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()