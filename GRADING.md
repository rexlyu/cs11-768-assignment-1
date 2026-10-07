# Assignment 1 Review & Grading Report

**Course**: CS11-768: Advanced Agentic Coding  
**Assignment**: Assignment 1 — Build an Agent Harness  
**Overall Grade**: **98 / 100**  
**Submission Status**: **Verified & Package-Compliant** (`submission.zip` generated cleanly)

---

## Executive Summary

Your submission demonstrates exceptional engineering quality and rigorous adherence to the assignment specifications. All public unit tests pass, both cloud evaluation benchmarks (**Part 1 chess app regression suite** and **Part 2 SWE-bench `django__django-15368`**) achieve `RESOLVED: yes` on remote Modal sandboxes, context compaction achieves a **>70% peak context reduction**, and the observation and programmatic chess tool pipelines function as specified.

---

## Detailed Score Breakdown by Rubric

| Part | Rubric Criterion | Max Pts | Awarded | Verification & Evidence |
|:---|:---|:---:|:---:|:---|
| **1** | Prompt construction and valid action/observation history | 6 | **6** | Domain-agnostic message history layout (`Agent.build_prompt()`); `<system_information>` block formatted verbatim in [`CodeAgent`](src/assignment/agent/code_agent.py); bidirectional elision for outputs > 10k chars preserving 4,900 chars on each end; unit tests pass. |
| **1** | ReAct lifecycle, text-only recovery, step limit, cleanup, trajectory | 6 | **6** | ReAct cycle implemented in [`Agent.run()`](src/assignment/agent/base.py#L448-L487); text-only assistant turns handled seamlessly without exceptions; strict `StepLimitError` enforcement; robust `finally` cleanup stopping sandbox and persisting trajectory. |
| **1** | Coding-tool dispatch, recoverable errors, patch submission | 6 | **6** | Clean dispatch of `execute` and `send_message` in [`CodeAgent.execute_tool_calls`](src/assignment/agent/code_agent.py#L72-L175); malformed JSON arguments and unregistered tools caught and converted to recoverable `<error>` observations; `send_message` finishes the task cleanly. |
| **1** | Chess patch applies and passes private/regression tests | 8 | **8** | Replay of [`artifacts/fix.patch`](artifacts/fix.patch) against a fresh Modal sandbox passed **1/1 `FAIL_TO_PASS`** and **9/9 `PASS_TO_PASS`** regression tests (`RESOLVED: yes`). |
| **1** | Skill discovery and `invoke_skill` behavior | 4 | **4** | Progressive disclosure implemented in [`Agent.load_skills`](src/assignment/agent/base.py#L178-L232); YAML frontmatter parsed; duplicate names rejected with `ValueError`; skill metadata exposed in system prompt while full body is hidden until `invoke_skill` is invoked. |
| **2** | Compaction trigger and model-generated summary | 6 | **6** | [`COMPACTION_SYSTEM_PROMPT`](src/assignment/agent/base.py#L35-L54) specifies factual extraction (files, edits, test outcomes, next steps); [`Agent.compact_context()`](src/assignment/agent/base.py#L343-L396) accurately prompts the model and integrates the summary; logged 6 compaction events in [`django__django-15368-trajectory.json`](artifacts/django__django-15368-trajectory.json). |
| **2** | Original instructions and complete recent tool step remain valid | 6 | **6** | System prompt and initial task prompt preserved verbatim; older turns sliced and compacted while `compaction_keep_recent_steps=1` preserves the latest assistant action and linked tool observation pair intact. Verified via `pytest`. |
| **2** | Auditable compaction materially reduces active context | 4 | **4** | Peak active prompt dropped from **20,856 tokens** down to **5,667 tokens** (**-72.8%** reduction). Cumulative tokens reduced from 407k down to 188k (**-53.7%** net savings). Compaction events fully recorded with input/output prompts. |
| **2** | Full context vs. compaction token usage analysis report | 4 | **4** | [`artifacts/token-usage-analysis.md`](artifacts/token-usage-analysis.md) provides comprehensive quantitative comparisons, sawtooth context progression tables, and deep analysis of architectural tradeoffs (attention scaling, noise filtering, conversational anchoring). |
| **2** | SWE-bench patch passes FAIL_TO_PASS and PASS_TO_PASS | 8 | **8** | Replay of [`artifacts/django__django-15368.patch`](artifacts/django__django-15368.patch) against Modal evaluation image passed **1/1 `FAIL_TO_PASS`** (`test_f_expression`) and **29/29 `PASS_TO_PASS`** tests (`RESOLVED: yes`). |
| **3** | `play_move` schema and registration | 4 | **4** | Strict schema in [`tools.py`](src/assignment/agent/tools.py#L136-L157) with `strict: True`, required string `move`, UCI documentation, and `additionalProperties: False`. Registered properly in [`ChessAgent.__init__`](src/assignment/agent/chess_agent.py#L133). |
| **3** | `play_move` state updates and recoverable errors | 6 | **6** | [`_play_move`](src/assignment/agent/chess_tools.py#L77-L102) handles `/api/move` POST; state formatting and `last_state`/`finished` updates verified; parallel move guard prevents multiple moves per turn; all server and validation errors wrapped in recoverable `<chess_error>`. |
| **3** | Basic chess trajectory reaches a terminal state | 4 | **2** | [`artifacts/game-result.json`](artifacts/game-result.json) shows a complete 52-ply terminal game (`game_over: True`, checkmate). However, [`artifacts/part3-trajectory.json`](artifacts/part3-trajectory.json) contains only 2 prompt/response turns (*deducted 2 pts for trajectory-result length discrepancy*). |
| **3** | Four-run observation A/B experiment is complete | 4 | **4** | All 4 experiment conditions generated without source modifications: DeepSeek with/without legal moves, GPT-OSS with/without legal moves. All 4 trajectories and results are present and verified. |
| **3** | Observation A/B experiment report | 4 | **4** | [`artifacts/observation-experiment.md`](artifacts/observation-experiment.md) contains accurate quantitative data matrix, in-depth behavioral comparisons across DeepSeek vs GPT-OSS, error cascading analysis, and tool affordance conclusions. |
| **3** | `simulate_move` stateless behavior and errors | 6 | **6** | Strict schema in [`tools.py`](src/assignment/agent/tools.py#L160-L185); [`_simulate_move`](src/assignment/agent/chess_tools.py#L41-L75) calls `/api/simulate` without altering live game state; robust `<chess_error>` trapping. |
| **3** | `run_python` sandbox execution, state refresh, errors | 6 | **6** | Code executes safely inside sandbox via `/opt/assignment/sandbox_python.py` using base64 encoding; local execution prevented; live game state refreshed and appended to observation after snippet runs. |
| **3** | Skill trajectory combines skill, programmatic search, and live move | 6 | **6** | [`artifacts/part3-python-skill-trajectory.json`](artifacts/part3-python-skill-trajectory.json) clearly demonstrates Turn 1 `invoke_skill`, followed by `run_python` containing minimax tree search calling `simulate_move` and concluding with `play_move(best)`. |
| **—** | Complete, parseable, rule-compliant submission | 2 | **2** | [`scripts/package_submission.py`](scripts/package_submission.py) verifies all 25 files present, `.env` and sensitive testbeds excluded, and [`AI_USAGE.md`](AI_USAGE.md) properly declared. |
| | **Total Score** | **100** | **98** | **Grade: A+** |

---

## Detailed Reviewer Observations & Strengths

1. **Robust ReAct Architecture**:
   - The shared base loop in [`base.py`](src/assignment/agent/base.py) cleanly isolates model communication, token estimation, and trajectory logging while leaving domain execution to subclasses.
   - The compaction mechanism avoids provider-specific lock-in and reliably bounds token growth into a healthy sawtooth pattern.

2. **Benchmark Verification**:
   - **Part 1**: The patch for `chess-terminal-move` correctly resolved the engine checkmate state bug, passing all 10 unit and regression tests.
   - **Part 2**: The generated fix for `django__django-15368` (`hasattr(attr, "resolve_expression")`) passed all 30 test cases on the published Docker image in Modal.

3. **Programmatic Chess & Skills Integration**:
   - In [`part3-python-skill-trajectory.json`](artifacts/part3-python-skill-trajectory.json), the agent successfully leveraged `invoke_skill` to learn the evaluation heuristic, implemented a minimax tree search in Python using `simulate_move`, and committed the best candidate via `play_move`.

4. **Recommendation for `part3-trajectory.json`**:
   - The file [`artifacts/game-result.json`](artifacts/game-result.json) reflects a full 52-ply checkmate game, whereas [`artifacts/part3-trajectory.json`](artifacts/part3-trajectory.json) captured only 2 steps (likely from a short test invocation). If you have the full trajectory log corresponding to that 52-ply game saved, replacing `artifacts/part3-trajectory.json` with it before submission would recover the 2 points for a perfect 100/100 score.
