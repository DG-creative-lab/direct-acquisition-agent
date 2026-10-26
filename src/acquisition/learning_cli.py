import json
from pathlib import Path

from acquisition.adapters.learning_report import write_learning


def add_learning_commands(commands):
    opened = commands.add_parser("learning-open", help="Freeze an accepted simulated campaign into a 28-day response cohort")
    opened.add_argument("--case", required=True)
    for name in ("learning-import", "learning-finalize"):
        command = commands.add_parser(name)
        command.add_argument("--cohort", required=True)
        if name == "learning-import":
            command.add_argument("--file", type=Path, required=True)
        else:
            command.add_argument("--complete-through", type=float, required=True)
    for command in (opened, commands.choices["learning-import"], commands.choices["learning-finalize"]):
        command.add_argument("--actor", required=True)
        command.add_argument("--request-id", required=True)
    show = commands.add_parser("learning-show")
    show.add_argument("--cohort", required=True)
    show.add_argument("--html", type=Path)
    demo = commands.add_parser("demo-learning", help="Scripted synthetic outcomes with an isolated simulated clock")
    demo.add_argument("--request-id", default="day-four")
    demo.add_argument("--out", type=Path, default=Path(".local/day-four"))


def learning_command(app, args):
    store, scope = app.learning.store, args.organization
    if args.command == "learning-open":
        return app.learning.open(scope, args.case, args.actor, args.request_id)
    if args.command == "learning-import":
        with args.file.open("rb") as stream:
            raw = stream.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError("Outcome batch exceeds the 4 MiB limit; split it into smaller batches")
        return store.ingest(scope, args.actor, args.request_id, args.cohort, json.loads(raw))
    if args.command == "learning-finalize":
        return store.finalize(scope, args.actor, args.request_id, args.cohort, args.complete_through)
    if args.command == "learning-show":
        view = store.view(scope, args.cohort)
        if args.html:
            view["learning_html"] = str(write_learning(view, args.html))
        return view
    raise ValueError("Unknown learning command")
