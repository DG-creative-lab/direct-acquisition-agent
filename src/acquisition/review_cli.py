import json
from pathlib import Path

from acquisition.adapters.review_report import write_review
from acquisition.reviews import ReviewPolicy
from acquisition.review_demo import run_review_demo


def add_review_commands(commands):
    actor = commands.add_parser("review-actor", help="Trusted local administration; not hosted authentication")
    actor.add_argument("--actor", required=True)
    actor.add_argument("--role", action="append", choices=("operator", "reviewer"), required=True)
    actor.add_argument("--disabled", action="store_true")
    evidence = commands.add_parser("review-evidence", help="Activate a manually verified product pack and review policy")
    evidence.add_argument("--actor", required=True)
    evidence.add_argument("--request-id", required=True)
    evidence.add_argument("--pack", type=Path, default=Path(__file__).resolve().parents[2] / "config/iwoca-product-facts-v1.json")
    evidence.add_argument("--policy", type=Path)
    opened = commands.add_parser("review-open")
    opened.add_argument("--run", required=True)
    opened.add_argument("--actor", required=True)
    shown = commands.add_parser("review-show")
    shown.add_argument("--case", required=True)
    shown.add_argument("--html", type=Path)
    shown.add_argument("--out", type=Path, default=Path(".local/review-exports"))
    for name in ("review-decide", "review-refresh", "review-replace", "review-revoke", "review-handoff"):
        command = commands.add_parser(name)
        command.add_argument("--case", required=True)
        command.add_argument("--actor", required=True)
        command.add_argument("--request-id", required=True)
        if name in {"review-decide", "review-refresh", "review-replace"}:
            command.add_argument("--subject", required=True)
        if name == "review-decide":
            command.add_argument("--decision", choices=("approve", "reject"), required=True)
            command.add_argument("--ttl-seconds", type=int, default=86400)
        if name in {"review-decide", "review-revoke"}:
            command.add_argument("--reason", required=True)
        if name in {"review-revoke", "review-handoff"}:
            command.add_argument("--approval", required=True)
        if name == "review-replace":
            command.add_argument("--draft", required=True)
    suppression = commands.add_parser("review-suppress", help="Record an organization-wide synthetic suppression")
    for key in ("actor", "request-id", "business", "reason"):
        suppression.add_argument("--" + key, required=True)
    demo = commands.add_parser("demo-review", help="Scripted synthetic reviewer decisions and a simulated agency")
    demo.add_argument("--request-id", default="day-three")
    demo.add_argument("--out", type=Path, default=Path(".local/day-three"))


def review_command(app, args):
    store, scope = app.reviews.store, args.organization
    if args.command == "review-actor":
        return store.register_actor(scope, args.actor, tuple(args.role), not args.disabled)
    if args.command == "review-evidence":
        policy = ReviewPolicy(**json.loads(args.policy.read_text())) if args.policy else ReviewPolicy()
        return store.activate(scope, args.actor, args.request_id, json.loads(args.pack.read_text()), policy)
    if args.command == "review-open":
        return store.open_case(scope, args.run, args.actor)
    if args.command == "review-show":
        view = store.view(scope, args.case)
        if args.html:
            view["export_directory"] = str(app.export_review(scope, args.case, args.out, view["subject"]["id"]).resolve())
            view["review_html"] = str(write_review(view, args.db, args.html))
        return view
    if args.command == "review-decide":
        return store.decide(scope, args.case, args.subject, args.actor, args.decision, args.request_id, args.reason, args.ttl_seconds)
    if args.command == "review-refresh":
        return app.reviews.refresh(scope, args.case, args.subject, args.actor, args.request_id)
    if args.command == "review-replace":
        return app.reviews.replace(scope, args.case, args.subject, args.draft, args.actor, args.request_id)
    if args.command == "review-revoke":
        return store.revoke(scope, args.case, args.approval, args.actor, args.request_id, args.reason)
    if args.command == "review-handoff":
        return store.handoff(scope, args.case, args.approval, args.actor, args.request_id)
    if args.command == "review-suppress":
        return store.suppress(scope, args.actor, args.request_id, args.business, args.reason)
    if args.command == "demo-review":
        return run_review_demo(app, scope, args.request_id, args.out, args.db)
    raise ValueError("Unknown review command")
