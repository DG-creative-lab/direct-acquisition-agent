"""CLI command execution using injected application APIs."""

def run_command(app, args, *, learning_command, review_command):
    scope = args.organization
    if args.command=='admission-cutover':
        result={'policy':'verified-paused/v1','execution':'fixture-only' if app.admissions.store.fixture_execution() else 'paused'}
    elif args.command=='execution-unresolved':
        result=app.execution.unresolved(scope)
    elif args.command=='execution-resolve-independent':
        result=app.execution.resolve_independent(scope,args.request_id,args.run,args.fingerprint,args.actor,args.reason)
    elif args.command.startswith("learning-"):
        result = learning_command(app, args)
    elif args.command.startswith("review-") or args.command == "demo-review":
        result = review_command(app, args)
    elif args.command in {"create", "demo", "create-model", "demo-model"}:
        start = app.start_model if args.command.endswith("model") else app.start
        run_id = start(scope, args.request_id, args.size, args.seed, args.budget_pence, args.as_of, campaign_id=args.campaign_id,
                       **({'parent_run_id':args.parent_run} if args.parent_run else {}))
        result = {"run_id": run_id, "mode": "synthetic_generated_unreviewed" if args.command.endswith("model") else "synthetic_day_one_no_release"}
        if args.command.startswith("demo"):
            result["worker_ticks"] = app.worker.drain(scope)
            result["state"] = app.tasks.inspect(scope, run_id)
            if result["state"]["run"]["status"] in {"waiting", "succeeded"}:
                result["export_directory"] = str(app.export(scope, run_id, ".local/exports").resolve())
            if args.command.endswith("model"):
                result["model_calls"] = app.calls.inspect(scope, run_id)
            if result["state"]["run"]["status"] == "failed":
                return result
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
    return result
