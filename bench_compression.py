#!/usr/bin/env python3
"""
Benchmark harness: Apply `compress_text` as a preprocessing step in lm-evaluation-harness
for OpenAI GPT-3.5 (chat completions). Runs evaluations across a sweep of
tokens_to_keep_ratio in [1.0, 0.9, ..., 0.1], collects accuracy, and plots
accuracy vs compression.
"""

import os
import json
import math
import argparse
from copy import deepcopy
from typing import Any, Dict, List, Optional

import matplotlib.pyplot as plt

# Import lm-evaluation-harness
from lm_eval.evaluator import simple_evaluate

# Import OpenAI chat completions model class to subclass
from lm_eval.models.openai_completions import OpenAIChatCompletion

# Reuse the project's compression implementation
from main import compress_text  # uses tiktoken and logging config from project


class CompressedOpenAIChatCompletion(OpenAIChatCompletion):
    """OpenAI chat-completions model that compresses user prompts before sending.

    Applies `compress_text` to user messages' content fields using
    `tokens_to_keep_ratio`. If `tokens_to_keep_ratio >= 1.0`, no compression.
    """

    def __init__(
        self,
        *,
        tokens_to_keep_ratio: float = 1.0,
        compression_ratio: float = 1.0,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._tokens_to_keep_ratio = tokens_to_keep_ratio
        self._compression_ratio = compression_ratio

    def _compress_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not isinstance(messages, list):
            return messages
        if self._tokens_to_keep_ratio is None or self._tokens_to_keep_ratio >= 1.0:
            return messages
        compressed: List[Dict[str, Any]] = []
        for msg in messages:
            msg_copy = deepcopy(msg)
            # Only compress user-authored content
            if msg_copy.get("role") == "user" and isinstance(msg_copy.get("content"), str):
                msg_copy["content"] = compress_text(
                    msg_copy["content"],
                    compression_ratio=self._compression_ratio,
                    tokens_to_keep_ratio=self._tokens_to_keep_ratio,
                )
            compressed.append(msg_copy)
        return compressed

    def _create_payload(
        self,
        messages: List[Dict[str, Any]],
        generate: bool = False,
        gen_kwargs: Optional[dict] = None,
        seed: int = 1234,
        eos: Optional[str] = "<|endoftext|>",
        **kwargs,
    ) -> dict:
        # messages is a list[dict] due to apply_chat_template usage upstream
        compressed_messages = self._compress_messages(messages)

        # Copy of OpenAIChatCompletion._create_payload, but using compressed_messages
        gen_kwargs = {} if gen_kwargs is None else gen_kwargs
        gen_kwargs.pop("do_sample", False)
        if "max_tokens" in gen_kwargs:
            max_tokens = gen_kwargs.pop("max_tokens")
        else:
            max_tokens = gen_kwargs.pop("max_gen_toks", self._max_gen_toks)
        temperature = gen_kwargs.pop("temperature", 0)

        # The base class uses handle_stop_sequences under the hood; we can pass through
        from lm_eval.models.utils import handle_stop_sequences

        stop = handle_stop_sequences(gen_kwargs.pop("until", ["<|endoftext|>"]), eos)
        if not isinstance(stop, (list, tuple)):
            stop = [stop]

        payload = {
            "messages": compressed_messages,
            "model": self.model,
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
            "stop": stop[:4],
            "seed": seed,
            **gen_kwargs,
        }
        if "o1" in self.model:
            payload.pop("stop", None)
            payload["temperature"] = 1
        elif "o3" in self.model:
            payload.pop("temperature", None)
        return payload


def run_benchmark(
    model_name: str = "gpt-3.5-turbo",
    task_list: Optional[List[str]] = None,
    output_dir: str = "/workspace/results",
    ratios: Optional[List[float]] = None,
    limit: Optional[int] = None,
) -> str:
    os.makedirs(output_dir, exist_ok=True)

    # Default: tinyGSM8k for quick sanity; user can expand to other tasks later
    if not task_list:
        task_list = ["tinyGSM8k"]

    # Sweep ratios from 1.0 down to 0.1 inclusive, step 0.1
    if ratios is None:
        ratios = [round(x, 1) for x in [1.0 - 0.1 * i for i in range(0, 10)]]

    all_results: List[Dict[str, Any]] = []

    for ratio in ratios:
        model = CompressedOpenAIChatCompletion(
            model=model_name,
            tokenizer_backend=None,  # use string prompts; chat template returns JsonChatStr
            tokenized_requests=False,
            tokens_to_keep_ratio=ratio,
            compression_ratio=1.0,
        )

        eval_result: Dict[str, Any] = simple_evaluate(
            model=model,
            tasks=task_list,
            apply_chat_template=True,
            # Be explicit: don't override YAML generation kwargs
            gen_kwargs=None,
            # Disable cache to measure actual runs
            use_cache=None,
            cache_requests=False,
            # Keep it deterministic
            random_seed=0,
            numpy_random_seed=1234,
            torch_random_seed=1234,
            limit=limit,
        )

        # Extract a primary accuracy-like metric per task
        task_metrics: Dict[str, Any] = eval_result.get("results", {})
        primary_metric_value: Optional[float] = None
        primary_metric_name: Optional[str] = None

        # Try to find a common metric (exact_match, acc/accuracy) across tasks
        preferred_metric_keys = ["exact_match", "acc", "accuracy", "f1"]
        # Aggregate average across tasks if multiple
        per_task_vals: List[float] = []
        for task_name, metrics in task_metrics.items():
            found_val: Optional[float] = None
            for key in preferred_metric_keys:
                if key in metrics and isinstance(metrics[key], (int, float)):
                    found_val = float(metrics[key])
                    break
            if found_val is None:
                # fallback: take first float metric
                for v in metrics.values():
                    if isinstance(v, (int, float)):
                        found_val = float(v)
                        break
            if found_val is not None:
                per_task_vals.append(found_val)

        if per_task_vals:
            primary_metric_value = float(sum(per_task_vals) / len(per_task_vals))
            primary_metric_name = "avg_primary_metric"

        record = {
            "tokens_to_keep_ratio": ratio,
            "primary_metric": primary_metric_value,
            "primary_metric_name": primary_metric_name,
            "task_metrics": task_metrics,
        }
        all_results.append(record)

        # Persist intermediate
        with open(os.path.join(output_dir, "compression_results.json"), "w") as f:
            json.dump(all_results, f, indent=2)

    # Plot accuracy vs compression
    xs = [r["tokens_to_keep_ratio"] for r in all_results]
    ys = [
        (r["primary_metric"] if r["primary_metric"] is not None else math.nan)
        for r in all_results
    ]

    plt.figure(figsize=(8, 5))
    plt.plot(xs, ys, marker="o")
    plt.gca().invert_xaxis()  # higher compression to the right (lower keep ratio)
    plt.xlabel("Tokens to Keep Ratio")
    plt.ylabel(record.get("primary_metric_name") or "Primary Metric")
    plt.title(
        f"Accuracy vs Compression (GPT-3.5 chat)\nTasks: {', '.join(task_list)}"
    )
    plt.grid(True, alpha=0.3)
    plot_path = os.path.join(output_dir, "accuracy_vs_compression.png")
    plt.tight_layout()
    plt.savefig(plot_path)

    return plot_path


if __name__ == "__main__":
    # Expect OPENAI_API_KEY to be present in env (Cursor user secrets)
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY not found in environment. Please set it via user secrets."
        )

    parser = argparse.ArgumentParser(description="Compression benchmark harness")
    parser.add_argument(
        "--tasks",
        type=str,
        default="tinyGSM8k",
        help="Comma-separated list of task names (e.g., 'triviaqa' or 'tinyGSM8k')",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit examples per task (int). Useful for quick runs",
    )
    parser.add_argument(
        "--output-subdir",
        type=str,
        default=None,
        help="Subdirectory under /workspace/results to store outputs",
    )
    args = parser.parse_args()

    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]
    out_dir = "/workspace/results"
    if args.output_subdir:
        out_dir = os.path.join(out_dir, args.output_subdir)

    out_image = run_benchmark(task_list=tasks, output_dir=out_dir, limit=args.limit)
    print(f"Saved plot to: {out_image}")

