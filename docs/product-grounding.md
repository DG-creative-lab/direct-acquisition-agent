# Product-grounded copy before day three

Implemented on 25 October 2026. New model commands use GPT-OSS-120B and `monthly-mail/v3`. The deliverable is a sourced, screened, unreviewed synthetic draft. It does not approve financial promotions, assess recipient eligibility or send mail.

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

The implementation stays inside `creative`, behind the existing `reasoning` port. Runtime remains business-agnostic. `workflows` chooses the grounded capability and revalidates at draft creation. SQLite retains contexts, catalogue and inference receipts through the existing schema; no new database migration is necessary.

Every creative carries its selected fact, pack ID, frozen context, evidence references and exact paired screening verdict. The candidate fingerprint covers headlines, hooks, hypotheses, arms, selected facts and pack identity. Changing copy cannot reuse the old verdict. The journal preserves the model/provider generation metadata and usage. A crash before catalogue persistence can replay both generation and critic receipts without another API call.

Exports include `product-evidence.json` alongside the manifest, letters and CSVs. The pack keys can be recomputed from their content. The manifest holds the screening receipts and selected fact IDs. Exporting historical evidence does not renew its freshness or grant release authority.

Legacy `monthly-mail/v2` tasks remain explicitly ungrounded and resumable under their original model configuration. New commands create v3 tasks, and a v3 capability cannot declare v2 inputs to skip grounding. Day-one serialization and exact artifact identity remain unchanged.

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

Final offline verification passed **52 tests** plus the architecture check. The new tests use real SQLite and controlled time. Their independent oracles are the checked pack, literal required qualification text, explicit rejected claim examples, expected scope/identity and labelled critic outcomes.

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

## Live validation

The completed acceptance run is `.local/grounded-iwoca-v6.json`: nine GPT-OSS-120B calls, reported cost **$0.00108033**, and a persisted draft waiting for review. It reconciles 1,000 synthetic records to 245 exclusions, 74 no-mail controls and 681 draft recipients, with £578.85 synthetic mailing cost. Mailing cost and inference cost are separate. Both segments' final paired checks passed after bounded corrections. The generated text was also read manually; it is a working demonstration, still somewhat wordy and not a finished direct-mail piece.

The exact draft is `draft_8578d1f9c53b6d372fc1f0fad88cda038b9372e055537fac5e6c1d94ec0df401`. Its export includes `letters.txt`, `manifest.json`, `product-evidence.json`, `mailing.csv` and `assignments.csv` under `.local/exports/`.

Development failures are retained rather than represented as successful acceptance runs. They included invented guidance IDs, unsupported repayment-schedule implications, a provider stop without a tool, and critic confusion between generated hooks and inserted product text. One earlier completed draft used questions implying business benefits; the earlier critic passed them. That human-discovered false negative became the `benefits-hidden-in-questions` regression case and an additional deterministic check. A later critic request returned malformed arguments; no classification or campaign authority was inferred from it.

The evaluation harness originally put independent cases in one fail-fast campaign-style run, which let one provider failure hide later cases. It now gives each case one inference reservation in its own run and reports incomplete results separately. The labelled corpus and critic prompt were developed together, so subsequent success on these examples is a regression result, not a held-out quality estimate. Earlier rounds remain in `.local/claim-screen-eval.sqlite`.

The final isolated regression, `.local/claim-screen-eval-v4.json`, completed all four pairs: **eight of eight variant labels matched**. It accepted both situational questions and rejected all six labelled negative examples, including implied benefits phrased as questions, injection and fabricated results. Four calls reported **$0.00045711**, with no missing cost receipts. This result does not erase the earlier false negative, false rejections or malformed/provider failures and is not a claim of general accuracy.

Across this grounding round's development and evaluation databases, all 44 call receipts together reported **$0.00493797**. That includes the failed experiments, not only the final successful runs. No cost receipt was missing in those two databases; earlier day-two model comparisons are separate.

The lexical list is intentionally bounded. Remaining risks include semantic false negatives, false rejections, source changes inside the review window, manual fact-pack mistakes and marketing judgment beyond the rubric. Day three must treat this catalogue as a proposal and bind any new approval mechanism to the exact artifact and current evidence.
