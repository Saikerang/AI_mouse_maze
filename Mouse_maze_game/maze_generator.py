"""
Maze Generator — 30×30 grid, cell size 16×16 px
- One Start (top-left) and one Finish (bottom-right)
- Guarantees at least 5 distinct solution paths
- Saves maze.png and prints found paths
"""

import random
import sys

# ─── Config ───────────────────────────────────────────────────────────────────
ROWS      = 30
COLS      = 30
CELL_SIZE = 16          # pixels per cell side
TARGET_PATHS = 5        # minimum number of distinct solutions required
RANDOM_SEED  = None     # set an integer for reproducible mazes, or None for random

START  = (0, 0)                # (row, col) — top-left
FINISH = (ROWS - 1, COLS - 1) # (row, col) — bottom-right

# ─── Direction helpers ────────────────────────────────────────────────────────
DIRECTIONS = {
    'N': (-1,  0, 'S'),
    'S': ( 1,  0, 'N'),
    'E': ( 0,  1, 'W'),
    'W': ( 0, -1, 'E'),
}

def neighbours(r, c, rows, cols):
    """Return valid (nr, nc, direction_to_go, opposite_direction) tuples."""
    result = []
    for d, (dr, dc, opp) in DIRECTIONS.items():
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            result.append((nr, nc, d, opp))
    return result


# ─── Maze generation ──────────────────────────────────────────────────────────
def generate_perfect_maze(rows, cols, seed=None):
    """
    Recursive DFS (recursive backtracker) — produces a perfect maze
    (exactly one path between any two cells).
    Returns walls[r][c] = set of directions {'N','S','E','W'} where a wall exists.
    """
    rng = random.Random(seed)
    walls = [[set(DIRECTIONS.keys()) for _ in range(cols)] for _ in range(rows)]
    visited = [[False] * cols for _ in range(rows)]

    def carve(r, c):
        visited[r][c] = True
        dirs = list(DIRECTIONS.items())
        rng.shuffle(dirs)
        for d, (dr, dc, opp) in dirs:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc]:
                walls[r][c].discard(d)
                walls[nr][nc].discard(opp)
                carve(nr, nc)

    sys.setrecursionlimit(rows * cols * 2 + 500)
    carve(0, 0)
    return walls


def collect_closed_walls(walls, rows, cols):
    """
    Return a list of all currently closed interior walls as (r, c, direction) tuples,
    where each entry represents a unique wall (only one side of each shared wall).
    """
    closed = []
    for r in range(rows):
        for c in range(cols):
            # Only consider S and E to avoid duplicating each shared wall
            if 'S' in walls[r][c] and r + 1 < rows:
                closed.append((r, c, 'S'))
            if 'E' in walls[r][c] and c + 1 < cols:
                closed.append((r, c, 'E'))
    return closed


def remove_wall(walls, r, c, direction):
    """Remove one wall between (r,c) and its neighbour in `direction`."""
    dr, dc, opp = DIRECTIONS[direction]
    nr, nc = r + dr, c + dc
    rows, cols = len(walls), len(walls[0])
    if 0 <= nr < rows and 0 <= nc < cols:
        walls[r][c].discard(direction)
        walls[nr][nc].discard(opp)
        return True
    return False


# ─── Path counting (capped DFS) ───────────────────────────────────────────────
def count_paths_up_to(walls, rows, cols, start, finish, cap=TARGET_PATHS):
    """
    DFS with backtracking — counts distinct simple paths from start to finish.
    Stops as soon as `cap` paths are found (avoids exponential blow-up).
    Returns the number of paths found (may be less than the actual total).
    """
    found = [0]

    def dfs(pos, visited_set):
        if found[0] >= cap:
            return
        if pos == finish:
            found[0] += 1
            return
        r, c = pos
        for nr, nc, d, _ in neighbours(r, c, rows, cols):
            if d not in walls[r][c] and (nr, nc) not in visited_set:
                visited_set.add((nr, nc))
                dfs((nr, nc), visited_set)
                visited_set.discard((nr, nc))

    dfs(start, {start})
    return found[0]


# ─── Add extra passages to reach TARGET_PATHS solutions ──────────────────────
def add_extra_passages(walls, rows, cols, start, finish, target, seed=None):
    """
    Remove closed interior walls, chosen randomly from all remaining candidates,
    until at least `target` distinct paths exist.

    Uses only truly-closed walls as candidates so no removal is ever wasted on
    an already-open edge.  Raises RuntimeError if all walls are exhausted before
    the target is reached (should never happen on a 30×30 maze with target=5).

    Returns the verified final path count (>= target).
    """
    rng = random.Random(seed)
    current = count_paths_up_to(walls, rows, cols, start, finish, cap=target)
    print(f"[init] paths found = {current}/{target}")

    while current < target:
        candidates = collect_closed_walls(walls, rows, cols)
        if not candidates:
            raise RuntimeError(
                f"Ran out of walls to remove but only reached {current}/{target} paths. "
                "This should never happen on a 30×30 maze — check grid size or target."
            )
        rng.shuffle(candidates)
        improved = False
        for r, c, d in candidates:
            remove_wall(walls, r, c, d)
            new_count = count_paths_up_to(walls, rows, cols, start, finish, cap=target)
            if new_count > current:
                current = new_count
                print(f"  → removed wall at ({r},{c}) dir={d} — paths now ≥ {current}")
                improved = True
                break
            # Wall didn't help — leave it open anyway (doesn't hurt)
        if not improved:
            # Removed a wall but it didn't grow path count yet; keep trying next round
            pass

    # Hard assertion: verify the guarantee before returning
    verified = count_paths_up_to(walls, rows, cols, start, finish, cap=target)
    if verified < target:
        raise RuntimeError(
            f"Guarantee check failed: only {verified}/{target} paths found after generation."
        )
    return verified


# ─── Find and print paths ─────────────────────────────────────────────────────
def find_paths(walls, rows, cols, start, finish, max_paths=TARGET_PATHS):
    """Return up to `max_paths` distinct simple paths (as lists of (r,c))."""
    paths = []

    def dfs(pos, path, visited_set):
        if len(paths) >= max_paths:
            return
        if pos == finish:
            paths.append(list(path))
            return
        r, c = pos
        for nr, nc, d, _ in neighbours(r, c, rows, cols):
            if d not in walls[r][c] and (nr, nc) not in visited_set:
                path.append((nr, nc))
                visited_set.add((nr, nc))
                dfs((nr, nc), path, visited_set)
                path.pop()
                visited_set.discard((nr, nc))

    dfs(start, [start], {start})
    return paths


# ─── Drawing ──────────────────────────────────────────────────────────────────
def draw_maze(walls, rows, cols, cell_size, start, finish, paths=None,
              output_file="maze.png"):
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        print("matplotlib not found — run: pip install matplotlib")
        return

    fig_px_w = cols * cell_size
    fig_px_h = rows * cell_size
    dpi = 96
    fig, ax = plt.subplots(figsize=(fig_px_w / dpi + 2, fig_px_h / dpi + 2), dpi=dpi)
    ax.set_xlim(0, cols * cell_size)
    ax.set_ylim(0, rows * cell_size)
    ax.set_aspect('equal')
    ax.axis('off')

    ax.set_facecolor('#FAFAFA')
    fig.patch.set_facecolor('#FFFFFF')

    # ── Highlight solution paths ───────────────────────────────────────────────
    path_colors = ['#AED6F1', '#A9DFBF', '#FAD7A0', '#D7BDE2', '#F9E79F']
    if paths:
        for idx, path in enumerate(reversed(paths)):
            color = path_colors[(len(paths) - 1 - idx) % len(path_colors)]
            for (r, c) in path:
                x = c * cell_size
                y = (rows - 1 - r) * cell_size
                rect = mpatches.FancyBboxPatch(
                    (x + 0.5, y + 0.5), cell_size - 1, cell_size - 1,
                    boxstyle="square,pad=0", linewidth=0,
                    facecolor=color, alpha=0.55, zorder=1
                )
                ax.add_patch(rect)

    # ── Draw walls ─────────────────────────────────────────────────────────────
    lw = 1.4
    wall_color = '#2C3E50'
    for r in range(rows):
        for c in range(cols):
            x = c * cell_size
            y = (rows - 1 - r) * cell_size   # flip row → y axis
            if 'N' in walls[r][c]:
                ax.plot([x, x + cell_size], [y + cell_size, y + cell_size],
                        color=wall_color, lw=lw, solid_capstyle='round', zorder=2)
            if 'S' in walls[r][c]:
                ax.plot([x, x + cell_size], [y, y],
                        color=wall_color, lw=lw, solid_capstyle='round', zorder=2)
            if 'E' in walls[r][c]:
                ax.plot([x + cell_size, x + cell_size], [y, y + cell_size],
                        color=wall_color, lw=lw, solid_capstyle='round', zorder=2)
            if 'W' in walls[r][c]:
                ax.plot([x, x], [y, y + cell_size],
                        color=wall_color, lw=lw, solid_capstyle='round', zorder=2)

    # ── Start marker ──────────────────────────────────────────────────────────
    sr, sc = start
    sx = sc * cell_size + cell_size / 2
    sy = (rows - 1 - sr) * cell_size + cell_size / 2
    ax.plot(sx, sy, 'o', markersize=cell_size * 0.65, color='#27AE60',
            markeredgecolor='white', markeredgewidth=1.2, zorder=5)
    ax.text(sx, sy, 'S', ha='center', va='center',
            fontsize=cell_size * 0.45, color='white', fontweight='bold', zorder=6)

    # ── Finish marker ─────────────────────────────────────────────────────────
    fr, fc = finish
    fx = fc * cell_size + cell_size / 2
    fy = (rows - 1 - fr) * cell_size + cell_size / 2
    ax.plot(fx, fy, 'o', markersize=cell_size * 0.65, color='#E74C3C',
            markeredgecolor='white', markeredgewidth=1.2, zorder=5)
    ax.text(fx, fy, 'F', ha='center', va='center',
            fontsize=cell_size * 0.45, color='white', fontweight='bold', zorder=6)

    # ── Legend ────────────────────────────────────────────────────────────────
    legend_handles = [
        mpatches.Patch(color='#27AE60', label=f'Start {start}'),
        mpatches.Patch(color='#E74C3C', label=f'Finish {finish}'),
    ]
    if paths:
        for i, color in enumerate(path_colors[:len(paths)]):
            legend_handles.append(
                mpatches.Patch(facecolor=color, alpha=0.7,
                               label=f'Path {i + 1} ({len(paths[i])} steps)')
            )
    ax.legend(handles=legend_handles, loc='upper right',
              bbox_to_anchor=(1.18, 1.02), fontsize=7, framealpha=0.85)

    n_solutions = len(paths) if paths else 0
    ax.set_title(
        f'Maze {rows}×{cols}  |  cell {cell_size}×{cell_size} px  |  '
        f'{n_solutions} solution paths highlighted',
        fontsize=10, pad=8
    )
    plt.tight_layout()
    plt.savefig(output_file, dpi=dpi, bbox_inches='tight')
    print(f"\nMaze image saved → {output_file}")
    plt.show()


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print(f"  Maze Generator  {ROWS}×{COLS}  |  cell {CELL_SIZE}×{CELL_SIZE} px")
    print(f"  Start: {START}   Finish: {FINISH}")
    print(f"  Target: ≥ {TARGET_PATHS} distinct solution paths")
    print("=" * 55)

    # 1. Generate perfect maze (1 solution)
    print("\n[1] Generating perfect maze …")
    walls = generate_perfect_maze(ROWS, COLS, seed=RANDOM_SEED)

    # 2. Add extra passages until ≥ TARGET_PATHS solutions (guaranteed)
    print(f"\n[2] Adding extra passages to reach ≥ {TARGET_PATHS} solutions …")
    final_count = add_extra_passages(
        walls, ROWS, COLS, START, FINISH,
        target=TARGET_PATHS, seed=RANDOM_SEED
    )
    print(f"\n✓ Guaranteed ≥ {final_count} distinct solution paths (verified)")

    # 3. Draw and save (no solution paths shown)
    print("\n[3] Rendering maze …")
    draw_maze(walls, ROWS, COLS, CELL_SIZE, START, FINISH,
              paths=None, output_file="maze.png")


if __name__ == "__main__":
    main()
