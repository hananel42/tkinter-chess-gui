
# DisplayBoard – Tkinter Chess Board Widget

A lightweight, interactive chess board widget for Python, built on **Tkinter** and **python-chess**.
Supports piece dragging, click-to-move, annotations (arrows & circles), board flipping, promotion dialogs, and SVG export.

---

## Features

* **Tkinter-based GUI**: No heavy dependencies, just Tkinter and python-chess.
* **Unicode Chess Pieces**: Clean, readable chess symbols for both black and white.
* **Interactive Moves**:

  * Click-to-select and click-to-move
  * Optional dragging of pieces
  * Promotion dialogs for pawn promotion
* **Board Annotations**: Draw arrows or circles with right-click drag.
* **Highlights & Legal Moves**: Shows selection and legal move circles.
* **Board Orientation**: Flip board at any time.
* **Export**: Save board state as **SVG** for web or printing.
* **Custom Hooks**: Register callbacks for moves and draw custom overlays.

---

## Installation

Requires **Python 3.x** with the following libraries:

```bash
pip install python-chess
```

Tkinter is usually included with Python. No other dependencies required.

---

## Usage

```python
import tkinter as tk
from displayboard import DisplayBoard

root = tk.Tk()
board = DisplayBoard(root)
board.pack()

# Optional: set a custom FEN
board.set_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")

root.mainloop()
```

---

### Callbacks

Register a callback to react to moves:

```python
def on_move(move, board):
    print("Move executed:", move, "FEN:", board.fen())

board.on_move(on_move)
```

---

### Exporting

**SVG Export:**

```python
board.export_svg("board.svg")
```

---

## Interaction

* **Left Click**: Select/move a piece. Drag if enabled.
* **Right Click + Drag**: Draw arrows (different squares) or circles (same square).
* **Promotion**: Click a pawn promotion option when prompted.
* **Flip Board**: Call `board.flip_board()` to toggle board orientation.

---

## Customization

* Board size, colors, font, and overlay widths can all be customized when creating `DisplayBoard`.
* Optional `draw_function` hook to overlay custom graphics.

---

## License

MIT License – free to use, modify, and distribute.

