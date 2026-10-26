"""Read-only HTML projection. Decisions always go through the transactional CLI."""

from datetime import datetime, timezone
from html import escape
from pathlib import Path
import shlex
import os


def render_review(view: dict, database_path: str) -> str:
    e = lambda value: escape(str(value), quote=True)
    subject, manifest = view["subject"], view["manifest"]
    counts = manifest["counts"]
    state = "Accepted by the local simulator" if view["handoff"] else "Approval valid" if view["approval_valid"] else "Review required"
    date = datetime.fromtimestamp(view["as_of"], timezone.utc).strftime("%d %B %Y, %H:%M UTC")
    reasons = "".join(f"<li>{e(reason)}</li>" for reason in view["blocked_reasons"])
    copy = "".join(f'<article><p class="eyebrow">{e(c["segment"])} / variant {e(c["arm"])}</p>'
        f'<h3>{e(c.get("headline") or "Synthetic fixture")}</h3><p>{e(c["opening"])}</p>'
        f'<p class="disclosure">{e(c.get("locked_block", "SYNTHETIC FIXTURE. HUMAN REVIEW REQUIRED."))}</p>'
        f'<details><summary>Provenance</summary><code>{e(c["id"])}</code><p>{e(c.get("hypothesis", "Fixed fixture; no measured outcome."))}</p></details></article>'
        for c in manifest["creatives"])
    events = "".join(f'<tr><td>{e(event["sequence"])}</td><td>{e(event["kind"].replace("_", " "))}</td>'
                     f'<td><code>{e(event["payload"])}</code></td></tr>' for event in view["events"])
    base = ["PYTHONPATH=src", "python3", "-m", "acquisition", "--db", database_path,
            "--organization", subject["organization"], "review-decide", "--case", view["case_id"],
            "--subject", subject["id"], "--actor", "REVIEWER_ID", "--request-id", "UNIQUE_REQUEST_ID"]
    command = " ".join(shlex.quote(s) if s != "PYTHONPATH=src" else s for s in base)
    commands = "\n\n".join(command + " --decision " + decision + " --reason 'REVIEW_REASON'" for decision in ("approve", "reject"))
    action = ("<p>This case has an accepted simulated job. Further approval or revision requires a new campaign.</p>"
              if view["handoff"] else f'<p>Replace the identity, request ID and reason. The CLI rejects stale subjects and rechecks evidence.</p><pre>{e(commands)}</pre>')
    revisions = "".join(f'<li>Revision {e(r["revision"])}: <code>{e(r["draft_id"])}</code></li>' for r in view["revisions"])
    sources = "".join(f'<li><a href="{e(s["url"])}" rel="noreferrer">{e(s["title"])}</a> / checked {e(s["checked_on"])}</li>'
                      for s in view["authority"]["pack"]["sources"])
    approval = view["approval"]
    decision = f'{e(approval["decision"])} by {e(approval["actor"])}: {e(approval["reason"])}' if approval else "No decision for this subject."
    if approval and approval["decision"] == "approve":
        decision += "<br>Expires: " + e(datetime.fromtimestamp(approval["expires_at"], timezone.utc).strftime("%d %b %Y, %H:%M UTC"))
    changes = view.get("changes")
    difference = (f'<section><h2>Changes since the previous revision</h2><p>{e(changes["removed_count"])} recipients removed; '
        f'{e(changes["added_count"])} added. Copy changed: {e("yes" if changes["copy_changed"] else "no")}. '
        f'Cost change: £{changes["cost_delta_pence"]/100:,.2f}.</p><p>Removed IDs, preview of up to {e(changes["preview_limit"])}: '
        f'<code>{e(", ".join(changes["removed_preview"]) or "none")}</code></p></section>' if changes else "")
    artifacts = view.get("artifact_link", "")
    files = f'<p><a href="{e(artifacts)}/manifest.json">Exact manifest</a> / <a href="{e(artifacts)}/mailing.csv">Mailing CSV</a> / <a href="{e(artifacts)}/assignments.csv">Assignments CSV</a></p>' if artifacts else ""
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'">
<title>Campaign review / revision {e(subject["revision"])}</title><style>
:root{{font-family:Arial,Helvetica,sans-serif;color:#18201c;background:#f3f1ea}}*{{box-sizing:border-box}}body{{margin:0}}main{{max-width:1240px;margin:auto;padding:44px 36px 70px}}a{{color:#174d36}}header{{border-top:5px solid #183f2d;padding-top:24px}}.eyebrow{{text-transform:uppercase;letter-spacing:.14em;font-size:11px;font-weight:700}}h1{{font-size:clamp(30px,4vw,46px);letter-spacing:-.045em;line-height:1.02;max-width:850px;margin:20px 0}}h2{{font-size:27px;letter-spacing:-.03em}}h3{{font-size:23px;line-height:1.18}}p,li{{line-height:1.6}}.intro{{max-width:780px;font-size:16px}}.status{{display:inline-block;padding:9px 13px;background:#dce8d8;font-weight:700}}.metrics{{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid #a8b4a7;border-bottom:1px solid #a8b4a7;margin:30px 0}}.metrics div{{padding:20px 10px}}.metrics strong{{display:block;font-size:34px;letter-spacing:-.04em}}.layout{{display:grid;grid-template-columns:2fr 1fr;gap:50px}}article{{padding:22px 0;border-bottom:1px solid #bcc5b8}}article p{{max-width:680px}}aside{{font-size:14px}}aside section{{border-top:1px solid #a8b4a7;padding:14px 0 20px}}code,pre{{font-family:ui-monospace,monospace;overflow-wrap:anywhere;white-space:pre-wrap;font-size:11px}}pre{{background:#e5e9df;padding:18px}}.disclosure{{font-size:12px;color:#515b50}}details{{margin:16px 0}}summary{{cursor:pointer}}table{{width:100%;border-collapse:collapse}}td{{border-top:1px solid #c3cbbb;padding:12px 8px;vertical-align:top;font-size:13px}}footer{{margin-top:40px;border-top:3px solid #183f2d;padding-top:18px;font-size:13px}}@media(max-width:760px){{main{{padding:26px 20px}}.layout{{grid-template-columns:1fr;gap:20px}}.metrics{{grid-template-columns:repeat(2,1fr)}}}}
</style><main><header><p class="eyebrow">Direct Acquisition Agent / local review</p><h1>Campaign review</h1>
<p class="intro">Check the audience, copy and evidence before recording a decision. Approval applies only to this revision and a local simulated handoff.</p>
<p class="status">{e(state)}</p><p>Revision {e(subject["revision"])} / report generated {e(date)}</p></header>
<section class="metrics" aria-label="Campaign totals"><div><strong>{e(counts["mailed"])}</strong>Draft recipients</div><div><strong>{e(counts["excluded"])}</strong>Excluded</div><div><strong>{e(counts["holdout"])}</strong>No-mail controls</div><div><strong>£{manifest["variable_cost_pence"]/100:,.2f}</strong>Synthetic mailing cost</div></section>
<div class="layout"><section><h2>Audience-specific copy</h2>{copy}</section><aside><section><p class="eyebrow">Decision</p><p>{decision}</p><ul>{reasons}</ul><p>Reviewer identity and permission are checked again when a decision is recorded and when the simulator accepts a job.</p></section>
<section><p class="eyebrow">Evidence</p><ul>{sources}</ul><p>Product evidence epoch: {e(subject["evidence_epoch"])}<br>Suppression epoch: {e(subject["audience_epoch"])}</p><p>Product review due: {e(view["authority"]["pack"]["review_by"])}</p></section>
<section><p class="eyebrow">Exact subject</p><code>{e(subject["id"])}</code><p>Draft</p><code>{e(subject["draft_id"])}</code><p>Audience snapshot</p><code>{e(subject["snapshot_id"])}</code></section></aside></div>
{difference}{files}<section><h2>Decision controls</h2><p>This report is read-only.</p>{action}</section>
<section><h2>Revision history</h2><ul>{revisions}</ul><h2>Recorded events</h2><table><thead><tr><th>Sequence</th><th>Event</th><th>Receipt</th></tr></thead><tbody>{events}</tbody></table></section>
<footer>Synthetic data. Trusted local identities, without hosted authentication. No print or send authority. This saved report can become stale; re-run review-show for current state.</footer></main></html>'''


def write_review(view: dict, database_path: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendered = dict(view)
    if "export_directory" in view:
        rendered["artifact_link"] = os.path.relpath(view["export_directory"], destination.parent)
    destination.write_text(render_review(rendered, database_path), encoding="utf-8")
    return destination.resolve()
