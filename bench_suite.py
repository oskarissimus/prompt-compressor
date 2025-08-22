#!/usr/bin/env python3
"""
Multi-benchmark compression sweep harness.

Runs the compression benchmark across multiple lm-evaluation-harness tasks
using OpenAI GPT-3.5 chat with your `compress_text` preprocessor.

For each task, saves results and a plot under results/<task>/.
"""

import os
import argparse
import subprocess
import sys
from typing import List


def run_one(task: str, limit: int | None, model: str) -> None:
    out_subdir = task.replace(",", "_")
    cmd = [
        sys.executable,
        "/workspace/bench_compression.py",
        "--tasks",
        task,
        "--output-subdir",
        out_subdir,
    ]
    if limit is not None:
        cmd.extend(["--limit", str(limit)])
    env = dict(os.environ)
    if not env.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY not set in environment")
    # Allow model override via env if needed later
    if model:
        env["BENCH_MODEL_NAME"] = model
    subprocess.check_call(cmd, env=env)


def main():
    parser = argparse.ArgumentParser(description="Run compression sweep on multiple tasks")
    parser.add_argument(
        "--tasks",
        type=str,
        default="triviaqa,squad_completion",
        help="Comma-separated task names",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Per-task example limit for quick runs",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-3.5-turbo",
        help="OpenAI chat model name",
    )
    args = parser.parse_args()

    tasks: List[str] = [t.strip() for t in args.tasks.split(",") if t.strip()]
    for t in tasks:
        print(f"\n=== Running task: {t} (limit={args.limit}) ===")
        try:
            run_one(t, args.limit, args.model)
        except Exception as e:
            print(f"[WARN] Task '{t}' failed: {e}. Continuing...")
            continue
        print(f"=== Finished task: {t} ===\n")


if __name__ == "__main__":
    main()

