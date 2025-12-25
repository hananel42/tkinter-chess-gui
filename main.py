#!/usr/bin/env python3
"""
DisplayBoard - a lightweight Tkinter-based chess board widget.

Features:
- Renders a chess.Board using Unicode pieces on a Tkinter Canvas.
- Click-to-select, click-to-move and optional dragging for moves.
- Right-click drag to draw arrows / circles for annotation.
- Highlights, circles and arrows management (avoid duplicates).
- Promotion dialog handling.
- Callback registration for move events.
- Board flipping and coordinate display.

Documentation (docstrings and inline comments) is in English.
Logic preserved as requested.
"""
import tkinter.font
import math
import chess
import tkinter as tk
from chess import Move
from typing import Callable, Optional, Tuple, override


class DisplayBoard(tk.Frame, chess.Board):
    """
    A Tkinter widget that displays and interacts with a chess.Board.

    Public methods of interest:
      - redraw(): redraw the entire board widget.
      - set_fen(fen): set position and redraw.
      - on_move(callback): register a callback(move, board) for executed moves.
      - make_move(from_sq, to_sq, promo_piece=None): attempt to make a move (returns Move or None).
      - flip_board(): flip board orientation and redraw.
      - push(move)/pop(): push/pop moves (keeps display updated).
    """

    UNICODE_PIECES = {
        "P": "♙", "N": "♘", "B": "♗", "R": "♖", "Q": "♕", "K": "♔",
        "p": "♟", "n": "♞", "b": "♝", "r": "♜", "q": "♛", "k": "♚"
    }

    def __init__(
            self,
            master=None,
            board_size: int = 480,
            allow_input: bool = True,
            allow_dragging: bool = True,
            allow_drawing: bool = True,
            black_bg: Tuple[int, int, int] = (181, 136, 99),
            white_bg: Tuple[int, int, int] = (240, 217, 181),
            arrow_color: Tuple[int, int, int] = (255, 0, 0),
            arrow_width: int = 3,
            circle_color: Tuple[int, int, int] = (50, 50, 255),
            circle_width: int = 3,
            show_legal: bool = True,
            legal_moves_circles_color: Tuple[int, int, int] = (50, 50, 50),
            legal_moves_circles_width: int = 5,
            legal_moves_circles_radius: int = 7,
            show_coordinates: bool = True,
            input_callback: "callable | None" = None,
            draw_function: "callable | None" = None,
            flipped: bool = False,
            highlight_color: Tuple[int, int, int] = (150, 232, 125),
            font: str = "Arial",
            *args,
            **kwargs):
        """
        Initialize display and internal board.

        Parameters largely mirror previously used parameter names and defaults.
        Documentation focuses on usage, not implementation details.
        """
        tk.Frame.__init__(self, master, width=board_size, height=board_size)
        chess.Board.__init__(self, *args, **kwargs)

        # Canvas setup
        self.master = master
        self.canvas = tk.Canvas(self, width=board_size, height=board_size, highlightthickness=0)
        self.canvas.pack()

        # Interaction / state flags
        self._promotion_active = False
        self._waiting_move = None
        self._promotion_buttons = []   # list[(x1,y1,x2,y2), promo]
        self._selected_square = None
        self._right_click_start = None
        self._right_click_end = None
        self._dragging_piece = None
        self._dragging_offset = (0, 0)

        # Collections used for overlay drawing (prevent duplicates)
        self.highlights = []  # list[(row, col, color)]
        self.circles = []     # list[(row, col, color, radius, width)]
        self.arrows = []      # list[(from_row, from_col, to_row, to_col, color, width)]

        # Move callbacks - appended via on_move()
        self._move_callbacks = []
        if input_callback:
            self._move_callbacks.append(input_callback)

        # Display / behavior settings
        self.board_size = board_size
        self.square_size = board_size // 8
        self.allow_input = allow_input
        self.allow_dragging = allow_dragging
        self.allow_drawing = allow_drawing
        self.draw_function = draw_function
        self.flipped = flipped
        self.black_bg = black_bg
        self.white_bg = white_bg
        self.circle_color = circle_color
        self.circle_width = circle_width
        self.arrow_color = arrow_color
        self.arrow_width = arrow_width
        self.highlight_color = highlight_color
        self.legal_moves_circles_color = legal_moves_circles_color
        self.legal_moves_circles_radius = legal_moves_circles_radius
        self.legal_moves_circles_width = legal_moves_circles_width
        self.show_legal = show_legal
        self.show_coordinates = show_coordinates
        self.font = tkinter.font.Font(family=font, size=int(self.square_size * 0.6))

        # Mouse bindings
        self.canvas.bind("<Button-1>", self._tk_left_click)
        self.canvas.bind("<Button-3>", self._tk_right_down)
        self.canvas.bind("<B3-Motion>", self._tk_right_motion)
        self.canvas.bind("<B1-Motion>", self._tk_left_motion)
        self.canvas.bind("<ButtonRelease-3>", self._tk_right_up)
        self.canvas.bind("<ButtonRelease-1>", self._tk_left_up)

        # Initial render
        self.redraw()

    # --------------------
    # Utilities / helpers
    # --------------------
    @staticmethod
    def _rgb_to_hex(col):
        """Convert an (r,g,b) tuple to a hex color string, or return string as-is."""
        if isinstance(col, str):
            return col
        r, g, b = col
        return f"#{r:02x}{g:02x}{b:02x}"

    @staticmethod
    def row_col_of(square):
        """Return (row, col) used for drawing rectangles from a chess.Square.
        Drawing uses top-left origin where row 0 is top of the canvas.
        """
        return 7 - chess.square_rank(square), chess.square_file(square)

    # --------------------
    # Mouse event handlers
    # --------------------
    def _tk_left_click(self, event):
        """
        Left click: handle promotion selection or select/move click flow.
        Dragging is started here if enabled.
        """
        if self.allow_drawing:
            self.clear_board_draw()
            self.redraw()
        if not self.allow_input:
            return

        x, y = event.x, event.y

        # If promotion dialog active, check which promo button was clicked
        if self._promotion_active:
            self._promotion_active = False
            for b_bbox, promo in self._promotion_buttons:
                x1, y1, x2, y2 = b_bbox
                if x1 <= x <= x2 and y1 <= y <= y2:
                    if self._waiting_move:
                        self.make_move(self._waiting_move.from_square, self._waiting_move.to_square, promo)
                        self._waiting_move = None
                    break
        else:
            square = self.square_at(x, y)
            if square is None:
                return

            # Try to complete a move if a square was previously selected
            if self._selected_square is not None and self.make_move(self._selected_square, square):
                self._selected_square = None
            else:
                # Otherwise select piece under cursor if it belongs to side to move
                self._selected_square = None
                piece = self.piece_at(square)
                if piece and piece.color == self.turn:
                    self._selected_square = square
                    # start dragging visualization if allowed
                    if self.allow_dragging:
                        self._dragging_piece = piece
                        center_x, center_y = self.square_center(square)
                        self._dragging_offset = (center_x - event.x, center_y - event.y)
                        self._show_selected()
                        self.redraw()
                        self.canvas.create_text(event.x + self._dragging_offset[0],
                                                event.y + self._dragging_offset[1],
                                                text=self.UNICODE_PIECES[self._dragging_piece.symbol()],
                                                font=self.font, fill="black")
                        return

        self._show_selected()
        self.redraw()

    def _tk_right_down(self, event):
        """Start right-click annotation (arrow/circle)."""
        if not self.allow_drawing:
            return
        x, y = event.x, event.y
        if self.square_at(x, y) is not None:
            self._right_click_start = x, y
            self._right_click_end = self._right_click_start
        self.redraw()

    def _tk_right_motion(self, event):
        """Update right-click annotation preview while dragging."""
        x, y = event.x, event.y
        if not self._right_click_start:
            return
        end_square = self.square_at(x, y)
        if end_square is not None:
            self._right_click_end = x, y
        self.redraw()

    def _tk_left_motion(self, event):
        """Show dragging piece while left button is held and dragging is enabled."""
        if not self.allow_input:
            return
        if not self._dragging_piece:
            return
        self.redraw()
        self.canvas.create_text(event.x + self._dragging_offset[0],
                                event.y + self._dragging_offset[1],
                                text=self.UNICODE_PIECES[self._dragging_piece.symbol()],
                                font=self.font, fill="black")

    def _tk_right_up(self, event):
        """Complete a right-click annotation: circle (same square) or arrow (different squares)."""
        x, y = event.x, event.y
        if self._right_click_start:
            start_square = self.square_at(*self._right_click_start)
            end_square = self.square_at(x, y)
            if start_square is not None and end_square is not None:
                start_row, start_col = 7 - chess.square_rank(start_square), chess.square_file(start_square)
                end_row, end_col = 7 - chess.square_rank(end_square), chess.square_file(end_square)
                if start_square == end_square:
                    self.draw_circle(start_row, start_col, self.circle_color, int(self.square_size / 2.1),
                                     self.circle_width)
                else:
                    self.draw_arrow(start_row, start_col, end_row, end_col, self.arrow_color, self.arrow_width)

        self._right_click_start = None
        self._right_click_end = None
        self.redraw()

    def _tk_left_up(self, event):
        """Finish dragging a piece (if any) and attempt to perform the move."""
        if not self.allow_input:
            return
        self.clear_board_draw()
        if self._dragging_piece is None:
            return
        to_square = self.square_at(event.x + self._dragging_offset[0], event.y + self._dragging_offset[1])
        if to_square is not None:
            if self.make_move(self._selected_square, to_square):
                self._selected_square = None
        self._dragging_piece = None
        self._show_selected()
        self.redraw()

    # --------------------
    # Drawing primitives
    # --------------------
    def _draw_arrow(self, start, end, color=(255, 0, 0), width=2):
        """Draw an arrow between two canvas pixel coordinates."""
        color_hex = self._rgb_to_hex(color)
        x1, y1 = start
        x2, y2 = end
        self.canvas.create_line(x1, y1, x2, y2, width=width, fill=color_hex)
        dx = x2 - x1
        dy = y2 - y1
        angle = math.atan2(dy, dx)
        arrow_size = self.square_size / 2
        arrow_angle = math.radians(35)

        left = (
            x2 - arrow_size * math.cos(angle - arrow_angle),
            y2 - arrow_size * math.sin(angle - arrow_angle)
        )
        right = (
            x2 - arrow_size * math.cos(angle + arrow_angle),
            y2 - arrow_size * math.sin(angle + arrow_angle)
        )
        self.canvas.create_line(x2, y2, left[0], left[1], width=width, fill=color_hex)
        self.canvas.create_line(x2, y2, right[0], right[1], width=width, fill=color_hex)

    def _draw_coordinates(self):
        """Draw board coordinates (a-h and 1-8) around the board."""
        if not self.show_coordinates:
            return
        font_size = max(6, self.square_size // 5)
        coord_font = tkinter.font.Font(size=font_size)
        for i in range(8):
            # letters a-h
            letter_index = i if not self.flipped else 7 - i
            letter = chr(ord('a') + letter_index)
            x = i * self.square_size
            y = self.board_size - font_size - 10
            self.canvas.create_text(x, y, text=letter, anchor="nw", font=coord_font, fill="black")

            # numbers 1-8
            number_index = 7 - i if not self.flipped else i
            number = str(number_index + 1)
            x = 2
            y = i * self.square_size + 2
            self.canvas.create_text(x, y, text=number, anchor="nw", font=coord_font, fill="black")

    def _draw_promotion_dialog(self):
        """Render a simple promotion chooser in the center of the board."""
        w, h = 320, 80
        x = (self.board_size - w) // 2
        y = (self.board_size - h) // 2
        self.canvas.create_rectangle(x, y, x + w, y + h, outline=self._rgb_to_hex((230, 230, 230)), width=2)
        options = [
            (chess.QUEEN, "♕"),
            (chess.ROOK, "♖"),
            (chess.BISHOP, "♗"),
            (chess.KNIGHT, "♘"),
        ]
        gap = 15
        size = 60
        bx = x + gap
        by = y + (h - size) // 2

        self._promotion_buttons = []
        for promo, symbol in options:
            x1 = bx
            y1 = by
            x2 = bx + size
            y2 = by + size
            self.canvas.create_rectangle(x1, y1, x2, y2, fill="white", outline="black", width=1)
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            self.canvas.create_text(cx, cy, text=symbol, font=self.font, fill="black")
            self._promotion_buttons.append(((x1, y1, x2, y2), promo))
            bx += size + gap

    def _draw_temp_arrow_or_circle(self):
        """Draw preview arrow / circle while right-click dragging."""
        if self._right_click_end and self._right_click_start:
            start_x, start_y = self._right_click_start
            end_x, end_y = self._right_click_end
            start_square = self.square_at(start_x, start_y)
            end_square = self.square_at(end_x, end_y)
            if start_square is not None and end_square is not None:
                start_row, start_col = 7 - chess.square_rank(start_square), chess.square_file(start_square)
                end_row, end_col = 7 - chess.square_rank(end_square), chess.square_file(end_square)
                if self.flipped:
                    start_row, start_col = 7 - start_row, 7 - start_col
                    end_row, end_col = 7 - end_row, 7 - end_col
                if start_square == end_square:
                    center = (start_col * self.square_size + self.square_size // 2,
                              start_row * self.square_size + self.square_size // 2)
                    r = int(self.square_size // 2.1)
                    self.canvas.create_oval(center[0] - r, center[1] - r, center[0] + r, center[1] + r,
                                            outline=self._rgb_to_hex(self.circle_color), width=self.circle_width)
                else:
                    start = (start_col * self.square_size + self.square_size // 2,
                             start_row * self.square_size + self.square_size // 2)
                    end = (end_col * self.square_size + self.square_size // 2,
                           end_row * self.square_size + self.square_size // 2)
                    self._draw_arrow(start, end, self.arrow_color, self.arrow_width)

    def _draw_squares(self):
        """Draw the 8x8 checkerboard squares."""
        for r in range(8):
            for c in range(8):
                color = self.white_bg if (r + c) % 2 == 0 else self.black_bg
                x1 = c * self.square_size
                y1 = r * self.square_size
                x2 = x1 + self.square_size
                y2 = y1 + self.square_size
                self.canvas.create_rectangle(x1, y1, x2, y2, fill=self._rgb_to_hex(color), width=0)

    def _draw_highlights(self):
        """Draw highlight rectangles stored in self.highlights."""
        for r, c, color in self.highlights:
            if self.flipped:
                r, c = 7 - r, 7 - c
            x1 = c * self.square_size
            y1 = r * self.square_size
            x2 = x1 + self.square_size
            y2 = y1 + self.square_size
            self.canvas.create_rectangle(x1, y1, x2, y2, outline=self._rgb_to_hex(color), width=3)

    def _draw_pieces(self):
        """Draw all pieces on the board using Unicode symbols."""
        for r in range(8):
            for c in range(8):
                square = chess.square(c, 7 - r)
                piece = self.piece_at(square)
                # skip drawing the piece currently being dragged at its origin square
                if piece == self._dragging_piece and square == self._selected_square:
                    continue
                if piece:
                    symbol = DisplayBoard.UNICODE_PIECES[piece.symbol()]
                    draw_r, draw_c = r, c
                    if self.flipped:
                        draw_r, draw_c = 7 - r, 7 - c
                    x_center = draw_c * self.square_size + self.square_size // 2
                    y_center = draw_r * self.square_size + self.square_size // 2
                    self.canvas.create_text(x_center, y_center, text=symbol, font=self.font, fill="black")

    def _draw_circles(self):
        """Draw circles from self.circles."""
        for r, c, color, radius, width in self.circles:
            rr, cc = r, c
            if self.flipped:
                rr, cc = 7 - r, 7 - c
            center_x = cc * self.square_size + self.square_size / 2
            center_y = rr * self.square_size + self.square_size / 2
            self.canvas.create_oval(center_x - radius, center_y - radius,
                                    center_x + radius, center_y + radius,
                                    outline=self._rgb_to_hex(color), width=width)

    def _draw_arrows(self):
        """Draw stored arrows from self.arrows."""
        for fr, fc, tr, tc, color, width in self.arrows:
            fr2, fc2, tr2, tc2 = fr, fc, tr, tc
            if self.flipped:
                fr2, fc2 = 7 - fr, 7 - fc
                tr2, tc2 = 7 - tr, 7 - tc
            start = (fc2 * self.square_size + self.square_size // 2,
                     fr2 * self.square_size + self.square_size // 2)
            end = (tc2 * self.square_size + self.square_size // 2,
                   tr2 * self.square_size + self.square_size // 2)
            self._draw_arrow(start, end, color=color, width=width)

    def redraw(self):
        """Clear canvas and redraw the entire board, overlays and optional custom drawing."""
        self.canvas.delete("all")
        self._draw_squares()
        self._draw_highlights()
        self._draw_pieces()
        self._draw_temp_arrow_or_circle()
        self._draw_circles()
        self._draw_arrows()
        self._draw_coordinates()
        if self._promotion_active:
            self._draw_promotion_dialog()
        if self.draw_function:
            # Optional user-supplied drawing hook: draw_function(self)
            self.draw_function(self)

    # --------------------
    # Selection / legal move visualization
    # --------------------
    def _show_selected(self):
        """Highlight the selected square and optionally show legal move circles for that piece."""
        if self._selected_square is None:
            return
        self.highlight_square(self._selected_square, self.highlight_color, False)
        if self.show_legal:
            for move in self.legal_moves:
                if move.from_square == self._selected_square:
                    to_sq = move.to_square
                    r, c = 7 - chess.square_rank(to_sq), chess.square_file(to_sq)
                    self.draw_circle(r, c, self.legal_moves_circles_color, self.legal_moves_circles_radius,
                                     self.legal_moves_circles_width, False)

    # --------------------
    # Game logic integration
    # --------------------
    def _is_promotion(self, from_square, to_square) -> bool:
        """Return True if the move is a pawn promotion (destination rank for pawn)."""
        piece = self.piece_at(from_square)
        if not piece or piece.piece_type != chess.PAWN:
            return False
        rank_to = chess.square_rank(to_square)
        if (piece.color == chess.WHITE and rank_to == 7) or (piece.color == chess.BLACK and rank_to == 0):
            return True
        return False

    def clear_board_draw(self, highlights: bool = True, circles: bool = True, arrows: bool = True):
        """Clear overlay lists selectively."""
        if highlights:
            self.highlights = []
        if arrows:
            self.arrows = []
        if circles:
            self.circles = []

    def push(self, move: Move) -> None:
        """Push a move to the underlying chess.Board and update display."""
        super().push(move)
        self.redraw()

    def pop(self) -> Move:
        """Pop last move from the board, clear overlays and update display."""
        self.clear_board_draw()
        move = super().pop()
        self.redraw()
        return move

    def clone_board(self) -> chess.Board:
        """Return a detached copy of the current board (chess.Board object)."""
        board_copy = chess.Board(fen=self.fen())
        return board_copy

    def make_move(self, from_square, to_square, promo_piece=None, callback: bool = True) -> Optional[chess.Move]:
        """
        Attempt to make a move from from_square to to_square.

        Returns:
            chess.Move if executed;
            None if the move is illegal or a promotion dialog is awaiting resolution.
        """
        if from_square is None or to_square is None:
            return None
        # If promotion needed and promotion not yet chosen, set waiting move and show dialog
        if promo_piece is None and self._is_promotion(from_square, to_square) and chess.Move(from_square, to_square, chess.QUEEN) in self.legal_moves:
            self._waiting_move = chess.Move(from_square, to_square)
            self._promotion_active = True
            return None
        move = chess.Move(from_square, to_square, promotion=promo_piece)
        if move in self.legal_moves:
            self.push(move)
            if callback:
                for cb in self._move_callbacks:
                    cb(move, self)
            return move
        return None

    def square_at(self, x: int, y: int) -> Optional[chess.Square]:
        """
        Convert canvas pixel coordinates to chess.Square.

        Returns None if coordinates are outside the board.
        """
        if x < 0 or y < 0 or x >= self.board_size or y >= self.board_size:
            return None
        col = int(x // self.square_size)
        row = int(y // self.square_size)
        if self.flipped:
            col, row = 7 - col, 7 - row
        return chess.square(col, 7 - row)

    def on_move(self, callback: Callable[[chess.Move, "DisplayBoard"], None]):
        """Register a callback(move, board) called after each executed move."""
        self._move_callbacks.append(callback)

    def square_center(self, square: chess.Square) -> Tuple[int, int]:
        """
        Return the canvas pixel coordinates of the center of the given square.
        Handles flipped orientation.
        """
        col = chess.square_file(square)
        row = chess.square_rank(square)
        if self.flipped:
            col = 7 - col
            row = 7 - row
        center_x = col * self.square_size + self.square_size // 2
        center_y = (7 - row) * self.square_size + self.square_size // 2
        return center_x, center_y

    def flip_board(self):
        """Toggle board orientation and redraw."""
        self.flipped = not self.flipped
        self.redraw()

    # --------------------
    # Overlays manipulation
    # --------------------
    def highlight_square(self, square: chess.Square, color, delete: bool = True):
        """
        Highlight the given chess.Square with a colored rectangle outline.
        Avoids duplicate highlights; if delete=True and the highlight exists it will be removed.
        """
        row, col = self.row_col_of(square)
        item = (row, col, color)
        if item not in self.highlights:
            self.highlights.append(item)
        elif delete:
            try:
                self.highlights.remove(item)
            except ValueError:
                pass

    def draw_circle(self, row: int, col: int, color, radius: int, width: int, delete: bool = True):
        """Add/remove a circle overlay at the specified row/col (drawing coordinates)."""
        item = (row, col, color, radius, width)
        if item not in self.circles:
            self.circles.append(item)
        elif delete:
            try:
                self.circles.remove(item)
            except ValueError:
                pass

    def draw_arrow(self, from_row: int, from_col: int, to_row: int, to_col: int, color, width: int, delete: bool = True):
        """Add/remove an arrow overlay defined by start/end square grid coordinates."""
        item = (from_row, from_col, to_row, to_col, color, width)
        if item not in self.arrows:
            self.arrows.append(item)
        elif delete:
            try:
                self.arrows.remove(item)
            except ValueError:
                pass

    def set_fen(self, fen: str):
        """Set position by FEN and refresh overlays and display."""
        super().set_fen(fen)
        self.clear_board_draw()
        self._selected_square = None
        self.redraw()

    def generate_svg(self,highlights:bool=True,circles:bool=True,arrows:bool=True) -> str:
        """Draw the board as SVG."""
        square_size = self.square_size
        board_size = self.board_size
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{board_size}" height="{board_size}">\n'


        # Draw squares
        for r in range(8):
            for c in range(8):
                color = self.white_bg if (r + c) % 2 == 0 else self.black_bg
                rr, cc = (7 - r, 7 - c) if self.flipped else (r, c)
                x = cc * square_size
                y = rr * square_size
                hex_color = self._rgb_to_hex(color)
                svg+=f'<rect x="{x}" y="{y}" width="{square_size}" height="{square_size}" fill="{hex_color}" />\n'

        if highlights:
            # Draw highlights
            for r, c, color in self.highlights:
                rr, cc = (7 - r, 7 - c) if self.flipped else (r, c)
                x = cc * square_size
                y = rr * square_size
                hex_color = self._rgb_to_hex(color)
                svg+=f'<rect x="{x}" y="{y}" width="{square_size}" height="{square_size}" fill="none" stroke="{hex_color}" stroke-width="3"/>\n'

        # Draw pieces (as text)
        font_size = int(square_size * 0.7)
        for r in range(8):
            for c in range(8):
                square = chess.square(c, 7 - r)
                piece = self.piece_at(square)
                if piece:
                    rr, cc = (7 - r, 7 - c) if self.flipped else (r, c)
                    cx = cc * square_size + square_size / 2
                    cy = rr * square_size + square_size / 2
                    symbol = self.UNICODE_PIECES[piece.symbol()]
                    svg+=f'<text x="{cx}" y="{cy}" font-size="{font_size}" text-anchor="middle" dominant-baseline="middle">{symbol}</text>\n'

        if circles:
            # Draw circles
            for r, c, color, radius, width in self.circles:
                rr, cc = (7 - r, 7 - c) if self.flipped else (r, c)
                cx = cc * square_size + square_size / 2
                cy = rr * square_size + square_size / 2
                hex_color = self._rgb_to_hex(color)
                svg+=f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="{hex_color}" stroke-width="{width}"/>\n'

        if arrows:
            # Draw arrows
            for fr, fc, tr, tc, color, width in self.arrows:
                fr, fc = (7 - fr, 7 - fc) if self.flipped else (fr, fc)
                tr, tc = (7 - tr, 7 - tc) if self.flipped else (tr, tc)
                x1 = fc * square_size + square_size / 2
                y1 = fr * square_size + square_size / 2
                x2 = tc * square_size + square_size / 2
                y2 = tr * square_size + square_size / 2
                hex_color = self._rgb_to_hex(color)
                dx = x2 - x1
                dy = y2 - y1
                angle = math.atan2(dy, dx)
                arrow_size = self.square_size / 2
                arrow_angle = math.radians(35)

                left = (
                    x2 - arrow_size * math.cos(angle - arrow_angle),
                    y2 - arrow_size * math.sin(angle - arrow_angle)
                )
                right = (
                    x2 - arrow_size * math.cos(angle + arrow_angle),
                    y2 - arrow_size * math.sin(angle + arrow_angle)
                )

                svg+=(
                    f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{hex_color}" stroke-width="{width}"/>\n'
                    f'<line x1="{x2}" y1="{y2}" x2="{left[0]}" y2="{left[1]}" stroke="{hex_color}" stroke-width="{width}"/>\n'
                    f'<line x1="{x2}" y1="{y2}" x2="{right[0]}" y2="{right[1]}" stroke="{hex_color}" stroke-width="{width}"/>\n'
                )

        svg+="</svg>"
        return svg

    def export_svg(self, path: str,highlights:bool=True,circles:bool=True,arrows:bool=True) -> bool:
            """Export the board as SVG."""
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(self.generate_svg(highlights, circles, arrows))
                return True
            except OSError:
                return False

    def set_readonly(self, value: bool):
        self.allow_input = not value
        self.allow_dragging = not value
        self.allow_drawing = not value
        self._dragging_offset = (0,0)
        self._dragging_piece = None
        self._promotion_active = False
        self._waiting_move = None
        self.redraw()

class AnimatedDisplayBoard(DisplayBoard):
    """DisplayBoard with smooth small animations. New animation kills previous one."""

    def __init__(self, *args,
                 animation_fps: int = 60,
                 animation_duration: float = 0.20,
                 allow_animation: bool = True,
                 **kwargs):
        # --- initialize animation-related attributes BEFORE calling super()
        # to avoid AttributeError if DisplayBoard.__init__ calls redraw()
        self.animation_fps = max(1, int(animation_fps))
        self.animation_duration = max(0.0, float(animation_duration))
        self.allow_animation = bool(allow_animation)

        self._animating: bool = False
        self._anim_after_id  = None
        self._anim_data = None

        # derived interval (ms)
        self._anim_frame_interval_ms = int(1000 / max(1, self.animation_fps))

        # now initialize parent (which will call redraw)
        super().__init__(*args, **kwargs)

    # --------------------
    # Easing / helpers
    # --------------------
    @staticmethod
    def _ease_out_quad(t: float) -> float:
        """Ease-out quadratic: t in [0,1] -> [0,1]."""
        return 1 - (1 - t) * (1 - t)

    def _frames_for_duration(self, duration: Optional[float] = None) -> int:
        d = self.animation_duration if duration is None else duration
        return max(1, int(round(d * self.animation_fps)))

    # --------------------
    # Animation control
    # --------------------
    def stop_animation(self):
        """Immediately stop current animation and, if an anim move exists, execute it."""
        # cancel scheduled callback
        if self._anim_after_id:
            try:
                self.after_cancel(self._anim_after_id)
            except Exception:
                pass
            self._anim_after_id = None

        # stop anim state
        self._animating = False

        # if there is an in-progress animation and it contained a move, commit it now
        if self._anim_data and "move" in self._anim_data:
            move = self._anim_data.get("move")
            # clear anim data before committing (avoid re-entry issues)
            self._anim_data = None
            try:
                # call DisplayBoard.push to bypass our override and avoid recursion
                DisplayBoard.push(self, move)
            except Exception:
                # as fallback try super().push
                try:
                    super().push(move)
                except Exception:
                    pass

        # redraw to clear any animated overlays
        try:
            self.redraw()
        except Exception:
            pass

    def _start_move_animation(self, move: chess.Move):
        """Start animating the given move (cancels any previous animation)."""
        # cancel any existing animation and commit its move first (stop_animation)
        if self._animating:
            self.stop_animation()

        # if animations disabled -> immediate push
        if not self.allow_animation:
            DisplayBoard.push(self, move)
            return

        # sanity check
        if not isinstance(move, chess.Move):
            DisplayBoard.push(self, move)
            return

        from_sq = move.from_square
        to_sq = move.to_square

        piece = self.piece_at(from_sq)
        if piece is None:
            # nothing to animate; just perform the push
            DisplayBoard.push(self, move)
            return

        frames = self._frames_for_duration()
        self._anim_data = {
            "move": move,
            "from_square": from_sq,
            "to_square": to_sq,
            "piece_symbol": self.UNICODE_PIECES[piece.symbol()],
            "frames": frames,
            "frame": 0,
        }
        self._animating = True
        # recalc interval in case fps changed
        self._anim_frame_interval_ms = int(1000 / max(1, self.animation_fps))
        # schedule first frame
        self._schedule_next_frame()

    def _schedule_next_frame(self):
        if not self._animating or self._anim_data is None:
            return
        # ensure previous after id cleared
        if self._anim_after_id:
            try:
                self.after_cancel(self._anim_after_id)
            except Exception:
                pass
            self._anim_after_id = None
        self._anim_after_id = self.after(self._anim_frame_interval_ms, self._animate_step)

    def _animate_step(self):
        """One animation tick; commit move when finished."""
        self._anim_after_id = None
        if not self._animating or self._anim_data is None:
            return

        self._anim_data["frame"] += 1
        frame = self._anim_data["frame"]
        frames = self._anim_data["frames"]

        # redraw shows the current animated position
        try:
            self.redraw()
        except Exception:
            pass

        if frame < frames:
            # continue animation
            self._schedule_next_frame()
            return

        # finished: commit the move to board (use DisplayBoard.push to bypass override)
        move = self._anim_data.get("move")
        try:
            DisplayBoard.push(self, move)
        except Exception:
            try:
                super().push(move)
            except Exception:
                pass

        # clear animation state
        self._animating = False
        self._anim_data = None
        self._anim_after_id = None

        # final redraw of committed state
        try:
            self.redraw()
        except Exception:
            pass

    # --------------------
    # Draw override to render animated piece on top
    # --------------------
    @override
    def _draw_pieces(self):
        """Draw all pieces on the board using Unicode symbols."""
        for r in range(8):
            for c in range(8):
                square = chess.square(c, 7 - r)
                piece = self.piece_at(square)
                # skip drawing the piece currently being dragged at its origin square
                if piece == self._dragging_piece and square == self._selected_square:
                    continue
                if self._anim_data:
                    if square == self._anim_data["from_square"]:continue
                if piece:
                    symbol = DisplayBoard.UNICODE_PIECES[piece.symbol()]
                    draw_r, draw_c = r, c
                    if self.flipped:
                        draw_r, draw_c = 7 - r, 7 - c
                    x_center = draw_c * self.square_size + self.square_size // 2
                    y_center = draw_r * self.square_size + self.square_size // 2
                    self.canvas.create_text(x_center, y_center, text=symbol, font=self.font, fill="black")

    @override
    def redraw(self):
        """Render board then draw moving piece (if animating)."""
        # parent draws board/pieces/overlays
        super().redraw()

        if not self._animating or not self._anim_data:
            return

        ad = self._anim_data
        frm = ad["from_square"]
        to = ad["to_square"]
        frame = ad["frame"]
        frames = ad["frames"]
        symbol = ad["piece_symbol"]

        # compute centers
        cx_from, cy_from = self.square_center(frm)
        cx_to, cy_to = self.square_center(to)

        # Normalise t in [0,1]. Use frames-1 so final frame lands exactly on dest.
        t = min(1.0, max(0.0, frame / max(1, frames - 1))) if frames > 1 else 1.0
        t_eased = self._ease_out_quad(t)

        cur_x = cx_from + (cx_to - cx_from) * t_eased
        cur_y = cy_from + (cy_to - cy_from) * t_eased

        # draw moving piece on top
        self.canvas.create_text(int(cur_x), int(cur_y), text=symbol, font=self.font, fill="black")

    # --------------------
    # Logic / safety overrides
    # --------------------
    @override
    def push(self, move: chess.Move,animate: bool = True) -> None:
        """Stop any running animation then start animating this push (or execute immediately if disabled)."""
        # stop existing animation and commit its move
        self.stop_animation()

        # If animations disabled -> immediate
        if not self.allow_animation or not animate:
            return DisplayBoard.push(self, move)

        # start this animation (kills any previous).

        self._start_move_animation(move)
        return None

    @override
    def pop(self) -> Optional[chess.Move]:
        self.stop_animation()
        return DisplayBoard.pop(self)

    @override
    def flip_board(self):
        self.stop_animation()
        return DisplayBoard.flip_board(self)

    # --------------------
    # Event handler overrides (stop anim then delegate)
    # --------------------
    @override
    def _tk_left_click(self, event):
        self.stop_animation()
        return super()._tk_left_click(event)

    @override
    def _tk_right_down(self, event):
        self.stop_animation()
        return super()._tk_right_down(event)

    @override
    def _tk_left_up(self, event):
        """Finish dragging a piece (if any) and attempt to perform the move."""
        if not self.allow_input:
            return
        self.clear_board_draw()
        if self._dragging_piece is None:
            return
        to_square = self.square_at(event.x + self._dragging_offset[0], event.y + self._dragging_offset[1])
        if to_square is not None:
            if self.make_move(self._selected_square, to_square,animate=False):
                self._selected_square = None
        self._dragging_piece = None
        self._show_selected()
        self.redraw()
    # Ensure make_move uses animated push path

    @override
    def make_move(self, from_square, to_square, promo_piece=None, callback: bool = True,animate: bool = True) -> Optional[chess.Move]:
        """Attempt to make a move; if legal, call push (which will animate or execute immediately)."""
        if from_square is None or to_square is None:
            return None

        # promotion handling (delegate to parent semantics)
        if promo_piece is None and self._is_promotion(from_square, to_square) and \
                any(chess.Move(from_square, to_square, p) in self.legal_moves
                    for p in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT)):
            self._waiting_move = chess.Move(from_square, to_square)
            self._promotion_active = True
            return None

        move = chess.Move(from_square, to_square, promotion=promo_piece)
        if move in self.legal_moves:
            # push will handle animation
            self.push(move,animate)
            if callback:
                for cb in self._move_callbacks:
                    try:
                        cb(move, self)
                    except Exception:
                        pass
            return move
        return None

if __name__ == '__main__':
    import sys

    # Example usage: run the module and pass an optional FEN on command line.
    root = tk.Tk()
    d = AnimatedDisplayBoard(root)
    d.config(borderwidth=5, bg="#000")
    d.pack()
    if len(sys.argv) > 1:
        d.set_fen(sys.argv[1])
        d.update()

    root.mainloop()
