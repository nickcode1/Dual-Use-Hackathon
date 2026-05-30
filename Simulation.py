"""
Airport Runway 3D Automated Detection Simulation
-----------------------------------------
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
TITLE = "3D Airfield Automated Detection"

# World
GROUND_Y = 0
GND_X0, GND_X1 = -250, 250
GND_Z0, GND_Z1 = -100, 300

RW_CX = 0
RW_HW = 20
RW_THRESH_Z = 0
RW_FAR_Z = -300

# Perimeter Towers (Left and Right flanks)
TOWER_POSITIONS = [
    (-120, GROUND_Y, 200), (120, GROUND_Y, 200),
    (-120, GROUND_Y, -50), (120, GROUND_Y, -50),
    (-120, GROUND_Y, -280), (120, GROUND_Y, -280)
]
TOWER_HEIGHT = -40  # Negative is UP in this coordinate system

# Colors
C_SKY        = (20, 25, 35)      # Darker sky for better visibility of tracking lines
C_GROUND     = (35, 45, 40)
C_GROUND_LN  = (50, 65, 55)
C_RUNWAY     = (45, 45, 50)
C_STRIPE     = (200, 200, 200)
C_TOWER      = (150, 150, 160)
C_BIRD       = (40, 200, 150)
C_PLANE      = (220, 220, 230)
C_DETECT     = (255, 100, 50)
C_LINE_BIRD  = (255, 150, 50)
C_LINE_PLANE = (50, 180, 255)
C_HUD_TXT    = (200, 200, 200)

# ---------------------------------------------------------------------------
# 3D Camera Engine
# ---------------------------------------------------------------------------
class Camera:
    def __init__(self):
        self.rot_x = 0.6   # pitch
        self.rot_y = -0.3  # yaw
        self.scale = 1.0
        self.cx = WIDTH // 2
        self.cy = HEIGHT // 2
        self.z_off = 500   # Distance of camera from center

    def project(self, x, y, z):
        # Rotate around Y axis (Yaw)
        cy, sy = math.cos(self.rot_y), math.sin(self.rot_y)
        rx = x * cy + z * sy
        rz = -x * sy + z * cy

        # Rotate around X axis (Pitch)
        cx, sx = math.cos(self.rot_x), math.sin(self.rot_x)
        ry = y * cx - rz * sx
        rz2 = y * sx + rz * cx

        # Perspective division
        fov = 700 * self.scale
        denom = rz2 + self.z_off
        
        # Prevent division by zero or negative rendering (behind camera)
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

    def update(self):
        self.pulse += 0.05

    def in_range(self, entity, radius):
        # Distance measured from the top of the tower
        dx = self.x - entity.x
        dy = (self.y + TOWER_HEIGHT) - entity.y
        dz = self.z - entity.z
        return math.sqrt(dx*dx + dy*dy + dz*dz) <= radius

class Bird:
    def __init__(self):
        # Spawn randomly off-screen left or right
        side = random.choice([-1, 1])
        self.x = side * 400
        self.y = random.uniform(-100, -20)
        self.z = random.uniform(-200, 200)
        self.vx = -side * random.uniform(1.5, 3.0)
        self.vy = random.uniform(-0.5, 0.5)
        self.vz = random.uniform(-1.0, 1.0)
        self.wphase = random.uniform(0, math.pi * 2)
        self.active = True

    def update(self, speed_mult):
        self.x += self.vx * speed_mult
        self.y += self.vy * speed_mult
        self.z += self.vz * speed_mult
        self.wphase += 0.15 * speed_mult
        
        # Flocking bob
        self.y += math.sin(self.wphase) * 0.2
        
        # Despawn if out of bounds
        if abs(self.x) > 500 or abs(self.z) > 500:
            self.active = False

class Plane:
    def __init__(self, mode):
        self.mode = mode
        self.active = True
        self.x = RW_CX
        
        if mode == "landing":
            self.z = GND_Z1 + 400
            self.y = -150
            self.vz = -2.5
        else: # takeoff
            self.z = RW_FAR_Z - 50
            self.y = GROUND_Y - 4
            self.vz = 2.5

    def update(self, speed_mult):
        s = speed_mult * 1.5
        self.z += self.vz * s

        if self.mode == "landing":
            # Glide slope
            if self.z > RW_THRESH_Z + 20:
                self.y += 0.6 * s
            else:
                self.y = GROUND_Y - 4 # Touchdown
            
            if self.z < RW_FAR_Z - 100:
                self.active = False
        else:
            # Takeoff
            if self.z > RW_THRESH_Z - 100:
                self.y -= 0.8 * s # Pitch up
                
            if self.z > GND_Z1 + 400:
                self.active = False
                
        self.y = min(GROUND_Y - 4, self.y)

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
    if all(p[4] for p in projected): # if all vertices visible
        pts2d = [(int(p[0]), int(p[1])) for p in projected]
        pygame.draw.polygon(surf, color, pts2d)
        if outline:
            pygame.draw.polygon(surf, outline, pts2d, 1)

def draw_wire_sphere(surf, cam, cx, cy, cz, r, color, segs=16):
    for i in range(segs):
        angle = (i / segs) * math.pi * 2
        # Horizontal circle
        p1 = (cx + math.cos(angle)*r, cy, cz + math.sin(angle)*r)
        p2 = (cx + math.cos(angle + 0.5)*r, cy, cz + math.sin(angle + 0.5)*r)
        draw_line_3d(surf, cam, p1, p2, color, 1)

# ---------------------------------------------------------------------------
# Environment Drawing
# ---------------------------------------------------------------------------
def draw_ground_and_runway(surf, cam):
    # Base ground
    corners = [
        (GND_X0, GROUND_Y, GND_Z0), (GND_X1, GROUND_Y, GND_Z0),
        (GND_X1, GROUND_Y, GND_Z1), (GND_X0, GROUND_Y, GND_Z1),
    ]
    draw_poly_3d(surf, cam, corners, C_GROUND, C_GROUND_LN)

    # Grid
    steps = 10
    xs = (GND_X1 - GND_X0) / steps
    zs = (GND_Z1 - GND_Z0) / steps
    for i in range(1, steps):
        x, z = GND_X0 + i * xs, GND_Z0 + i * zs
        draw_line_3d(surf, cam, (x, GROUND_Y, GND_Z0), (x, GROUND_Y, GND_Z1), C_GROUND_LN)
        draw_line_3d(surf, cam, (GND_X0, GROUND_Y, z), (GND_X1, GROUND_Y, z), C_GROUND_LN)

    # Runway
    Y = GROUND_Y + 0.5
    cx, hw = RW_CX, RW_HW
    rw_pts = [
        (cx - hw, Y, RW_FAR_Z), (cx + hw, Y, RW_FAR_Z),
        (cx + hw, Y, GND_Z1 - 20), (cx - hw, Y, GND_Z1 - 20)
    ]
    draw_poly_3d(surf, cam, rw_pts, C_RUNWAY)
    
    # Threshold Line
    draw_line_3d(surf, cam, (cx - hw, Y, RW_THRESH_Z), (cx + hw, Y, RW_THRESH_Z), (255, 200, 50), 3)

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
    
    # State
    radius = 120
    speed = 2
    paused = False
    spawn_timer = 0
    dragging = False
    last_mouse = (0,0)

    while True:
        # --- Event Handling ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            
            if event.type == pygame.KEYDOWN:
                k = event.key
                if k == pygame.K_ESCAPE: pygame.quit(); sys.exit()
                if k == pygame.K_SPACE: paused = not paused
                if k == pygame.K_r: radius = min(250, radius + 10)
                if k == pygame.K_f: radius = max(30, radius - 10)
                if k == pygame.K_s: speed = min(5, speed + 1)
                if k == pygame.K_d: speed = max(1, speed - 1)

            # Camera Orbit Controls
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
                cam.rot_x = max(-0.1, min(1.4, cam.rot_x)) # Clamp pitch
                last_mouse = event.pos
            if event.type == pygame.MOUSEWHEEL:
                cam.scale *= 0.9 if event.y < 0 else 1.1
                cam.scale = max(0.3, min(2.5, cam.scale))

        # --- Automation & Logic ---
        if not paused:
            spawn_timer -= 1
            if spawn_timer <= 0:
                choice = random.random()
                if choice < 0.25:
                    entities.append(Plane("takeoff"))
                elif choice < 0.5:
                    entities.append(Plane("landing"))
                else:
                    # Spawn a flock of birds
                    flock_size = random.randint(3, 8)
                    for _ in range(flock_size):
                        entities.append(Bird())
                spawn_timer = random.randint(60, 180) # Next event in 1-3 seconds

            for e in entities:
                e.update(speed)
            
            # Clean up inactive
            entities = [e for e in entities if e.active]
            
            for t in towers:
                t.update()

        # --- Rendering ---
        surf.fill(C_SKY)
        draw_ground_and_runway(surf, cam)

        bird_dets = 0
        plane_dets = 0

        # Sort all dynamic elements by Z-depth relative to camera
        # Calculate distance to camera for sorting
        def get_depth(obj):
            if isinstance(obj, Tower):
                _, _, z, _, _ = cam.project(obj.x, obj.y + TOWER_HEIGHT, obj.z)
                return z
            else:
                _, _, z, _, _ = cam.project(obj.x, obj.y, obj.z)
                return z
                
        draw_queue = sorted(towers + entities, key=get_depth, reverse=True)

        for obj in draw_queue:
            if isinstance(obj, Tower):
                # Draw pole
                draw_line_3d(surf, cam, (obj.x, obj.y, obj.z), (obj.x, obj.y + TOWER_HEIGHT, obj.z), C_TOWER, 3)
                # Draw sphere
                pulse_r = radius + math.sin(obj.pulse) * 5
                alpha_color = (*C_DETECT, max(50, int(abs(math.sin(obj.pulse))*150)))
                draw_wire_sphere(surf, cam, obj.x, obj.y + TOWER_HEIGHT, obj.z, pulse_r, alpha_color)
                
            elif isinstance(obj, Plane):
                # Draw Plane
                fwd = 15 if obj.mode == "takeoff" else -15
                nose = (obj.x, obj.y, obj.z + fwd)
                tail = (obj.x, obj.y, obj.z - fwd)
                lw = (obj.x - 20, obj.y, obj.z)
                rw = (obj.x + 20, obj.y, obj.z)
                vtail = (obj.x, obj.y - 10, obj.z - fwd)
                
                draw_line_3d(surf, cam, nose, tail, C_PLANE, 5)
                draw_line_3d(surf, cam, lw, rw, C_PLANE, 4)
                draw_line_3d(surf, cam, tail, vtail, C_PLANE, 3)
                
            elif isinstance(obj, Bird):
                px, py, pz, pf, v = cam.project(obj.x, obj.y, obj.z)
                if v:
                    sz = max(2, pf * 4)
                    wing = math.sin(obj.wphase) * sz
                    pygame.draw.line(surf, C_BIRD, (px-sz, py-wing), (px, py), 2)
                    pygame.draw.line(surf, C_BIRD, (px, py), (px+sz, py-wing), 2)

        # Draw Tracking Lines (rendered last so they overlay)
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

        # --- HUD ---
        hud_bg = pygame.Surface((220, 140), pygame.SRCALPHA)
        hud_bg.fill((20, 20, 20, 200))
        surf.blit(hud_bg, (10, 10))
        
        texts = [
            f"Active Planes: {sum(1 for e in entities if isinstance(e, Plane))}",
            f"Active Birds:  {sum(1 for e in entities if isinstance(e, Bird))}",
            f"Plane Detects: {plane_dets}",
            f"Bird Detects:  {bird_dets}",
            f"Range (R/F):   {radius}m",
            f"Speed (S/D):   {speed}x"
        ]
        
        for i, text in enumerate(texts):
            img = font.render(text, True, C_HUD_TXT)
            surf.blit(img, (20, 20 + i * 18))

        pygame.display.flip()
        clock.tick(FPS)

if __name__ == "__main__":
    main()