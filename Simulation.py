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
TITLE = "3D Airfield Detection - Enhanced (Spheres & Extended Ground)"

# World
GROUND_Y = 0
GND_X0, GND_X1 = -250, 250
# EXTENDED GROUND: Z0 was -100, now -450 so it extends past the runway far end
GND_Z0, GND_Z1 = -450, 400

RW_CX = 0
RW_HW = 25
RW_THRESH_Z = 0
RW_FAR_Z = -350

# Perimeter Towers
TOWER_POSITIONS = [
    (-140, GROUND_Y, 250), (140, GROUND_Y, 250),
    (-140, GROUND_Y, -50), (140, GROUND_Y, -50),
    (-140, GROUND_Y, -300), (140, GROUND_Y, -300)
]
TOWER_HEIGHT = -50

# Colors (Dusk/Night Theme)
C_SKY        = (12, 16, 24)
C_GROUND     = (22, 28, 26)
C_GROUND_LN  = (32, 42, 38)
C_RUNWAY     = (35, 38, 42)
C_STRIPE     = (200, 200, 210)
C_RWY_LIGHT  = (255, 240, 150)
C_TOWER_BASE = (80, 85, 95)
C_TOWER_CAB  = (180, 180, 190)
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
        dx = self.x - entity.x
        dy = (self.y + TOWER_HEIGHT) - entity.y
        dz = self.z - entity.z
        return math.sqrt(dx*dx + dy*dy + dz*dz) <= radius

class Bird:
    def __init__(self):
        side = random.choice([-1, 1])
        self.x = side * 400
        self.y = random.uniform(-120, -20)
        self.z = random.uniform(-350, 350)
        self.vx = -side * random.uniform(1.2, 2.5)
        self.vy = random.uniform(-0.3, 0.3)
        self.vz = random.uniform(-0.8, 0.8)
        self.wphase = random.uniform(0, math.pi * 2)
        self.active = True

    def update(self, speed_mult):
        self.x += self.vx * speed_mult
        self.y += self.vy * speed_mult
        self.z += self.vz * speed_mult
        self.wphase += 0.12 * speed_mult
        self.y += math.sin(self.wphase) * 0.15
        
        if abs(self.x) > 500 or abs(self.z) > 500:
            self.active = False

class Plane:
    def __init__(self, mode):
        self.mode = mode
        self.active = True
        self.x = RW_CX
        
        if mode == "landing":
            self.z = GND_Z1 + 450
            self.y = -150
            self.vz = -1.0 
        else:
            self.z = RW_FAR_Z - 50
            self.y = GROUND_Y - 5
            self.vz = 1.0

    def update(self, speed_mult):
        s = speed_mult * 1.5
        self.z += self.vz * s

        if self.mode == "landing":
            if self.z > RW_THRESH_Z + 15:
                self.y += 0.31 * s 
            else:
                self.y = GROUND_Y - 5 
            if self.z < RW_FAR_Z - 100:
                self.active = False
        else:
            if self.z > RW_THRESH_Z - 80:
                self.y -= 0.35 * s 
            if self.z > GND_Z1 + 450:
                self.active = False
                
        self.y = min(GROUND_Y - 5, self.y)

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

def draw_sphere_3d(surf, cam, cx, cy, cz, r, color, width=1, segs=24):
    """Draws a 3-axis wireframe sphere."""
    pts_xz, pts_xy, pts_yz = [], [], []
    for i in range(segs + 1):
        angle = (i / segs) * math.pi * 2
        c, s = math.cos(angle), math.sin(angle)
        pts_xz.append((cx + c*r, cy, cz + s*r))          # Horizontal ring
        pts_xy.append((cx + c*r, cy + s*r, cz))          # Vertical facing camera
        pts_yz.append((cx, cy + c*r, cz + s*r))          # Vertical side profile
        
    for i in range(segs):
        draw_line_3d(surf, cam, pts_xz[i], pts_xz[i+1], color, width)
        draw_line_3d(surf, cam, pts_xy[i], pts_xy[i+1], color, width)
        draw_line_3d(surf, cam, pts_yz[i], pts_yz[i+1], color, width)

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

    # Runway Base
    Y = GROUND_Y + 0.5
    cx, hw = RW_CX, RW_HW
    draw_poly_3d(surf, cam, [
        (cx - hw, Y, RW_FAR_Z), (cx + hw, Y, RW_FAR_Z),
        (cx + hw, Y, GND_Z1 - 20), (cx - hw, Y, GND_Z1 - 20)
    ], C_RUNWAY)

    # Threshold markings (Piano Keys)
    for i in range(8):
        ox = cx - hw + 3 + (i * 6)
        if i == 4: continue # gap in middle
        draw_poly_3d(surf, cam, [
            (ox, Y, RW_THRESH_Z - 5), (ox + 4, Y, RW_THRESH_Z - 5),
            (ox + 4, Y, RW_THRESH_Z + 15), (ox, Y, RW_THRESH_Z + 15)
        ], C_STRIPE)
        
    # Centerline dashes
    dash_len, dash_gap = 20, 25
    z_curr = RW_THRESH_Z - dash_gap
    while z_curr > RW_FAR_Z + 20:
        draw_line_3d(surf, cam, (cx, Y, z_curr), (cx, Y, z_curr - dash_len), C_STRIPE, 3)
        z_curr -= (dash_len + dash_gap)

    # Runway Edge Lights
    z_light = GND_Z1 - 30
    while z_light > RW_FAR_Z:
        for lx in [cx - hw - 2, cx + hw + 2]:
            px, py, _, pf, v = cam.project(lx, Y-1, z_light)
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
    
    radius = 140
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
                if choice < 0.25:
                    entities.append(Plane("takeoff"))
                elif choice < 0.5:
                    entities.append(Plane("landing"))
                else:
                    for _ in range(random.randint(4, 10)):
                        entities.append(Bird())
                spawn_timer = random.randint(90, 240)

            for e in entities: e.update(speed)
            entities = [e for e in entities if e.active]
            for t in towers: t.update()

        # Rendering
        surf.fill(C_SKY)
        draw_ground_and_runway(surf, cam)

        bird_dets = plane_dets = 0

        # Sort dynamic objects by Z-depth
        def get_depth(obj):
            y_offset = TOWER_HEIGHT if isinstance(obj, Tower) else 0
            return cam.project(obj.x, obj.y + y_offset, obj.z)[2]
                
        draw_queue = sorted(towers + entities, key=get_depth, reverse=True)

        for obj in draw_queue:
            if isinstance(obj, Tower):
                # Tapered Base
                draw_poly_3d(surf, cam, [
                    (obj.x-4, obj.y, obj.z-4), (obj.x+4, obj.y, obj.z-4),
                    (obj.x+2, obj.y+TOWER_HEIGHT, obj.z-2), (obj.x-2, obj.y+TOWER_HEIGHT, obj.z-2)
                ], C_TOWER_BASE)
                draw_poly_3d(surf, cam, [
                    (obj.x-4, obj.y, obj.z+4), (obj.x+4, obj.y, obj.z+4),
                    (obj.x+2, obj.y+TOWER_HEIGHT, obj.z+2), (obj.x-2, obj.y+TOWER_HEIGHT, obj.z+2)
                ], C_TOWER_BASE)
                
                # Cabin & Radar
                ty = obj.y + TOWER_HEIGHT
                draw_poly_3d(surf, cam, [
                    (obj.x-6, ty, obj.z-6), (obj.x+6, ty, obj.z-6),
                    (obj.x+6, ty, obj.z+6), (obj.x-6, ty, obj.z+6)
                ], C_TOWER_CAB)
                
                rx = obj.x + math.cos(obj.radar_angle) * 8
                rz = obj.z + math.sin(obj.radar_angle) * 8
                draw_line_3d(surf, cam, (obj.x, ty-2, obj.z), (rx, ty-6, rz), (200, 200, 200), 2)

                # Detection Sphere (Now fully 3D)
                pulse_r = radius + math.sin(obj.pulse) * 5
                alpha_c = (*C_DETECT, max(30, int(abs(math.sin(obj.pulse))*120)))
                draw_sphere_3d(surf, cam, obj.x, ty, obj.z, pulse_r, alpha_c, 1, 24)
                
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
                if t.in_range(e, radius):
                    if isinstance(e, Plane):
                        plane_dets += 1
                        draw_line_3d(surf, cam, (tx, ty, tz), (e.x, e.y, e.z), C_LINE_PLANE, 2)
                    else:
                        bird_dets += 1
                        draw_line_3d(surf, cam, (tx, ty, tz), (e.x, e.y, e.z), C_LINE_BIRD, 1)

        # HUD
        hud_bg = pygame.Surface((230, 140), pygame.SRCALPHA)
        hud_bg.fill((15, 20, 25, 210))
        surf.blit(hud_bg, (15, 15))
        
        texts = [
            f"Active Planes: {sum(1 for e in entities if isinstance(e, Plane))}",
            f"Active Birds:  {sum(1 for e in entities if isinstance(e, Bird))}",
            f"Plane Detects: {plane_dets}",
            f"Bird Detects:  {bird_dets}",
            f"Range (R/F):   {radius}m",
            f"Speed (S/D):   {speed}x"
        ]
        for i, text in enumerate(texts):
            surf.blit(font.render(text, True, C_HUD_TXT), (25, 25 + i * 18))

        pygame.display.flip()
        clock.tick(FPS)

if __name__ == "__main__":
    main()