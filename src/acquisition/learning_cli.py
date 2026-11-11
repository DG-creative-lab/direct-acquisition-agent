import json
from pathlib import Path

from acquisition.adapters.learning_report import write_learning


def add_learning_commands(commands):
    opened = commands.add_parser("learning-open", help="Freeze an accepted simulated campaign into a 28-day response cohort")
    opened.add_argument("--case", required=True)
    for name in ("learning-import", "learning-import-report", "learning-finalize"):
        command = commands.add_parser(name)
        command.add_argument("--cohort", required=True)
        if name != "learning-finalize":
            command.add_argument("--file", type=Path, required=True)
        else:
            command.add_argument("--complete-through", type=float, required=True)
    for name in ("learning-open", "learning-import", "learning-import-report", "learning-finalize"):
        command = commands.choices[name]
        command.add_argument("--actor", required=True)
        command.add_argument("--request-id", required=True)
    show = commands.add_parser("learning-show")
    show.add_argument("--cohort", required=True)
    show.add_argument("--html", type=Path)
    report = commands.add_parser("learning-show-report", help="Inspect the saved pages and receipt for one provider report")
    report.add_argument("--cohort", required=True)
    report.add_argument("--report", required=True)
    start = commands.add_parser("learning-monitor-start", help="Schedule recorded synthetic reports for a cohort")
    start.add_argument("--first-check", type=float, required=True, help="Unix timestamp within the cohort window")
    start.add_argument("--interval-seconds", type=int, required=True)
    start.add_argument("--file", type=Path, action="append", required=True, help="Repeat in report watermark order")
    update = commands.add_parser("learning-monitor-update", help="Pause, resume or change the cadence of an unfinished schedule")
    update.add_argument("--revision", type=int, required=True)
    update.add_argument("--status", choices=("scheduled", "paused"), required=True)
    update.add_argument("--interval-seconds", type=int)
    for command in (start, update):
        command.add_argument("--actor", required=True)
        command.add_argument("--request-id", required=True)
    for command in (start, update,
                    commands.add_parser("learning-monitor-show", help="Inspect report monitoring progress"),
                    commands.add_parser("learning-monitor-tick", help="Check one due recorded report in a standalone store")):
        command.add_argument("--cohort", required=True)
    demo = commands.add_parser("demo-learning", help="Scripted synthetic outcomes with an isolated simulated clock")
    demo.add_argument("--request-id", default="day-four")
    demo.add_argument("--out", type=Path, default=Path(".local/day-four"))


def learning_command(app, args):
    store, scope = app.learning.store, args.organization
    if args.command == "learning-open":
        return app.learning.open(scope, args.case, args.actor, args.request_id)
    if args.command == "learning-import-report":
        return app.learning.ingest_report(scope, args.actor, args.request_id, args.cohort, args.file)
    if args.command == "learning-show-report":
        return store.report_snapshot(scope, args.cohort, args.report)
    if args.command == "learning-monitor-start":
        return app.learning.schedule_reports(scope, args.actor, args.request_id, args.cohort,
                                             args.first_check, args.interval_seconds, args.file)
    if args.command == "learning-monitor-update":
        return app.learning.monitoring.update(scope, args.actor, args.request_id, args.cohort,
                                              args.revision, args.status, args.interval_seconds)
    if args.command == "learning-monitor-tick":
        app.learning.check_reports(scope, args.cohort, standalone=True)
    if args.command in ("learning-monitor-tick", "learning-monitor-show"):
        return {"monitoring": app.learning.monitoring.status(scope, args.cohort)}
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
