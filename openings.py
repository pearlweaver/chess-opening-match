import chess
import chess.engine

# Each opening is a priority list of SAN moves. On every turn the first move in the
# list that is legal, not yet played by that side, and not a blunder is chosen.
# When nothing qualifies, Stockfish picks the move.
WHITE_OPENINGS = {
    "Stockfish (no book)": [],
    "London System": ["d4", "Nf3", "Bf4", "e3", "c3", "Nbd2", "Bd3", "O-O"],
    "Queen's Gambit": ["d4", "c4", "Nc3", "Nf3", "Bg5", "e3", "Bd3", "O-O"],
    "Catalan": ["d4", "c4", "g3", "Bg2", "Nf3", "O-O", "Nc3"],
    "English Opening": ["c4", "Nc3", "g3", "Bg2", "Nf3", "O-O", "d3"],
    "King's Indian Attack": ["Nf3", "g3", "Bg2", "O-O", "d3", "Nbd2", "e4"],
    "Ruy Lopez": ["e4", "Nf3", "Bb5", "O-O", "Re1", "c3", "d4"],
    "Italian Game": ["e4", "Nf3", "Bc4", "c3", "d3", "O-O", "Re1"],
    "Scotch Game": ["e4", "Nf3", "d4", "Nxd4", "Nc3", "Bc4"],
}

BLACK_OPENINGS = {
    "Stockfish (no book)": [],
    "Sicilian Najdorf": ["c5", "d6", "cxd4", "Nf6", "a6", "e5", "Be7", "O-O"],
    "King's Indian Defense": ["Nf6", "g6", "Bg7", "d6", "O-O", "Nbd7", "e5"],
    "Queen's Gambit Declined": ["d5", "e6", "Nf6", "Be7", "O-O", "Nbd7", "c6"],
    "Slav Defense": ["d5", "c6", "Nf6", "dxc4", "Bf5", "e6", "Nbd7"],
    "Nimzo-Indian Defense": ["Nf6", "e6", "Bb4", "O-O", "c5", "Nc6"],
    "French Defense": ["e6", "d5", "c5", "Nc6", "Nf6", "Be7", "O-O"],
    "Caro-Kann Defense": ["c6", "d5", "dxe4", "Bf5", "Nd7", "Nf6", "e6"],
    "Pirc Defense": ["d6", "Nf6", "g6", "Bg7", "O-O", "c6"],
    "Scandinavian Defense": ["d5", "Qxd5", "Qa5", "Nf6", "c6", "Bf5", "e6"],
}

# A book move is skipped if the engine rates it this many centipawns below its best move.
TOLERANCE = 100
MATE_SCORE = 10000


def analyse_lines(engine, board, seconds=0.4, count=3):
    """Top engine lines for a position as [(move, PovScore)], best first."""
    infos = engine.analyse(board, chess.engine.Limit(time=seconds), multipv=count)
    return [(info["pv"][0], info["score"]) for info in infos if "pv" in info]


def pick_move(engine, board, wishes, played, lines):
    """Returns (move, "book" or "engine"). lines is analyse_lines() for this position."""
    best_move, best_score = lines[0]

    candidates = []
    for san in wishes:
        if san in played:
            continue
        try:
            candidates.append(board.parse_san(san))
        except ValueError:
            pass  # illegal or ambiguous in this position

    if candidates:
        infos = engine.analyse(
            board,
            chess.engine.Limit(time=0.15),
            root_moves=candidates,
            multipv=len(candidates),
        )
        scores = {info["pv"][0]: info["score"] for info in infos if "pv" in info}
        floor = best_score.relative.score(mate_score=MATE_SCORE) - TOLERANCE
        for move in candidates:
            score = scores.get(move)
            if score and score.relative.score(mate_score=MATE_SCORE) >= floor:
                return move, "book"

    return best_move, "engine"
