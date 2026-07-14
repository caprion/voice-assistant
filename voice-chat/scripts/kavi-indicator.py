#!/usr/bin/env python3
"""kavi-indicator.py - small floating, draggable dot showing Kavi's state.

Polls ~/.cache/kavi/state (written by kavi.py's Kavi.set_state()) every 150ms
and recolors a small borderless window. This is the visual complement to the
hotkey: since Kavi doesn't show live word-by-word transcription (see
CLAUDE.md - that's a deliberate choice, not a limitation), this dot is the
"is it hearing me?" signal - it changes color the instant recording starts,
well before the transcript is ready.

Drag it anywhere with the mouse; its position is remembered across restarts
in ~/.cache/kavi/indicator-pos. Defaults to bottom-right corner on first run.

States (mirrors kavi.py):
  idle       - grey, small, low opacity   (default / nothing happening)
  listening  - red, pulsing-ish            (recording your speech)
  processing - amber                       (STT/LLM running, brief)

Deliberately dependency-free: uses only tkinter (stdlib, via python3-tk),
which is already installed alongside Python on this system. No new packages,
no extra network calls, negligible CPU (one file stat + one canvas recolor
per poll).
"""
import tkinter as tk
from pathlib import Path

STATE_FILE = Path.home() / ".cache" / "kavi" / "state"
POS_FILE = Path.home() / ".cache" / "kavi" / "indicator-pos"  # remembers where you last dragged it
POLL_MS = 150
SIZE = 30          # dot diameter in px (bumped up from 18 - more visible)
MARGIN = 24         # distance from bottom-right screen corner (default position)

COLORS = {
    "idle": "#555555",
    "listening": "#e0453d",
    "processing": "#e0a83d",
}


def main() -> None:
    root = tk.Tk()
    root.overrideredirect(True)          # no titlebar/border
    root.attributes("-topmost", True)    # always on top
    try:
        root.attributes("-alpha", 0.85)  # slight transparency where supported
    except tk.TclError:
        pass

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    win_size = SIZE + 4

    # Restore last dragged position if we have one, else default bottom-right.
    if POS_FILE.exists():
        try:
            x_str, y_str = POS_FILE.read_text().strip().split(",")
            x, y = int(x_str), int(y_str)
        except Exception:
            x = screen_w - win_size - MARGIN
            y = screen_h - win_size - MARGIN - 40
    else:
        x = screen_w - win_size - MARGIN
        y = screen_h - win_size - MARGIN - 40
    root.geometry(f"{win_size}x{win_size}+{x}+{y}")

    canvas = tk.Canvas(root, width=win_size, height=win_size, highlightthickness=0)
    canvas.pack()
    dot = canvas.create_oval(2, 2, win_size - 2, win_size - 2, fill=COLORS["idle"], outline="")

    # --- Drag to reposition anywhere on screen; position persists across restarts ---
    drag = {"x": 0, "y": 0}

    def on_press(event):
        drag["x"], drag["y"] = event.x, event.y

    def on_motion(event):
        new_x = root.winfo_x() + (event.x - drag["x"])
        new_y = root.winfo_y() + (event.y - drag["y"])
        root.geometry(f"+{new_x}+{new_y}")

    def on_release(_event):
        try:
            POS_FILE.write_text(f"{root.winfo_x()},{root.winfo_y()}")
        except Exception:
            pass

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_motion)
    canvas.bind("<ButtonRelease-1>", on_release)

    last_state = None

    def poll() -> None:
        nonlocal last_state
        try:
            state = STATE_FILE.read_text().strip()
        except FileNotFoundError:
            state = "idle"
        if state not in COLORS:
            state = "idle"
        if state != last_state:
            canvas.itemconfig(dot, fill=COLORS[state])
            # idle fades into background (small+dim); active states are a touch bigger
            r = (win_size - 6) if state == "idle" else (win_size - 2)
            offset = (win_size - r) / 2
            canvas.coords(dot, offset, offset, win_size - offset, win_size - offset)
            last_state = state
        root.after(POLL_MS, poll)

    poll()
    root.mainloop()


if __name__ == "__main__":
    main()
