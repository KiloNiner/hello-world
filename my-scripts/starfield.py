#!/usr/bin/env python3
"""
starfield.py — Animated terminal star field.

Stars fade in and out through colour gradients using Unicode round (●)
and pointed (★) glyphs.  Colour depth is detected automatically.
Handles terminal resize.  Press Ctrl-C to exit.

Requirements: Python 3.8+, ANSI-capable terminal.
Best experienced with a truecolor terminal (set COLORTERM=truecolor).
"""

from __future__ import annotations

import atexit
import math
import os
import random
import signal
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

TARGET_FPS   = 20
FRAME_SECS   = 1.0 / TARGET_FPS

STAR_DENSITY = 0.003        # fraction of terminal cells occupied by stars
MIN_STARS    = 25
MAX_STARS    = 350

MIN_SPEED    = 0.004        # phase units per frame  ≈ lifecycle of ~50 s at 20 fps
MAX_SPEED    = 0.014        # phase units per frame  ≈ lifecycle of ~4 s at 20 fps

# Glyph ladders indexed by brightness (0 = faintest, last = brightest).
# Round shapes use circles; pointed shapes use star glyphs.
ROUND_GLYPHS:  Tuple[str, ...] = ('·', '•', '◦', '○', '◉', '●')
POINTY_GLYPHS: Tuple[str, ...] = ('·', '✦', '✧', '✶', '★', '✸')

# Colour palettes: lists of (r, g, b) stops from dark → bright.
PALETTES: Dict[str, List[Tuple[int, int, int]]] = {
    'blue-white': [(5,  5,  25),  (30,  30, 110),  (90,  100, 210),  (210, 220, 255)],
    'yellow':     [(25, 15,  5),  (110, 85,  20),  (210, 170,  55),  (255, 240, 160)],
    'red-orange': [(30,  5,  5),  (120, 35,  15),  (235,  95,  35),  (255, 185, 100)],
    'cool-white': [(12, 12, 18),  (80,  82, 100),  (185, 190, 210),  (255, 255, 255)],
}
PALETTE_NAMES = list(PALETTES)

# ──────────────────────────────────────────────────────────────────────────────
# Terminal capability detection
# ──────────────────────────────────────────────────────────────────────────────

def _detect_colour_depth() -> str:
    """Return 'truecolor', '256', or 'ansi'."""
    ct = os.environ.get('COLORTERM', '').lower()
    if ct in ('truecolor', '24bit'):
        return 'truecolor'
    # Windows Terminal always supports truecolor
    if os.environ.get('WT_SESSION'):
        return 'truecolor'
    term = os.environ.get('TERM', '')
    tp   = os.environ.get('TERM_PROGRAM', '')
    if '256color' in term or tp in ('iTerm.app', 'WezTerm', 'kitty', 'alacritty', 'Hyper'):
        return '256'
    return 'ansi'


_COLOUR_DEPTH = _detect_colour_depth()
_RESET        = '\033[0m'


def _ansi_colour(r: int, g: int, b: int) -> str:
    """Return an ANSI escape string that sets the foreground colour."""
    if _COLOUR_DEPTH == 'truecolor':
        return f'\033[38;2;{r};{g};{b}m'

    if _COLOUR_DEPTH == '256':
        # Map into the 6×6×6 colour cube embedded in the 256-colour palette.
        ri = round(r / 255 * 5)
        gi = round(g / 255 * 5)
        bi = round(b / 255 * 5)
        return f'\033[38;5;{16 + 36 * ri + 6 * gi + bi}m'

    # Basic 8-colour ANSI: bucket by perceptual luminance.
    lum = (r * 299 + g * 587 + b * 114) // 1000
    if lum > 200: return '\033[1;37m'   # bold white
    if lum > 120: return '\033[37m'     # white
    if lum > 60:  return '\033[2;37m'   # dim white
    return '\033[0;30m'                 # near-black (invisible on dark bg)


# ──────────────────────────────────────────────────────────────────────────────
# Terminal setup / teardown
# ──────────────────────────────────────────────────────────────────────────────

def _enter_alt_screen() -> None:
    sys.stdout.write(
        '\033[?1049h'   # switch to alternate screen buffer
        '\033[?25l'     # hide cursor
        '\033[2J'       # clear screen
        '\033[H'        # move cursor to home position
    )
    sys.stdout.flush()


def _leave_alt_screen() -> None:
    sys.stdout.write('\033[?25h\033[?1049l')    # show cursor, leave alt screen
    sys.stdout.flush()


# ──────────────────────────────────────────────────────────────────────────────
# Star data and rendering
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Star:
    x:       int    # column (0-based)
    y:       int    # row (0-based)
    phase:   float  # lifecycle position: 0.0 (born) → 1.0 (gone)
    speed:   float  # phase increment per frame
    variant: str    # 'round' or 'pointy'
    palette: str    # key into PALETTES


def _lerp_colour(palette: str, t: float) -> Tuple[int, int, int]:
    """Linearly interpolate along palette stops at normalised position t ∈ [0, 1]."""
    stops  = PALETTES[palette]
    scaled = t * (len(stops) - 1)
    lo     = int(scaled)
    hi     = min(lo + 1, len(stops) - 1)
    f      = scaled - lo
    r = round(stops[lo][0] + f * (stops[hi][0] - stops[lo][0]))
    g = round(stops[lo][1] + f * (stops[hi][1] - stops[lo][1]))
    b = round(stops[lo][2] + f * (stops[hi][2] - stops[lo][2]))
    return r, g, b


def _star_appearance(star: Star) -> Tuple[str, Tuple[int, int, int]]:
    """Return (glyph, (r, g, b)) for the star at its current phase."""
    # sin curve: 0 at phase=0 and phase=1, peak of 1 at phase=0.5
    brightness = math.sin(star.phase * math.pi)

    # Subtle random twinkle near peak brightness
    if 0.35 < star.phase < 0.65:
        brightness *= random.uniform(0.88, 1.0)

    glyphs = ROUND_GLYPHS if star.variant == 'round' else POINTY_GLYPHS
    idx    = min(int(brightness * len(glyphs)), len(glyphs) - 1)

    return glyphs[idx], _lerp_colour(star.palette, brightness)


def _new_star(cols: int, rows: int, phase: Optional[float] = None) -> Star:
    return Star(
        x       = random.randint(0, cols - 1),
        y       = random.randint(0, max(0, rows - 2)),  # avoid last row (shell prompt risk)
        phase   = phase if phase is not None else random.random(),
        speed   = random.uniform(MIN_SPEED, MAX_SPEED),
        variant = random.choice(('round', 'pointy')),
        palette = random.choice(PALETTE_NAMES),
    )


def _target_count(cols: int, rows: int) -> int:
    return max(MIN_STARS, min(MAX_STARS, int(cols * rows * STAR_DENSITY)))


# ──────────────────────────────────────────────────────────────────────────────
# Differential frame rendering
# ──────────────────────────────────────────────────────────────────────────────

# Sparse frame buffer: position → (glyph, r, g, b)
Cell  = Tuple[str, int, int, int]
Frame = Dict[Tuple[int, int], Cell]


def _render_diff(prev: Frame, curr: Frame) -> str:
    """
    Build a single ANSI string that brings the terminal from *prev* to *curr*
    by updating only the cells that changed.  This minimises flicker.
    """
    parts: List[str] = []
    for pos in set(prev) | set(curr):
        old = prev.get(pos)
        new = curr.get(pos)
        if old == new:
            continue
        col, row = pos
        parts.append(f'\033[{row + 1};{col + 1}H')   # cursor move (1-indexed)
        if new:
            ch, r, g, b = new
            parts.append(_ansi_colour(r, g, b) + ch + _RESET)
        else:
            parts.append(_RESET + ' ')                # erase departed star
    return ''.join(parts)


# ──────────────────────────────────────────────────────────────────────────────
# Main loop
# ──────────────────────────────────────────────────────────────────────────────

_resize_pending = False


def _handle_sigwinch(signum: int, frame: object) -> None:  # noqa: ARG001
    global _resize_pending
    _resize_pending = True


def main() -> None:
    global _resize_pending

    # Ensure the terminal sees UTF-8 encoded output.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    atexit.register(_leave_alt_screen)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    if hasattr(signal, 'SIGWINCH'):
        signal.signal(signal.SIGWINCH, _handle_sigwinch)

    _enter_alt_screen()

    cols, rows = os.get_terminal_size()
    stars: List[Star] = [
        _new_star(cols, rows, phase=random.random())   # stagger phases on startup
        for _ in range(_target_count(cols, rows))
    ]
    prev_frame: Frame = {}

    try:
        while True:
            t0 = time.monotonic()

            # ── Handle terminal resize ─────────────────────────────────────
            if _resize_pending:
                _resize_pending = False
                cols, rows = os.get_terminal_size()
                stars = [
                    _new_star(cols, rows, phase=random.random())
                    for _ in range(_target_count(cols, rows))
                ]
                prev_frame = {}
                sys.stdout.write('\033[2J')   # full clear after resize
                sys.stdout.flush()

            # ── Build current frame ────────────────────────────────────────
            curr_frame: Frame = {}
            for star in stars:
                glyph, (r, g, b) = _star_appearance(star)
                curr_frame[(star.x, star.y)] = (glyph, r, g, b)

            # ── Write only changed cells ───────────────────────────────────
            diff = _render_diff(prev_frame, curr_frame)
            if diff:
                sys.stdout.write(diff)
                sys.stdout.flush()
            prev_frame = curr_frame

            # ── Advance phases; respawn stars that completed their cycle ───
            for i, star in enumerate(stars):
                star.phase += star.speed
                if star.phase >= 1.0:
                    stars[i] = _new_star(cols, rows, phase=0.0)

            # ── Sleep to maintain target frame rate ────────────────────────
            elapsed = time.monotonic() - t0
            if (rem := FRAME_SECS - elapsed) > 0:
                time.sleep(rem)

    except KeyboardInterrupt:
        pass    # atexit handler restores the terminal


if __name__ == '__main__':
    main()
