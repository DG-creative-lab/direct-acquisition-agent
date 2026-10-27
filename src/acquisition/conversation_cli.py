"""Persistent planning access before the conversational React client is added."""

import argparse
import json
from pathlib import Path

from acquisition.workspace import Workspace


def main():
    parser = argparse.ArgumentParser(description="Local campaign conversation and explicit model planning")
    parser.add_argument("--root", type=Path, default=Path(".local/workspace"))
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("new")
    create.add_argument("--request-id", required=True)
    create.add_argument("--title", default="New campaign conversation")
    commands.add_parser("list")
    for command in ("show", "message", "plan"):
        sub = commands.add_parser(command, help="Plan explicitly invokes the configured OpenRouter model" if command == "plan" else None)
        sub.add_argument("--conversation", required=True)
        if command != "show":
            sub.add_argument("--request-id", required=True)
            sub.add_argument("--revision", type=int, required=True)
        if command == "message":
            sub.add_argument("--content", required=True)
    args = parser.parse_args()
    workspace = Workspace(args.root)
    if args.command == "new":
        result = workspace.create_conversation(args.request_id, args.title)
    elif args.command == "list":
        result = workspace.conversations()
    elif args.command == "show":
        result = workspace.conversation(args.conversation)
    elif args.command == "message":
        result = workspace.message_conversation(args.conversation, args.request_id, args.revision, args.content)
    else:
        result = workspace.plan_conversation(args.conversation, args.request_id, args.revision)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
