"""
Airport Runway 3D Automated Detection Simulation - Enhanced Edition
-------------------------------------------------------------------
An automated airfield monitoring system. Perimeter towers scan for 
incoming/outgoing commercial flights and biological hazards (birds).

Controls:
  DRAG    – rotate camera 360 degrees (left mouse button)
  SCROLL  – zoom in/out
  R/F     – increase/decrease detection range
  S/D     – increase/decrease simulation speed
  SPACE   – pause / resume
  ESC     – quit
"""

import math
import random
import sys
import pygame

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WIDTH, HEIGHT = 1024, 768
FPS = 60
TITLE = "3D Airfield Detection - Multi-Runway"

# World
GROUND_Y = 0
GND_X0, GND_X1 = -250, 250
# EXTENDED GROUND: Z0 was -100, now -450 so it extends past the runway far end
GND_Z0, GND_Z1 = -450, 400

RW_HW = 25
RW_THRESH_Z = 0
RW_FAR_Z = -350


class Runway:
    """Parallel runway strip (shared length, distinct lateral center)."""
    def __init__(self, cx):
        self.cx = cx
        self.hw = RW_HW
        self.far_z = RW_FAR_Z
        self.thresh_z = RW_THRESH_Z
        self.near_z = GND_Z1 - 20
        self.z_min = self.far_z - 50
        self.z_max = GND_Z1 + 100


RUNWAYS = [Runway(-80), Runway(0), Runway(80)]

# Perimeter Towers (set back from outer runway edges at x = ±105)
TOWER_X = 210
TOWER_POSITIONS = [
    (-TOWER_X, GROUND_Y, 250), (TOWER_X, GROUND_Y, 250),
    (-TOWER_X, GROUND_Y, -50), (TOWER_X, GROUND_Y, -50),
    (-TOWER_X, GROUND_Y, -300), (TOWER_X, GROUND_Y, -300)
]
TOWER_HEIGHT = -50

# Colors (Dusk/Night Theme)
C_SKY        = (12, 16, 24)
C_GROUND     = (22, 28, 26)
C_GROUND_LN  = (32, 42, 38)
C_RUNWAY     = (35, 38, 42)
C_STRIPE     = (200, 200, 210)
C_RWY_LIGHT  = (255, 240, 150)
C_TRASH_BODY   = (42, 92, 52)
C_TRASH_BAND   = (28, 62, 36)
C_TRASH_RIM    = (22, 48, 30)
C_TRASH_LID    = (58, 118, 68)
C_TRASH_HANDLE = (120, 125, 130)
C_BIRD       = (40, 220, 150)
C_PLANE      = (240, 240, 255)
C_DETECT     = (255, 80, 40)
C_LINE_BIRD  = (255, 180, 50)
C_LINE_PLANE = (40, 160, 255)
C_HUD_TXT    = (220, 220, 220)

# ---------------------------------------------------------------------------
# 3D Camera Engine
# ---------------------------------------------------------------------------
class Camera:
    def __init__(self):
        self.rot_x = 0.5   # pitch
        self.rot_y = -0.25 # yaw
        self.scale = 1.0
        self.cx = WIDTH // 2
        self.cy = HEIGHT // 2
        self.z_off = 600

    def project(self, x, y, z):
        cy, sy = math.cos(self.rot_y), math.sin(self.rot_y)
        rx = x * cy + z * sy
        rz = -x * sy + z * cy

        cx, sx = math.cos(self.rot_x), math.sin(self.rot_x)
        ry = y * cx - rz * sx
        rz2 = y * sx + rz * cx

        fov = 800 * self.scale
        denom = rz2 + self.z_off
        
        visible = denom > 10 
        if denom < 0.1: denom = 0.1
        
        pf = fov / denom
        px = self.cx + rx * pf
        py = self.cy + ry * pf
        
        return px, py, rz2, pf, visible

# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------
class Tower:
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z
        self.pulse = random.uniform(0, math.pi * 2)
        self.radar_angle = random.uniform(0, math.pi * 2)

    def update(self):
        self.pulse += 0.04
        self.radar_angle += 0.08

    def in_range(self, entity, radius):
        tx, ty, tz = self.x, self.y + TOWER_HEIGHT, self.z
        dx = tx - entity.x
        dy = ty - entity.y
        dz = tz - entity.z
        return math.sqrt(dx*dx + dy*dy + dz*dz) <= radius

    def plane_in_range(self, plane, radius):
        """Extended detection for runway-aligned aircraft."""
        tx, ty, tz = self.x, self.y + TOWER_HEIGHT, self.z
        dx = tx - plane.x
        dy = ty - plane.y
        dz = tz - plane.z
        dist = math.sqrt(dx*dx + dy*dy + dz*dz)
        if dist <= radius * 1.35:
            return True
        on_runway = any(
            abs(plane.x - r.cx) <= r.hw + 40
            and r.far_z - 80 <= plane.z <= GND_Z1 + 480
            for r in RUNWAYS
        )
        if on_runway:
            horiz = math.sqrt(dx*dx + dz*dz)
            return horiz <= radius * 2.0 and abs(dy) <= radius * 1.25
        return False

    def detects(self, entity, radius):
        if isinstance(entity, Plane):
            return self.plane_in_range(entity, radius)
        return self.in_range(entity, radius)

class Bird:
    def __init__(self, runway=None):
        self.runway = runway or random.choice(RUNWAYS)
        side = random.choice([-1, 1])
        self.x = self.runway.cx + side * random.uniform(180, 320)
        self.y = random.uniform(-120, -20)
        self.z = random.uniform(self.runway.far_z, GND_Z1)
        self.vx = -side * random.uniform(1.2, 2.5)
        self.vy = random.uniform(-0.3, 0.3)
        self.vz = random.uniform(-0.8, 0.8)
        self.wphase = random.uniform(0, math.pi * 2)
        self.active = True
        self.trail = []

    def track_point(self):
        return self.x, self.y, self.z

    def update(self, speed_mult):
        self.x += self.vx * speed_mult
        self.y += self.vy * speed_mult
        self.z += self.vz * speed_mult
        self.wphase += 0.12 * speed_mult
        self.y += math.sin(self.wphase) * 0.15
        
        if abs(self.x) > 500 or abs(self.z) > 500:
            self.active = False

    def record_trail(self, tracked):
        if tracked:
            self.trail.append(self.track_point())
            if len(self.trail) > 14:
                self.trail.pop(0)
        elif self.trail:
            self.trail.pop(0)

class Plane:
    def __init__(self, mode, runway):
        self.mode = mode
        self.runway = runway
        self.active = True
        self.x = runway.cx
        self.trail = []
        rw = runway

        if mode == "landing":
            self.z = GND_Z1 + 450
            self.y = -150
            self.vz = -1.0
        else:
            self.z = rw.far_z - 50
            self.y = GROUND_Y - 5
            self.vz = 1.0

    def update(self, speed_mult, entities):
        rw = self.runway
        s = speed_mult * 1.5
        delta_z = self.vz * s
        new_z = self.z + delta_z

        entering_runway = (
            not plane_on_runway(self)
            and rw.z_min <= new_z <= rw.z_max
        )
        if entering_runway and opposing_traffic_on_runway(entities, self, exclude=self):
            return

        self.z = new_z

        if self.mode == "landing":
            if self.z > rw.thresh_z + 15:
                self.y += 0.31 * s
            else:
                self.y = GROUND_Y - 5
            if self.z < rw.far_z - 100:
                self.active = False
        else:
            if self.z > rw.thresh_z - 80:
                self.y -= 0.35 * s
            if self.z > GND_Z1 + 450:
                self.active = False

        self.y = min(GROUND_Y - 5, self.y)

    def track_point(self):
        fwd = 15 if self.mode == "takeoff" else -15
        pitch = 3 if (self.mode == "takeoff" and self.y < GROUND_Y - 10) else 0
        return self.x, self.y - pitch, self.z + fwd * 1.8

    def record_trail(self, tracked):
        if tracked:
            self.trail.append(self.track_point())
            if len(self.trail) > 18:
                self.trail.pop(0)
        elif self.trail:
            self.trail.pop(0)

def bird_on_runway(bird, runway):
    return (
        abs(bird.x - runway.cx) < runway.hw + 20
        and runway.far_z <= bird.z <= GND_Z1
        and bird.y < -10
    )


def runway_has_birds(entities, runway):
    for e in entities:
        if isinstance(e, Bird) and bird_on_runway(e, runway):
            return True
    return False


def plane_on_runway(plane):
    rw = plane.runway
    return rw.z_min <= plane.z <= rw.z_max


def opposing_traffic_on_runway(entities, plane, exclude=None):
    for e in entities:
        if e is exclude or not isinstance(e, Plane):
            continue
        if e.runway is plane.runway and e.mode != plane.mode and plane_on_runway(e):
            return True
    return False


def runway_blocked_for(entities, mode, runway):
    """Block spawns when opposing traffic occupies this runway."""
    for e in entities:
        if not isinstance(e, Plane) or e.runway is not runway:
            continue
        if e.mode != mode and plane_on_runway(e):
            return True
    return False


def pick_runway_for_spawn(entities, mode):
    available = [
        r for r in RUNWAYS
        if not runway_has_birds(entities, r) and not runway_blocked_for(entities, mode, r)
    ]
    return random.choice(available) if available else None

# ---------------------------------------------------------------------------
# Rendering Helpers
# ---------------------------------------------------------------------------
def draw_line_3d(surf, cam, p1, p2, color, width=1):
    x1, y1, z1, p_f1, v1 = cam.project(*p1)
    x2, y2, z2, p_f2, v2 = cam.project(*p2)
    if v1 and v2:
        pygame.draw.line(surf, color, (int(x1), int(y1)), (int(x2), int(y2)), width)

def draw_poly_3d(surf, cam, pts3d, color, outline=None):
    projected = [cam.project(*pt) for pt in pts3d]
    if all(p[4] for p in projected):
        pts2d = [(int(p[0]), int(p[1])) for p in projected]
        pygame.draw.polygon(surf, color, pts2d)
        if outline:
            pygame.draw.polygon(surf, outline, pts2d, 1)

def draw_track_reticle(surf, cam, x, y, z, color, size=8):
    """Lock-on bracket shown while an entity is being tracked."""
    px, py, _, pf, visible = cam.project(x, y, z)
    if not visible:
        return
    s = max(6, int(pf * size))
    bracket = [
        ((px - s, py - s), (px - s * 0.35, py - s)),
        ((px - s, py - s), (px - s, py - s * 0.35)),
        ((px + s, py - s), (px + s * 0.35, py - s)),
        ((px + s, py - s), (px + s, py - s * 0.35)),
        ((px - s, py + s), (px - s * 0.35, py + s)),
        ((px - s, py + s), (px - s, py + s * 0.35)),
        ((px + s, py + s), (px + s * 0.35, py + s)),
        ((px + s, py + s), (px + s, py + s * 0.35)),
    ]
    for p1, p2 in bracket:
        pygame.draw.line(surf, color, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), 2)

def draw_track_trail(surf, cam, trail, color):
    for i in range(1, len(trail)):
        fade = i / len(trail)
        c = tuple(int(ch * (0.35 + 0.65 * fade)) for ch in color[:3])
        draw_line_3d(surf, cam, trail[i - 1], trail[i], c, 1)

def draw_filled_sphere_3d(surf, cam, cx, cy, cz, r, color, segs_lat=10, segs_lon=16):
    """Draw a continuous semi-transparent detection sphere."""
    tris = []
    for lat_i in range(segs_lat):
        phi0 = (lat_i / segs_lat) * math.pi - math.pi / 2
        phi1 = ((lat_i + 1) / segs_lat) * math.pi - math.pi / 2
        for lon_i in range(segs_lon):
            theta0 = (lon_i / segs_lon) * math.pi * 2
            theta1 = ((lon_i + 1) / segs_lon) * math.pi * 2

            def sph(phi, theta):
                cp, sp = math.cos(phi), math.sin(phi)
                ct, st = math.cos(theta), math.sin(theta)
                return (cx + r * cp * ct, cy + r * sp, cz + r * cp * st)

            p00 = sph(phi0, theta0)
            p01 = sph(phi0, theta1)
            p10 = sph(phi1, theta0)
            p11 = sph(phi1, theta1)
            tris.append((p00, p10, p01))
            tris.append((p01, p10, p11))

    projected = []
    for tri in tris:
        proj = [cam.project(*p) for p in tri]
        if not any(p[4] for p in proj):
            continue
        avg_z = sum(p[2] for p in proj) / 3
        pts2d = [(p[0], p[1]) for p in proj]
        projected.append((avg_z, pts2d))

    projected.sort(key=lambda item: item[0], reverse=True)
    for _, pts in projected:
        int_pts = [(int(x), int(y)) for x, y in pts]
        pygame.draw.polygon(surf, color, int_pts)


def draw_trash_can(surf, cam, tower):
    """Perimeter sensor tower styled as a trash can."""
    x, y, z = tower.x, tower.y, tower.z
    y_bot = y
    y_band = y + TOWER_HEIGHT * 0.35
    y_rim = y + TOWER_HEIGHT * 0.92
    y_top = y + TOWER_HEIGHT
    y_lid = y_top - 5

    r_bot, r_mid, r_top = 5.5, 7.0, 8.5
    r_lid = 7.5

    def panel(x0, z0, x1, z1, x2, z2, x3, z3, y0, y1, color):
        draw_poly_3d(surf, cam, [
            (x0, y0, z0), (x1, y0, z1), (x2, y1, z2), (x3, y1, z3)
        ], color, C_TRASH_RIM)

    # Tapered body (wider at rim like a municipal bin)
    panel(x - r_bot, z - r_bot, x + r_bot, z - r_bot,
          x + r_top, z - r_top, x - r_top, z - r_top, y_bot, y_top, C_TRASH_BODY)
    panel(x - r_bot, z + r_bot, x + r_bot, z + r_bot,
          x + r_top, z + r_top, x - r_top, z + r_top, y_bot, y_top, C_TRASH_BODY)
    panel(x - r_bot, z - r_bot, x - r_bot, z + r_bot,
          x - r_top, z + r_top, x - r_top, z - r_top, y_bot, y_top, C_TRASH_BODY)
    panel(x + r_bot, z - r_bot, x + r_bot, z + r_bot,
          x + r_top, z + r_top, x + r_top, z - r_top, y_bot, y_top, C_TRASH_BODY)

    # Base band (darker stripe near bottom)
    r_band = 6.2
    panel(x - r_mid, z - r_mid, x + r_mid, z - r_mid,
          x + r_band, z - r_band, x - r_band, z - r_band, y_bot, y_band, C_TRASH_BAND)
    panel(x - r_mid, z + r_mid, x + r_mid, z + r_mid,
          x + r_band, z + r_band, x - r_band, z + r_band, y_bot, y_band, C_TRASH_BAND)
    panel(x - r_mid, z - r_mid, x - r_mid, z + r_mid,
          x - r_band, z + r_band, x - r_band, z - r_band, y_bot, y_band, C_TRASH_BAND)
    panel(x + r_mid, z - r_mid, x + r_mid, z + r_mid,
          x + r_band, z + r_band, x + r_band, z - r_band, y_bot, y_band, C_TRASH_BAND)

    # Rolled rim lip
    draw_poly_3d(surf, cam, [
        (x - r_top, y_rim, z - r_top), (x + r_top, y_rim, z - r_top),
        (x + r_top, y_top, z - r_top), (x - r_top, y_top, z - r_top)
    ], C_TRASH_RIM)
    draw_poly_3d(surf, cam, [
        (x - r_top, y_rim, z + r_top), (x + r_top, y_rim, z + r_top),
        (x + r_top, y_top, z + r_top), (x - r_top, y_top, z + r_top)
    ], C_TRASH_RIM)
    draw_poly_3d(surf, cam, [
        (x - r_top, y_rim, z - r_top), (x - r_top, y_rim, z + r_top),
        (x - r_top, y_top, z + r_top), (x - r_top, y_top, z - r_top)
    ], C_TRASH_RIM)
    draw_poly_3d(surf, cam, [
        (x + r_top, y_rim, z - r_top), (x + r_top, y_rim, z + r_top),
        (x + r_top, y_top, z + r_top), (x + r_top, y_top, z - r_top)
    ], C_TRASH_RIM)

    # Domed lid
    lid_segs = 8
    for i in range(lid_segs):
        a0 = (i / lid_segs) * math.pi * 2
        a1 = ((i + 1) / lid_segs) * math.pi * 2
        c0, s0 = math.cos(a0), math.sin(a0)
        c1, s1 = math.cos(a1), math.sin(a1)
        draw_poly_3d(surf, cam, [
            (x, y_lid, z),
            (x + c0 * r_lid, y_top, z + s0 * r_lid),
            (x + c1 * r_lid, y_top, z + s1 * r_lid),
        ], C_TRASH_LID)

    # Side handles
    for sx in (-1, 1):
        hx = x + sx * (r_top + 1.2)
        draw_line_3d(surf, cam, (hx, y_rim, z - 2), (hx, y_rim, z + 2), C_TRASH_HANDLE, 3)
        draw_line_3d(surf, cam, (hx, y_rim, z - 2), (hx, y_top - 2, z - 2), C_TRASH_HANDLE, 2)
        draw_line_3d(surf, cam, (hx, y_rim, z + 2), (hx, y_top - 2, z + 2), C_TRASH_HANDLE, 2)

    # Lid lift indicator (swinging on hinge — reads as open bin / sensor sweep)
    hx = x + math.cos(tower.radar_angle) * (r_lid + 2)
    hz = z + math.sin(tower.radar_angle) * (r_lid + 2)
    draw_line_3d(surf, cam, (x, y_lid, z), (hx, y_top - 8, hz), C_TRASH_HANDLE, 2)

# ---------------------------------------------------------------------------
# Environment Drawing
# ---------------------------------------------------------------------------
def draw_ground_and_runway(surf, cam):
    # Base ground
    draw_poly_3d(surf, cam, [
        (GND_X0, GROUND_Y, GND_Z0), (GND_X1, GROUND_Y, GND_Z0),
        (GND_X1, GROUND_Y, GND_Z1), (GND_X0, GROUND_Y, GND_Z1)
    ], C_GROUND, C_GROUND_LN)

    # Grid - updated bounds for the extended depth
    steps_x = 12
    steps_z = 24
    xs = (GND_X1 - GND_X0) / steps_x
    zs = (GND_Z1 - GND_Z0) / steps_z
    for i in range(1, steps_x):
        x = GND_X0 + i * xs
        draw_line_3d(surf, cam, (x, GROUND_Y, GND_Z0), (x, GROUND_Y, GND_Z1), C_GROUND_LN)
    for i in range(1, steps_z):
        z = GND_Z0 + i * zs
        draw_line_3d(surf, cam, (GND_X0, GROUND_Y, z), (GND_X1, GROUND_Y, z), C_GROUND_LN)

    Y = GROUND_Y + 0.5
    dash_len, dash_gap = 20, 25

    for rw in RUNWAYS:
        cx, hw = rw.cx, rw.hw
        draw_poly_3d(surf, cam, [
            (cx - hw, Y, rw.far_z), (cx + hw, Y, rw.far_z),
            (cx + hw, Y, rw.near_z), (cx - hw, Y, rw.near_z)
        ], C_RUNWAY)

        for i in range(8):
            ox = cx - hw + 3 + (i * 6)
            if i == 4:
                continue
            draw_poly_3d(surf, cam, [
                (ox, Y, rw.thresh_z - 5), (ox + 4, Y, rw.thresh_z - 5),
                (ox + 4, Y, rw.thresh_z + 15), (ox, Y, rw.thresh_z + 15)
            ], C_STRIPE)

        z_curr = rw.thresh_z - dash_gap
        while z_curr > rw.far_z + 20:
            draw_line_3d(surf, cam, (cx, Y, z_curr), (cx, Y, z_curr - dash_len), C_STRIPE, 3)
            z_curr -= (dash_len + dash_gap)

        z_light = GND_Z1 - 30
        while z_light > rw.far_z:
            for lx in [cx - hw - 2, cx + hw + 2]:
                px, py, _, pf, v = cam.project(lx, Y - 1, z_light)
                if v:
                    rad = max(1, int(pf * 3))
                    pygame.draw.circle(surf, C_RWY_LIGHT, (int(px), int(py)), rad)
            z_light -= 40

# ---------------------------------------------------------------------------
# Main Loop
# ---------------------------------------------------------------------------
def main():
    pygame.init()
    surf = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption(TITLE)
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Courier New", 14, bold=True)

    cam = Camera()
    towers = [Tower(*pos) for pos in TOWER_POSITIONS]
    entities = []
    
    radius = 205
    speed = 1   
    paused = False
    spawn_timer = 0
    dragging = False
    last_mouse = (0,0)

    while True:
        # Event Handling
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                k = event.key
                if k == pygame.K_ESCAPE: pygame.quit(); sys.exit()
                if k == pygame.K_SPACE: paused = not paused
                if k == pygame.K_r: radius = min(300, radius + 10)
                if k == pygame.K_f: radius = max(30, radius - 10)
                if k == pygame.K_s: speed = min(5, speed + 1)
                if k == pygame.K_d: speed = max(1, speed - 1)

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                dragging = True
                last_mouse = event.pos
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                dragging = False
            if event.type == pygame.MOUSEMOTION and dragging:
                dx = event.pos[0] - last_mouse[0]
                dy = event.pos[1] - last_mouse[1]
                cam.rot_y += dx * 0.005
                cam.rot_x += dy * 0.005
                cam.rot_x = max(-0.1, min(1.4, cam.rot_x))
                last_mouse = event.pos
            if event.type == pygame.MOUSEWHEEL:
                cam.scale *= 0.9 if event.y < 0 else 1.1
                cam.scale = max(0.3, min(2.5, cam.scale))

        # Automation
        if not paused:
            spawn_timer -= 1
            if spawn_timer <= 0:
                choice = random.random()
                if choice < 0.46:
                    rw = pick_runway_for_spawn(entities, "takeoff")
                    if rw:
                        entities.append(Plane("takeoff", rw))
                elif choice < 0.90:
                    rw = pick_runway_for_spawn(entities, "landing")
                    if rw:
                        entities.append(Plane("landing", rw))
                else:
                    # Bird spawn: ~8% chance, flock of 1-2 (was 20%, 2-5)
                    for _ in range(random.randint(1, 3)):
                        entities.append(Bird(random.choice(RUNWAYS)))

                spawn_timer = random.randint(90, 240)

            for e in entities:
                if isinstance(e, Plane):
                    e.update(speed, entities)
                else:
                    e.update(speed)
            entities = [e for e in entities if e.active]
            for t in towers: t.update()

        # Rendering
        surf.fill(C_SKY)
        draw_ground_and_runway(surf, cam)

        bird_dets = plane_dets = 0
        tracked_planes = set()
        tracked_birds = set()

        # Continuous detection spheres (drawn before solid geometry)
        sphere_overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        for t in towers:
            ty = t.y + TOWER_HEIGHT
            sphere_alpha = 42 + int(abs(math.sin(t.pulse)) * 18)
            draw_filled_sphere_3d(
                sphere_overlay, cam, t.x, ty, t.z, radius,
                (*C_DETECT, sphere_alpha)
            )
        surf.blit(sphere_overlay, (0, 0))

        # Sort dynamic objects by Z-depth
        def get_depth(obj):
            y_offset = TOWER_HEIGHT if isinstance(obj, Tower) else 0
            return cam.project(obj.x, obj.y + y_offset, obj.z)[2]
                
        draw_queue = sorted(towers + entities, key=get_depth, reverse=True)

        for obj in draw_queue:
            if isinstance(obj, Tower):
                draw_trash_can(surf, cam, obj)

            elif isinstance(obj, Plane):
                # Detailed Swept-wing Aircraft
                fwd = 15 if obj.mode == "takeoff" else -15
                pitch = 3 if (obj.mode == "takeoff" and obj.y < GROUND_Y - 10) else 0
                
                # Fuselage
                nose = (obj.x, obj.y - pitch, obj.z + fwd * 1.8)
                tail = (obj.x, obj.y + pitch, obj.z - fwd * 1.5)
                draw_line_3d(surf, cam, nose, tail, C_PLANE, 6)
                
                # Main Wings (Swept back)
                lw_tip = (obj.x - 30, obj.y, obj.z - fwd * 0.4)
                rw_tip = (obj.x + 30, obj.y, obj.z - fwd * 0.4)
                w_root = (obj.x, obj.y, obj.z + fwd * 0.5)
                draw_line_3d(surf, cam, w_root, lw_tip, C_PLANE, 4)
                draw_line_3d(surf, cam, w_root, rw_tip, C_PLANE, 4)
                
                # Tail Wings & Vertical Stabilizer
                lt = (obj.x - 12, obj.y + pitch, obj.z - fwd * 1.4)
                rt = (obj.x + 12, obj.y + pitch, obj.z - fwd * 1.4)
                v_tail = (obj.x, obj.y - 12 + pitch, obj.z - fwd * 1.7)
                draw_line_3d(surf, cam, tail, lt, C_PLANE, 2)
                draw_line_3d(surf, cam, tail, rt, C_PLANE, 2)
                draw_line_3d(surf, cam, tail, v_tail, C_PLANE, 3)
                
            elif isinstance(obj, Bird):
                px, py, pz, pf, v = cam.project(obj.x, obj.y, obj.z)
                if v:
                    sz = max(2, pf * 4.5)
                    wing = math.sin(obj.wphase) * sz
                    pygame.draw.line(surf, C_BIRD, (px-sz, py-wing), (px, py), 2)
                    pygame.draw.line(surf, C_BIRD, (px, py), (px+sz, py-wing), 2)

        # Tracking Lines
        for t in towers:
            tx, ty, tz = t.x, t.y + TOWER_HEIGHT, t.z
            for e in entities:
                if not t.detects(e, radius):
                    continue
                tx_pt, ty_pt, tz_pt = e.track_point()
                if isinstance(e, Plane):
                    plane_dets += 1
                    tracked_planes.add(id(e))
                    draw_line_3d(surf, cam, (tx, ty, tz), (tx_pt, ty_pt, tz_pt), C_LINE_PLANE, 2)
                elif isinstance(e, Bird):
                    bird_dets += 1
                    tracked_birds.add(id(e))
                    draw_line_3d(surf, cam, (tx, ty, tz), (tx_pt, ty_pt, tz_pt), C_LINE_BIRD, 1)

        for e in entities:
            tracked = id(e) in (tracked_planes if isinstance(e, Plane) else tracked_birds)
            e.record_trail(tracked)
            if not tracked:
                continue
            tx_pt, ty_pt, tz_pt = e.track_point()
            if isinstance(e, Plane):
                draw_track_trail(surf, cam, e.trail, C_LINE_PLANE)
                draw_track_reticle(surf, cam, tx_pt, ty_pt, tz_pt, C_LINE_PLANE, size=10)
            elif isinstance(e, Bird):
                draw_track_trail(surf, cam, e.trail, C_LINE_BIRD)
                draw_track_reticle(surf, cam, tx_pt, ty_pt, tz_pt, C_LINE_BIRD, size=6)

        # HUD
        hud_bg = pygame.Surface((250, 176), pygame.SRCALPHA)
        hud_bg.fill((15, 20, 25, 210))
        surf.blit(hud_bg, (15, 15))
        
        texts = [
            f"Runways:        {len(RUNWAYS)}",
            f"Active Planes:  {sum(1 for e in entities if isinstance(e, Plane))}",
            f"Active Birds:   {sum(1 for e in entities if isinstance(e, Bird))}",
            f"Tracked Planes: {len(tracked_planes)}",
            f"Tracked Birds:  {len(tracked_birds)}",
            f"Plane Detects:  {plane_dets}",
            f"Bird Detects:   {bird_dets}",
            f"Range (R/F):    {radius}m",
            f"Speed (S/D):    {speed}x"
        ]
        for i, text in enumerate(texts):
            surf.blit(font.render(text, True, C_HUD_TXT), (25, 25 + i * 18))

        pygame.display.flip()
        clock.tick(FPS)

if __name__ == "__main__":
    main()
