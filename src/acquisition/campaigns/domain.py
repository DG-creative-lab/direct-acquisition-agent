import csv
import hashlib
import io
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date

from acquisition.audiences import Snapshot, AudienceTaxonomy, ProfiledSnapshot, taxonomy_from, catalogue_identity
from acquisition.contracts import canonical, digest
from acquisition.creative import Creative, creative_record


@dataclass(frozen=True)
class CampaignScope:
    product: str = 'iwoca_flexi_loan'
    channel: str = 'direct_mail'
    country: str = 'UK'
    objective: str = 'response_experiment'


def requested_scope_values(scope):
    return {key: scope['requirements'][key]['value'] for key in asdict(CampaignScope())}


def validate_requested_scope(scope):
    if (type(scope) is not dict or scope.get('schema') != 'requested-campaign-scope/v1'
            or scope.get('id') != 'request_scope_' + digest({k:v for k,v in scope.items() if k != 'id'})
            or scope.get('authority') != 'none' or scope.get('status') != 'supported'
            or type(scope.get('requirements')) is not dict or set(scope['requirements']) != set(asdict(CampaignScope()))
            or any(type(v) is not dict or 'value' not in v for v in scope['requirements'].values())
            or requested_scope_values(scope) != asdict(CampaignScope())):
        raise ValueError('Campaign does not satisfy its frozen requested scope')


@dataclass(frozen=True)
class Brief:
    campaign_id: str
    budget_pence: int = 85000
    unit_cost_pence: int = 85
    max_candidates: int = 1000
    policy_version: str = "demo-marketing/v1"

    def __post_init__(self) -> None:
        if not self.campaign_id or self.policy_version != "demo-marketing/v1":
            raise ValueError("Unknown campaign or policy")
        for value in (self.budget_pence, self.unit_cost_pence, self.max_candidates):
            if type(value) is not int:
                raise ValueError("Money and counts must be integers")
        if self.budget_pence < 0 or self.unit_cost_pence <= 0 or not 0 < self.max_candidates <= 400_000:
            raise ValueError("Invalid budget, unit cost or candidate limit")


@dataclass(frozen=True)
class CampaignProfile:
    key: str
    version: str
    company: str
    product_key: str
    product_profile_id: str
    taxonomy: AudienceTaxonomy
    country: str = 'UK'
    currency: str = 'GBP'
    channel: str = 'direct_mail'
    objective: str = 'response_experiment'
    schema: str = 'campaign-profile/v1'

    def __post_init__(self):
        for value in (self.key, self.version, self.company, self.product_key):
            catalogue_identity(value)
        if (self.schema != 'campaign-profile/v1' or self.country != 'UK' or self.currency != 'GBP'
                or self.channel != 'direct_mail' or self.objective != 'response_experiment'
                or type(self.taxonomy) is not AudienceTaxonomy
                or type(self.product_profile_id) is not str or not self.product_profile_id.startswith('product_profile_')
                or len(self.product_profile_id) != len('product_profile_') + 64
                or any(c not in '0123456789abcdef' for c in self.product_profile_id[len('product_profile_'):])):
            raise ValueError('Unsupported profile, market, currency, channel or objective')

    @property
    def id(self):
        return 'campaign_profile_' + digest(asdict(self))


def campaign_profile_from(payload):
    return CampaignProfile(**(payload | {'taxonomy': taxonomy_from(payload['taxonomy'])}))


@dataclass(frozen=True)
class ProfiledBrief(Brief):
    profile: CampaignProfile | None = None
    segments: tuple[str, ...] = ()
    plan: dict | None = None

    def __post_init__(self):
        super().__post_init__()
        if (type(self.profile) is not CampaignProfile or type(self.segments) is not tuple or not self.segments
                or len(set(self.segments)) != len(self.segments)
                or set(self.segments) - {s.key for s in self.profile.taxonomy.segments}):
            raise ValueError('A profiled brief requires exact profile and taxonomy membership')
        plan = self.plan
        if (type(plan) is not dict or plan.get('schema') != 'profile-plan/v1'
                or canonical(plan.get('profile')) != canonical(asdict(self.profile))
                or plan.get('profile_id') != self.profile.id or plan.get('budget_pence') != self.budget_pence
                or plan.get('segments') != list(self.segments) or plan.get('approval') != 'not_granted'
                or plan.get('objective_kind') != self.profile.objective
                or (plan.get('country'), plan.get('currency'), plan.get('channel')) != (
                    self.profile.country, self.profile.currency, self.profile.channel)
                or plan.get('copy_mode') != 'fixture' or plan.get('execution') != 'not_performed'
                or plan.get('mode') != 'SYNTHETIC_PLANNING_ONLY'
                or plan.get('id') != 'profile_plan_' + digest({k:v for k,v in plan.items() if k != 'id'})):
            raise ValueError('Profile brief differs from its frozen plan')


@dataclass(frozen=True)
class ConversationBrief(Brief):
    segments: tuple[str, ...] = ()
    conversation_id: str = ""
    conversation_revision: int = 0
    plan_id: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if (type(self.segments) is not tuple or not self.segments or len(set(self.segments)) != len(self.segments)
                or any(segment not in {"inventory", "contractors"} for segment in self.segments)
                or not self.conversation_id.startswith("conversation_") or not self.plan_id.startswith("brief_")
                or type(self.conversation_revision) is not int or self.conversation_revision < 1):
            raise ValueError("A conversation brief requires supported segments and exact proposal provenance")


@dataclass(frozen=True)
class SourcedConversationBrief(ConversationBrief):
    audience_source: dict | None = None

    def __post_init__(self):
        super().__post_init__()
        source = self.audience_source
        if (type(source) is not dict or source.get('conversation_id') != self.conversation_id
                or source.get('revision') != self.conversation_revision or source.get('plan_id') != self.plan_id
                or source.get('id') != 'selection_' + digest({k:v for k,v in source.items() if k != 'id'})
                or source.get('authority') != 'none'):
            raise ValueError('Campaign requires its exact confirmed audience provenance')


@dataclass(frozen=True)
class FollowupBrief(Brief):
    segments: tuple[str, ...] = ()
    followup_id: str = ""

    def __post_init__(self):
        super().__post_init__()
        if not self.followup_id.startswith("followup_") or not self.segments or set(self.segments) - {"inventory", "contractors"}:
            raise ValueError("Follow-up requires a frozen proposal and supported segments")


@dataclass(frozen=True)
class ScopedConversationBrief(ConversationBrief):
    requested_scope: dict | None = None

    def __post_init__(self):
        super().__post_init__()
        validate_requested_scope(self.requested_scope)


@dataclass(frozen=True)
class ScopedSourcedConversationBrief(SourcedConversationBrief):
    requested_scope: dict | None = None

    def __post_init__(self):
        super().__post_init__()
        validate_requested_scope(self.requested_scope)


@dataclass(frozen=True)
class ScopedFollowupBrief(FollowupBrief):
    requested_scope: dict | None = None

    def __post_init__(self):
        super().__post_init__()
        validate_requested_scope(self.requested_scope)


def conversation_brief_from_plan(plan, campaign_id, selection=None):
    cls = SourcedConversationBrief if selection else ConversationBrief
    extra = {'audience_source': selection} if selection else {}
    if 'requested_scope' in plan:
        cls = ScopedSourcedConversationBrief if selection else ScopedConversationBrief
        extra['requested_scope'] = plan['requested_scope']
    return cls(campaign_id=campaign_id, budget_pence=plan['budget_pence'], segments=tuple(plan['segments']),
               conversation_id=plan['conversation_id'], conversation_revision=plan['revision'], plan_id=plan['id'], **extra)


def conversation_copy_brief(brief, objective):
    result = {'objective': objective, 'budget_pence': brief.budget_pence, 'segments': list(brief.segments), 'plan_id': brief.plan_id}
    scope = getattr(brief, 'requested_scope', None)
    if scope is not None:
        result['requested_scope'] = {'id': scope['id'], 'values': requested_scope_values(scope)}
    return result


def brief_from(payload: dict) -> Brief:
    if 'profile' in payload:
        return ProfiledBrief(**(payload | {'profile': campaign_profile_from(payload['profile']),
                                          'segments': tuple(payload['segments'])}))
    if "segments" not in payload:
        return Brief(**payload)
    kind = FollowupBrief if "followup_id" in payload else SourcedConversationBrief if "audience_source" in payload else ConversationBrief
    if 'requested_scope' in payload:
        kind = ScopedFollowupBrief if 'followup_id' in payload else ScopedSourcedConversationBrief if 'audience_source' in payload else ScopedConversationBrief
    return kind(**(payload | {"segments": tuple(payload["segments"])}))


@dataclass(frozen=True)
class Draft:
    manifest: dict
    mailing_csv: str
    assignments_csv: str

    @property
    def id(self) -> str:
        return "draft_" + digest(self.manifest)


def _csv(headers: tuple[str, ...], rows: list[tuple]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue()


def build_draft(snapshot: Snapshot, brief: Brief, creatives: tuple[Creative, ...]) -> Draft:
    """Complete batch computation, fixed experiment, no model or I/O."""
    if not snapshot.complete:
        raise ValueError("Incomplete audience snapshot")
    if snapshot.score_semantics != "synthetic_response_propensity_not_uplift":
        raise ValueError("Unsupported score semantics")
    profiled = isinstance(brief, ProfiledBrief)
    if profiled:
        brief.__post_init__()
        if (type(snapshot) is not ProfiledSnapshot or snapshot.taxonomy != brief.profile.taxonomy
                or brief.plan.get('organization') != snapshot.organization or brief.plan.get('snapshot_id') != snapshot.id):
            raise ValueError('Profiled campaign requires the exact scoped audience taxonomy and plan')
    elif isinstance(snapshot, ProfiledSnapshot):
        raise ValueError('Profiled audiences cannot downgrade to a legacy campaign')
    catalogue = {(item.segment, item.arm): item for item in creatives}
    if len(catalogue) != len(creatives) or len({item.id for item in creatives}) != len(creatives):
        raise ValueError("Duplicate creative identity or segment/arm")
    segments = brief.segments if isinstance(brief, (ConversationBrief, FollowupBrief, ProfiledBrief)) else ("inventory", "contractors")
    if set(catalogue) != {(s, a) for s in segments for a in ("A", "B")}:
        raise ValueError("Incomplete creative catalogue")
    identity_counts = Counter(row.business_id for row in snapshot.records)
    reasons: Counter[str] = Counter()
    eligible = []
    as_of = date.fromisoformat(snapshot.as_of)
    for row in snapshot.records:
        reason = None
        if identity_counts[row.business_id] > 1:
            reason = "duplicate_business"
        elif row.suppressed:
            reason = "suppressed"
        elif row.country != "UK" or row.entity_type not in {"LTD", "LLP"}:
            reason = "product_scope"
        elif not row.deliverable or not row.address.startswith("DEMO ONLY"):
            reason = "unusable_demo_address"
        elif row.propensity_ppm is None:
            reason = "missing_score"
        elif row.contacts_last_90_days >= 2:
            reason = "contact_cap"
        elif row.last_contact and (as_of - date.fromisoformat(row.last_contact)).days < 30:
            reason = "contact_cooldown"
        elif isinstance(brief, (ConversationBrief, FollowupBrief, ProfiledBrief)) and row.segment not in segments:
            reason = "outside_selected_segment"
        if reason:
            reasons[reason] += 1
        else:
            eligible.append(row)
    eligible.sort(key=lambda row: (-row.propensity_ppm, row.business_id))
    # Enroll first, then randomize inside the same cohort. Conservative budget:
    # even if every enrolled business were mailed the cap would be respected.
    limit = min(brief.max_candidates, brief.budget_pence // brief.unit_cost_pence)
    cohort = eligible[:limit]
    assignment_rows, mailing_rows = [], []
    arm_counts: Counter[str] = Counter()
    for segment in segments:
        group = sorted((row for row in cohort if row.segment == segment), key=lambda row: digest({
            "algorithm": "hash-randomization/v1", "seed": snapshot.seed,
            "campaign": brief.campaign_id, "business": row.business_id,
        }))
        holdout = len(group) // 10
        for index, row in enumerate(group):
            arm = "no_mail" if index < holdout else ("A" if (index - holdout) % 2 == 0 else "B")
            creative = None if arm == "no_mail" else catalogue[(segment, arm)]
            arm_counts[f"{segment}:{arm}"] += 1
            assignment_rows.append((row.business_id, segment, arm, creative.id if creative else ""))
            if creative:
                mailing_rows.append((row.business_id, segment, arm, creative.id, row.address))
    mailing = _csv(("business_id", "segment", "arm", "creative_id", "demo_address"), sorted(mailing_rows))
    assignments = _csv(("business_id", "segment", "arm", "creative_id"), sorted(assignment_rows))
    selected = len(mailing_rows)
    held = len(cohort) - selected
    counts = {"input": len(snapshot.records), "excluded": sum(reasons.values()),
              "eligible_unselected": len(eligible) - len(cohort), "holdout": held, "mailed": selected}
    if counts["input"] != sum(value for key, value in counts.items() if key != "input"):
        raise AssertionError("Population did not reconcile")
    brief_data = asdict(brief)
    if isinstance(brief, (ConversationBrief, FollowupBrief, ProfiledBrief)):
        brief_data["segments"] = list(brief.segments)
    if profiled:
        brief_data['profile']['taxonomy']['segments'] = list(brief_data['profile']['taxonomy']['segments'])
    manifest = {
        "schema": "draft/v1", "mode": "SYNTHETIC_DRY_RUN_UNAPPROVED",
        "organization": snapshot.organization, "snapshot_id": snapshot.id,
        "as_of": snapshot.as_of, "model_version": snapshot.model_version,
        "score_semantics": snapshot.score_semantics, "forecast_basis": "response_not_incremental_value",
        "brief": brief_data, "counts": counts, "exclusion_reasons": dict(sorted(reasons.items())),
        "assignment_algorithm": "hash-randomization/v1", "seed": snapshot.seed,
        "arm_counts": dict(sorted(arm_counts.items())),
        "variable_cost_pence": selected * brief.unit_cost_pence,
        "mailing_sha256": hashlib.sha256(mailing.encode()).hexdigest(),
        "assignments_sha256": hashlib.sha256(assignments.encode()).hexdigest(),
        "creatives": [creative_record(item) | {"id": item.id, "content_hash": item.content_hash}
                      for item in sorted(creatives, key=lambda c: c.id)],
        "limitations": ["No authority to print or send",
                        "Copy is generated and unreviewed" if any(item.status == "generated_unreviewed" for item in creatives)
                        else "Copy is fixed unapproved fixture content",
                        "Budget conservatively includes potential holdouts", "Small strata may have no holdout",
                        "Rows with missing scores are explicitly excluded; no complete scoring claim"],
    }
    if getattr(brief, 'requested_scope', None) is not None:
        manifest['campaign_scope'] = asdict(CampaignScope())
    if profiled:
        manifest['schema'] = 'profile-draft/v1'
        manifest['profile_id'] = brief.profile.id
        manifest['product_profile_id'] = brief.profile.product_profile_id
        manifest['currency'] = brief.profile.currency
        manifest['approval'] = 'not_granted'
        manifest['limitations'].append('Profile proposals have no installed review, handoff or model execution capability')
    canonical(manifest)  # Reject non-serializable/non-finite content before persistence.
    return Draft(manifest, mailing, assignments)


def validate_copy_revision(base: Draft, candidate: Draft, target_id: str) -> None:
    """Independent publication check of copy-only scope against the actual base."""
    from acquisition.contracts import Conflict
    for field in ("brief", "snapshot_id", "counts", "arm_counts", "variable_cost_pence", "exclusion_reasons"):
        if base.manifest[field] != candidate.manifest[field]:
            raise Conflict("Copy revision changed the campaign population, budget or assignments")
    if base.manifest.get('campaign_scope') != candidate.manifest.get('campaign_scope'):
        raise Conflict('Copy revision changed the delivered campaign scope')
    old = {(c["segment"], c["arm"]): c for c in base.manifest["creatives"]}
    new = {(c["segment"], c["arm"]): c for c in candidate.manifest["creatives"]}
    target = next((key for key, c in old.items() if c["id"] == target_id), None)
    if target is None or set(old) != set(new) or old[target]["id"] == new[target]["id"]:
        raise Conflict("Revision must replace the exact selected creative")
    for key in old:
        if key[0] != target[0] and old[key] != new[key]:
            raise Conflict("Copy revision changed another segment")
        if old[key].get("fact_id") != new[key].get("fact_id") or old[key].get("fact_pack_id") != new[key].get("fact_pack_id"):
            raise Conflict("Copy revision changed product evidence")
        if key != target:
            for field in ("id", "headline", "opening", "locked_block", "hypothesis"):
                if old[key].get(field) != new[key].get(field):
                    raise Conflict("Copy revision changed an untargeted letter")
    before = list(csv.DictReader(io.StringIO(base.assignments_csv)))
    after = list(csv.DictReader(io.StringIO(candidate.assignments_csv)))
    if [(r["business_id"], r["segment"], r["arm"]) for r in before] != [(r["business_id"], r["segment"], r["arm"]) for r in after]:
        raise Conflict("Copy revision reassigned the audience")
