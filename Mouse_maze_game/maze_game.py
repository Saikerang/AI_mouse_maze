"""
maze_game.py — Animated mouse maze game (pygame)

Run:
    python maze_game.py

Controls:
    SPACE   — pause / resume
    R       — restart immediately
    +/-     — speed up / slow down mouse
    ESC/Q   — quit
"""

import sys
import time
import math
import pygame

from maze_generator import (
    generate_perfect_maze,
    add_extra_passages,
    ROWS, COLS, TARGET_PATHS, RANDOM_SEED,
)
from mouse_algorithm import SmellGuidedDFS, MOVE_DELTA

# ─── Game settings ────────────────────────────────────────────────────────────
START         = (0, 0)
FINISH        = (ROWS - 1, COLS - 1)
TIME_LIMIT    = 180          # seconds (3 minutes)
STEP_DELAY    = 0.10         # seconds between steps (default speed)
STEP_DELTA    = 0.02         # how much +/- changes the delay
STEP_MIN      = 0.02
STEP_MAX      = 0.50
TRAIL_LEN     = 60           # max cells shown in trail
TRAIL_FADE    = True         # fade older trail cells

# ─── Display settings ─────────────────────────────────────────────────────────
CELL          = 20           # display pixels per maze cell
PANEL_W       = 220          # right-side info panel width
MARGIN        = 0
WIN_W         = COLS * CELL + PANEL_W
WIN_H         = ROWS * CELL + 40        # +40 for bottom bar

# ─── Colours ──────────────────────────────────────────────────────────────────
C_BG          = (15,  17,  35)
C_WALL        = (220, 225, 240)
C_CELL        = (22,  25,  50)
C_START       = (46,  204, 113)
C_FINISH      = (52,  152, 219)
C_CHEESE      = (255, 215,   0)
C_MOUSE_LIVE  = (255, 160,  40)
C_MOUSE_DEAD  = (231,  76,  60)
C_MOUSE_WIN   = (255, 215,   0)
C_TRAIL_BASE  = (255, 140,  40)
C_PANEL_BG    = (10,  12,  28)
C_TEXT        = (200, 210, 230)
C_DIM         = (100, 110, 130)
C_TIMER_OK    = (100, 220, 150)
C_TIMER_WARN  = (255, 200,  50)
C_TIMER_CRIT  = (231,  76,  60)
C_BAR_BG      = (40,  45,  75)
C_OVERLAY_BG  = (15,  17,  35, 210)


# ─── Helper ───────────────────────────────────────────────────────────────────
def cell_rect(r: int, c: int) -> pygame.Rect:
    """Screen rect for maze cell (r, c)."""
    return pygame.Rect(c * CELL, r * CELL, CELL, CELL)


def lerp_color(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


# ─── Pre-render the static maze surface ───────────────────────────────────────
def build_maze_surface(walls) -> pygame.Surface:
    surf = pygame.Surface((COLS * CELL, ROWS * CELL))
    surf.fill(C_CELL)

    # Cell floors (subtle gradient not needed — solid fill is clean)
    for r in range(ROWS):
        for c in range(COLS):
            pygame.draw.rect(surf, C_CELL, cell_rect(r, c))

    # Start / finish background tint
    pygame.draw.rect(surf, (20, 60, 35), cell_rect(*START))
    pygame.draw.rect(surf, (20, 40, 70), cell_rect(*FINISH))

    # Walls
    for r in range(ROWS):
        for c in range(COLS):
            x, y = c * CELL, r * CELL
            if 'N' in walls[r][c]:
                pygame.draw.line(surf, C_WALL, (x, y),           (x + CELL, y),      1)
            if 'S' in walls[r][c]:
                pygame.draw.line(surf, C_WALL, (x, y + CELL),    (x + CELL, y + CELL), 1)
            if 'E' in walls[r][c]:
                pygame.draw.line(surf, C_WALL, (x + CELL, y),    (x + CELL, y + CELL), 1)
            if 'W' in walls[r][c]:
                pygame.draw.line(surf, C_WALL, (x, y),           (x, y + CELL),      1)

    # Outer border
    pygame.draw.rect(surf, C_WALL, (0, 0, COLS * CELL, ROWS * CELL), 2)

    # Start label
    font_sm = pygame.font.Font(None, 13)
    surf.blit(font_sm.render('S', True, C_START),
              (START[1] * CELL + 4, START[0] * CELL + 3))
    surf.blit(font_sm.render('F', True, C_FINISH),
              (FINISH[1] * CELL + 4, FINISH[0] * CELL + 3))

    return surf


# ─── Game state ───────────────────────────────────────────────────────────────
class GameState:
    def __init__(self, walls, algorithm):
        self.walls      = walls
        self.algo       = algorithm
        self.run        = 0
        self.paused     = False
        self._pause_ts  = None          # timestamp when pause began
        self.step_delay = STEP_DELAY
        self._reset_run(waiting=True)   # first launch always waits

    def _reset_run(self, waiting=False):
        self.run      += 1
        self.pos       = START
        self.trail: list[tuple[int, int]] = [START]
        self.start_ts  = None
        self.steps     = 0
        self.status    = 'waiting' if waiting else 'playing'   # 'waiting' | 'playing' | 'won' | 'died'
        self.end_ts    = None
        self.paused    = False        # always start active
        self._pause_ts = None
        self.algo.reset()

    def begin(self):
        """Transition from waiting → playing and start the timer."""
        if self.status == 'waiting':
            self.status   = 'playing'
            self.start_ts = time.time()

    # ── Queries ───────────────────────────────────────────────────────────────
    def elapsed(self) -> float:
        if self.start_ts is None:
            return 0.0
        return time.time() - self.start_ts

    def remaining(self) -> float:
        if self.start_ts is None:
            return float(TIME_LIMIT)
        return max(0.0, TIME_LIMIT - self.elapsed())

    def available_moves(self):
        r, c = self.pos
        return [d for d in ('N', 'S', 'E', 'W') if d not in self.walls[r][c]]

    def smell_hint(self):
        fr, fc = FINISH
        r,  c  = self.pos
        return (fr - r, fc - c)

    # ── Advance one step ──────────────────────────────────────────────────────
    def tick(self):
        if self.status != 'playing' or self.paused:
            return

        if self.remaining() <= 0:
            self.status = 'died'
            self.end_ts = time.time()
            return

        moves     = self.available_moves()
        direction = self.algo.decide(self.pos, moves, self.smell_hint())
        if direction:
            dr, dc   = MOVE_DELTA[direction]
            self.pos = (self.pos[0] + dr, self.pos[1] + dc)
            self.steps += 1
            self.trail.append(self.pos)
            if len(self.trail) > TRAIL_LEN:
                self.trail.pop(0)

        if self.pos == FINISH:
            self.status = 'won'
            self.end_ts = time.time()

    def restart(self):
        self._reset_run(waiting=True)


# ─── Rendering ────────────────────────────────────────────────────────────────
class Renderer:
    def __init__(self, screen: pygame.Surface, maze_surf: pygame.Surface):
        self.screen    = screen
        self.maze_surf = maze_surf
        self.font_lg   = pygame.font.Font(None, 22)
        self.font_md   = pygame.font.Font(None, 17)
        self.font_sm   = pygame.font.Font(None, 14)
        self.font_xl   = pygame.font.Font(None, 36)

    def draw(self, gs: GameState):
        self.screen.fill(C_BG)

        # Static maze
        self.screen.blit(self.maze_surf, (0, 0))

        # Trail
        self._draw_trail(gs)

        # Cheese
        self._draw_cheese()

        # Mouse
        self._draw_mouse(gs)

        # Start marker circle
        self._draw_start()

        # Right panel
        self._draw_panel(gs)

        # Bottom bar
        self._draw_bottom_bar(gs)

        # Overlay (waiting / won / died / paused)
        if gs.status == 'waiting':
            self._draw_overlay_waiting(gs)
        elif gs.status == 'won':
            self._draw_overlay_won(gs)
        elif gs.status == 'died':
            self._draw_overlay_died(gs)
        elif gs.paused:
            self._draw_overlay_paused()

        pygame.display.flip()

    # ── Sub-renderers ─────────────────────────────────────────────────────────
    def _draw_trail(self, gs: GameState):
        n = len(gs.trail)
        for i, (r, c) in enumerate(gs.trail[:-1]):   # skip last (= current pos)
            t     = i / max(n - 1, 1)
            alpha = int(30 + 140 * t)
            color = lerp_color((30, 30, 60), C_TRAIL_BASE, t)
            pad   = CELL // 2 - max(1, int((CELL // 2 - 2) * t))
            rect  = cell_rect(r, c).inflate(-pad * 2, -pad * 2)
            s     = pygame.Surface(rect.size, pygame.SRCALPHA)
            s.fill((*color, alpha))
            self.screen.blit(s, rect.topleft)

    def _draw_cheese(self):
        r, c  = FINISH
        cx    = c * CELL + CELL // 2
        cy    = r * CELL + CELL // 2
        rad   = CELL // 2 - 2
        pygame.draw.circle(self.screen, C_CHEESE, (cx, cy), rad)
        pygame.draw.circle(self.screen, (200, 160, 0), (cx, cy), rad, 1)
        # small holes on cheese
        for hx, hy in [(-3, -2), (2, 3), (-1, 4)]:
            pygame.draw.circle(self.screen, (200, 160, 0),
                               (cx + hx, cy + hy), 1)

    def _draw_start(self):
        r, c = START
        cx   = c * CELL + CELL // 2
        cy   = r * CELL + CELL // 2
        rad  = CELL // 2 - 3
        pygame.draw.circle(self.screen, C_START, (cx, cy), rad, 1)

    def _draw_mouse(self, gs: GameState):
        color = {
            'waiting': C_MOUSE_LIVE,
            'playing': C_MOUSE_LIVE,
            'won':     C_MOUSE_WIN,
            'died':    C_MOUSE_DEAD,
        }[gs.status]
        r, c = gs.pos
        cx   = c * CELL + CELL // 2
        cy   = r * CELL + CELL // 2
        rad  = CELL // 2 - 2
        pygame.draw.circle(self.screen, color, (cx, cy), rad)
        pygame.draw.circle(self.screen, (255, 255, 255), (cx, cy), rad, 1)
        # eyes
        eye_r = max(1, rad // 4)
        pygame.draw.circle(self.screen, (30, 20, 10),
                           (cx - rad // 3, cy - rad // 3), eye_r)
        pygame.draw.circle(self.screen, (30, 20, 10),
                           (cx + rad // 3, cy - rad // 3), eye_r)

    def _draw_panel(self, gs: GameState):
        panel_x = COLS * CELL
        pygame.draw.rect(self.screen, C_PANEL_BG,
                         (panel_x, 0, PANEL_W, ROWS * CELL))
        pygame.draw.line(self.screen, C_WALL,
                         (panel_x, 0), (panel_x, ROWS * CELL), 1)

        x  = panel_x + 14
        y  = 18
        dy = 24

        def label(text, color=C_DIM, font=None):
            nonlocal y
            f = font or self.font_sm
            self.screen.blit(f.render(text, True, color), (x, y))
            y += dy

        def value(text, color=C_TEXT, font=None):
            nonlocal y
            f = font or self.font_md
            self.screen.blit(f.render(text, True, color), (x, y))
            y += dy

        # Title
        value('🐭  MOUSE MAZE', C_CHEESE, self.font_md)
        y += 6
        pygame.draw.line(self.screen, C_DIM, (x, y), (x + PANEL_W - 28, y), 1)
        y += 10

        # Timer
        rem = gs.remaining()
        if   rem > 60:   tc = C_TIMER_OK
        elif rem > 20:   tc = C_TIMER_WARN
        else:            tc = C_TIMER_CRIT
        mins = int(rem // 60)
        secs = int(rem  % 60)
        label('TIME LEFT')
        value(f'  {mins}:{secs:02d}', tc, self.font_lg)

        # Timer bar
        bar_w  = PANEL_W - 28
        bar_h  = 8
        filled = int(bar_w * rem / TIME_LIMIT)
        pygame.draw.rect(self.screen, C_BAR_BG,   (x, y, bar_w, bar_h), border_radius=4)
        pygame.draw.rect(self.screen, tc,          (x, y, filled, bar_h), border_radius=4)
        y += bar_h + 14

        label('RUN #')
        value(f'  {gs.run}')
        label('STEPS')
        value(f'  {gs.steps}')
        label('POSITION')
        value(f'  {gs.pos}')

        y += 8
        pygame.draw.line(self.screen, C_DIM, (x, y), (x + PANEL_W - 28, y), 1)
        y += 14

        # Algorithm name
        label('ALGORITHM')
        algo_name = type(gs.algo).__name__
        # word-wrap if long
        if len(algo_name) > 14:
            value(algo_name[:14])
            value(algo_name[14:])
        else:
            value(algo_name)

        y += 10
        pygame.draw.line(self.screen, C_DIM, (x, y), (x + PANEL_W - 28, y), 1)
        y += 14

        # Controls
        label('── CONTROLS ──')
        for key, action in [
            ('SPACE', 'pause/resume'),
            ('R',     'restart'),
            ('+',     'faster'),
            ('-',     'slower'),
            ('ESC/Q', 'quit'),
        ]:
            self.screen.blit(
                self.font_sm.render(f'  {key:<6} {action}', True, C_DIM), (x, y))
            y += 16

        # Speed indicator
        y += 4
        spd = round(1 / gs.step_delay) if gs.step_delay > 0 else 999
        self.screen.blit(
            self.font_sm.render(f'  speed: ~{spd} steps/s', True, C_DIM), (x, y))

    def _draw_bottom_bar(self, gs: GameState):
        bar_y = ROWS * CELL
        pygame.draw.rect(self.screen, C_PANEL_BG,
                         (0, bar_y, WIN_W, 40))
        pygame.draw.line(self.screen, C_WALL, (0, bar_y), (WIN_W, bar_y), 1)
        msg = (f'Start{START} → Finish{FINISH}  |  '
               f'Maze {ROWS}×{COLS}  |  ≥{TARGET_PATHS} solution paths')
        surf = self.font_sm.render(msg, True, C_DIM)
        self.screen.blit(surf, (10, bar_y + 13))

    def _overlay_base(self, alpha=210):
        overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        overlay.fill((15, 17, 35, alpha))
        self.screen.blit(overlay, (0, 0))

    def _draw_overlay_won(self, gs: GameState):
        self._overlay_base(160)
        cx, cy = WIN_W // 2, WIN_H // 2
        elapsed = gs.end_ts - gs.start_ts
        lines = [
            ('CHEESE FOUND!',     C_CHEESE,    self.font_xl),
            (f'{elapsed:.1f} s  ·  {gs.steps} steps', C_TEXT, self.font_md),
            ('Restarting…',       C_DIM,        self.font_sm),
        ]
        total_h = sum(f.get_height() + 8 for _, _, f in lines)
        y = cy - total_h // 2
        for text, color, font in lines:
            surf = font.render(text, True, color)
            self.screen.blit(surf, (cx - surf.get_width() // 2, y))
            y += font.get_height() + 8

    def _draw_overlay_died(self, gs: GameState):
        self._overlay_base(180)
        cx, cy = WIN_W // 2, WIN_H // 2
        lines = [
            ("TIME'S UP!",    C_MOUSE_DEAD, self.font_xl),
            (f'{gs.steps} steps taken', C_TEXT, self.font_md),
            ('Restarting…',   C_DIM,        self.font_sm),
        ]
        total_h = sum(f.get_height() + 8 for _, _, f in lines)
        y = cy - total_h // 2
        for text, color, font in lines:
            surf = font.render(text, True, color)
            self.screen.blit(surf, (cx - surf.get_width() // 2, y))
            y += font.get_height() + 8

    def _draw_overlay_waiting(self, gs: GameState):
        self._overlay_base(170)
        cx = WIN_W // 2
        cy = ROWS * CELL // 2
        lines = [
            ('MOUSE MAZE',            C_CHEESE,    self.font_xl),
            (f'Maze {ROWS}x{COLS}  |  >= {TARGET_PATHS} paths', C_DIM, self.font_sm),
            ('',                       C_TEXT,       self.font_sm),
            ('Press SPACE to start',   C_TIMER_OK,   self.font_lg),
            ('R = restart  ESC = quit',C_DIM,        self.font_sm),
        ]
        total_h = sum(f.get_height() + 6 for _, _, f in lines)
        y = cy - total_h // 2
        for text, color, font in lines:
            surf = font.render(text, True, color)
            self.screen.blit(surf, (cx - surf.get_width() // 2, y))
            y += font.get_height() + 6

    def _draw_overlay_paused(self):
        self._overlay_base(120)
        cx, cy = WIN_W // 2, WIN_H // 2
        surf = self.font_xl.render('PAUSED', True, C_TEXT)
        self.screen.blit(surf, (cx - surf.get_width() // 2, cy - surf.get_height() // 2))


# ─── Main loop ────────────────────────────────────────────────────────────────
def main():
    print('Generating maze…')
    walls = generate_perfect_maze(ROWS, COLS, seed=RANDOM_SEED)
    add_extra_passages(walls, ROWS, COLS, START, FINISH,
                       target=TARGET_PATHS, seed=RANDOM_SEED)
    print('Maze ready. Opening game window…')

    pygame.init()
    pygame.display.set_caption('Mouse Maze')
    screen    = pygame.display.set_mode((WIN_W, WIN_H))
    clock     = pygame.time.Clock()
    maze_surf = build_maze_surface(walls)

    algo      = SmellGuidedDFS()
    gs        = GameState(walls, algo)
    renderer  = Renderer(screen, maze_surf)

    RESTART_DELAY = 2.5   # seconds to show won/died screen before restart

    last_step_time = time.time()

    while True:
        # ── Events ────────────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    pygame.quit(); sys.exit()
                elif event.key == pygame.K_r:
                    gs.restart()
                    last_step_time = time.time()
                elif event.key == pygame.K_SPACE:
                    if gs.status == 'waiting':
                        gs.begin()
                        last_step_time = time.time()
                    elif gs.status == 'playing':
                        if not gs.paused:
                            gs.paused    = True
                            gs._pause_ts = time.time()
                        else:
                            # Shift start_ts by exact paused duration so timer stays accurate
                            gs.start_ts += time.time() - gs._pause_ts
                            gs._pause_ts = None
                            gs.paused    = False
                elif event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    gs.step_delay = max(STEP_MIN, gs.step_delay - STEP_DELTA)
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    gs.step_delay = min(STEP_MAX, gs.step_delay + STEP_DELTA)

        # ── Auto-restart after won/died ────────────────────────────────────────
        if gs.status in ('won', 'died') and gs.end_ts is not None:
            if time.time() - gs.end_ts >= RESTART_DELAY:
                gs.restart()
                last_step_time = time.time()

        # ── Step mouse ────────────────────────────────────────────────────────
        now = time.time()
        if gs.status == 'playing' and not gs.paused:
            if now - last_step_time >= gs.step_delay:
                gs.tick()
                last_step_time = now

        # ── Render ────────────────────────────────────────────────────────────
        renderer.draw(gs)
        clock.tick(60)


if __name__ == '__main__':
    main()
