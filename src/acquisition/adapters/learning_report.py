"""Read-only synthetic response report. No campaign mutation controls."""

from datetime import datetime, timezone
from html import escape
from pathlib import Path


def render_learning(view):
    e = lambda v: escape(str(v), quote=True)
    date = lambda v: datetime.fromtimestamp(v, timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    pct = lambda v: f"{100*v:.1f}%"
    probability = lambda v: "&gt;99.9%" if v >= .999 else "&lt;0.1%" if v <= .001 else pct(v)
    clock_label = "Simulated report clock" if view.get("clock_mode") == "SIMULATED" else "Report clock"
    rows, recommendations = [], []
    intervals = {r["segment"]: r.get("response_intervals_90", {}) for r in view["recommendations"]}
    for g in view["beliefs"]:
        interval = intervals.get(g["segment"], {}).get(g["arm"])
        span = f'{pct(interval[0])} to {pct(interval[1])}' if interval else "Unavailable"
        rows.append(f'<tr><th scope="row">{e(g["segment"])} / {e(g["arm"])}</th><td>{g["successes"]} / {g["trials"]}</td>'
            f'<td>{pct(g["mean"])}</td><td>{span}</td><td><details><summary>View identity</summary><code>{e(g["creative_id"] or "No-mail control")}</code></details></td></tr>')
    for r in view["recommendations"]:
        content = f'<p>{e(r["reason"])}</p>'
        if "candidate_arm" in r:
            lo, hi = r["lift_interval_90"]
            content += f'<p>Candidate: variant {e(r["candidate_arm"])}. Estimated response lift over control: <strong>{r["lift_mean"]*100:+.1f} percentage points</strong>.</p>'
            content += f'<p>90% posterior interval: {lo*100:+.1f} to {hi*100:+.1f} points. Estimated probability of beating control: {probability(r["probability_beats_control"])}; beating the other variant: {probability(r["probability_beats_other"])}.</p>'
        recommendations.append(f'<article><p class="label">{e(r["segment"])}</p><h3>{"Propose another experiment" if r["action"] == "propose_next_experiment" else "Collect more evidence"}</h3>{content}</article>')
    limitations = ''.join(f'<li>{e(v)}</li>' for v in view["limitations"])
    cohort = view["cohort"]
    history = ''.join(f'<li>{e(ev["kind"].replace("_", " "))}<details><summary>Receipt</summary><pre>{e(ev["payload"])}</pre></details></li>' for ev in view["events"])
    groups = ''.join(rows) or '<tr><td colspan="5">Beliefs remain unchanged until the closed cohort is finalized.</td></tr>'
    decisions = ''.join(recommendations) or '<p>No recommendation while observations are pending.</p>'
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'"><title>Campaign learning / synthetic responses</title>
<style>:root{{font-family:Arial,Helvetica,sans-serif;color:#18201c;background:#f3f1ea}}*{{box-sizing:border-box}}body{{margin:0}}main{{max-width:1240px;margin:auto;padding:44px 36px 70px}}header{{border-top:5px solid #183f2d;padding-top:24px}}.label{{text-transform:uppercase;letter-spacing:.14em;font-size:11px;font-weight:700}}h1{{font-size:clamp(30px,4vw,46px);letter-spacing:-.04em;margin:20px 0}}h2{{font-size:27px;letter-spacing:-.03em}}h3{{font-size:23px}}p,li{{line-height:1.6}}.state{{display:inline-block;background:#dce8d8;padding:9px 13px;font-weight:700}}.metrics{{display:grid;grid-template-columns:repeat(3,1fr);border-block:1px solid #a8b4a7;margin:28px 0}}.metrics div{{padding:20px 10px}}.metrics strong{{display:block;font-size:34px;letter-spacing:-.04em}}.table{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;text-align:left;min-width:650px}}th,td{{padding:15px 10px;border-bottom:1px solid #bcc5b8;vertical-align:top;font-size:14px}}td:last-child{{max-width:260px}}code,pre{{font-size:11px;font-family:ui-monospace,monospace;overflow-wrap:anywhere;white-space:pre-wrap}}.recommendations{{display:grid;grid-template-columns:1fr 1fr;gap:48px}}article{{border-top:1px solid #a8b4a7;padding:18px 0}}section{{margin-top:32px}}.note{{font-size:14px;max-width:850px}}footer{{border-top:3px solid #183f2d;margin-top:40px;padding-top:18px}}details{{margin:14px 0}}summary{{cursor:pointer}}@media(max-width:760px){{main{{padding:26px 20px}}.metrics strong{{font-size:28px}}.metrics div{{padding:16px 5px}}.recommendations{{grid-template-columns:1fr;gap:15px}}}}</style>
<main><header><p class="label">Direct Acquisition Agent / synthetic learning</p><h1>Campaign learning</h1><p>Response evidence for one frozen experiment. Recommendations require a new proposal and approval.</p>
<p class="state">{e(view["status"].replace("_", " ").capitalize())}</p><p class="note">{clock_label}: {e(date(view["as_of"]))}<br>Observation window: {e(date(cohort["window_start"]))} to {e(date(cohort["window_end"]))}</p></header>
<div class="metrics"><div><strong>{view["enrolled"]}</strong>Enrolled businesses</div><div><strong>{view["received"]}</strong>Explicit outcomes</div><div><strong>{view["missing"]}</strong>Pending results</div></div>
<section><h2>Response beliefs</h2><p class="note">One Bernoulli response per business. Beta(1,19) prior, with a 5% starting mean. Intervals estimate the central 90% posterior range from 10,000 seeded draws.</p><div class="table" tabindex="0" aria-label="Response beliefs, scroll horizontally on narrow screens"><table><thead><tr><th>Segment / arm</th><th>Responses / trials</th><th>Posterior mean</th><th>90% interval</th><th>Exact creative</th></tr></thead><tbody>{groups}</tbody></table></div></section>
<section><h2>Next experiment</h2><div class="recommendations">{decisions}</div><p class="note">Recommendation thresholds: at least 30 trials per treatment and 10 controls, 90% probability of beating the other variant and 95% probability of beating control. These are demonstration rules, not a calibrated campaign policy.</p></section>
<section><h2>Evidence and limits</h2><ul>{limitations}</ul><details><summary>Exact cohort and provenance</summary><pre>{e(cohort)}</pre></details><details><summary>Recorded operations</summary><ol>{history}</ol></details></section>
<footer><strong>Synthetic outcomes. No measured customer performance.</strong><p class="note">Read-only saved report. Simulated agency acceptance does not establish actual delivery. Re-run learning-show for current state.</p></footer></main></html>'''


def write_learning(view, destination):
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_learning(view), encoding="utf-8")
    return path.resolve()
