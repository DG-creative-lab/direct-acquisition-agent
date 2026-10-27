# Product evidence and grounded copy

New model commands use GPT-OSS-120B and `monthly-mail/v3`. The deliverable is a sourced, screened, unreviewed synthetic draft. It does not approve financial promotions, assess recipient eligibility or send mail.

## Evidence and editorial authority

`config/iwoca-product-facts-v1.json` is a small, manually verified public-source pack from the [official iwoca Flexi-Loan page](https://www.iwoca.co.uk/flexi-loan). Its two permitted product statements, individual qualifications, assessment qualification and CTA are local editorial paraphrases of that page. They are not copy approved by iwoca. The pack records source URL, section names, check date and a brief excerpt. Numerical offers, pricing, speed, credit-score effects, eligibility, testimonials and regulatory endorsements are deliberately outside this pack.

The evidence was checked on 25 October 2026. A local thirty-day review policy makes it unusable for new generation or draft preparation after 24 November 2026. This is a review window, not a guarantee that a website cannot change earlier. Re-verification is a human source-review step; the model cannot extend the window or mark new claims verified. The local configuration is trusted operator input, not a signed external attestation or automatic web monitor.

Each run freezes the complete pack alongside `editorial-v3.json`, segment context and scoped reviewer preferences. Its `facts_…` identity hashes the whole pack. An edited source pack, qualification or rubric produces new context and request identities. Historical runs retain the evidence they used.

## Generation and checks

1. Read the frozen editorial context through the existing inference journal.
2. Propose two headlines, short situational hooks, experiment hypotheses and selected fact IDs. The tool schema enumerates the actual allowed IDs.
3. Validate the exact shape, evidence relationships, segment vocabulary, bounded text and distinct openings. Reject product/price/entitlement language in generated framing, unsupported benefit language, assumed personal need, numeric claims and hidden control characters. Questions do not exempt a benefit claim.
4. Use a separate GPT-OSS request with a fresh context to screen both variants. Its input labels `generated_framing`, `experiment_hypothesis` and `locked_product_block` separately. It sees the source pack and combined relationship, but no drafting transcript or preference memory. The verdict must bind both variants and the exact pack hash.
5. Code appends the selected fact's exact text, its qualification, the general qualification and fixed official CTA. The demonstration disclosure also comes from code.
6. Revalidate the complete A/B catalogue, freshness and provenance before saving the campaign draft and again when revisiting its checkpoint.

A critic rejection can trigger one bounded correction per segment. At most five calls per segment are possible: context read, proposal, check, corrected proposal, second check. A normal run needs six calls in total. The CLI cap is ten reservations, including errors, with the existing input/output and provider-price ceilings. GPT-OSS-120B uses required tool choice; other models retain optional support. Model workers have a 180-second lease to cover the bounded five-call segment loop with the adapter's per-request timeout. Unknown calls and malformed completions are not silently retried.

The critic uses the same underlying model in a separate request. It is a probabilistic screen, not independent truth, lender approval, legal validation or evidence of customer response. Deterministic checks enforce exact product blocks and known constraints; they do not prove arbitrary prose cannot imply something unsupported. Human review remains necessary. All variants retain `generated_unreviewed` status.

## Persistence and module boundaries

The implementation stays inside `creative`, behind the existing `reasoning` port. Runtime remains business-agnostic. `workflows` chooses the grounded capability and revalidates at draft creation. SQLite retains contexts, catalogue and inference receipts. Review hardening adds schema v3 to freeze pre-existing task-plan admissions for legacy replay.

Every creative carries its selected fact, pack ID, frozen context, evidence references and exact paired screening verdict. The candidate fingerprint covers headlines, hooks, hypotheses, arms, selected facts and pack identity. Changing copy cannot reuse the old verdict. The journal preserves the model/provider generation metadata and usage. A crash before catalogue persistence can replay both generation and critic receipts without another API call.

Exports include `product-evidence.json` alongside the manifest, letters and CSVs. The pack keys can be recomputed from their content. The manifest holds the screening receipts and selected fact IDs. Exporting historical evidence does not renew its freshness or grant release authority.

Legacy `monthly-mail/v2` tasks remain explicitly ungrounded and resumable only when their exact persisted plan matches an admission frozen by the schema-v3 migration. Restarting cannot grant legacy status to new rows, and new v2 admission is rejected. An incompatible worker skips a task before claiming it, without consuming attempts. New commands create v3 tasks, and a v3 capability cannot declare v2 inputs to skip grounding. Historical deterministic artifacts retain their original identity.

## Reproduce

```sh
make test
make arch-check
PYTHONPATH=src python3 -m acquisition --db .local/grounded-demo.sqlite demo-model --request-id grounded-demo
```

The model defaults to `openai/gpt-oss-120b`; it needs the existing ignored `.env.local`. An explicit model still overrides the default. To resume a current run:

```sh
PYTHONPATH=src python3 -m acquisition --db .local/grounded-demo.sqlite --model openai/gpt-oss-120b work
```

Old GPT-OSS runs used six calls and optional tool choice; resuming those requires `--model-max-calls 6 --tool-choice auto` in addition to their original database/model. Never reuse a request ID after changing frozen inputs.

The optional live critic regression is separate from offline tests:

```sh
PYTHONPATH=src python3 scripts/evaluate_claim_screen.py --request-id screen-evaluation
```

`config/claim-screen-cases-v1.json` supplies independent expected labels for four pairs: acceptable situational questions, invented product/approval claims, benefits hidden in questions, and injection/fabricated results. Expected labels are not sent to the critic. The script stores requests and receipts through the same runtime/journal. An invalid verdict is an incomplete evaluation, never a correct classification. Eight examples are a regression corpus, not an estimate of general accuracy.

## Failure-space evidence

Offline tests use real SQLite and controlled time. Independent oracles include literal required qualification text, rejected claim examples, expected identity/scope and labelled critic outcomes. See [validation](validation.md) for the current test portfolio.

| Invariant | Failure exercised | Observable consequence |
| --- | --- | --- |
| Sources and freshness | Missing source/facts, invented source, deceptive hostname, inconsistent dates, duplicate fact, future/expired pack | Validation rejection |
| Required product qualifications | Omitted/changed qualification or disclosure | No accepted catalogue |
| Framing constraints | Unsupported product terms, entitlement, numeric claims, implied benefits as questions, hidden characters, wrong segment | Rejected before critic |
| Complete bound verdict | Different candidate hash, missing fields, altered copy, swapped pack, different pair receipts | Rejected before draft |
| Critic rejection | Persistent negative verdict through both bounded attempts | No catalogue or draft; five calls maximum for that segment |
| Recovery | Crash after saved critic receipt but before catalogue persistence | Completed run with six calls, no duplicate inference |
| Evidence lifetime at effect boundary | Expiry after generation, before campaign draft | Draft blocked, no extra inference |
| Version compatibility | Legacy v2 replay and v3 capability/input downgrade | Legacy stays ungrounded; inconsistent downgrade blocked |
| Evaluation independence | First critic call fails with unknown cost | Remaining three cases execute; report retains incomplete case and missing cost |

## Recorded live evaluation, 25 October 2026

A recorded GPT-OSS-120B generation run used nine calls, reported $0.00108033 in inference cost and persisted an unreviewed draft. The synthetic population reconciled to 245 exclusions, 74 controls and 681 recipients, with £578.85 in separate simulated mailing cost. Both segments passed their paired screen after bounded corrections. A [portable copy example](../examples/grounded-run/letters.txt) is included for inspection. Passing the screen did not constitute editorial approval; the manually inspected output was still wordy.

The labelled regression in `config/claim-screen-cases-v1.json` completed four pairs, matching eight of eight variant labels with four calls and $0.00045711 reported cost. Expected labels were hidden from the critic, but the corpus and rubric were developed together. This is a regression observation, not held-out accuracy. These dated costs describe those executions, not current pricing or a future cost guarantee.

Observed failures included a false negative for benefits phrased as questions, false rejections, malformed tool arguments and provider completions without a tool. The false negative informed an additional deterministic rule and a regression case. Incomplete verdicts remain incomplete evaluations, never inferred passes. The evaluation harness isolates cases so one provider failure cannot hide the remainder.

The lexical list is bounded, and the drafting and screening requests use the same underlying model. Remaining risks include semantic false negatives, false rejections, source changes inside the review window, manual pack mistakes and judgment beyond the rubric. The [review flow](reviews.md) binds any approval to the exact artifact and current evidence. Development databases are not shipped, and no new model call is implied by these recorded results.
