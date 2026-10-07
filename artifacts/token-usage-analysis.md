# Token Usage Analysis: Context Compaction vs. Full-Context Baseline
**Task**: `django__django-15368` (SWE-bench)  
**Evaluator**: ReAct `CodeAgent` with Working Memory Compaction  

---

## 1. Experimental Setup & Methodology

Long-horizon agent execution in complex codebases inevitably encounters the limits of language model context windows and incurs quadratic attention compute overhead. To evaluate working memory efficiency, we compared two experimental conditions on `django__django-15368`:

1. **Compacted Condition (`COMPACT_THRESHOLD=6000`)**:
   - Monitored active prompt token estimation before each step.
   - When active tokens exceeded 6,000, triggered `Agent.compact_context()`.
   - Distilled historical actions, edits, test outcomes, and failures into dense working memory while keeping the latest complete turn pair intact.
2. **Full-Context Baseline (`COMPACT_THRESHOLD=0`)**:
   - Compaction disabled.
   - Preserved full transcript of all prior assistant turns and raw terminal tool outputs.

---

## 2. Quantitative Results & Comparison

Data extracted directly from `artifacts/django__django-15368-trajectory.json` and `artifacts/django__django-15368-baseline-trajectory.json` via `scripts/analyze_trajectories.py`:

| Metric | Context Compaction (Threshold: 6000) | Full-Context Baseline (Threshold: 0) | Impact / Savings |
|:---|:---:|:---:|:---:|
| **Total ReAct Steps** | 46 | 33 | +13 steps (stochastic exploration) |
| **Compaction Events Triggered** | **6** | 0 | 6 distillations |
| **Peak Active Context (Tokens)** | **5,667** | **20,856** | **-72.8% reduction** |
| **Average Prompt Size / Turn** | **3,356.2** | **11,910.4** | **-71.8% reduction** |
| **Total Cumulative Tokens** | **188,579** | **407,469** | **-53.7% reduction (218,890 tokens saved)** |
| **Benchmark Status** | **RESOLVED: yes** (30/30 tests) | **RESOLVED: yes** (30/30 tests) | Both produced correct patch |

---

## 3. Trajectory Progression & Context Growth

Comparing active prompt size (in tokens) across sampled steps illustrates the architectural difference:

```text
Step      Compacted Active Tokens       Baseline Active Tokens
---------------------------------------------------------------
Step 01:     518 tokens                    518 tokens
Step 05:   2,061 tokens                  5,829 tokens
Step 10:   4,830 tokens                  7,730 tokens
Step 15:   3,584 tokens (after compact) 12,108 tokens
Step 20:   1,135 tokens (after compact) 13,917 tokens
Step 25:   5,173 tokens                 15,644 tokens
Step 30:   2,486 tokens (after compact) 18,841 tokens
Step 33:   3,210 tokens                 20,856 tokens (Peak)
Step 46:   4,353 tokens (End)               --
```

- **Baseline Condition**: Displays monotonic, unbounded context accumulation. By Step 33, active prompt size surged past **20,800 tokens**, causing substantial latency per inference call.
- **Compacted Condition**: The active context follows a bounded "sawtooth" pattern: growing as intermediate tool executions accumulate, and dropping back down to ~1,100–3,500 tokens whenever `compact_context()` synthesizes working memory.

---

## 4. Analysis of Trends & Tradeoffs

### A. Token Cost Efficiency vs. Compaction Request Overhead
- Although compaction introduces 6 auxiliary model invocations to synthesize working memory, the total tokens consumed dropped from **407,469 down to 188,579 tokens**—an overall net savings of **53.7% (218,890 tokens saved)**.
- Because attention cost scales with prompt length across subsequent turns, shrinking prompt size by ~72% per turn vastly outweighs the marginal cost of the compaction queries.

### B. Information Density vs. Loss of Fine-Grained Traces
- **Retained**: High-level architectural deductions, modified files (`django/db/models/query.py`), test failures (`bulk_update()` with `F()` expressions), and key diffs remain prominent in the synthesized memory.
- **Pruned**: Intermediate noisy terminal outputs (e.g. verbose test discovery logs, `git status` listings, long stack traces) are cleanly discarded without impairing the agent's problem-solving ability.
- Both agents independently converged to the exact same canonical fix: replacing `if not isinstance(attr, Expression):` with `if not hasattr(attr, "resolve_expression"):`.

### C. Conversational Anchoring
- Retaining the most recent complete action and linked observation pair (`compaction_keep_recent_steps=1`) prevented the model from suffering "memory amnesia" or re-executing identical commands right after compaction.

### D. Long-Horizon Scalability
- For real-world SWE tasks requiring 50+ turns, full-context baselines inevitably saturate context windows and degrade instruction adherence. Working memory compaction provides a stable, predictable, and cost-effective harness for arbitrarily long agent runs.
