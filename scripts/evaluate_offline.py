"""Bounded offline product evaluation. Run with PYTHONPATH=src python3 scripts/evaluate_offline.py."""
import argparse
import csv
import io
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from acquisition.conversations import FIXTURE_MESSAGE, validate_result
from acquisition.contracts import Conflict, NotFound
from acquisition.workspace import Workspace

NOW = 1792972800.0  # Fixed demo clock, independent of the operator's current date.


def evaluate(output):
    run = Path(tempfile.mkdtemp(prefix="run-", dir=output))
    checks = []
    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)
    def rejects(name, operation):
        try:
            operation()
        except (Conflict, NotFound, ValueError):
            check(name, True)
        else:
            check(name, False)
    def save(name, value):
        (run / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    report = {"mode": "OFFLINE_SYNTHETIC_EVALUATION", "clock": NOW,
              "checks": checks, "limitations": ["Supplied candidate validation is not model reasoning quality.",
              "Fixture copy is not live generated copy or a copy revision evaluation.",
              "Synthetic responses do not establish campaign performance.",
              "This is a serial local lifecycle, not concurrent hosted operation."]}
    try:
        # Guard both provider construction and ordinary Python socket dispatch.
        with patch('acquisition.workspace.OpenRouter', side_effect=AssertionError('Provider forbidden in offline evaluation')), patch('socket.socket.connect', side_effect=AssertionError('Network forbidden in offline evaluation')):
            candidate = {"outcome":"brief_proposal", "objective":"Test contractor response", "budget_pence":60000,
                         "segments":["contractors"], "copy_mode":"fixture", "question":"", "assumptions":[], "unsupported_reason":""}
            cases = [
                ("explicit_total", ["Prepare a £600 contractor campaign."], 60000, True),
                ("missing_total", ["Prepare a contractor campaign."], 60000, False),
                ("corrected_total", ["Use £600.", "Change the budget to £300."], 30000, True),
                ("stale_total", ["Use £600.", "Change the budget to £300."], 60000, False),
                ("relative_adjustment", ["Use £600.", "Increase the budget by £200."], 20000, False),
                ("unsupported_suffix", ["Use £600.", "Change the budget to £600k instead."], 60000, False),
                ("foreign_currency", ["Use USD 600."], 60000, False),
                ("ambiguous_total", ["Use £300 or £600."], 60000, False),
            ]
            corpus=[]
            for name, messages, budget, expected in cases:
                frozen={"messages":[{"id":f"m{i}","content":s} for i,s in enumerate(messages)], "conversation_id":"evaluation", "revision":len(messages), "knowledge_id":"offline-evaluation", "request_id":name}
                try:
                    result=validate_result(candidate | {"budget_pence":budget}, frozen, "evaluation")
                    accepted=True
                except ValueError:
                    result=None; accepted=False
                check("brief_"+name, accepted == expected)
                if not expected:
                    clarification=validate_result(candidate | {"outcome":"clarification", "budget_pence":None,"question":"What absolute GBP budget should I use?"},frozen,"evaluation")
                    check("clarification_"+name, clarification["approval"] == "not_granted")
                corpus.append({"name":name,"messages":messages,"candidate_budget_pence":budget,"expected_acceptance":expected,"accepted":accepted,"result":result})
            save("brief-corpus.json",corpus)
            root=run / "workspace"
            w=Workspace(root,real_clock=lambda:NOW)
            c=w.create_conversation("demo","Offline demo evaluation")["id"]
            w.message_conversation(c,"message",0,FIXTURE_MESSAGE)
            w.start_preparation(c,"prepare",1,True,False)
            for _ in range(10):
                w.advance_preparations()
                if w.conversation(c)["preparations"][0]["status"] == "review_ready": break
            check("preparation_reaches_review",w.conversation(c)["preparations"][0]["status"] == "review_ready")
            sid=w.conversation(c)["campaigns"][0]["session_id"]
            state=w.view(sid); save("initial-campaign.json",state)
            review=state["review"]; subject=review["subject"]["id"]
            check("draft_has_no_approval",not review["approval_valid"] and review["handoff"] is None)
            assignment_text=w.artifact(sid,"assignments",subject)[0].decode()
            (run / "assignments.csv").write_text(assignment_text)
            save("manifest.json",review["manifest"])
            assignments=list(csv.DictReader(io.StringIO(assignment_text)))
            mailed=sum(r["arm"] in {"A","B"} for r in assignments)
            controls=sum(r["arm"] == "no_mail" for r in assignments)
            check("independent_business_ids",len({r["business_id"] for r in assignments}) == len(assignments))
            check("assignment_counts_reconcile",mailed == review["manifest"]["counts"]["mailed"] and controls == review["manifest"]["counts"]["holdout"] and mailed+controls == len(assignments))
            check("integer_cost_within_budget",review["manifest"]["variable_cost_pence"] == mailed*85 <= 60000)
            rejects("unapproved_handoff_blocked",lambda:w.action(sid,"handoff",{"request_id":"unapproved","approval_id":"absent"}))
            a=w.action(sid,"approve",{"request_id":"approve","subject_id":subject,"reason":"Offline evaluation of exact campaign."})["review"]["approval"]["id"]
            payload={"request_id":"handoff","approval_id":a}
            accepted=w.action(sid,"handoff",payload); receipt=accepted["review"]["handoff"]
            save("acceptance-receipt.json",receipt)
            check("simulated_acceptance_only",receipt["mode"] == "SYNTHETIC_NO_PRINT_NO_SEND" and receipt["subject_id"] == subject)
            check("acceptance_replay",w.action(sid,"handoff",payload)["review"]["handoff"] == receipt)
            opened=w.action(sid,"open-learning",{"request_id":"open","handoff_id":receipt["id"]})
            cohort=opened["learning"]["cohort"]["id"]
            check("unknown_results_not_failures",opened["learning"]["missing"] == len(assignments) and opened["learning"]["beliefs"] == [])
            final=w.action(sid,"finalize",{"request_id":"final","handoff_id":receipt["id"],"cohort_id":cohort})
            check("complete_learning_counts",final["learning"]["missing"] == 0 and sum(b["trials"] for b in final["learning"]["beliefs"]) == len(assignments))
            check("all_experiment_arms_counted",{b["arm"] for b in final["learning"]["beliefs"]} == {"A","B","no_mail"})
            check("finalization_replay",w.action(sid,"finalize",{"request_id":"final","handoff_id":receipt["id"],"cohort_id":cohort})["learning"] == final["learning"])
            check("single_finalization_event",sum(e["kind"] == "cohort_finalized" for e in final["learning"]["events"]) == 1)
            save("finalized-learning.json",final["learning"])
            p=w.propose_followup(sid,"proposal",cohort); save("followup-proposal.json",p)
            child=w.prepare_followup(sid,"child",p["id"],"fixture",False)
            check("followup_needs_fresh_approval",child["review"]["subject"]["id"] != subject and not child["review"]["approval_valid"])
            old={r["business_id"] for r in assignments}
            new={r["id"] for r in child["audience"] if r["arm"] != "excluded"}
            check("followup_disjoint_and_nonempty",bool(new) and not old & new)
            check("parent_learning_immutable",w.view(sid)["learning"] == final["learning"])
            rejects("followup_cannot_inherit_approval",lambda:w.action(child["session"]["id"],"handoff",{"request_id":"old-approval","approval_id":a}))
            child_id=child["session"]["id"]
            child_subject=child["review"]["subject"]["id"]
            approved_child=w.action(child_id,"approve",{"request_id":"child-approve","subject_id":child_subject,
                "reason":"Reviewed the exact independent follow-up campaign."})
            decision=approved_child["review"]["approval"]
            check("followup_fresh_decision",decision["decision"] == "approve" and decision["id"] != a
                  and decision["subject_id"] == child_subject and decision["case_id"] == child["review"]["case_id"]
                  and decision["purpose"] == "simulated_agency_handoff")
            check("followup_current_approval_authority",approved_child["review"]["approval_valid"]
                  and approved_child["review"]["candidate_valid"] and approved_child["review"]["handoff"] is None)
            saved_child=Workspace(root,real_clock=lambda:NOW).view(child_id)
            check("followup_approval_persists",saved_child["review"]["approval"] == decision
                  and saved_child["review"]["approval_valid"] and saved_child["review"]["subject"]["id"] == child_subject)
            save("followup-campaign.json",saved_child)
            # Read the committed receipt in a genuinely new interpreter.
            code="from acquisition.workspace import Workspace; import sys,json; from unittest.mock import patch;\nwith patch('socket.socket.connect',side_effect=AssertionError('Offline')):\n print(json.dumps(Workspace(sys.argv[1],real_clock=lambda:1792972800.).view(sys.argv[2])['review']['handoff']))"
            process=subprocess.run([sys.executable,"-c",code,str(root),sid],capture_output=True,text=True,timeout=30)
            check("fresh_process_receipt",process.returncode == 0 and json.loads(process.stdout) == receipt)
            w.message_conversation(c,"correction",1,"Change the budget to £300.")
            check("brief_edit_invalidates_current_candidate",not w.view(sid)["review"]["candidate_valid"])
            check("accepted_history_survives_edit",json.loads(w.artifact(sid,"handoff",subject)[0]) == receipt)
            report["conversation_id"]=c; report["session_id"]=sid
    except Exception as error:
        report["error_type"]=type(error).__name__
        report["passed"]=False
    else:
        report["passed"]=True
    report["finished_at"]=datetime.now(timezone.utc).isoformat()
    save("report.json",report)
    print(json.dumps({"passed":report["passed"],"checks":len(checks),"report":str(run / 'report.json')}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=Path('.local/offline-evaluation'))
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    sys.exit(evaluate(args.output))
