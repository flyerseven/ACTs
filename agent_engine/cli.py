"""Command-line interface for the Agent decision engine."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from agent_engine.engine import AgentEngine
from agent_engine.config import EngineConfig
from agent_engine.builtin_tools import calculate, read_file, write_file, web_search, execute_python

from llm.factory import LLMAdapterFactory
from core.models import LLMConfig


def build_engine(args) -> AgentEngine:
    """Build an AgentEngine from CLI arguments."""
    config = EngineConfig(
        max_steps=args.max_steps,
        reflect_interval=args.reflect_interval,
        llm_api_key=args.api_key or "",
        llm_base_url=args.base_url,
        llm_model=args.model,
        log_format="json" if args.json_log else "text",
        workspace_dir=args.workspace,
        debug=args.debug,
    )

    if not args.api_key:
        print("No API key provided. Use --api-key or set AGENT_ENGINE_LLM_API_KEY env var.")
        sys.exit(1)

    llm_config = LLMConfig(
        provider="deepseek",
        name=args.model,
        base_url=args.base_url,
    )
    adapter = LLMAdapterFactory.create(llm_config, args.api_key)

    engine = AgentEngine(llm=adapter, config=config)

    # Register builtin tools
    for tool_name in (args.tools or "all").split(","):
        tool_name = tool_name.strip()
        if tool_name in ("all", "calculator"):
            engine.tools.register_from_func(calculate)
        if tool_name in ("all", "files"):
            engine.tools.register_from_func(read_file)
            engine.tools.register_from_func(write_file)
        if tool_name in ("all", "search"):
            engine.tools.register_from_func(web_search)
        if tool_name in ("all", "code_exec"):
            engine.tools.register_from_func(execute_python)

    return engine


async def cmd_run(args) -> None:
    """Execute the run subcommand."""
    engine = build_engine(args)
    print(f"Goal: {args.goal}")
    print(f"Max steps: {args.max_steps} | Model: {args.model}")
    print("-" * 50)

    state = await engine.run(args.goal)

    print()
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(state.model_dump(mode="json"), f, indent=2, ensure_ascii=False, default=str)
        print(f"State saved to {args.output}")

    if args.mermaid:
        from agent_engine.observe import Observer
        obs = Observer()
        mermaid = obs.generate_mermaid(state)
        with open(args.mermaid, "w", encoding="utf-8") as f:
            f.write(mermaid)
        print(f"Mermaid diagram saved to {args.mermaid}")


def cmd_tools(args) -> None:
    """List available builtin tools."""
    print("Builtin tools:")
    print("  calculator   - Safe mathematical expression evaluation")
    print("  read_file    - Read a file (absolute path = full filesystem; relative = workspace)")
    print("  list_files   - List files in a directory (absolute or workspace-relative)")
    print("  write_file   - Write content to a file in the workspace")
    print("  web_search   - Search the web via DuckDuckGo")
    print("  code_exec    - Execute Python code in an isolated subprocess")


def cmd_visualize(args) -> None:
    """Generate a Mermaid diagram from a saved state file."""
    import json as _json
    from agent_engine.state import StateManager
    from agent_engine.observe import Observer

    with open(args.state_file, "r", encoding="utf-8") as f:
        data = _json.load(f)

    sm = StateManager.from_dict(data)
    obs = Observer()
    mermaid = obs.generate_mermaid(sm.state)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(mermaid)
        print(f"Mermaid diagram saved to {args.output}")
    else:
        print(mermaid)


def main():
    parser = argparse.ArgumentParser(
        prog="agent-engine",
        description="Autonomous Agent Decision Engine",
    )
    sub = parser.add_subparsers(dest="command")

    # Run
    run_parser = sub.add_parser("run", help="Run the agent with a goal")
    run_parser.add_argument("goal", help="The goal/task for the agent")
    run_parser.add_argument("--max-steps", type=int, default=50)
    run_parser.add_argument("--reflect-interval", type=int, default=3)
    run_parser.add_argument("--model", default="deepseek-v4-pro")
    run_parser.add_argument("--api-key", default="")
    run_parser.add_argument("--base-url", default="https://api.deepseek.com")
    run_parser.add_argument("--tools", default="all")
    run_parser.add_argument("--workspace", default="./workspace")
    run_parser.add_argument("--output", default="")
    run_parser.add_argument("--mermaid", default="")
    run_parser.add_argument("--json-log", action="store_true")
    run_parser.add_argument("--debug", "-d", action="store_true", help="Enable real-time debug output to stderr")

    # Tools
    sub.add_parser("tools", help="List available tools")

    # Visualize
    viz_parser = sub.add_parser("visualize", help="Generate Mermaid diagram from a saved state")
    viz_parser.add_argument("state_file", help="Path to saved state JSON")
    viz_parser.add_argument("--output", default="")

    args = parser.parse_args()

    if args.command == "run":
        asyncio.run(cmd_run(args))
    elif args.command == "tools":
        cmd_tools(args)
    elif args.command == "visualize":
        cmd_visualize(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
