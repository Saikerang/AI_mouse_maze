"""
mouse_algorithm.py — Reusable mouse navigation algorithms for maze solving.

Public API
----------
BaseMouseAlgorithm   Abstract base class. Subclass this to build your own algorithm.
SmellGuidedDFS       Built-in implementation: DFS exploration guided by cheese smell.

How to plug in your own algorithm
----------------------------------
    from mouse_algorithm import BaseMouseAlgorithm, MOVE_DELTA

    class MyAlgorithm(BaseMouseAlgorithm):
        def reset(self):
            ...  # clear any internal state

        def decide(self, pos, available_moves, smell_hint):
            ...  # return one string from available_moves
            return available_moves[0]   # e.g. always pick first option

    # Then in maze_game.py:
    game = MazeGame(walls, algorithm=MyAlgorithm())
"""

from abc import ABC, abstractmethod

# ─── Direction constants ───────────────────────────────────────────────────────

MOVE_DELTA: dict[str, tuple[int, int]] = {
    'N': (-1,  0),   # row decreases  → move up
    'S': ( 1,  0),   # row increases  → move down
    'E': ( 0,  1),   # col increases  → move right
    'W': ( 0, -1),   # col decreases  → move left
}


# ─── Abstract base ────────────────────────────────────────────────────────────

class BaseMouseAlgorithm(ABC):
    """
    Abstract base for maze-solving mouse algorithms.

    Contract
    --------
    reset()   Called once at the start of every new run (including restarts).
    decide()  Called once per step; must return a direction from available_moves.
    """

    @abstractmethod
    def reset(self) -> None:
        """Reset all internal state for a fresh run."""

    @abstractmethod
    def decide(
        self,
        pos:             tuple[int, int],
        available_moves: list[str],
        smell_hint:      tuple[int, int],
    ) -> str | None:
        """
        Choose the next move.

        Parameters
        ----------
        pos : (row, col)
            Current cell of the mouse.
        available_moves : list of str
            Directions with no wall blocking them — subset of ['N','S','E','W'].
        smell_hint : (delta_row, delta_col)
            Vector from mouse to cheese: (finish_row - pos_row, finish_col - pos_col).
            Positive delta_row  → cheese is further South.
            Positive delta_col  → cheese is further East.

        Returns
        -------
        One of the strings in available_moves, or None if completely stuck.
        """


# ─── Built-in algorithm: SmellGuidedDFS ───────────────────────────────────────

class SmellGuidedDFS(BaseMouseAlgorithm):
    """
    DFS-flavoured explorer with cheese-smell tie-breaking.

    Strategy (per step)
    -------------------
    1. Count how many times each candidate neighbour has been visited.
    2. Prefer the least-visited neighbour (pure exploration drive).
    3. Break equal-visit ties by dot-product alignment with the smell vector
       (the move that points most towards the cheese wins the tie).
    4. When all neighbours have been visited at least once (dead end / loop),
       the algorithm naturally backtracks because the cell we came from still
       has the lowest visit count among the visited ones.

    Properties
    ----------
    - Deterministic given a fixed maze and fixed start.
    - Visit counts grow monotonically, so the algorithm strongly tends to escape
      loops over time — in practice it reliably solves 30×30 mazes well within
      3 minutes, though no formal termination proof is claimed.
    - Smell guidance keeps average path length low.
    """

    def __init__(self) -> None:
        self._visit_count: dict[tuple[int, int], int] = {}

    # ── BaseMouseAlgorithm interface ──────────────────────────────────────────

    def reset(self) -> None:
        self._visit_count = {}

    def decide(
        self,
        pos:             tuple[int, int],
        available_moves: list[str],
        smell_hint:      tuple[int, int],
    ) -> str | None:
        if not available_moves:
            return None

        # Mark current cell as visited (increment counter)
        self._visit_count[pos] = self._visit_count.get(pos, 0) + 1

        dr_smell, dc_smell = smell_hint

        def sort_key(move: str):
            mr, mc = MOVE_DELTA[move]
            neighbour = (pos[0] + mr, pos[1] + mc)
            visits     = self._visit_count.get(neighbour, 0)
            # Negative dot-product so that better smell alignment = smaller value
            smell_score = -(mr * dr_smell + mc * dc_smell)
            return (visits, smell_score)

        return min(available_moves, key=sort_key)
