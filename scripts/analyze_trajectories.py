#!/usr/bin/env python3
"""Trajectory Analysis Helper for CS11-768 Assignment 1.

Extracts token metrics for Part 2 (Context Compaction) and
move statistics for Part 3.2 (Observation A/B Experiment).
"""

import json
from pathlib import Path
import sys
from typing import Any


def analyze_token_usage(compacted_path: str, baseline_path: str) -> dict[str, Any]:
    """Compare compacted vs baseline SWE-bench trajectories."""
    p_comp = Path(compacted_path)
    p_base = Path(baseline_path)

    if not p_comp.exists() or not p_base.exists():
        print(f"Error: Missing trajectory file(s). Found {p_comp.exists()} and {p_base.exists()}")
        return {}

    data_comp = json.loads(p_comp.read_text())
    data_base = json.loads(p_base.read_text())

    def extract_metrics(data: dict) -> dict[str, Any]:
        responses = data.get("responses", [])
        compactions = data.get("compactions", [])
        prompts = data.get("prompts", [])

        prompt_tokens = sum(r.get("usage", {}).get("prompt_tokens", 0) for r in responses)
        completion_tokens = sum(r.get("usage", {}).get("completion_tokens", 0) for r in responses)
        total_tokens = prompt_tokens + completion_tokens

        prompt_lengths = [len(json.dumps(p)) // 4 for p in prompts]
        peak_prompt = max(prompt_lengths) if prompt_lengths else 0
        avg_prompt = sum(prompt_lengths) / len(prompt_lengths) if prompt_lengths else 0

        return {
            "steps": len(responses),
            "compactions": len(compactions),
            "total_prompt_tokens": prompt_tokens,
            "total_completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "peak_prompt_tokens": peak_prompt,
            "avg_prompt_tokens": round(avg_prompt, 1),
            "step_prompt_sizes": prompt_lengths,
        }

    metrics_comp = extract_metrics(data_comp)
    metrics_base = extract_metrics(data_base)

    print("\n=== Context Compaction Comparison (Part 2) ===")
    print(f"Metric                       | Compacted (6000) | Baseline (Full)")
    print(f"-----------------------------|------------------|----------------")
    print(f"Steps Taken                  | {metrics_comp['steps']:<16} | {metrics_base['steps']:<15}")
    print(f"Compaction Events Triggered  | {metrics_comp['compactions']:<16} | {metrics_base['compactions']:<15}")
    print(f"Peak Active Context (Tokens) | {metrics_comp['peak_prompt_tokens']:<16} | {metrics_base['peak_prompt_tokens']:<15}")
    print(f"Avg Prompt Size per Turn     | {metrics_comp['avg_prompt_tokens']:<16} | {metrics_base['avg_prompt_tokens']:<15}")
    print(f"Total Tokens Consumed        | {metrics_comp['total_tokens']:<16} | {metrics_base['total_tokens']:<15}")

    return {"compacted": metrics_comp, "baseline": metrics_base}


def analyze_chess_observation_experiment(conditions: dict[str, tuple[str, str]]) -> dict[str, Any]:
    """Extract metrics for Part 3.2 Observation A/B Experiment runs.

    conditions: dict of {name: (trajectory_path, result_path)}
    """
    results = {}
    print("\n=== Observation A/B Experiment Matrix (Part 3.2) ===")
    print(f"Condition                     | Total Moves | Illegal Moves | Error Rate | Game Over")
    print(f"------------------------------|-------------|---------------|------------|----------")

    for name, (traj_path, res_path) in conditions.items():
        p_traj = Path(traj_path)
        p_res = Path(res_path)

        if not p_traj.exists():
            print(f"{name:<29} | (File not found)")
            continue

        traj_data = json.loads(p_traj.read_text())
        game_over = False
        if p_res.exists():
            res_data = json.loads(p_res.read_text())
            game_over = res_data.get("game_over", False)

        total_moves = 0
        illegal_moves = 0

        responses = traj_data.get("responses", [])
        prompts = traj_data.get("prompts", [])

        # Index all tool observations by tool_call_id
        obs_by_id: dict[str, str] = {}
        for prompt in prompts:
            for msg in prompt:
                if msg.get("role") == "tool" and "tool_call_id" in msg:
                    obs_by_id[msg["tool_call_id"]] = msg.get("content", "")

        for resp in responses:
            choice = resp.get("choices", [{}])[0]
            msg = choice.get("message", {})
            tool_calls = msg.get("tool_calls") or []
            for call in tool_calls:
                if call.get("function", {}).get("name") == "play_move":
                    total_moves += 1
                    call_id = call.get("id")
                    obs_content = obs_by_id.get(call_id, "")
                    if "<chess_error>" in obs_content:
                        illegal_moves += 1

        error_rate = (illegal_moves / total_moves * 100) if total_moves else 0.0

        print(
            f"{name:<29} | {total_moves:<11} | {illegal_moves:<13} | {error_rate:>9.1f}% | {str(game_over):<9}"
        )

        results[name] = {
            "total_moves": total_moves,
            "illegal_moves": illegal_moves,
            "error_rate": error_rate,
            "game_over": game_over,
        }

    return results


def update_observation_report(matrix_results: dict[str, Any], report_path: str = "artifacts/observation-experiment.md") -> None:
    """Update Section 2 table in observation-experiment.md with computed metrics."""
    p = Path(report_path)
    if not p.exists():
        print(f"Report not found at {p}")
        return

    content = p.read_text(encoding="utf-8")

    # Format table rows
    row_mapping = {
        "DeepSeek (No Legal Moves)": ("**DeepSeek-V4-Flash**", "No Legal Moves"),
        "DeepSeek (Legal Moves)": ("**DeepSeek-V4-Flash**", "With Legal Moves"),
        "GPT-OSS (No Legal Moves)": ("**GPT-OSS-120B**", "No Legal Moves"),
        "GPT-OSS (Legal Moves)": ("**GPT-OSS-120B**", "With Legal Moves"),
    }

    new_rows = []
    for cond_name, (model_name, cond_label) in row_mapping.items():
        data = matrix_results.get(cond_name)
        if not data:
            new_rows.append(f"| {model_name} | {cond_label} | *Pending* | *Pending* | *Pending* | *Pending* |")
            continue
        total = data["total_moves"]
        illegal = data["illegal_moves"]
        err_rate = f"{data['error_rate']:.1f}%"
        go = "Yes" if data["game_over"] else "No"
        new_rows.append(f"| {model_name} | {cond_label} | {total} | {illegal} | {err_rate} | {go} |")

    table_header = (
        "| Model | Observation Condition | Total Moves | Illegal / Rejected Moves | Invalid Move Error Rate (%) | Reached Terminal State (`game_over`) |\n"
        "|:---|:---|:---:|:---:|:---:|:---:|"
    )
    full_table = table_header + "\n" + "\n".join(new_rows)

    # Replace table in markdown
    import re
    pattern = r"\| Model \| Observation Condition \|.*?\n(?:\|.*?\|\n)+"
    if re.search(pattern, content):
        updated = re.sub(pattern, full_table + "\n", content)
        p.write_text(updated, encoding="utf-8")
        print(f"\n[OK] Updated table in {p}")
    else:
        print("Could not find table pattern to replace in markdown.")


if __name__ == "__main__":
    obs_conditions = {
        "DeepSeek (No Legal Moves)": (
            "artifacts/part3-no-legal-moves-deepseek.json",
            "artifacts/part3-no-legal-moves-deepseek-result.json",
        ),
        "DeepSeek (Legal Moves)": (
            "artifacts/part3-legal-moves-deepseek.json",
            "artifacts/part3-legal-moves-deepseek-result.json",
        ),
        "GPT-OSS (No Legal Moves)": (
            "artifacts/part3-no-legal-moves-gpt-oss.json",
            "artifacts/part3-no-legal-moves-gpt-oss-result.json",
        ),
        "GPT-OSS (Legal Moves)": (
            "artifacts/part3-legal-moves-gpt-oss.json",
            "artifacts/part3-legal-moves-gpt-oss-result.json",
        ),
    }

    if len(sys.argv) > 1 and sys.argv[1] == "swebench":
        analyze_token_usage(
            "artifacts/django__django-15368-trajectory.json",
            "artifacts/django__django-15368-baseline-trajectory.json",
        )
    elif len(sys.argv) > 1 and sys.argv[1] == "chess":
        analyze_chess_observation_experiment(obs_conditions)
    elif len(sys.argv) > 1 and sys.argv[1] == "update-report":
        res = analyze_chess_observation_experiment(obs_conditions)
        update_observation_report(res)
    else:
        print("Usage: python scripts/analyze_trajectories.py [swebench|chess|update-report]")
