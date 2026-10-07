"""Deterministic tactical facts and a blunder guard, computed with python-chess.

The LLM is bad at board geometry (it has called g1-f2 a knight move), so every
spatial fact the agent relies on is computed here instead: adjacency around
each king, attackers and defenders of every piece, discovered-check batteries,
pins, immediate mates, and a shallow material search used to veto blunders.

This file is self-contained on purpose. When python-chess is not installed in
the agent process, ``ChessAgent`` uploads this file into the sandbox (which has
python-chess for the chess server) and runs it as a script:

    python chess_analysis.py analyze '<fen>'
    python chess_analysis.py check '<fen>' <uci>

Each command prints exactly one JSON object on its last line.
"""

from __future__ import annotations

import json
import sys
from typing import Any

try:  # Optional locally; always present in the sandbox.
    import chess
except ImportError:  # pragma: no cover - depends on the environment
    chess = None

PIECE_VALUES = {1: 100, 2: 320, 3: 330, 4: 500, 5: 900, 6: 0}
MATE_SCORE = 100_000
# A move scoring this far below the best alternative is treated as a blunder.
BLUNDER_MARGIN_CP = 300


def available() -> bool:
    return chess is not None


def _label(board: "chess.Board", square: int) -> str:
    piece = board.piece_at(square)
    symbol = piece.symbol() if piece else "."
    return f"{chess.square_name(square)}({symbol})"


def _side(color: bool) -> str:
    return "White" if color else "Black"


def _material(board: "chess.Board", color: bool) -> int:
    score = 0
    for piece in board.piece_map().values():
        value = PIECE_VALUES[piece.piece_type]
        score += value if piece.color == color else -value
    return score


def _mates_in_one(board: "chess.Board") -> list[str]:
    mates = []
    for move in board.legal_moves:
        board.push(move)
        if board.is_checkmate():
            mates.append(move.uci())
        board.pop()
    return sorted(mates)


def _pieces_by_file(board: "chess.Board") -> list[str]:
    lines = []
    for file_index, file_name in enumerate("abcdefgh"):
        occupants = [
            _label(board, chess.square(file_index, rank))
            for rank in range(8)
            if board.piece_at(chess.square(file_index, rank))
        ]
        if occupants:
            lines.append(f"{file_name}-file: " + ", ".join(occupants))
    return lines


def _king_zone(board: "chess.Board", color: bool) -> str:
    king = board.king(color)
    if king is None:
        return f"{_side(color)} king: missing"
    cells = []
    for square in sorted(chess.SquareSet(chess.BB_KING_ATTACKS[king])):
        piece = board.piece_at(square)
        if piece is None:
            occupant = "empty"
        elif piece.color == color:
            occupant = f"own {piece.symbol()}"
        else:
            occupant = f"enemy {piece.symbol()}"
        enemy = board.is_attacked_by(not color, square)
        if piece is not None and piece.color != color:
            status = "defended" if enemy else "UNDEFENDED, king can capture it"
        else:
            status = "ATTACKED" if enemy else "safe"
        cells.append(f"{chess.square_name(square)}[{occupant}, {status}]")
    return (
        f"{_side(color)} king on {chess.square_name(king)}; adjacent squares "
        f"(distance 1, the king can step or capture here): " + " ".join(cells)
    )


def _threatened_pieces(board: "chess.Board", color: bool) -> list[str]:
    """Pieces of ``color`` attacked by a cheaper piece or attacked and undefended."""

    rows = []
    for square, piece in board.piece_map().items():
        if piece.color != color or piece.piece_type == chess.KING:
            continue
        attackers = board.attackers(not color, square)
        if not attackers:
            continue
        defenders = board.attackers(color, square)
        cheapest = min(PIECE_VALUES[board.piece_type_at(a)] or 10_000 for a in attackers)
        if defenders and cheapest >= PIECE_VALUES[piece.piece_type]:
            continue
        rows.append(
            f"{_label(board, square)} attacked by "
            f"{', '.join(_label(board, a) for a in sorted(attackers))}; defenders: "
            f"{', '.join(_label(board, d) for d in sorted(defenders)) or 'NONE'}"
        )
    return sorted(rows)


def _discovered_batteries(board: "chess.Board", color: bool) -> list[str]:
    """Own slider aimed at the enemy king with exactly one own piece in between."""

    enemy_king = board.king(not color)
    if enemy_king is None:
        return []
    rows = []
    for square, piece in board.piece_map().items():
        if piece.color != color or piece.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
            continue
        if not chess.ray(square, enemy_king):
            continue
        orthogonal = (
            chess.square_file(square) == chess.square_file(enemy_king)
            or chess.square_rank(square) == chess.square_rank(enemy_king)
        )
        if orthogonal and piece.piece_type == chess.BISHOP:
            continue
        if not orthogonal and piece.piece_type == chess.ROOK:
            continue
        between = list(chess.SquareSet(chess.between(square, enemy_king)))
        blockers = [s for s in between if board.piece_at(s)]
        if len(blockers) == 1 and board.piece_at(blockers[0]).color == color:
            rows.append(
                f"{_label(board, square)} -> {_label(board, blockers[0])} -> "
                f"{_label(board, enemy_king)}: moving {_label(board, blockers[0])} "
                "gives a DISCOVERED CHECK"
            )
    return sorted(rows)


def _pins(board: "chess.Board", color: bool) -> list[str]:
    return sorted(
        f"{_label(board, square)} is pinned to its king"
        for square, piece in board.piece_map().items()
        if piece.color == color and piece.piece_type != chess.KING and board.is_pinned(color, square)
    )


def _checks(board: "chess.Board") -> list[str]:
    rows = []
    for move in sorted(board.legal_moves, key=lambda m: m.uci()):
        if not board.gives_check(move):
            continue
        san = board.san(move)
        board.push(move)
        checkers = board.checkers()
        mate = board.is_checkmate()
        board.pop()
        tags = []
        if len(checkers) >= 2:
            tags.append("DOUBLE CHECK")
        elif move.to_square not in checkers:
            tags.append("discovered")
        if mate:
            tags.append("CHECKMATE")
        rows.append(f"{move.uci()} ({san}{', ' + ', '.join(tags) if tags else ''})")
    return rows


def _captures(board: "chess.Board") -> list[str]:
    rows = []
    for move in sorted(board.legal_moves, key=lambda m: m.uci()):
        if not board.is_capture(move):
            continue
        victim = board.piece_at(move.to_square)
        victim_value = PIECE_VALUES[victim.piece_type] if victim else 100  # en passant
        defended = board.is_attacked_by(not board.turn, move.to_square)
        rows.append(
            f"{move.uci()} ({board.san(move)}, wins {victim_value}cp, "
            f"target {'defended' if defended else 'UNDEFENDED'})"
        )
    return rows


def _opponent_threats(board: "chess.Board") -> list[str]:
    """What the opponent could do if it were their move (null-move probe)."""

    if board.is_check():
        return []
    board.push(chess.Move.null())
    try:
        mates = _mates_in_one(board)
    finally:
        board.pop()
    return [f"opponent threatens mate with {uci}" for uci in mates]


def _score_move(board: "chess.Board", move: "chess.Move") -> int:
    """Material after: our move, the opponent's best reply, our best capture."""

    me = board.turn
    board.push(move)
    try:
        if board.is_checkmate():
            return MATE_SCORE
        if board.is_game_over(claim_draw=True):
            return 0
        worst = None
        for reply in list(board.legal_moves):
            board.push(reply)
            try:
                if board.is_checkmate():
                    value = -MATE_SCORE
                else:
                    value = _material(board, me)
                    for capture in list(board.generate_legal_captures()):
                        board.push(capture)
                        value = max(value, _material(board, me))
                        board.pop()
            finally:
                board.pop()
            if worst is None or value < worst:
                worst = value
        return _material(board, me) if worst is None else worst
    finally:
        board.pop()


def ranked_moves(board: "chess.Board") -> list[tuple[int, str, str]]:
    ranked = [
        (_score_move(board, move), move.uci(), board.san(move))
        for move in sorted(board.legal_moves, key=lambda m: m.uci())
    ]
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return ranked


def analyze(fen: str) -> dict[str, Any]:
    """Facts about the position for the side to move."""

    board = chess.Board(fen)
    me = board.turn
    if board.is_game_over(claim_draw=True):
        return {"fen": fen, "game_over": True}
    ranked = ranked_moves(board)
    return {
        "fen": fen,
        "side_to_move": _side(me),
        "game_over": False,
        "material_balance_cp": _material(board, me),
        "mate_in_one": _mates_in_one(board),
        "checks": _checks(board),
        "captures": _captures(board),
        "discovered_check_batteries": _discovered_batteries(board, me),
        "my_threatened_pieces": _threatened_pieces(board, me),
        "enemy_threatened_pieces": _threatened_pieces(board, not me),
        "my_pinned_pieces": _pins(board, me),
        "opponent_threats": _opponent_threats(board),
        "king_zones": [_king_zone(board, me), _king_zone(board, not me)],
        "pieces_by_file": _pieces_by_file(board),
        "engine_top_moves": [
            {"uci": uci, "san": san, "score_cp": score} for score, uci, san in ranked[:3]
        ],
    }


def check_move(fen: str, uci: str) -> dict[str, Any]:
    """Decide whether ``uci`` should be vetoed as a blunder in ``fen``."""

    board = chess.Board(fen)
    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        return {"verdict": "allow", "reason": "unparseable; the server will reject it"}
    if move not in board.legal_moves:
        return {"verdict": "allow", "reason": "illegal; the server will reject it"}

    mates = _mates_in_one(board)
    if mates and uci not in mates:
        return {
            "verdict": "block",
            "reason": f"{uci} misses a forced win: {', '.join(mates)} is CHECKMATE in one.",
            "suggest": mates,
        }

    ranked = ranked_moves(board)
    scores = {move_uci: score for score, move_uci, _ in ranked}
    best_score, best_uci, _ = ranked[0]
    mine = scores[uci]
    suggest = [move_uci for _, move_uci, _ in ranked[:3]]
    if mine <= -MATE_SCORE and best_score > -MATE_SCORE:
        return {
            "verdict": "block",
            "reason": f"{uci} allows the opponent to checkmate you on the next move.",
            "suggest": suggest,
        }
    if best_score - mine >= BLUNDER_MARGIN_CP:
        return {
            "verdict": "block",
            "reason": (
                f"{uci} loses about {best_score - mine}cp of material compared with "
                f"{best_uci} (2-ply search with recapture)."
            ),
            "suggest": suggest,
        }
    return {"verdict": "allow", "score_cp": mine, "best": best_uci, "best_score_cp": best_score}


def format_facts(facts: dict[str, Any]) -> str:
    """Render ``analyze`` output as an observation block for the model."""

    if not facts or facts.get("game_over"):
        return ""

    def section(title: str, rows: list[str]) -> str:
        return f"{title}:\n" + ("\n".join(f"  - {row}" for row in rows) if rows else "  - none")

    top = [
        f"{m['uci']} ({m['san']}, score {m['score_cp']}cp)" for m in facts.get("engine_top_moves", [])
    ]
    parts = [
        "<tactical_facts source=\"python-chess, exact\">",
        f"material_balance (your view): {facts.get('material_balance_cp')}cp",
        section("MATE IN ONE (play it!)", facts.get("mate_in_one", [])),
        section("opponent threats", facts.get("opponent_threats", [])),
        section("your pieces under threat", facts.get("my_threatened_pieces", [])),
        section("enemy pieces you can win", facts.get("enemy_threatened_pieces", [])),
        section("discovered-check batteries", facts.get("discovered_check_batteries", [])),
        section("your pinned pieces", facts.get("my_pinned_pieces", [])),
        section("checks available", facts.get("checks", [])),
        section("captures available", facts.get("captures", [])),
        section("king neighbourhoods", facts.get("king_zones", [])),
        section("pieces by file", facts.get("pieces_by_file", [])),
        section("search top moves (2-ply material)", top),
        "</tactical_facts>",
    ]
    return "\n".join(parts)


if __name__ == "__main__":  # pragma: no cover - exercised in the sandbox
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if command == "analyze":
            result = analyze(sys.argv[2])
        elif command == "check":
            result = check_move(sys.argv[2], sys.argv[3])
        else:
            result = {"error": f"unknown command {command!r}"}
    except Exception as exc:  # report, never crash the caller
        result = {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result))
