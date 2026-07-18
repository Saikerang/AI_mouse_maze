"""
record_game.py — Runs the game headlessly and saves an animated GIF.
"""

import os, sys, time
os.environ["SDL_VIDEODRIVER"] = "offscreen"

import pygame
from maze_generator import generate_perfect_maze, add_extra_passages, ROWS, COLS, TARGET_PATHS
from mouse_algorithm import SmellGuidedDFS, MOVE_DELTA
from maze_game      import (build_maze_surface, GameState, Renderer,
                             WIN_W, WIN_H, STEP_DELAY)
from PIL import Image

START  = (0, 0)
FINISH = (ROWS - 1, COLS - 1)

# ── Recording settings ──────────────────────────────────────────────────────
MAX_STEPS   = 900       # stop after this many game steps
STEP_DELAY  = 0.0       # no real-time wait — run as fast as possible
FRAME_EVERY = 3         # capture 1 frame every N game steps
GIF_DELAY   = 60        # ms per GIF frame  (~16 fps)
OUT_FILE    = "maze_run.gif"

def main():
    print("Generating maze…")
    walls = generate_perfect_maze(ROWS, COLS, seed=7)
    add_extra_passages(walls, ROWS, COLS, START, FINISH,
                       target=TARGET_PATHS, seed=7)

    pygame.init()
    screen    = pygame.display.set_mode((WIN_W, WIN_H))
    maze_surf = build_maze_surface(walls)

    algo     = SmellGuidedDFS()
    gs       = GameState(walls, algo)
    gs.step_delay = STEP_DELAY
    renderer = Renderer(screen, maze_surf)

    frames = []
    step   = 0

    # Capture the waiting/title screen for a moment, then begin
    for _ in range(18):
        renderer.draw(gs)
        raw = pygame.surfarray.array3d(screen)
        frames.append(Image.fromarray(raw.transpose(1, 0, 2)))
    gs.begin()

    print(f"Simulating up to {MAX_STEPS} steps…")
    while step < MAX_STEPS:
        # Advance one game step
        if gs.status == 'playing':
            gs.tick()
            step += 1

        # Auto-restart after won/died (no delay)
        if gs.status in ('won', 'died') and gs.end_ts is not None:
            gs.restart()

        # Capture frame
        if step % FRAME_EVERY == 0 or gs.status in ('won', 'died'):
            renderer.draw(gs)
            raw  = pygame.surfarray.array3d(screen)   # (W, H, 3)
            img  = Image.fromarray(raw.transpose(1, 0, 2))
            frames.append(img)

        if gs.status == 'won':
            # Freeze a few extra frames on the win screen
            for _ in range(12):
                renderer.draw(gs)
                raw = pygame.surfarray.array3d(screen)
                frames.append(Image.fromarray(raw.transpose(1, 0, 2)))
            gs.restart()

        if len(frames) >= 300:
            break

    pygame.quit()

    print(f"Saving {len(frames)} frames → {OUT_FILE}…")
    frames[0].save(
        OUT_FILE,
        save_all=True,
        append_images=frames[1:],
        duration=GIF_DELAY,
        loop=0,
        optimize=False,
    )
    print(f"Done! Saved {OUT_FILE}")

if __name__ == "__main__":
    main()
