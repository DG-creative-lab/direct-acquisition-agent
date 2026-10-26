"""Reproducible posterior sampling. Advisory only, never campaign authority."""

import random
from acquisition.contracts import digest


DRAWS = 10000


def recommend(cohort_id, groups):
    results = []
    for segment in ("inventory", "contractors"):
        arms = {g["arm"]: g for g in groups if g["segment"] == segment}
        if set(arms) != {"A", "B", "no_mail"}:
            results.append({"segment": segment, "action": "collect_more_evidence", "reason": "Missing treatment or no-mail control stratum."})
            continue
        rng = random.Random(digest({"algorithm": "posterior-comparison/v1", "cohort": cohort_id, "segment": segment}))
        draws = {arm: [rng.betavariate(g["alpha"], g["beta"]) for _ in range(DRAWS)] for arm, g in arms.items()}
        winner = max(("A", "B"), key=lambda a: arms[a]["mean"])
        other = "B" if winner == "A" else "A"
        lift = sorted(a - b for a, b in zip(draws[winner], draws["no_mail"]))
        p_best = sum(a > b for a, b in zip(draws[winner], draws[other])) / DRAWS
        p_positive = sum(v > 0 for v in lift) / DRAWS
        enough = min(arms[a]["trials"] for a in ("A", "B")) >= 30 and arms["no_mail"]["trials"] >= 10
        ready = enough and p_best >= .9 and p_positive >= .95
        intervals = {arm: [sorted(values)[int(DRAWS * q)] for q in (.05, .95)] for arm, values in draws.items()}
        results.append({"segment": segment, "action": "propose_next_experiment" if ready else "collect_more_evidence",
            "candidate_arm": winner, "creative_id": arms[winner]["creative_id"], "probability_beats_other": p_best,
            "probability_beats_control": p_positive, "lift_mean": arms[winner]["mean"] - arms["no_mail"]["mean"],
            "lift_interval_90": [lift[500], lift[9500]], "response_intervals_90": intervals,
            "sampling": {"method": "seeded_beta_monte_carlo/v1", "draws": DRAWS},
            "reason": "Thresholds met for a further synthetic experiment." if ready else "Sample size or posterior evidence is insufficient.",
            "authority": "ADVISORY_REQUIRES_NEW_PROPOSAL_AND_APPROVAL"})
    return results
