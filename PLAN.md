# Assignment 1 Execution Plan: Building an Agent Harness
**Course**: CS11-768 | **Structure**: 18 Subtasks × 1 Hour per Subtask

---

## 1. System Architecture & Workflow

The assignment builds a generalized [ReAct (Reason + Act)](https://arxiv.org/abs/2210.03629) agent harness in Python that evolves across three interconnected parts:

```text
                  SWE-Bench Issue (django-15368)
                                |
                                v
buggy chess app  --->      CodeAgent      ---> fix.patch ---> repaired chess server (Modal)
                                                                    ^
                                                                    |
                                                            ChessAgent Tools
                                                     (play_move / simulate / run_python)
```

### Component Flow
1. **Base ReAct Loop (`base.py`)**: Domain-agnostic query loop, state tracking, tool execution dispatch, trajectory serialization, step limit enforcement, and context compaction.
2. **CodeAgent (`code_agent.py`)**: Environment discovery, tool execution (`execute`, `send_message`), progressive skill disclosure, and code bug resolution (`fix.patch`).
3. **Context Compaction (`base.py`)**: Working memory extraction on threshold, prompt prefix truncation, recent step preservation, and token efficiency analysis.
4. **ChessAgent (`chess_agent.py` & `chess_tools.py`)**: Strict tool schema validation (`play_move`), recoverable error handling (`<chess_error>`), observation A/B testing, stateless simulation (`simulate_move`), and programmatic Python execution (`run_python`).

---

## 2. Schedule & Subtask Breakdown (1 Hour per Block)

| Hour | Part | Subtask | Key Deliverable / Verification |
|:---:|:---:|:---|:---|
| **H01** | Setup | Toolchain, Modal authentication & API verification | `make setup`, `make doctor` passing |
| **H02** | Part 1 | Base Agent state tracking & prompt building (TODO 1.1.a) | `Agent.messages`, `test_prompt_carries_task_action_and_result` |
| **H03** | Part 1 | `CodeAgent` system & task prompt construction (TODO 1.1.b) | `<system_information>` JSON block |
| **H04** | Part 1 | Core ReAct loop execution & step limit (TODO 1.2) | `Agent.run()`, `test_step_limit_raises` |
| **H05** | Part 1 | Code tool execution & recoverable errors (TODO 1.3) | `execute`, `send_message`, recoverable observations |
| **H06** | Part 1 | Skill discovery & progressive disclosure (TODO 1.4) | `load_skills()`, catalog metadata without leaking body |
| **H07** | Part 1 | Run CodeAgent on chess repair & verify patch | `artifacts/fix.patch`, `make check-part1` passing |
| **H08** | Part 2 | Context compaction prompt & working memory (TODO 2.1) | `COMPACTION_SYSTEM_PROMPT`, `Agent.compact_context()` |
| **H09** | Part 2 | Compaction trigger integration & unit testing (TODO 2.2) | `maybe_compact_context()`, compaction unit tests |
| **H10** | Part 2 | SWE-Bench compacted run (`django__django-15368`) | `make run-swebench-agent`, `make check-swebench` |
| **H11** | Part 2 | SWE-Bench baseline run (`COMPACT_THRESHOLD=0`) | Baseline trajectory & patch capture |
| **H12** | Part 2 | Context usage comparison & analysis report | `artifacts/token-usage-analysis.md` |
| **H13** | Part 3 | `play_move` schema & API dispatch (TODO 3.1.a, 3.1.b) | `PLAY_MOVE_TOOL`, `_play_move`, `test_chess_agent.py` |
| **H14** | Part 3 | Baseline chess run & Observation A/B experiments | 4 observation trajectories + result JSONs |
| **H15** | Part 3 | Observation experiment evaluation & report | `artifacts/observation-experiment.md` |
| **H16** | Part 3 | Stateless `simulate_move` tool (TODO 3.3.a, 3.3.b) | `SIMULATE_MOVE_TOOL`, `_simulate_move` |
| **H17** | Part 3 | Programmatic tool execution & chess skill (TODO 3.4, 3.5) | `run_python`, `_invoke_skill`, skill trajectory |
| **H18** | Final | Artifacts audit, `AI_USAGE.md` & submission packaging | Verification checklist & clean ZIP archive |

---

## 3. Detailed Subtask Specifications

### Hour 1: Setup, Modal & Toolchain Validation
- **Objective**: Ensure the local environment, Modal sandbox credentials, and LLM endpoint are operational.
- **Files**: `.env`, `pyproject.toml`, `Makefile`
- **Actions**:
  1. Sync environment: `uv sync && uv pip install -e .`
  2. Authenticate Modal: `uv run modal setup`
  3. Verify `.env` parameters (`OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`).
  4. Run health check: `make doctor`
  5. Run baseline unit tests: `make test` (verify baseline failing tests due to TODO stubs).
- **Deliverable**: `make doctor` exits 0 with all green checks.

---

### Hour 2: Base Agent State & Prompt Construction (TODO 1.1.a)
- **Objective**: Implement domain-agnostic conversation tracking and prompt serialization in `Agent`.
- **Files**: `src/assignment/agent/base.py`
- **Actions**:
  1. In `Agent.__init__`, initialize `self.messages: list[dict[str, Any]] = []`.
  2. In `Agent.build_prompt`, assemble the ordered message list:
     - Message 0: `{"role": "system", "content": <system_prompt + skill_metadata>}`
     - Message 1: `{"role": "user", "content": <task_prompt>}`
     - History turns: preserved assistant turns and tool observations.
  3. Ensure observation strings exceeding `MAX_OBSERVATION_CHARS` (10,000) are truncated via `format_tool_output` (retaining 4,900 characters each from head and tail).
- **Verification**:
  ```bash
  uv run pytest tests/test_agent.py -k "test_prompt_carries_task_action_and_result or test_long_observation_is_truncated"
  ```

---

### Hour 3: CodeAgent System Information & Task Prompts (TODO 1.1.b)
- **Objective**: Implement `CodeAgent` system prompt incorporating sandbox host properties and task statement.
- **Files**: `src/assignment/agent/code_agent.py`
- **Actions**:
  1. Read host properties from `self.env`: `machine`, `release`, `system`, `version`.
  2. Populate `self.system_prompt` with the verbatim required block:
     ```text
     <system_information>
     {
       "machine": <machine>,
       "release": <release>,
       "system": <system>,
       "version": <version>
     }
     </system_information>
     ```
  3. Set `self.task_prompt = self.task`.
  4. Include guidance on terminal usage, inspecting code, and running tests.
- **Verification**: Instantiate test agent and verify prompt format against assignment specifications.

---

### Hour 4: Core ReAct Execution Loop & Step Limit (TODO 1.2)
- **Objective**: Implement the generic ReAct loop in `Agent.run`.
- **Files**: `src/assignment/agent/base.py`
- **Actions**:
  1. In `Agent.run()`, loop while `not self.finished` and `self.steps_taken < self.step_limit`:
     - Obtain next assistant action: `message = self.query_language_model()`.
     - Record `message` into `self.messages`.
     - Extract `tool_calls = message.get("tool_calls", [])`.
     - If `tool_calls` present: call `observations = self.execute_tool_calls(tool_calls)` and append to `self.messages`.
     - If no `tool_calls` (plain text response): preserve response and continue or conclude if finished.
  2. If `self.steps_taken >= self.step_limit` without finishing: raise `StepLimitError`.
  3. Retain provided `finally` block intact to save trajectories and terminate environments.
- **Verification**:
  ```bash
  uv run pytest tests/test_agent.py -k "test_step_limit_raises"
  ```

---

### Hour 5: Code Tool Execution & Recoverability (TODO 1.3)
- **Objective**: Implement robust tool dispatching for `execute` and `send_message`.
- **Files**: `src/assignment/agent/code_agent.py`, `src/assignment/agent/tools.py`
- **Actions**:
  1. In `CodeAgent.__init__`, register tools: `self.tools.extend([EXECUTE_TOOL, SEND_MESSAGE_TOOL])`.
  2. In `CodeAgent.execute_tool_calls(self, tool_calls)`:
     - For each call, extract `tool_call_id` and function payload.
     - Safely parse arguments with `json.loads`. On decode failure or invalid schema, return a recoverable observation dict: `{"role": "tool", "tool_call_id": tool_call_id, "content": f"<error>Malformed JSON: {e}</error>"}`.
     - If tool name is unknown: return recoverable error observation without executing anything.
     - For `execute`: execute via `self.env.execute(command, cwd=..., timeout=..., env=...)` and format via `format_tool_output`.
     - For `send_message`: record message and return acknowledgment.
     - For `invoke_skill`: return full skill content from `self.skills`.
- **Verification**:
  ```bash
  uv run pytest tests/test_agent.py -k "test_malformed_arguments_are_not_executed or test_unknown_tool_is_not_executed"
  ```

---

### Hour 6: Skill Discovery & Progressive Disclosure (TODO 1.4)
- **Objective**: Discover, parse, and validate skills according to the Agent Skills protocol.
- **Files**: `src/assignment/agent/base.py`
- **Actions**:
  1. Implement `Agent.load_skills(self, skills_path: Path)`:
     - Scan child directories for `SKILL.md`.
     - Extract YAML frontmatter delimited by `---`.
     - Validate `name` and `description`; raise `ValueError` for duplicates or invalid YAML.
     - Return `{name: {"metadata": frontmatter_str, "content": full_text}}`.
  2. In `Agent.build_prompt`: append only skill metadata (name and description) to the system prompt.
  3. Ensure `patch.txt` is never mentioned prior to explicit `invoke_skill` invocation.
- **Verification**:
  ```bash
  uv run pytest tests/test_agent.py -k "test_skill_catalog_lists_names_without_skill_bodies"
  ```

---

### Hour 7: Part 1 Execution & Chess App Repair
- **Objective**: Run `CodeAgent` to fix the chess terminal move bug and verify the generated patch.
- **Files**: `artifacts/fix.patch`, `artifacts/part1-trajectory.json`
- **Actions**:
  1. Run the agent against the task:
     ```bash
     make run-code-agent
     ```
  2. Monitor container status: `modal container list`.
  3. Validate the patch against the test suite:
     ```bash
     make check-part1
     ```
- **Verification**: `make check-part1` passes all public regression tests on a clean testbed.

---

### Hour 8: Context Compaction Prompt & Working Memory (TODO 2.1)
- **Objective**: Design working memory compaction instructions and implement `compact_context`.
- **Files**: `src/assignment/agent/base.py`
- **Actions**:
  1. Write `COMPACTION_SYSTEM_PROMPT`:
     - Instruct the model to synthesize a factual, compact working memory summary.
     - Must preserve: goal, constraints, examined files, commands run, concrete edits, test results, failures, blockers, and next action.
     - Must avoid verbatim duplication of command stdout/stderr.
  2. In `Agent.compact_context(self)`:
     - Preserve initial system/task prompt verbatim.
     - Retain at least the most recent `compaction_keep_recent_steps` assistant turns + linked tool observations intact.
     - Formulate `compaction_prompt` containing `COMPACTION_SYSTEM_PROMPT` and the old interaction history.
     - Invoke model via provided `self.client.chat.completions.create`.
     - Replace the old history slice with the generated working memory summary.
- **Verification**: Check that prompt length after compaction is significantly reduced.

---

### Hour 9: Compaction Trigger Integration & Unit Testing (TODO 2.2)
- **Objective**: Integrate compaction check into the ReAct loop and run offline unit tests.
- **Files**: `src/assignment/agent/base.py`
- **Actions**:
  1. In `Agent.run()`, invoke `self.maybe_compact_context()` before each `self.query_language_model()` call.
  2. Ensure `self.compaction_events` correctly logs before/after token estimations and compaction payloads.
  3. Execute complete Part 1 & Part 2 unit test suite:
     ```bash
     uv run pytest tests/test_agent.py
     ```
- **Verification**: All tests in `tests/test_agent.py` pass cleanly offline.

---

### Hour 10: SWE-Bench Compacted Run (`django__django-15368`)
- **Objective**: Run SWE-Bench evaluation with 6,000-token threshold and verify patch.
- **Files**: `artifacts/django__django-15368.patch`, `artifacts/django__django-15368-trajectory.json`
- **Actions**:
  1. Run agent with compaction:
     ```bash
     COMPACT_THRESHOLD=6000 \
     SWEBENCH_PATCH=artifacts/django__django-15368.patch \
     SWEBENCH_TRAJECTORY=artifacts/django__django-15368-trajectory.json \
     make run-swebench-agent INSTANCE=django__django-15368
     ```
  2. Verify at least one compaction event was recorded in the trajectory.
  3. Evaluate patch:
     ```bash
     make check-swebench INSTANCE=django__django-15368
     ```
- **Verification**: `make check-swebench` reports pass on both FAIL_TO_PASS and PASS_TO_PASS test suites.

---

### Hour 11: SWE-Bench Baseline Run (`COMPACT_THRESHOLD=0`)
- **Objective**: Run full-context baseline without compaction to collect comparison data.
- **Files**: `artifacts/django__django-15368-baseline.patch`, `artifacts/django__django-15368-baseline-trajectory.json`
- **Actions**:
  1. Run baseline without compaction:
     ```bash
     COMPACT_THRESHOLD=0 \
     SWEBENCH_PATCH=artifacts/django__django-15368-baseline.patch \
     SWEBENCH_TRAJECTORY=artifacts/django__django-15368-baseline-trajectory.json \
     make run-swebench-agent INSTANCE=django__django-15368
     ```
  2. Extract token statistics: step count, total prompt/completion tokens, peak context size.
- **Verification**: Both baseline and compacted trajectory JSONs are valid and contain complete run logs.

---

### Hour 12: Context Usage Comparison & Analysis Report
- **Objective**: Write comprehensive analysis in `artifacts/token-usage-analysis.md`.
- **Files**: `artifacts/token-usage-analysis.md`
- **Actions**:
  1. Tabulate comparative metrics: total token usage, peak context tokens, compaction frequency, ReAct steps taken.
  2. Analyze tradeoffs:
     - Token cost vs compaction request overhead.
     - Preserving semantic context vs loss of fine-grained error details.
     - Potential for hallucination or error propagation in working memory summaries.
- **Verification**: Document addresses all questions outlined in `ASSIGNMENT.md`.

---

### Hour 13: Chess `play_move` Schema & API Dispatch (TODO 3.1.a, 3.1.b)
- **Objective**: Define `play_move` tool schema, implement HTTP API communication, and handle errors.
- **Files**: `src/assignment/agent/tools.py`, `src/assignment/agent/chess_tools.py`, `src/assignment/agent/chess_agent.py`
- **Actions**:
  1. In `tools.py`, define `PLAY_MOVE_TOOL`:
     - Strict mode: `strict: True`.
     - Required parameter: `move` (UCI string, e.g. `e2e4`, `e7e8q`).
     - Reject extra arguments (`additionalProperties: False`).
  2. In `chess_agent.py`, register `PLAY_MOVE_TOOL` in `self.tools`.
  3. In `chess_tools.py`, implement `_play_move(client, arguments)`:
     - Parse JSON arguments.
     - Post `{"move": move}` to `/api/move`.
     - On error (malformed JSON, non-string move, HTTP 400/500, network error): return `<chess_error>{msg}</chess_error>`.
  4. In `chess_agent.py`, implement `execute_tool_calls`:
     - If parallel moves are received, execute at most one and return recoverable error for the rest.
     - Update `self.last_state` and `self.finished`.
- **Verification**:
  ```bash
  uv run pytest tests/test_chess_agent.py
  ```

---

### Hour 14: Baseline Chess Run & Observation A/B Experiment
- **Objective**: Execute baseline chess game and the 4-condition Observation A/B test matrix.
- **Files**: Trajectories and results under `artifacts/`
- **Actions**:
  1. Run baseline game:
     ```bash
     make run-chess-agent
     ```
     Produces `artifacts/part3-trajectory.json` and `artifacts/game-result.json`.
  2. Run the 4 observation conditions:
     ```bash
     make run-obs-deepseek-no-legal
     make run-obs-deepseek-legal
     make run-obs-gpt-oss-no-legal
     make run-obs-gpt-oss-legal
     ```
- **Verification**: All 10 expected artifact files generated under `artifacts/`.

---

### Hour 15: Observation Experiment Evaluation & Report
- **Objective**: Synthesize observation experiment data into `artifacts/observation-experiment.md`.
- **Files**: `artifacts/observation-experiment.md`
- **Actions**:
  1. Parse the 4 observation trajectories and compute:
     - Total `play_move` calls.
     - Calls rejected as illegal.
     - Invalid move rate (percentage).
     - Whether terminal state (`game_over: true`) was reached.
  2. Write analysis on:
     - Effect of legal move enumeration on move legality and hallucination.
     - Performance comparison between DeepSeek-V4-Flash and GPT-OSS.
     - Context cost vs reliability tradeoffs.
- **Verification**: Document contains complete quantitative table and empirical analysis.

---

### Hour 16: Stateless Move Simulation Tool (TODO 3.3.a, 3.3.b)
- **Objective**: Implement `simulate_move` tool schema and server dispatch.
- **Files**: `src/assignment/agent/tools.py`, `src/assignment/agent/chess_tools.py`, `src/assignment/agent/chess_agent.py`
- **Actions**:
  1. In `tools.py`, define `SIMULATE_MOVE_TOOL`:
     - Parameters: `fen` (required string), `move` (optional string or null).
  2. In `chess_tools.py`, implement `_simulate_move(client, arguments)`:
     - Post to `/api/simulate`.
     - Return resulting JSON state.
     - Wrap any validation or HTTP errors in `<chess_error>`.
  3. In `chess_agent.py`, dispatch `simulate_move` without mutating `self.last_state` or `self.finished`.
- **Verification**: Test simulation endpoint with valid FEN and verify returned legal moves and plies.

---

### Hour 17: Programmatic Execution & Chess Skill (TODO 3.4, 3.5)
- **Objective**: Implement `run_python`, chess skill lookup, and run programmatic strategy.
- **Files**: `src/assignment/agent/tools.py`, `src/assignment/agent/chess_tools.py`, `src/assignment/agent/chess_agent.py`
- **Actions**:
  1. In `tools.py`, define `RUN_PYTHON_TOOL`: parameter `code` (string).
  2. In `chess_tools.py`, implement `_run_python(env, port, arguments)`:
     - Base64 encode code: `base64.b64encode(code.encode()).decode()`.
     - Execute in sandbox: `python /opt/assignment/sandbox_python.py <port> <base64-code>`.
     - Return execution JSON (`stdout`, `stderr`, `error`).
     - Re-read live board state to update `last_state` and `finished`.
  3. In `chess_tools.py`, implement `_invoke_skill(skills, arguments)`.
  4. Run programmatic skill-guided game:
     ```bash
     uv run assignment-play-chess \
       --programmatic-tools \
       --skills-path tasks/chess-skills \
       --trajectory artifacts/part3-python-skill-trajectory.json
     ```
- **Verification**: Verify trajectory demonstrates `invoke_skill` -> `run_python` (calling `simulate_move`) -> `play_move`.

---

### Hour 18: Final Audit, `AI_USAGE.md` & Submission Packaging
- **Objective**: Audit all 17 required artifacts, create `AI_USAGE.md`, and produce clean submission ZIP.
- **Files**: `AI_USAGE.md`, submission ZIP
- **Actions**:
  1. Audit existence of all 17 artifacts in `artifacts/`:
     - `artifacts/fix.patch`
     - `artifacts/part1-trajectory.json`
     - `artifacts/django__django-15368.patch`
     - `artifacts/django__django-15368-trajectory.json`
     - `artifacts/token-usage-analysis.md`
     - `artifacts/part3-trajectory.json`
     - `artifacts/game-result.json`
     - `artifacts/part3-no-legal-moves-deepseek.json`
     - `artifacts/part3-no-legal-moves-deepseek-result.json`
     - `artifacts/part3-legal-moves-deepseek.json`
     - `artifacts/part3-legal-moves-deepseek-result.json`
     - `artifacts/part3-no-legal-moves-gpt-oss.json`
     - `artifacts/part3-no-legal-moves-gpt-oss-result.json`
     - `artifacts/part3-legal-moves-gpt-oss.json`
     - `artifacts/part3-legal-moves-gpt-oss-result.json`
     - `artifacts/observation-experiment.md`
     - `artifacts/part3-python-skill-trajectory.json`
  2. Write `AI_USAGE.md` describing AI tools used and prompt approaches.
  3. Package ZIP containing `src/`, `artifacts/`, and `AI_USAGE.md` (excluding `.env`, tests, git files, or submodules).
- **Verification**: Confirm archive contents match submission requirements.

---

## 4. Grading Rubric Breakdown (100 Points Total)

| Part | Rubric Item | Points | Verification Evidence |
|:---:|:---|:---:|:---|
| 1 | Prompt construction and valid action/observation history | 6 | Private unit tests |
| 1 | ReAct lifecycle, text recovery, step limit, cleanup | 6 | Private unit tests |
| 1 | Coding tool dispatch, recoverable errors, patch submission | 6 | Private unit tests |
| 1 | Chess patch applies and passes regression tests | 8 | Patch replay in testbed |
| 1 | Skill discovery and `invoke_skill` behavior | 4 | Private unit tests |
| 2 | Compaction trigger and model-generated summary | 6 | Trajectory & private tests |
| 2 | Original instructions & recent tool step remain valid | 6 | Trajectory & private tests |
| 2 | Compaction materially reduces active context | 4 | Compaction events & tokens |
| 2 | Token usage analysis report | 4 | `token-usage-analysis.md` |
| 2 | SWE-bench patch passes FAIL_TO_PASS & PASS_TO_PASS | 8 | Evaluation on SWE-bench image |
| 3 | `play_move` schema and registration | 4 | Schema validation tests |
| 3 | `play_move` state updates and recoverable errors | 6 | Integration tests |
| 3 | Basic chess trajectory reaches terminal state | 4 | Trajectory & result JSON |
| 3 | Four-run observation A/B experiment complete | 4 | 4 trajectories & 4 results |
| 3 | Observation experiment report | 4 | `observation-experiment.md` |
| 3 | `simulate_move` stateless behavior & errors | 6 | Simulation unit tests |
| 3 | `run_python` sandbox execution, state refresh, errors | 6 | Sandbox execution tests |
| 3 | Skill trajectory combines skill, simulation & move | 6 | Trajectory replay |
| — | Complete, rule-compliant submission archive | 2 | Archive format validation |
| | **Total** | **100** | |
