import argparse
import json
from pathlib import Path

from acquisition.bootstrap import build_cli_application, model_catalogue
from acquisition.application.cli_commands import run_command
from acquisition.contracts import Conflict, NotFound
from acquisition.reasoning import ModelError
from acquisition.entrypoints.learning_cli import add_learning_commands, learning_command
from acquisition.entrypoints.learning_demo import run_learning_demo
from acquisition.entrypoints.review_cli import add_review_commands, review_command


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic acquisition workflow; optional OpenRouter copy generation. No sending.")
    parser.add_argument("--db", default=".local/day-one.sqlite")
    parser.add_argument("--organization", default="demo-org", help="Local scope selector, not authentication")
    parser.add_argument("--model", help="OpenRouter model ID; model commands default to openai/gpt-oss-120b")
    parser.add_argument("--model-max-calls", type=int, default=10, help="Inference reservations per run, including claim checks (maximum 12)")
    parser.add_argument("--tool-choice", choices=("auto", "required"), help="GPT-OSS-120B defaults to required tool use; auto omits the parameter")
    parser.add_argument("--env-file", type=Path, default=Path(".env.local"))
    parser.add_argument('--verified-admissions',action='store_true',help='Seal this database to verified admission. Execution stays paused; this cannot be undone.')
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("create", "demo", "create-model", "demo-model"):
        create = commands.add_parser(name)
        create.add_argument("--request-id", default="grounded-day-two-plain" if name.endswith("model") else "day-one-plain")
        create.add_argument("--size", type=int, default=1000)
        create.add_argument("--seed", type=int, default=42)
        create.add_argument("--budget-pence", type=int, default=85000)
        create.add_argument("--as-of", default="2026-10-25")
        create.add_argument("--campaign-id", help="Stable campaign identity when preparing a new copy revision")
        create.add_argument('--parent-run',help='Exact verified parent run for a new descendant campaign')
    work = commands.add_parser("work")
    work.add_argument("--max-tasks", type=int, default=20)
    commands.add_parser("models", help="List inexpensive tool-capable models from the live public catalogue")
    commands.add_parser('admission-cutover',help='Close legacy creation in a quiescent store; does not activate execution')
    commands.add_parser("execution-unresolved", help="Inspect quarantined legacy runs before operator reconciliation")
    resolve=commands.add_parser("execution-resolve-independent", help="Attest that an inspected legacy run is independent of conversations")
    for field in ('run','request-id','fingerprint','actor','reason'):
        resolve.add_argument('--'+field,required=True)
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
    add_learning_commands(commands)
    add_review_commands(commands)
    args = parser.parse_args()
    try:
        if args.command == "models":
            print(json.dumps(model_catalogue(), indent=2))
            return
        if args.command == "demo-learning":
            if args.verified_admissions:raise ValueError('Verified admissions are paused; the complete learning demo requires execution')
            print(json.dumps(run_learning_demo(args.db, args.organization, args.request_id, args.out), indent=2))
            return
        model = args.model or ("openai/gpt-oss-120b" if args.command in {"create-model", "demo-model"} else None)
        app = build_cli_application(args.db, model=model, max_calls=args.model_max_calls,
                                    tool_choice=args.tool_choice, env_file=args.env_file,
                                    verified_admissions=args.verified_admissions or args.command=='admission-cutover')
        result = run_command(app, args, learning_command=learning_command, review_command=review_command)
        if args.command.startswith('demo') and result.get('state', {}).get('run', {}).get('status') == 'failed':
            print(json.dumps(result, indent=2))
            parser.exit(1, "Workflow failed; inspect its task and model receipts.\n")
        print(json.dumps(result, indent=2))
    except (ValueError, Conflict, NotFound, ModelError) as error:
        parser.exit(2, f"{type(error).__name__}: {error}\n")


if __name__ == "__main__":
    main()
