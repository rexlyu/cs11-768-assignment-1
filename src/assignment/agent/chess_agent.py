"""The Part 3 chess agent: reuse the shared loop with one new domain tool."""

from __future__ import annotations

import base64
import json
import re
import shlex
from pathlib import Path
from typing import Any

import httpx

from assignment.agent import chess_analysis
from assignment.agent.base import (
    DEFAULT_COMPACTION_KEEP_RECENT_STEPS,
    DEFAULT_COMPACTION_MAX_TOKENS,
    Agent,
)
from assignment.agent.chess_tools import (
    _game_state,
    _invoke_skill,
    _play_move,
    CHESS_PORT,
    _run_python,
    _simulate_move,
)
from assignment.agent.tools import (
    INVOKE_SKILL_TOOL,
    PLAY_MOVE_TOOL,
    RUN_PYTHON_TOOL,
    SIMULATE_MOVE_TOOL,
)
from assignment.prompts import (
    CHESS_AGENT_NO_LEGAL_MOVES_PROMPT_TEMPLATE,
    CHESS_AGENT_SYSTEM_PROMPT_TEMPLATE,
    PROGRAMMATIC_CHESS_PROMPT,
)
from assignment.env import Environment

# Where chess_analysis.py is uploaded when python-chess is only in the sandbox.
ANALYSIS_PATH = "/tmp/chess_analysis.py"
# After this many vetoes in one position the model's choice is let through.
MAX_GUARD_BLOCKS_PER_POSITION = 2

TACTICAL_ASSIST_PROMPT = """Every observation ends with a <tactical_facts> block computed
exactly by python-chess: king neighbourhoods (adjacency), attackers and defenders,
discovered-check batteries, pins, available checks and captures, mates in one, and a
2-ply material search. These facts are ground truth. Do NOT re-derive board geometry,
distances, or attack lines yourself; your own coordinate arithmetic is unreliable.

Decide in this order and keep reasoning short:
1. If MATE IN ONE lists a move, play it.
2. If an opponent threat or one of your threatened pieces is listed, address it.
3. Otherwise prefer winning captures and forcing checks that the search ranks highly,
   then sound development and king safety.
A blunder guard re-checks every move; if it rejects yours, pick one of its candidates."""

def format_chess_state(
    state: dict[str, Any], *, include_legal_moves: bool = True
) -> str:
    """Turn chess API JSON into a compact observation an LLM can act on."""

    squares = state.get("squares", {})
    board_lines = ["    a b c d e f g h"]
    for rank in range(8, 0, -1):
        pieces = [squares.get(f"{file}{rank}", ".") for file in "abcdefgh"]
        board_lines.append(f"{rank} | {' '.join(pieces)} | {rank}")
    board_lines.append("    a b c d e f g h")

    recent_history = state.get("history", [])[-8:]
    history = (
        " ".join(
            f"{item.get('ply', '?')}:{item.get('san', '?')}" for item in recent_history
        )
        or "(none)"
    )
    legal_moves = " ".join(state.get("legal_moves", [])) or "(none)"
    board_text = "\n".join(board_lines)

    observation = (
        "<chess_state>\n"
        f"status: {state.get('status', 'unknown')}\n"
        f"turn: {state.get('turn', 'unknown')}\n"
        f"in_check: {state.get('in_check', False)}\n"
        f"game_over: {state.get('game_over', False)}\n"
        f"fen: {state.get('fen', '')}\n"
        f"human_move: {state.get('human_move') or '(none)'}\n"
        f"engine_move: {state.get('engine_move') or '(none)'}\n"
        "board:\n"
        f"{board_text}\n"
        f"recent_history: {history}\n"
    )
    if include_legal_moves:
        observation += f"legal_moves: {legal_moves}\n"
    return observation + "</chess_state>"


class ChessAgent(Agent):
    """An agent that plays White against the server's deterministic Black bot."""

    def __init__(
        self,
        environment: Environment,
        model: str | None = None,
        logs_save_path: str | None = None,
        step_limit: int = 200,
        skills_path: str | None = None,
        auto_stop_environment: bool = True,
        http_client: Any | None = None,
        reset_game: bool = True,
        compact_threshold_tokens: int | None = None,
        compaction_keep_recent_steps: int = None,
        compaction_max_tokens: int = None,
        programmatic_tools: bool = False,
        python_sandbox_port: int = CHESS_PORT,
        include_legal_moves: bool = True,
        tactical_assist: bool = False,
    ):
        super().__init__(
            environment=environment,
            model=model,
            logs_save_path=logs_save_path,
            step_limit=step_limit,
            skills_path=skills_path,
            auto_stop_environment=auto_stop_environment,
            compact_threshold_tokens=compact_threshold_tokens,
            compaction_keep_recent_steps=compaction_keep_recent_steps,
            compaction_max_tokens=compaction_max_tokens,
        )

        # TODO(Part 3): Register the play_move tool schema from tools.py.
        self.tools.append(PLAY_MOVE_TOOL)

        if programmatic_tools:
            self.tools.append(SIMULATE_MOVE_TOOL)
            self.tools.append(RUN_PYTHON_TOOL)

        # run_python always executes in the sandbox, on the port the chess
        # server is listening on there.
        self.python_sandbox_port = python_sandbox_port
        self.include_legal_moves = include_legal_moves

        # Opt-in symbolic layer: python-chess computes geometry/tactics and
        # vetoes blunders, so the model never does board geometry in prose.
        self.tactical_assist = tactical_assist
        self._analysis_uploaded = False
        self._guard_blocks: dict[str, int] = {}

        if http_client is None:
            server_url = getattr(environment, "server_url", "")
            if not server_url:
                raise ValueError(
                    "ChessAgent needs an environment with server_url or an http_client."
                )
            http_client = httpx.Client(base_url=server_url, timeout=20)
        self.chess_client = http_client

        initial_state = _game_state(self.chess_client, reset=reset_game)
        self.last_state = initial_state
        self.finished = bool(initial_state.get("game_over"))
        prompt_template = (
            CHESS_AGENT_SYSTEM_PROMPT_TEMPLATE
            if include_legal_moves
            else CHESS_AGENT_NO_LEGAL_MOVES_PROMPT_TEMPLATE
        )
        self.system_prompt = prompt_template.render()
        if programmatic_tools:
            self.system_prompt += "\n\n" + PROGRAMMATIC_CHESS_PROMPT
        if self.skills:
            catalog = "\n".join(skill["metadata"] for skill in self.skills.values())
            self.system_prompt += (
                "\n\nReusable skills are available. Call `invoke_skill` with a "
                "skill's name to load its instructions, and follow them in place "
                f"of your default approach.\n\n<skills>\n{catalog}\n</skills>\n"
            )
        if self.tactical_assist:
            self.system_prompt += "\n\n" + TACTICAL_ASSIST_PROMPT
        opening_instruction = (
            "Choose one move from legal_moves and call play_move."
            if include_legal_moves
            else "Infer a legal move from the board and FEN, then call play_move."
        )
        self.task_prompt = (
            f"Play this game as White. {opening_instruction}\n\n"
            f"{self.format_state(initial_state)}"
        )

    def format_state(self, state: dict[str, Any]) -> str:
        """Format a state according to this run's observation condition."""

        observation = format_chess_state(state, include_legal_moves=self.include_legal_moves)
        if (
            getattr(self, "tactical_assist", False)
            and not state.get("game_over")
            and state.get("turn") == "white"
            and state.get("fen")
        ):
            facts = self._analysis("analyze", state["fen"])
            if facts and "error" not in facts:
                observation += "\n" + chess_analysis.format_facts(facts)
        return observation

    def _analysis(self, command: str, *args: str) -> dict[str, Any] | None:
        """Run chess_analysis locally if python-chess is installed, else in the sandbox."""

        try:
            if chess_analysis.available():
                if command == "analyze":
                    return chess_analysis.analyze(*args)
                return chess_analysis.check_move(*args)

            execute = getattr(self.env, "execute", None)
            if not callable(execute):
                return None
            if not self._analysis_uploaded:
                source = Path(chess_analysis.__file__).read_text(encoding="utf-8")
                encoded = base64.b64encode(source.encode("utf-8")).decode("ascii")
                uploaded = execute(f"echo {encoded} | base64 -d > {ANALYSIS_PATH}")
                if uploaded.get("returncode", 1) != 0:
                    return None
                self._analysis_uploaded = True
            quoted = " ".join(shlex.quote(arg) for arg in args)
            result = execute(f"python {ANALYSIS_PATH} {command} {quoted}")
            lines = (result.get("output") or "").strip().splitlines()
            return json.loads(lines[-1]) if lines else None
        except Exception:
            # The symbolic layer is an aid; never let it break a turn.
            return None

    def _guard_move(self, raw_args: Any) -> str | None:
        """Return a <chess_error> veto for a blunder or missed mate, else None."""

        if not self.tactical_assist:
            return None
        fen = (self.last_state or {}).get("fen")
        try:
            parsed = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            move = parsed.get("move") if isinstance(parsed, dict) else None
        except (TypeError, ValueError):
            return None
        if not fen or not isinstance(move, str):
            return None
        # Veto at most twice per position so the model can always insist.
        if self._guard_blocks.get(fen, 0) >= MAX_GUARD_BLOCKS_PER_POSITION:
            return None
        verdict = self._analysis("check", fen, move.strip().lower())
        if not verdict or verdict.get("verdict") != "block":
            return None
        self._guard_blocks[fen] = self._guard_blocks.get(fen, 0) + 1
        suggestions = ", ".join(verdict.get("suggest", [])) or "(none)"
        return (
            "<chess_error>Blunder guard rejected this move; the board is unchanged. "
            f"{verdict.get('reason', '')} Safer candidates from the engine: "
            f"{suggestions}. Pick one and call play_move again.</chess_error>"
        )

    def build_prompt(self) -> list[dict[str, Any]]:
        """Construct model prompt, keeping past tool observations compact to maintain fast inference."""

        messages = super().build_prompt()
        if len(messages) <= 4:
            return messages

        # Find the last tool message
        last_tool_idx = -1
        for idx in range(len(messages) - 1, -1, -1):
            if messages[idx].get("role") == "tool" and "<chess_state>" in str(
                messages[idx].get("content", "")
            ):
                last_tool_idx = idx
                break

        if last_tool_idx < 0:
            return messages

        pruned: list[dict[str, Any]] = []
        for idx, msg in enumerate(messages):
            if idx < last_tool_idx and msg.get("role") == "tool":
                content = msg.get("content", "")
                if "<chess_state>" in content:
                    fen_match = re.search(r"fen:\s*([^\n]+)", content)
                    fen_str = fen_match.group(1) if fen_match else ""
                    compact = f"<chess_state fen=\"{fen_str}\">move played</chess_state>"
                    pruned.append({**msg, "content": compact})
                else:
                    pruned.append(msg)
            else:
                pruned.append(msg)

        return pruned

    def execute_tool_calls(
        self, tool_calls: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        """Execute model-generated ``play_move`` calls against the chess API."""

        registered_names = {
            t.get("function", {}).get("name")
            for t in self.tools
            if isinstance(t, dict) and "function" in t
        }

        observations: list[dict[str, str]] = []
        move_played_in_batch = False

        for call in tool_calls:
            call_id = call.get("id", "")
            func = call.get("function", {})
            name = func.get("name", "")
            raw_args = func.get("arguments", "{}")

            if name not in registered_names:
                observations.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": f"<chess_error>Tool '{name}' is not registered.</chess_error>",
                    }
                )
                continue

            if name == "play_move":
                if move_played_in_batch:
                    observations.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": (
                                "<chess_error>Cannot execute multiple moves in one turn. "
                                "Only one move may be played per turn.</chess_error>"
                            ),
                        }
                    )
                    continue

                move_played_in_batch = True
                veto = self._guard_move(raw_args)
                if veto is not None:
                    observations.append(
                        {"role": "tool", "tool_call_id": call_id, "content": veto}
                    )
                    continue
                result_str = _play_move(self.chess_client, raw_args)
                if "<chess_error>" in result_str:
                    content = result_str
                else:
                    try:
                        state = json.loads(result_str)
                        self.last_state = state
                        self.finished = bool(state.get("game_over", False))
                        content = self.format_state(state)
                    except Exception as exc:
                        content = f"<chess_error>Failed to process move result: {exc}</chess_error>"

                observations.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": content,
                    }
                )

            elif name == "simulate_move":
                result_str = _simulate_move(self.chess_client, raw_args)
                observations.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": result_str,
                    }
                )

            elif name == "run_python":
                result_str = _run_python(self.env, self.python_sandbox_port, raw_args)
                if "<chess_error>" in result_str:
                    content = result_str
                else:
                    try:
                        current_state = _game_state(self.chess_client)
                        self.last_state = current_state
                        self.finished = bool(current_state.get("game_over", False))
                        content = f"{result_str}\n\n{self.format_state(current_state)}"
                    except Exception as exc:
                        content = f"{result_str}\n\n<chess_error>Failed to refresh board state: {exc}</chess_error>"

                observations.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": content,
                    }
                )

            elif name == "invoke_skill":
                result_str = _invoke_skill(self.skills, raw_args)
                observations.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": result_str,
                    }
                )

            else:
                observations.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": f"<chess_error>Unknown tool: '{name}'</chess_error>",
                    }
                )

        return observations
