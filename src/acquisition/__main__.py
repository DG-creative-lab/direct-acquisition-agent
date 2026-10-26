import argparse
import json
from pathlib import Path

from acquisition.bootstrap import build
from acquisition.contracts import Conflict, NotFound
from acquisition.adapters.environment import openrouter_key
from acquisition.adapters.openrouter import OpenRouter, inexpensive_models
from acquisition.reasoning import ModelConfig, ModelError


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic acquisition workflow; optional OpenRouter copy generation. No sending.")
    parser.add_argument("--db", default=".local/day-one.sqlite")
    parser.add_argument("--organization", default="demo-org", help="Local scope selector, not authentication")
    parser.add_argument("--model", help="OpenRouter model ID; model commands default to openai/gpt-oss-120b")
    parser.add_argument("--model-max-calls", type=int, default=10, help="Inference reservations per run, including claim checks (maximum 12)")
    parser.add_argument("--tool-choice", choices=("auto", "required"), help="GPT-OSS-120B defaults to required tool use; auto omits the parameter")
    parser.add_argument("--env-file", type=Path, default=Path(".env.local"))
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("create", "demo", "create-model", "demo-model"):
        create = commands.add_parser(name)
        create.add_argument("--request-id", default="grounded-day-two-plain" if name.endswith("model") else "day-one-plain")
        create.add_argument("--size", type=int, default=1000)
        create.add_argument("--seed", type=int, default=42)
        create.add_argument("--budget-pence", type=int, default=85000)
        create.add_argument("--as-of", default="2026-10-25")
    work = commands.add_parser("work")
    work.add_argument("--max-tasks", type=int, default=20)
    commands.add_parser("models", help="List inexpensive tool-capable models from the live public catalogue")
    remember = commands.add_parser("remember", help="Store a local reviewer preference, not outcome evidence")
    for field in ("segment", "preferred", "avoid", "reason"):
        remember.add_argument("--" + field, required=True)
    for name in ("status", "acknowledge", "cancel", "export", "calls"):
        action = commands.add_parser(name)
        action.add_argument("--run", required=True)
        if name == "acknowledge":
            action.add_argument("--reference", required=True)
        if name == "export":
            action.add_argument("--out", type=Path, default=Path(".local/exports"))
    args = parser.parse_args()
    try:
        if args.command == "models":
            print(json.dumps(inexpensive_models(), indent=2))
            return
        model = args.model or ("openai/gpt-oss-120b" if args.command in {"create-model", "demo-model"} else None)
        gateway = OpenRouter(openrouter_key(args.env_file)) if model else None
        force_tools = args.tool_choice == "required" if args.tool_choice else model == "openai/gpt-oss-120b"
        config = ModelConfig(model, max_calls=args.model_max_calls, force_tool_choice=force_tools) if model else None
        app = build(args.db, gateway=gateway, model_config=config)
        scope = args.organization
        if args.command in {"create", "demo", "create-model", "demo-model"}:
            start = app.start_model if args.command.endswith("model") else app.start
            run_id = start(scope, args.request_id, args.size, args.seed, args.budget_pence, args.as_of)
            result = {"run_id": run_id, "mode": "synthetic_generated_unreviewed" if args.command.endswith("model") else "synthetic_day_one_no_release"}
            if args.command.startswith("demo"):
                result["worker_ticks"] = app.worker.drain(scope)
                result["state"] = app.tasks.inspect(scope, run_id)
                if result["state"]["run"]["status"] in {"waiting", "succeeded"}:
                    result["export_directory"] = str(app.export(scope, run_id, Path(".local/exports")).resolve())
                if args.command.endswith("model"):
                    result["model_calls"] = app.calls.inspect(scope, run_id)
                if result["state"]["run"]["status"] == "failed":
                    print(json.dumps(result, indent=2))
                    parser.exit(1, "Workflow failed; inspect its task and model receipts.\n")
        elif args.command == "work":
            result = {"worker_ticks": app.worker.drain(scope, args.max_tasks)}
        elif args.command == "status":
            result = app.tasks.inspect(scope, args.run)
        elif args.command == "calls":
            result = app.calls.inspect(scope, args.run)
        elif args.command == "remember":
            result = {"memory_id": app.memory.remember(scope, args.segment, args.preferred, args.avoid, args.reason)}
        elif args.command == "export":
            result = {"export_directory": str(app.export(scope, args.run, args.out).resolve())}
        else:
            if args.command == "acknowledge":
                app.tasks.acknowledge(scope, args.run, args.reference, app.clock())
            else:
                app.tasks.cancel(scope, args.run, app.clock())
            result = app.tasks.inspect(scope, args.run)
        print(json.dumps(result, indent=2))
    except (ValueError, Conflict, NotFound, ModelError) as error:
        parser.exit(2, f"{type(error).__name__}: {error}\n")


if __name__ == "__main__":
    main()
