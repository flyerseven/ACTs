"""Track Claude Code token usage for the ACTs project.

Usage:
  python scripts/track_claude.py record <prompt> <completion> [--model deepseek-v4-pro] [--note "..."]
  python scripts/track_claude.py stats
  python scripts/track_claude.py recent [-n 10]
  python scripts/track_claude.py models
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path so we can import from src
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.token_tracker import MODEL_PRICING, TokenTracker


def cmd_record(args: argparse.Namespace) -> int:
    tracker = TokenTracker()
    total = args.prompt + args.completion
    usage = tracker.record(
        model=args.model,
        provider="claude-code",
        prompt_tokens=args.prompt,
        completion_tokens=args.completion,
        total_tokens=total,
    )
    cost_str = f" ${usage.cost:.4f}" if usage.cost else ""
    print(f"Recorded: {usage.prompt_tokens:,} + {usage.completion_tokens:,} = {total:,} tokens{cost_str}")
    print(f"  Model: {usage.model}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    tracker = TokenTracker()
    stats = tracker.get_total_stats()

    if stats.total_requests == 0:
        print("No token usage recorded yet.")
        print(f"Log file: {tracker.log_path}")
        return 0

    print("=" * 55)
    print("  Claude Code Token Usage — ACTs Project")
    print("=" * 55)
    print(f"  Total requests:        {stats.total_requests:>8}")
    print(f"  Prompt tokens:         {stats.total_prompt_tokens:>12,}")
    print(f"  Completion tokens:     {stats.total_completion_tokens:>12,}")
    print(f"  Total tokens:          {stats.total_tokens:>12,}")
    if stats.total_cost > 0:
        print(f"  Estimated cost:        ${stats.total_cost:>11.4f}")
    print("-" * 55)
    if stats.by_model:
        print("  By model:")
        for model, ms in sorted(stats.by_model.items()):
            cost_s = f"  ${ms['cost']:.4f}" if ms["cost"] else ""
            print(f"    {model}: {ms['requests']} req, {ms['tokens']:,} tokens{cost_s}")
    print("=" * 55)
    return 0


def cmd_recent(args: argparse.Namespace) -> int:
    tracker = TokenTracker()
    entries = tracker.get_recent(args.n)
    if not entries:
        print("No entries.")
        return 0
    print(f"{'Timestamp':<20} {'Model':<22} {'Prompt':>10} {'Comp':>10} {'Total':>10} {'Cost':>10}")
    print("-" * 92)
    for e in entries:
        cost_s = f"${e.cost:.4f}" if e.cost else "-"
        print(f"{e.timestamp:<20} {e.model:<22} {e.prompt_tokens:>10,} {e.completion_tokens:>10,} {e.total_tokens:>10,} {cost_s:>10}")
    return 0


def cmd_models(_args: argparse.Namespace) -> int:
    print("Known model pricing (per 1M tokens):")
    print(f"{'Model':<25} {'Input':>12} {'Output':>12}")
    print("-" * 49)
    for model, price in MODEL_PRICING.items():
        print(f"{model:<25} ${price['input']:>10.2f} ${price['output']:>10.2f}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Track Claude Code token consumption for ACTs development"
    )
    sub = parser.add_subparsers(dest="command")

    p_rec = sub.add_parser("record", help="Record a Claude Code conversation's token usage")
    p_rec.add_argument("prompt", type=int, help="Prompt (input) tokens")
    p_rec.add_argument("completion", type=int, help="Completion (output) tokens")
    p_rec.add_argument("--model", default="deepseek-v4-pro", help="Model name (default: deepseek-v4-pro)")
    p_rec.add_argument("--note", default="", help="Optional note about the session")

    p_stats = sub.add_parser("stats", help="Show total token usage statistics")

    p_recent = sub.add_parser("recent", help="Show recent usage entries")
    p_recent.add_argument("-n", type=int, default=10, help="Number of entries (default: 10)")

    p_models = sub.add_parser("models", help="List known model pricing")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 1

    handlers = {
        "record": cmd_record,
        "stats": cmd_stats,
        "recent": cmd_recent,
        "models": cmd_models,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
