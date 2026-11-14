"""Deterministic constraints and account assignment, independent of advisory strategy scores."""

from dataclasses import asdict

from acquisition.audiences import run_issues
from acquisition.contracts import Conflict, digest


def contact_decision_plan(batch, request, run, readiness):
    if (readiness['source_id'] != batch.source_id or readiness['profile_id'] != batch.profile_id
            or readiness['channel'] != batch.channel or readiness['purpose'] != batch.purpose
            or digest(readiness) != batch.readiness_digest
            or {r['contact_id'] for r in readiness['rows']} != {r.contact_id for r in batch.rows}):
        raise Conflict('Decision features differ from independent contact readiness')
    issues = run_issues(batch,request,run)
    if not readiness['coverage_complete']: issues.append('evidence_incomplete')
    allocations = []
    if not issues:
        scores = {r.contact_id:r.value for r in run.decisions.observations}
        # Eligibility comes from campaign policy, never an inference flag or category.
        eligible = [r for r in readiness['rows'] if r['eligible_for_preparation']]
        ranked = sorted(eligible,key=lambda r:(-scores[r['contact_id']],r['contact_id']))
        seen = set()
        limit = min(request.max_candidates,request.budget_pence//request.unit_cost_pence)
        for row in ranked:
            unit = row['experiment_unit']
            if unit in seen or len(allocations)>=limit: continue
            if unit is None: raise Conflict('Eligible contact has no experiment identity')
            seen.add(unit)
            # Assignment is independent of scores and stable for an account in this scope/seed.
            bucket = int(digest({'algorithm':'contact-account-hash/v1','organization':batch.organization,
                'profile':batch.profile_id,'channel':batch.channel,'seed':request.seed,'unit':unit}),16)%10
            arm = 'no_contact' if bucket==0 else 'A' if bucket%2 else 'B'
            allocations.append({'contact_id':row['contact_id'],'experiment_unit':unit,'arm':arm,
                                'score':scores[row['contact_id']]})
    charged = sum(r['arm']!='no_contact' for r in allocations)*request.unit_cost_pence
    return {'schema':'contact-decision-plan/v1','policy':'contact-selection/v1','mode':'SYNTHETIC_ONLY',
        'feature_batch_id':batch.id,'source_id':batch.source_id,'score_semantics':asdict(request.score),
        'score_order':'higher_is_preferred','categorizer_id':request.categorizer.id,'strategy_id':request.decision.id,
        'status':'incomplete' if issues else 'complete','issues':sorted(set(issues)),
        'allocations':allocations,'excluded':[r for r in readiness['rows'] if not r['eligible_for_preparation']],
        'budget_pence':request.budget_pence,'unit_cost_pence':request.unit_cost_pence,
        'cost_basis':'user_supplied_synthetic_estimate','conservative_cost_pence':len(allocations)*request.unit_cost_pence,
        'estimated_treatment_cost_pence':charged,'currency':'GBP','max_candidates':request.max_candidates,
        'assignment_algorithm':'contact-account-hash/v1','seed':request.seed,
        'capacity_reserved':False,'authority':'none','approval':'not_granted','execution':'not_performed'}
