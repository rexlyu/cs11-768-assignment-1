# AI Usage Declaration

**Course**: CS11-768: Advanced Agentic Coding  
**Assignment**: Assignment 1 — Build an Agent Harness  

---

## 1. AI Tools Used

During the completion of this assignment, the following AI tool was used:
- **Antigravity AI Assistant** (Powered by Google Gemini 3.8 Flash / Thinking models)

---

## 2. Description of AI Assistance and Methodology

AI assistance was utilized as an interactive pair-programming partner across all stages of development:

### A. Architectural Planning & Task Decomposition
- Used AI to analyze `ASSIGNMENT.md` and decompose the 3 interconnected parts into a structured 18-hour subtask execution plan documented in `PLAN.md`.
- Modeled the system relationships between the ReAct loop base agent (`base.py`), domain-specific coding agent (`code_agent.py`), and the interactive chess agent (`chess_agent.py` and `chess_tools.py`).

### B. Core Implementation & Code Generation
1. **Part 1 (ReAct Loop & Coding Agent)**:
   - Implemented domain-agnostic conversation state management (`Agent.messages`) and observation truncation (preserving 4,900 characters each from head and tail for terminal logs > 10,000 characters).
   - Designed the `CodeAgent` system prompt containing the required `<system_information>` JSON specification.
   - Structured the core ReAct loop in `Agent.run` with `step_limit` bound enforcement and `finally` block trajectory logging.
   - Implemented recoverable error handling in `CodeAgent.execute_tool_calls` for `execute`, `send_message`, and `invoke_skill`, converting malformed JSON arguments and unknown tools into informative `<error>` observations rather than crashing.
   - Implemented YAML frontmatter parsing for the Agent Skills protocol and progressive disclosure in `Agent.load_skills`.

2. **Part 2 (Context Compaction & Working Memory)**:
   - Formulated `COMPACTION_SYSTEM_PROMPT` to guide the model in producing high-density factual working memory (preserving objectives, modified files, commands, test assertions, failed approaches, blockers, and next steps) without verbatim stdout reproduction.
   - Implemented `Agent.compact_context`, which slices the older turn history, invokes the compaction prompt, and updates `self.messages` while keeping the initial system/task prompts and the latest assistant/tool turns verbatim.
   - Integrated dynamic compaction triggering via `Agent.maybe_compact_context()`.

3. **Part 3 (Chess Agent & Programmatic Tools)**:
   - Defined strict OpenAI function-calling schemas for `play_move`, `simulate_move`, and `run_python` in `tools.py`.
   - Implemented API communication in `chess_tools.py` with error trapping into `<chess_error>` tags.
   - Enforced a single-move-per-turn execution guard in `ChessAgent.execute_tool_calls` to prevent position corruption from parallel move calls.
   - Handled graceful teardown and reliable result persistence to safeguard against remote sandbox disconnects.
   - Implemented sandboxed Python code execution via base64 encoding sent to `/opt/assignment/sandbox_python.py`.

### C. Testing & Verification
- AI was used to execute and interpret test failures in `pytest`, diagnose environment dependencies (e.g. editable install via `uv pip install -e .`), and ensure 100% test pass rate across all public unit tests prior to launching billable runs.

---

## 3. Human Oversight & Code Understanding
All AI-generated code was reviewed, validated against assignment constraints (e.g. ensuring no modification to `tests/`, `tasks/`, or `chess_app/`, and confirming that no API credentials or `.env` files are leaked), and fully verified through offline test suites.
