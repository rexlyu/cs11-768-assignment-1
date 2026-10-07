"""Chess tool implementations, decoupled from the agent that registers them.

Every function here takes the HTTP client explicitly instead of reading it off
an agent, so the same code can run in the agent process or inside the sandbox
beside the server it talks to.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx

CHESS_PORT = 8000


def _request_state(
    client: httpx.Client, method: str, endpoint: str, **kwargs: Any
) -> dict[str, Any]:
    """Make one chess API request and validate its JSON response."""

    response = client.request(method, endpoint, **kwargs)
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Chess server returned non-JSON ({response.status_code})."
        ) from exc
    if response.status_code >= 400:
        detail = (
            payload.get("detail", payload) if isinstance(payload, dict) else payload
        )
        raise ValueError(str(detail))
    if not isinstance(payload, dict):
        raise RuntimeError("Chess server response must be a JSON object.")
    return payload


def _simulate_move(client: httpx.Client, arguments: str) -> str:
    """New tool: inspect FEN or simulate one ply without changing the game.

    Takes the raw JSON arguments of one tool call and returns the observation
    to send back, so a bad argument or a server error reaches the model as a
    recoverable ``<chess_error>`` instead of ending the run.
    """
    try:
        if isinstance(arguments, str):
            parsed = json.loads(arguments)
        elif isinstance(arguments, dict):
            parsed = arguments
        else:
            return "<chess_error>Arguments must be a JSON object.</chess_error>"

        if not isinstance(parsed, dict):
            return "<chess_error>Arguments must be a JSON object.</chess_error>"

        fen = parsed.get("fen")
        if not isinstance(fen, str):
            return "<chess_error>Missing or non-string 'fen' argument.</chess_error>"

        move = parsed.get("move")
        if move is not None and not isinstance(move, str):
            return "<chess_error>Invalid non-string 'move' argument.</chess_error>"

        payload: dict[str, Any] = {"fen": fen}
        if move:
            payload["move"] = move

        state = _request_state(client, "POST", "/api/simulate", json=payload)
        return json.dumps(state)
    except Exception as exc:
        return f"<chess_error>{exc}</chess_error>"


def _play_move(client: httpx.Client, arguments: str) -> str:
    """Existing tool: play one move as White and return the resulting state.

    Takes the raw JSON arguments of one tool call. Returns the new state, or a
    `<chess_error>` observation if the move could not be played.
    """
    try:
        if isinstance(arguments, str):
            parsed = json.loads(arguments)
        elif isinstance(arguments, dict):
            parsed = arguments
        else:
            return "<chess_error>Arguments must be a JSON object.</chess_error>"

        if not isinstance(parsed, dict):
            return "<chess_error>Arguments must be a JSON object.</chess_error>"

        move = parsed.get("move")
        if not isinstance(move, str):
            return "<chess_error>Missing or non-string 'move' argument.</chess_error>"

        state = _request_state(client, "POST", "/api/move", json={"move": move})
        return json.dumps(state)
    except Exception as exc:
        return f"<chess_error>{exc}</chess_error>"


def _run_python(env: Any, port: int, arguments: str) -> str:
    """New tool: run Python with access to the existing registered tools.

    The snippet runs inside the sandbox, which already has the tool
    implementations and the chess server, so code the model wrote never
    executes in the agent process.
    """
    try:
        if isinstance(arguments, str):
            parsed = json.loads(arguments)
        elif isinstance(arguments, dict):
            parsed = arguments
        else:
            return "<chess_error>Arguments must be a JSON object.</chess_error>"

        if not isinstance(parsed, dict):
            return "<chess_error>Arguments must be a JSON object.</chess_error>"

        code = parsed.get("code")
        if not isinstance(code, str):
            return "<chess_error>Missing or non-string 'code' argument.</chess_error>"

        encoded_code = base64.b64encode(code.encode("utf-8")).decode("utf-8")
        command = f"python /opt/assignment/sandbox_python.py {port} {encoded_code}"
        result = env.execute(command)

        if result.get("returncode", 0) != 0:
            error_msg = result.get("stderr") or result.get("output") or "Execution failed"
            return f"<chess_error>{error_msg}</chess_error>"

        return result.get("output", "")
    except Exception as exc:
        return f"<chess_error>{exc}</chess_error>"


def _invoke_skill(skills: dict[str, dict[str, str]], arguments: str) -> str:
    """Existing tool: load one skill's instructions into the conversation."""
    try:
        if isinstance(arguments, str):
            parsed = json.loads(arguments)
        elif isinstance(arguments, dict):
            parsed = arguments
        else:
            return "<chess_error>Arguments must be a JSON object.</chess_error>"

        if not isinstance(parsed, dict):
            return "<chess_error>Arguments must be a JSON object.</chess_error>"

        name = parsed.get("name")
        if not isinstance(name, str):
            return "<chess_error>Missing or non-string 'name' argument.</chess_error>"

        if name in skills:
            return skills[name]["content"]

        return f"<chess_error>Skill '{name}' not found.</chess_error>"
    except Exception as exc:
        return f"<chess_error>{exc}</chess_error>"


def _game_state(client: httpx.Client, reset: bool = False) -> dict:
    """Read the live game, or start a new one and read the opening position."""

    method, endpoint = ("POST", "/api/reset") if reset else ("GET", "/api/state")
    return _request_state(client, method, endpoint)
