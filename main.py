import math
import os
import shutil
import threading

import chess
import chess.engine

from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, InstructionGroup, Line, Rectangle, RoundedRectangle, Triangle
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.widget import Widget
from kivy.utils import platform

from openings import BLACK_OPENINGS, WHITE_OPENINGS, analyse_lines, pick_move


def prepare_stockfish_binary():
    """Locates a runnable Stockfish binary for this platform."""
    if platform == "android":
        # Preferred: bundled as a native library via buildozer's
        # android.add_libs_arm64_v8a (libs/android-v8/libstockfish.so). Files in
        # the native lib dir stay executable on every Android version.
        try:
            from jnius import autoclass
            info = autoclass("org.kivy.android.PythonActivity").mActivity.getApplicationInfo()
            candidate = os.path.join(info.nativeLibraryDir, "libstockfish.so")
            if os.path.exists(candidate):
                return candidate
        except ImportError:
            pass  # pyjnius unavailable on desktop; fall through to asset copy

        # fallback: copy the asset into user data. Exec'ing from app data only
        # works when targetSdk <= 28 (Android 10+ blocks it); for modern builds
        # prefer the native-library route above.
        target_path = os.path.join(App.get_running_app().user_data_dir, "stockfish_arm64")
        if not os.path.exists(target_path):
            source_path = os.path.join(os.path.dirname(__file__), "assets", "stockfish_arm64")
            if os.path.exists(source_path):
                shutil.copy(source_path, target_path)
                os.chmod(target_path, 0o755)  # Grant execution permissions
        return target_path
    else:
        # Desktop: any Stockfish on PATH (of this repo folder)
        return shutil.which("stockfish")


FONT = os.path.join(os.path.dirname(__file__), "assets", "DejaVuSans.ttf")
if not os.path.exists(FONT):
    FONT = "Roboto"

# filled glyphs for both sides: color and outline are drawn by Square
PIECES = {
    chess.KING: "♚", chess.QUEEN: "♛", chess.ROOK: "♜",
    chess.BISHOP: "♝", chess.KNIGHT: "♞", chess.PAWN: "♟",
}
FIGURINE = {"K": "♚", "Q": "♛", "R": "♜", "B": "♝", "N": "♞"}
VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
OUTLINE = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)]

# palette (chess.com dark theme)
BG = (0.188, 0.180, 0.169, 1)
PANEL = (0.149, 0.141, 0.129, 1)
ROW_ALT = (0.180, 0.172, 0.160, 1)
CUR = (0.36, 0.35, 0.34, 1)
BTN = (0.24, 0.23, 0.22, 1)
GREEN = (0.506, 0.714, 0.298, 1)
GREEN_DARK = (0.27, 0.46, 0.14, 1)
TEXT = (0.94, 0.94, 0.93, 1)
MUTED = (0.61, 0.60, 0.58, 1)
PENDING = (0.35, 0.34, 0.33, 1)
LIGHT = (0.922, 0.925, 0.816, 1)
DARK = (0.451, 0.584, 0.322, 1)
LAST_LIGHT = (0.96, 0.965, 0.51, 1)
LAST_DARK = (0.725, 0.79, 0.26, 1)
CHECK = (0.90, 0.35, 0.30, 1)
ARROW = (0.40, 0.80, 0.30)

# Move grades by win-probability lost versus the engine's best line.
BOOK = ("Book", (0.82, 0.69, 0.45, 1))
BEST = ("Best", GREEN)
GRADES = [
    (0.02, "Excellent", GREEN),
    (0.05, "Good", (0.60, 0.69, 0.50, 1)),
    (0.10, "Inaccuracy", (0.96, 0.78, 0.27, 1)),
    (0.20, "Mistake", (0.92, 0.58, 0.22, 1)),
    (1.01, "Blunder", (0.80, 0.20, 0.17, 1)),
]


def figurine(san):
    return FIGURINE.get(san[0], san[0]) + san[1:]


def hex_color(c):
    return "%02x%02x%02x" % tuple(int(v * 255) for v in c[:3])


def material(board, color):
    return sum(v * len(board.pieces(t, color)) for t, v in VALUES.items())


def white_share(score):
    """Share of the eval bar (0..1) that belongs to White. score is a PovScore."""
    s = score.white()
    if s.is_mate():
        return 1.0 if s.mate() > 0 else 0.0
    return 1 / (1 + 10 ** (-s.score() / 400))


def score_text(score):
    s = score.white()
    if s.is_mate():
        return f"{'+' if s.mate() > 0 else '-'}M{abs(s.mate())}"
    return f"{s.score() / 100:+.1f}"


def left_label(**kwargs):
    label = Label(halign="left", valign="middle", **kwargs)
    label.bind(size=lambda l, s: setattr(l, "text_size", s))
    return label


_textures = {}


def piece_texture(piece_type, size):
    key = (piece_type, size)
    if key not in _textures:
        label = CoreLabel(text=PIECES[piece_type], font_size=size, font_name=FONT)
        label.refresh()
        _textures[key] = label.texture
    return _textures[key]


class Panel(BoxLayout):
    """BoxLayout with a rounded dark background."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*PANEL)
            self.rect = RoundedRectangle(radius=[dp(8)])
        self.bind(pos=self.redraw, size=self.redraw)

    def redraw(self, *args):
        self.rect.pos, self.rect.size = self.pos, self.size


class FlatButton(Button):
    """Rounded button with an optional darker lip underneath, like chess.com's green button."""
    def __init__(self, bg=BTN, shadow=None, **kwargs):
        super().__init__(background_normal="", background_down="",
                         background_color=(0, 0, 0, 0), **kwargs)
        self.bg = bg
        self.shadow = shadow
        with self.canvas.before:
            self.shadow_fill = Color(*(shadow or (0, 0, 0, 0)))
            self.shadow_rect = RoundedRectangle(radius=[dp(6)])
            self.fill = Color(*bg)
            self.rect = RoundedRectangle(radius=[dp(6)])
        self.bind(pos=self.redraw, size=self.redraw, state=self.redraw, disabled=self.redraw)

    def redraw(self, *args):
        x, y = self.pos
        w, h = self.size
        pressed = self.state == "down"
        lip = dp(3) if self.shadow and not pressed else 0
        self.shadow_rect.pos, self.shadow_rect.size = (x, y), (w, h)
        self.rect.pos, self.rect.size = (x, y + lip), (w, h - lip)
        r, g, b = self.bg[:3]
        if pressed:
            r, g, b = min(1, r + 0.08), min(1, g + 0.08), min(1, b + 0.08)
        self.fill.rgba = (r, g, b, 0.4 if self.disabled else 1)
        if self.shadow:
            self.shadow_fill.rgba = (*self.shadow[:3], 0.4 if self.disabled else 1)


class Option(SpinnerOption):
    def __init__(self, **kwargs):
        super().__init__(background_normal="", background_down="", background_color=BTN, **kwargs)


class FlatSpinner(FlatButton, Spinner):
    pass


class Square(Widget):
    """One board square: background, outlined piece, move hint, and optional edge coordinates."""
    def __init__(self, light, rank_text=None, file_text=None, **kwargs):
        super().__init__(**kwargs)
        self.light = light
        self.base = LIGHT if light else DARK
        self.piece = None
        self.hint = None  # "dot" for a quiet move, "ring" for a capture
        with self.canvas:
            self.fill = Color(*self.base)
            self.rect = Rectangle()
        self.piece_group = InstructionGroup()
        self.canvas.add(self.piece_group)

        # coordinate text takes the color of the opposite square, as on chess.com
        tag = DARK if light else LIGHT
        self.rank_lbl = self.file_lbl = None
        if rank_text:
            self.rank_lbl = Label(text=rank_text, bold=True, font_size="11sp", color=tag,
                                  size_hint=(None, None), size=(dp(14), dp(14)))
            self.add_widget(self.rank_lbl)
        if file_text:
            self.file_lbl = Label(text=file_text, bold=True, font_size="11sp", color=tag,
                                  size_hint=(None, None), size=(dp(14), dp(14)))
            self.add_widget(self.file_lbl)
        self.bind(pos=self.redraw, size=self.redraw)

    def redraw(self, *args):
        x, y = self.pos
        w, h = self.size
        self.rect.pos, self.rect.size = self.pos, self.size
        if self.rank_lbl:
            self.rank_lbl.pos = (x + dp(1), y + h - dp(15))
        if self.file_lbl:
            self.file_lbl.pos = (x + w - dp(14), y + dp(1))
        self.draw()

    def set_state(self, piece, mark, hint=None):
        self.piece = piece
        self.hint = hint
        self.fill.rgba = mark or self.base
        self.draw()

    def draw(self):
        group = self.piece_group
        group.clear()
        if self.piece:
            size = max(8, int(self.height * 0.8) // 4 * 4)
            tex = piece_texture(self.piece.piece_type, size)
            tw, th = tex.size
            x = self.x + (self.width - tw) / 2
            y = self.y + (self.height - th) / 2
            white = self.piece.color == chess.WHITE
            fill = (0.98, 0.98, 0.98, 1) if white else (0.17, 0.16, 0.15, 1)
            o = max(1, self.height * 0.025)
            for dx, dy in OUTLINE:
                group.add(Color(0.10, 0.10, 0.10, 1))
                group.add(Rectangle(texture=tex, pos=(x + dx * o, y + dy * o), size=(tw, th)))
            group.add(Color(*fill))
            group.add(Rectangle(texture=tex, pos=(x, y), size=(tw, th)))
        cx, cy = self.center_x, self.center_y
        if self.hint == "dot":
            d = self.width * 0.3
            group.add(Color(0, 0, 0, 0.18))
            group.add(Ellipse(pos=(cx - d / 2, cy - d / 2), size=(d, d)))
        elif self.hint == "ring":
            group.add(Color(0, 0, 0, 0.18))
            group.add(Line(circle=(cx, cy, self.width * 0.46), width=self.width * 0.06))


class ChessBoardWidget(AnchorLayout):
    """Square-fitting 8x8 board: draws pieces and arrows, reports clicked squares."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.square_callback = None
        self.arrows = []
        self.grid = GridLayout(cols=8, size_hint=(None, None))
        self.add_widget(self.grid)
        self.squares = {}
        for rank in range(7, -1, -1):
            for file in range(8):
                sq = Square((rank + file) % 2 != 0,
                            rank_text=str(rank + 1) if file == 0 else None,
                            file_text=chr(97 + file) if rank == 0 else None)
                self.squares[chess.square(file, rank)] = sq
                self.grid.add_widget(sq)
        self.bind(size=lambda *a: setattr(self.grid, "size", (min(self.size),) * 2))

        # arrows live in the grid's canvas.after so they draw over every square
        self.arrow_group = InstructionGroup()
        self.grid.canvas.after.add(self.arrow_group)
        self.grid.bind(pos=self.draw_arrows, size=self.draw_arrows)

    def on_touch_down(self, touch):
        if getattr(touch, "is_mouse_scrolling", False) or not self.grid.collide_point(*touch.pos):
            return False
        cell = self.grid.width / 8
        file = min(7, int((touch.x - self.grid.x) / cell))
        rank = min(7, int((touch.y - self.grid.y) / cell))
        if self.square_callback:
            self.square_callback(chess.square(file, rank))
        return True

    def update_board(self, board, last_move=None, selected=None, hints=None):
        hints = hints or {}
        marked = {last_move.from_square, last_move.to_square} if last_move else set()
        if selected is not None:
            marked.add(selected)
        checked = board.king(board.turn) if board.is_check() else None
        for sq, widget in self.squares.items():
            if sq == checked:
                mark = CHECK
            elif sq in marked:
                mark = LAST_LIGHT if widget.light else LAST_DARK
            else:
                mark = None
            widget.set_state(board.piece_at(sq), mark, hints.get(sq))

    def set_arrows(self, moves):
        self.arrows = moves
        self.draw_arrows()

    def draw_arrows(self, *args):
        self.arrow_group.clear()
        cell = self.grid.width / 8

        def center(sq):
            return (self.grid.x + (chess.square_file(sq) + 0.5) * cell,
                    self.grid.y + (chess.square_rank(sq) + 0.5) * cell)

        for i, move in enumerate(self.arrows):
            alpha, scale = ((0.9, 1.0), (0.55, 0.75), (0.4, 0.6))[i]
            a, b = center(move.from_square), center(move.to_square)
            df = abs(chess.square_file(move.to_square) - chess.square_file(move.from_square))
            dr = abs(chess.square_rank(move.to_square) - chess.square_rank(move.from_square))
            points = [a, b]
            if {df, dr} == {1, 2}:  # knight moves bend, as on chess.com
                points = [a, (b[0], a[1]) if df == 2 else (a[0], b[1]), b]

            (px, py), (bx, by) = points[-2], points[-1]
            length = math.hypot(bx - px, by - py)
            ux, uy = (bx - px) / length, (by - py) / length
            head, half = cell * 0.38 * scale ** 0.5, cell * 0.2 * scale ** 0.5
            base = (bx - ux * head, by - uy * head)
            shaft = points[:-1] + [base]

            self.arrow_group.add(Color(*ARROW, alpha))
            self.arrow_group.add(Line(points=[c for p in shaft for c in p],
                                      width=cell * 0.09 * scale, joint="round"))
            self.arrow_group.add(Triangle(points=[
                bx, by,
                base[0] - uy * half, base[1] + ux * half,
                base[0] + uy * half, base[1] - ux * half,
            ]))


class EvalBar(Widget):
    """Vertical bar: White's share fills from the bottom, Black's from the top."""
    def __init__(self, **kwargs):
        super().__init__(size_hint_x=None, width=dp(34), **kwargs)
        self.share = 0.5
        with self.canvas:
            Color(0.25, 0.24, 0.22, 1)
            self.black_rect = Rectangle()
            Color(0.97, 0.97, 0.97, 1)
            self.white_rect = Rectangle()
        self.label = Label(text="0.0", bold=True, font_size="11sp", size_hint=(None, None))
        self.add_widget(self.label)
        self.bind(pos=self.redraw, size=self.redraw)

    def set_eval(self, share, text):
        self.share = share
        self.label.text = text
        self.redraw()

    def redraw(self, *args):
        x, y = self.pos
        w, h = self.size
        split = h * self.share
        self.white_rect.pos, self.white_rect.size = (x, y), (w, split)
        self.black_rect.pos, self.black_rect.size = (x, y + split), (w, h - split)
        self.label.size = (w, dp(20))
        if self.share >= 0.5:
            self.label.color = (0.25, 0.24, 0.22, 1)
            self.label.pos = (x, y)
        else:
            self.label.color = (1, 1, 1, 1)
            self.label.pos = (x, y + h - dp(20))


class PlayerBar(BoxLayout):
    """Avatar, opening name and material lead, lined up with the board's left edge."""
    def __init__(self, glyph_color, **kwargs):
        # left padding = eval bar width + gap, so the bar starts where the board starts
        super().__init__(size_hint_y=None, height=dp(44), spacing=dp(8),
                         padding=[dp(40), 0, 0, 0], **kwargs)
        avatar = Label(text="♚", font_name=FONT, font_size="26sp", color=glyph_color,
                       size_hint_x=None, width=dp(36))
        with avatar.canvas.before:
            Color(0.32, 0.31, 0.30, 1)
            rect = RoundedRectangle(radius=[dp(4)])
        avatar.bind(pos=lambda a, v: setattr(rect, "pos", v),
                    size=lambda a, v: setattr(rect, "size", v))
        self.add_widget(avatar)
        self.name = left_label(markup=True, font_size="13sp")
        self.add_widget(self.name)
        self.lead = Label(color=MUTED, bold=True, size_hint_x=None, width=dp(50))
        self.add_widget(self.lead)

    def set_text(self, title, subtitle):
        self.name.text = f"[b]{title}[/b]\n[color=9b9995]{subtitle}[/color]"


class MoveCell(ButtonBehavior, Label):
    """One cell of the move list with its own background."""
    def __init__(self, bg, **kwargs):
        super().__init__(font_name=FONT, font_size="15sp", halign="left", valign="middle",
                         padding=(dp(10), 0), markup=True, **kwargs)
        with self.canvas.before:
            Color(*bg)
            self.rect = Rectangle()
        self.bind(pos=self.redraw, size=self.redraw)
        self.bind(size=lambda c, s: setattr(c, "text_size", s))

    def redraw(self, *args):
        self.rect.pos, self.rect.size = self.pos, self.size


class ReviewApp(App):
    def build(self):
        Window.clearcolor = BG
        Window.bind(on_key_down=self.on_key)
        if platform != "android":
            Window.size = (1100, 760)

        self.token = 0  # bumped on every new game so late engine replies are ignored
        self.busy = False
        self.selected = None  # square of the piece the user clicked
        self.show_arrows = True
        self.cache = {}  # position (EPD) -> [(move, PovScore)] top engine lines, [] if analysis failed
        self.pending = set()  # positions with an analysis thread running
        self.wanted = set()  # positions on screen; queued analyses for others are skipped
        self.lock = threading.RLock()  # one engine command at a time
        self.engine = None
        self.engine_error = "Stockfish not found. Install it or add it to PATH (desktop), or bundle libstockfish.so (Android)."
        path = prepare_stockfish_binary()
        if path and os.path.exists(path):
            try:
                self.engine = chess.engine.SimpleEngine.popen_uci(path)
            except Exception as e:
                self.engine_error = f"Engine initialization error: {e}"

        root = BoxLayout(
            orientation="vertical" if platform == "android" else "horizontal",
            padding=dp(16),
            spacing=dp(16),
        )

        # Left: black bar, eval bar + board, white bar
        self.top_bar = PlayerBar((0.08, 0.08, 0.08, 1))
        self.bottom_bar = PlayerBar((0.98, 0.98, 0.98, 1))
        self.eval_bar = EvalBar()
        self.board_widget = ChessBoardWidget()
        self.board_widget.square_callback = self.square_clicked
        board_row = BoxLayout(spacing=dp(6))
        board_row.add_widget(self.eval_bar)
        board_row.add_widget(self.board_widget)

        column = BoxLayout(orientation="vertical", spacing=dp(4), size_hint=(None, None))
        column.add_widget(self.top_bar)
        column.add_widget(board_row)
        column.add_widget(self.bottom_bar)

        # the column is sized so the board is exactly square
        stage = AnchorLayout(size_hint_x=1.4)
        stage.add_widget(column)

        def fit(s, size):
            side = max(dp(100), min(size[0] - dp(40), size[1] - dp(96)))
            column.size = (side + dp(40), side + dp(96))
        stage.bind(size=fit)
        root.add_widget(stage)

        # Right: controls
        panel = Panel(orientation="vertical", spacing=dp(8), padding=dp(12),
                      size_hint_x=1.0 if platform == "android" else 0.8)
        panel.add_widget(left_label(text="Opening Lab", font_size="20sp", bold=True,
                                    size_hint_y=None, height=dp(34)))

        self.white_spinner = self.opening_row(panel, "White", WHITE_OPENINGS)
        self.black_spinner = self.opening_row(panel, "Black", BLACK_OPENINGS)

        self.plan_label = left_label(size_hint_y=None, height=dp(48), font_size="12sp", color=MUTED)
        self.plan_label.valign = "top"
        panel.add_widget(self.plan_label)

        self.move_list = GridLayout(cols=3, size_hint_y=None, row_default_height=dp(34),
                                    row_force_default=True)
        self.move_list.bind(minimum_height=self.move_list.setter("height"))
        self.scroll = ScrollView(bar_width=dp(6))
        self.scroll.add_widget(self.move_list)
        panel.add_widget(self.scroll)

        self.status = left_label(size_hint_y=None, height=dp(24), font_name=FONT,
                                 font_size="13sp", color=MUTED, markup=True)
        panel.add_widget(self.status)

        nav = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        self.nav_btns = []
        for text, target in (("|◀", lambda: 0), ("◀", lambda: self.ply - 1),
                             ("▶", lambda: self.ply + 1), ("▶|", lambda: len(self.moves))):
            btn = FlatButton(text=text, bg=BTN, font_name=FONT, font_size="18sp")
            btn.bind(on_release=lambda b, t=target: self.goto(t()))
            nav.add_widget(btn)
            self.nav_btns.append(btn)
        panel.add_widget(nav)

        actions = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        self.next_btn = FlatButton(text="Next move", bg=GREEN, shadow=GREEN_DARK,
                                   font_size="18sp", bold=True, size_hint_x=0.5)
        self.next_btn.bind(on_release=self.next_move)
        self.arrow_btn = FlatButton(text="Arrows", bg=GREEN_DARK, size_hint_x=0.25)
        self.arrow_btn.bind(on_release=self.toggle_arrows)
        new_btn = FlatButton(text="New game", bg=BTN, size_hint_x=0.25)
        new_btn.bind(on_release=self.new_game)
        actions.add_widget(self.next_btn)
        actions.add_widget(self.arrow_btn)
        actions.add_widget(new_btn)
        panel.add_widget(actions)

        root.add_widget(panel)

        self.on_opening_changed()
        self.new_game()
        if not self.engine:
            self.status.text = self.engine_error
        return root

    def opening_row(self, panel, name, openings):
        row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        row.add_widget(left_label(text=name, color=MUTED, size_hint_x=0.22))
        spinner = FlatSpinner(text=list(openings)[1], values=list(openings),
                              option_cls=Option, bg=BTN)
        spinner.bind(text=self.on_opening_changed)
        row.add_widget(spinner)
        panel.add_widget(row)
        return spinner

    def on_opening_changed(self, *args):
        white, black = self.white_spinner.text, self.black_spinner.text
        self.bottom_bar.set_text(white, "White")
        self.top_bar.set_text(black, "Black")
        self.plan_label.text = (
            f"White plan: {' '.join(WHITE_OPENINGS[white]) or 'Stockfish picks every move'}\n"
            f"Black plan: {' '.join(BLACK_OPENINGS[black]) or 'Stockfish picks every move'}"
        )

    def on_key(self, window, key, *args):
        if key == 276:  # left arrow
            self.goto(self.ply - 1)
        elif key == 275:  # right arrow
            self.next_move()

    def toggle_arrows(self, *args):
        self.show_arrows = not self.show_arrows
        self.arrow_btn.bg = GREEN_DARK if self.show_arrows else BTN
        self.arrow_btn.redraw()
        self.refresh()

    # --- game state: self.moves[:self.ply] is the position on screen ---

    def new_game(self, *args):
        self.token += 1
        self.busy = False
        self.selected = None
        self.moves = []
        self.sans = []
        self.tags = []  # "book", "engine" or "you" for each move
        self.ply = 0
        self.refresh()

    def board_at(self, ply):
        board = chess.Board()
        for move in self.moves[:ply]:
            board.push(move)
        return board

    def position_keys(self):
        """EPD of every position in the game, index 0 = start. Used as analysis cache keys."""
        board = chess.Board()
        keys = [board.epd()]
        for move in self.moves:
            board.push(move)
            keys.append(board.epd())
        return keys

    def goto(self, ply):
        self.ply = max(0, min(ply, len(self.moves)))
        self.selected = None
        self.refresh()

    def next_move(self, *args):
        if self.busy:
            return
        if self.ply < len(self.moves):
            self.goto(self.ply + 1)
            return

        board = self.board_at(self.ply)
        if board.is_game_over():
            return
        if self.engine is None:
            self.status.text = self.engine_error
            return

        white = board.turn == chess.WHITE
        name = (self.white_spinner if white else self.black_spinner).text
        wishes = (WHITE_OPENINGS if white else BLACK_OPENINGS)[name]
        mine = self.sans[0::2] if white else self.sans[1::2]
        played = {san.rstrip("+#") for san in mine}

        self.busy = True
        self.selected = None
        self.refresh()
        threading.Thread(target=self.think, args=(board, wishes, played, self.token),
                         daemon=True).start()

    def square_clicked(self, sq):
        if self.busy:
            return
        board = self.board_at(self.ply)
        if board.is_game_over():
            return

        if self.selected is not None:
            move = chess.Move(self.selected, sq)
            piece = board.piece_at(self.selected)
            if piece and piece.piece_type == chess.PAWN and chess.square_rank(sq) in (0, 7):
                move.promotion = chess.QUEEN  # always promotes to a queen
            if move in board.legal_moves:
                self.selected = None
                self.play_user_move(board, move)
                return

        piece = board.piece_at(sq)
        self.selected = sq if piece and piece.color == board.turn and sq != self.selected else None
        self.draw_board(board)

    def play_user_move(self, board, move):
        if self.ply < len(self.moves) and self.moves[self.ply] == move:
            self.goto(self.ply + 1)  # same move as the game: just step forward
            return
        # a different move: the old continuation is dropped and the game goes on from here
        del self.moves[self.ply:], self.sans[self.ply:], self.tags[self.ply:]
        self.sans.append(board.san(move))
        self.moves.append(move)
        self.tags.append("you")
        self.goto(len(self.moves))

    # --- engine work (worker threads) ---

    def lines_for(self, board, wanted_only=False):
        """Cached top lines for a position, analysing it if needed. None when the game is over."""
        if board.is_game_over():
            return None
        key = board.epd()
        with self.lock:
            if key not in self.cache and not (wanted_only and key not in self.wanted):
                self.cache[key] = analyse_lines(self.engine, board)
            return self.cache.get(key)

    def think(self, board, wishes, played, token):
        try:
            lines = self.lines_for(board)
            if not lines:
                raise RuntimeError("engine returned no analysis")
            with self.lock:
                move, tag = pick_move(self.engine, board, wishes, played, lines)
            after = board.copy()
            after.push(move)
            self.lines_for(after)  # so the new position's eval and arrows are ready on arrival
        except Exception as e:
            Clock.schedule_once(lambda dt, err=e: self.failed(err, token))
            return
        Clock.schedule_once(lambda dt: self.apply(move, tag, token))

    def analyse_job(self, board, key):
        try:
            self.lines_for(board, wanted_only=True)
        except Exception:
            self.cache[key] = []  # stops refresh from retrying forever
        self.pending.discard(key)
        Clock.schedule_once(lambda dt: self.refresh())

    def request_analysis(self, keys):
        """Analyse the position on screen and the one before it (needed to grade the last move)."""
        plies = [p for p in (self.ply, self.ply - 1) if p >= 0]
        self.wanted = {keys[p] for p in plies}
        if not self.engine:
            return
        for p in plies:
            key = keys[p]
            if key in self.cache or key in self.pending:
                continue
            board = self.board_at(p)
            if board.is_game_over():
                continue
            self.pending.add(key)
            threading.Thread(target=self.analyse_job, args=(board, key), daemon=True).start()

    def apply(self, move, tag, token):
        if token != self.token:
            return  # new game started while the engine was thinking
        self.busy = False
        at_end = self.ply == len(self.moves)
        self.sans.append(self.board_at(len(self.moves)).san(move))
        self.moves.append(move)
        self.tags.append(tag)
        self.goto(len(self.moves) if at_end else self.ply)

    def failed(self, error, token):
        if token != self.token:
            return
        self.busy = False
        self.refresh()
        self.status.text = f"Engine error: {error}"

    # --- grading ---

    def grade(self, j, keys):
        """(label, color) for move j, or None until both positions around it are analysed."""
        if self.tags[j] == "book":
            return BOOK
        before = self.cache.get(keys[j])
        if not before:
            return None
        if self.moves[j] == before[0][0]:
            return BEST

        if j + 1 == len(self.moves) and self.board_at(j + 1).is_game_over():
            after = {"1-0": 1.0, "0-1": 0.0}.get(self.board_at(j + 1).result(), 0.5)
        elif self.cache.get(keys[j + 1]):
            after = white_share(self.cache[keys[j + 1]][0][1])
        else:
            return None

        lost = white_share(before[0][1]) - after
        if j % 2:  # Black moved: a rise in White's share is Black's loss
            lost = -lost
        for limit, label, color in GRADES:
            if lost <= limit:
                return label, color

    # --- drawing ---

    def draw_board(self, board):
        last = self.moves[self.ply - 1] if self.ply else None
        hints = {}
        if self.selected is not None:
            for m in board.legal_moves:
                if m.from_square == self.selected:
                    hints[m.to_square] = "ring" if board.is_capture(m) else "dot"
        self.board_widget.update_board(board, last, self.selected, hints)

    def refresh(self):
        board = self.board_at(self.ply)
        keys = self.position_keys()
        self.request_analysis(keys)
        lines = self.cache.get(keys[self.ply])

        self.draw_board(board)
        shown = [m for m, s in lines[:3]] if lines and self.show_arrows else []
        self.board_widget.set_arrows(shown)

        if board.is_game_over():
            result = board.result()
            self.eval_bar.set_eval({"1-0": 1.0, "0-1": 0.0}.get(result, 0.5),
                                   result if result in ("1-0", "0-1") else "=")
        elif lines:
            self.eval_bar.set_eval(white_share(lines[0][1]), score_text(lines[0][1]))

        diff = material(board, chess.WHITE) - material(board, chess.BLACK)
        self.bottom_bar.lead.text = f"+{diff}" if diff > 0 else ""
        self.top_bar.lead.text = f"+{-diff}" if diff < 0 else ""

        if self.busy:
            text = "Thinking..."
        elif self.ply == 0:
            text = "Start position. Click a piece to play your own move."
        else:
            i = self.ply - 1
            grade = self.grade(i, keys)
            dots = "." if i % 2 == 0 else "..."
            label = grade[0] if grade else ("Analysing" if self.engine else "")
            text = f"{label}: {i // 2 + 1}{dots} {figurine(self.sans[i])}"
            if grade and grade[0] in ("Inaccuracy", "Mistake", "Blunder"):
                best = self.board_at(i).san(self.cache[keys[i]][0][0])
                text += f"   Best was {figurine(best)}"
        if board.is_game_over():
            text += f"   Game over {board.result()}"
        self.status.text = text

        for btn in self.nav_btns[:2]:
            btn.disabled = self.ply == 0
        for btn in self.nav_btns[2:]:
            btn.disabled = self.ply == len(self.moves)
        self.next_btn.disabled = self.busy or (self.ply == len(self.moves) and board.is_game_over())
        self.rebuild_list(keys)

    def rebuild_list(self, keys):
        self.move_list.clear_widgets()
        for i in range(0, len(self.moves), 2):
            bg = ROW_ALT if (i // 2) % 2 else PANEL
            self.move_list.add_widget(MoveCell(bg, text=f"{i // 2 + 1}.", color=MUTED, size_hint_x=0.2))
            for j in (i, i + 1):
                if j >= len(self.moves):
                    self.move_list.add_widget(MoveCell(bg, size_hint_x=0.4))
                    continue
                current = j + 1 == self.ply
                grade = self.grade(j, keys)
                dot = hex_color(grade[1] if grade else PENDING)
                cell = MoveCell(CUR if current else bg, bold=current, size_hint_x=0.4, color=TEXT,
                                text=f"[color={dot}]●[/color] {figurine(self.sans[j])}")
                cell.bind(on_release=lambda c, p=j + 1: self.goto(p))
                self.move_list.add_widget(cell)
        # follow the newest move once the list is taller than the view, else stay at the top
        Clock.schedule_once(lambda dt: setattr(
            self.scroll, "scroll_y",
            0 if self.ply == len(self.moves) and self.move_list.height > self.scroll.height else 1))

    def on_stop(self):
        engine, self.engine = self.engine, None
        if engine:
            engine.quit()


if __name__ == "__main__":
    ReviewApp().run()
