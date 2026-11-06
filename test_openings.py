import unittest

import chess

from openings import OPENINGS_DATABASE, DynamicOpeningEngine


class OpeningIdentityTests(unittest.TestCase):
    """Each opening must open with its signature central pawn push.

    Regression test: the +5 development bonus (knights = 15) used to beat
    pawn target squares (+10), so White opened Nf3/Nc3 instead of d4/e4.
    """

    def _replay(self, key, plies=8):
        board = chess.Board()
        config = OPENINGS_DATABASE[key]
        sans = []
        for _ in range(plies):
            move = DynamicOpeningEngine.select_opening_move(board, config)
            self.assertIsNotNone(move)
            sans.append(board.san(move))
            board.push(move)
        self.assertTrue(board.is_valid())
        return sans

    def test_london_opens_d4(self):
        self.assertEqual(self._replay("London System vs KID")[:2], ["d4", "Nf6"])

    def test_sicilian_opens_e4_c5(self):
        self.assertEqual(self._replay("Sicilian Defense (Najdorf)")[:3], ["e4", "c5", "Nf3"])

    def test_qgd_opens_d4_d5(self):
        self.assertEqual(self._replay("Queen's Gambit Declined")[:3], ["d4", "d5", "c4"])

    def test_all_openings_play_8_legal_plies(self):
        for key in OPENINGS_DATABASE:
            parts = self._replay(key)
            self.assertEqual(len(parts), 8)

    def test_returns_none_when_nothing_scores_above_zero(self):
        """0-score moves must return None so Stockfish takes over, not a random move.

        The QGD classical line (d4 d5 c4 Nf6 Nc3 e6 Bg5 Be7) uses up every scoring
        option; with fullmove > 4 even the +5 dev bonus is gone, so White has
        nothing scoring. Old code returned the first legal move instead.
        """
        key = "Queen's Gambit Declined"
        config = OPENINGS_DATABASE[key]
        board = chess.Board()
        for _ in range(config["max_opening_ply"]):
            move = DynamicOpeningEngine.select_opening_move(board, config)
            self.assertIsNotNone(move, "should still be in book at ply 8")
            board.push(move)
        self.assertTrue(board.is_valid())
        self.assertIsNone(
            DynamicOpeningEngine.select_opening_move(board, config),
            "out of book: must return None instead of playing a 0-score move",
        )

    def test_piece_on_target_does_not_retarget(self):
        """After 1.d4 d5 the engine must not push d4-d5: the d-pawn already sits
        on a preferred square. Old code scored that 37 and hung the pawn to ...exd5."""
        board = chess.Board()
        board.push_san("d4")
        board.push_san("d5")
        move = DynamicOpeningEngine.select_opening_move(
            board, OPENINGS_DATABASE["Queen's Gambit Declined"]
        )
        self.assertIsNotNone(move)
        self.assertNotEqual(move.uci(), "d4d5")


if __name__ == "__main__":
    unittest.main()
