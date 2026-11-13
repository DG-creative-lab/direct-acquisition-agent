"""Scoped synthetic contact evidence, separate from postal snapshot contracts."""

from dataclasses import asdict, dataclass
import math

from acquisition.contracts import digest
from .domain import catalogue_identity


CHANNELS = frozenset({'direct_mail', 'email', 'human_call'})
PURPOSES = frozenset({'acquisition'})


def bounded(value, maximum=200):
    if (type(value) is not str or not 1 <= len(value.strip()) <= maximum
            or value != value.strip() or any(ord(c) < 32 for c in value) or chr(0x2014) in value):
        raise ValueError('Use bounded plain contact evidence text')


def timestamp(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('Use a finite nonnegative evidence timestamp')


def channel_purpose(channel, purpose):
    if channel not in CHANNELS or purpose not in PURPOSES:
        raise ValueError('Unsupported contact channel or purpose')


@dataclass(frozen=True)
class ContactConnection:
    organization: str
    key: str
    provider: str
    provider_account: str
    mapping_version: str

    def __post_init__(self):
        for value in asdict(self).values():
            catalogue_identity(value)

    @property
    def id(self):
        # Access aliases and mapping revisions cannot rename an external account and erase objections.
        return 'connection_' + digest({k:v for k,v in asdict(self).items() if k not in {'key','mapping_version'}})


@dataclass(frozen=True)
class NativeReference:
    connection: ContactConnection
    native_type: str
    native_id: str
    role: str

    def __post_init__(self):
        if type(self.connection) is not ContactConnection or self.role not in {'account', 'contact'}:
            raise ValueError('Declare a scoped native account or contact')
        bounded(self.native_type)
        bounded(self.native_id)

    @property
    def id(self):
        return 'native_' + digest({'connection_id': self.connection.id,
                                  'native_type': self.native_type, 'native_id': self.native_id})


def lifecycle(ref, state, merged_into):
    if state not in {'active', 'merged', 'deleted'}:
        raise ValueError('Unsupported identity lifecycle state')
    if state == 'merged':
        if (type(merged_into) is not NativeReference or merged_into.id == ref.id
                or merged_into.connection != ref.connection or merged_into.native_type != ref.native_type
                or merged_into.role != ref.role):
            raise ValueError('A merge needs a different native identity in the same scoped mapping')
    elif merged_into is not None:
        raise ValueError('Only a merged identity has a target')


@dataclass(frozen=True)
class ContactAccount:
    ref: NativeReference
    business_id: str
    segment: str
    country: str = 'UK'
    entity_type: str = 'LTD'
    state: str = 'active'
    merged_into: NativeReference | None = None

    def __post_init__(self):
        if type(self.ref) is not NativeReference or self.ref.role != 'account':
            raise ValueError('An account requires its native account reference')
        for value in (self.business_id, self.segment, self.country, self.entity_type):
            catalogue_identity(value)
        lifecycle(self.ref, self.state, self.merged_into)

    @property
    def experiment_unit(self):
        return 'account_unit_' + digest({'organization': self.ref.connection.organization,
                                        'business_id': self.business_id})


@dataclass(frozen=True)
class ContactPerson:
    ref: NativeReference
    accounts: tuple[NativeReference, ...]
    email: str | None
    phone: str | None
    state: str = 'active'
    merged_into: NativeReference | None = None

    def __post_init__(self):
        if type(self.ref) is not NativeReference or self.ref.role != 'contact':
            raise ValueError('A person requires a native contact reference')
        if (type(self.accounts) is not tuple or len(self.accounts) > 8
                or len({r.id for r in self.accounts}) != len(self.accounts)
                or any(type(r) is not NativeReference or r.role != 'account'
                       or r.connection != self.ref.connection for r in self.accounts)):
            raise ValueError('Preserve bounded, scoped account associations without guessing')
        if self.email is not None:
            bounded(self.email, 254)
            if (self.email.count('@') != 1 or not self.email.split('@')[0]
                    or not self.email.split('@')[1].endswith('.invalid') or any(c.isspace() for c in self.email)):
                raise ValueError('Only synthetic .invalid contact email is installed')
        if self.phone is not None:
            bounded(self.phone, 200)
            if not self.phone.startswith('DEMO ONLY DO NOT CALL:'):
                raise ValueError('Only marked synthetic call destinations are installed')
        lifecycle(self.ref, self.state, self.merged_into)


@dataclass(frozen=True)
class PermissionObservation:
    contact: NativeReference
    channel: str
    purpose: str
    status: str
    source_id: str
    observed_at: float
    expires_at: float

    def __post_init__(self):
        if self.contact.role != 'contact' or self.status not in {'granted', 'denied', 'unknown'}:
            raise ValueError('Declare an explicit contact permission observation')
        channel_purpose(self.channel, self.purpose)
        bounded(self.source_id)
        timestamp(self.observed_at); timestamp(self.expires_at)
        if self.expires_at <= self.observed_at:
            raise ValueError('Permission observations need a bounded lifetime')


@dataclass(frozen=True)
class ContactPressure:
    contact: NativeReference
    experiment_unit: str
    contact_count: int | None
    account_count: int | None
    window_start: float
    observed_at: float
    expires_at: float
    complete: bool
    source_id: str

    def __post_init__(self):
        if self.contact.role != 'contact' or type(self.complete) is not bool:
            raise ValueError('Pressure needs a scoped contact and explicit coverage')
        bounded(self.experiment_unit); bounded(self.source_id)
        for count in (self.contact_count, self.account_count):
            if count is not None and (type(count) is not int or count < 0):
                raise ValueError('Pressure counts are nonnegative integers or unknown')
        for value in (self.window_start, self.observed_at, self.expires_at):
            timestamp(value)
        if not self.window_start < self.observed_at < self.expires_at:
            raise ValueError('Pressure observations need an explicit window and lifetime')


@dataclass(frozen=True)
class ContactSnapshot:
    connection: ContactConnection
    version: int
    profile_id: str
    observed_at: float
    expires_at: float
    declared_accounts: int
    declared_contacts: int
    complete: bool
    cursor: str | None
    accounts: tuple[ContactAccount, ...]
    contacts: tuple[ContactPerson, ...]
    permissions: tuple[PermissionObservation, ...]
    pressure: tuple[ContactPressure, ...]
    schema: str = 'contact-source/v1'
    mode: str = 'SYNTHETIC_ONLY'

    def __post_init__(self):
        if (type(self.connection) is not ContactConnection or type(self.version) is not int or not 1 <= self.version <= 100
                or self.schema != 'contact-source/v1' or self.mode != 'SYNTHETIC_ONLY' or type(self.complete) is not bool):
            raise ValueError('Unsupported bounded synthetic contact source')
        bounded(self.profile_id)
        timestamp(self.observed_at); timestamp(self.expires_at)
        if self.expires_at <= self.observed_at:
            raise ValueError('A source requires a bounded observation window')
        for values, kind, maximum in ((self.accounts, ContactAccount, 128), (self.contacts, ContactPerson, 500),
                                     (self.permissions, PermissionObservation, 1500), (self.pressure, ContactPressure, 500)):
            if type(values) is not tuple or len(values) > maximum or any(type(v) is not kind for v in values):
                raise ValueError('Use bounded typed contact source populations')
        for count, values in ((self.declared_accounts, self.accounts), (self.declared_contacts, self.contacts)):
            if type(count) is not int or not len(values) <= count <= 500:
                raise ValueError('Declare explicit source population coverage')
            if self.complete and count != len(values):
                raise ValueError('A complete source must cover its whole declared population')
        if self.cursor is not None:
            bounded(self.cursor)
        if self.complete and self.cursor is not None:
            raise ValueError('Incomplete pagination cannot claim complete coverage')
        refs = [r.ref for r in (*self.accounts, *self.contacts)]
        if len({r.id for r in refs}) != len(refs) or any(r.connection != self.connection for r in refs):
            raise ValueError('Source records require distinct identities in the exact connection mapping')
        people = {r.ref.id for r in self.contacts}
        for item in (*self.permissions, *self.pressure):
            if item.contact.connection != self.connection or item.contact.id not in people:
                raise ValueError('Contact observations must belong to this exact source population')
            if item.observed_at > self.observed_at:
                raise ValueError('A source cannot attest a later observation')
        keys = [(p.contact.id, p.channel, p.purpose) for p in self.permissions]
        if len(set(keys)) != len(keys) or len({p.contact.id for p in self.pressure}) != len(self.pressure):
            raise ValueError('Conflicting observations require a new explicit source version')

    @property
    def id(self):
        return 'contact_source_' + digest(asdict(self))


def native_reference_from(payload):
    return NativeReference(**(payload | {'connection': ContactConnection(**payload['connection'])}))


def contact_snapshot_from(payload):
    def record(value, kind):
        fields = value | {'ref': native_reference_from(value['ref']),
                          'merged_into': native_reference_from(value['merged_into']) if value['merged_into'] else None}
        if kind is ContactPerson:
            fields['accounts'] = tuple(native_reference_from(r) for r in value['accounts'])
        return kind(**fields)
    def observation(value, kind):
        return kind(**(value | {'contact': native_reference_from(value['contact'])}))
    return ContactSnapshot(**(payload | {'connection': ContactConnection(**payload['connection']),
        'accounts': tuple(record(v, ContactAccount) for v in payload['accounts']),
        'contacts': tuple(record(v, ContactPerson) for v in payload['contacts']),
        'permissions': tuple(observation(v, PermissionObservation) for v in payload['permissions']),
        'pressure': tuple(observation(v, ContactPressure) for v in payload['pressure'])}))


def related_identities(identity, snapshots):
    """Merge ancestry propagates objections, never execution targets or permission grants."""
    edges = [(row.ref.id, row.merged_into.id) for snapshot in snapshots
             for row in (*snapshot.accounts, *snapshot.contacts) if row.state == 'merged']
    found = {identity}
    while True:
        expanded = found | {b for a,b in edges if a in found} | {a for a,b in edges if b in found}
        if expanded == found:
            return found
        found = expanded


def contact_evidence_conflicts(snapshot, snapshots, channel, purpose):
    """Known newer evidence cannot be bypassed through an older source alias.

    Absence does not erase a recorded observation. No grant or count is copied
    into the candidate; its own source must attest coherent current evidence.
    """
    permissions, pressure = {}, {}
    for source in sorted(snapshots,key=lambda value:value.version):
        for observation in source.permissions:
            key = (source.connection.key,observation.contact.id,observation.channel,observation.purpose)
            known = permissions.get(key,())
            if not known or observation.observed_at > known[0].observed_at:
                permissions[key] = (observation,)
            elif observation.observed_at == known[0].observed_at and observation not in known:
                permissions[key] = (*known,observation)
        for observation in source.pressure:
            key = (source.connection.key,observation.contact.id)
            known = pressure.get(key,())
            if not known or observation.observed_at > known[0].observed_at:
                pressure[key] = (observation,)
            elif observation.observed_at == known[0].observed_at and observation not in known:
                pressure[key] = (*known,observation)
    own_permissions = {(p.contact.id,p.channel,p.purpose):p for p in snapshot.permissions}
    own_pressure = {p.contact.id:p for p in snapshot.pressure}
    permission_conflicts, pressure_conflicts = set(), set()
    for person in snapshot.contacts:
        component = related_identities(person.ref.id,snapshots)
        own = own_permissions.get((person.ref.id,channel,purpose))
        if own is not None:
            for other in (value for group in permissions.values() for value in group):
                if other.contact.id in component and (other.channel,other.purpose)==(channel,purpose):
                    if (other.observed_at > own.observed_at or (other.observed_at == own.observed_at
                            and (other.status,other.expires_at)!=(own.status,own.expires_at))):
                        permission_conflicts.add(person.ref.id)
        own = own_pressure.get(person.ref.id)
        if own is not None:
            for other in (value for group in pressure.values() for value in group):
                same_person = other.contact.id in component
                if not same_person and other.experiment_unit != own.experiment_unit:
                    continue
                if other.observed_at > own.observed_at:
                    pressure_conflicts.add(person.ref.id)
                elif other.observed_at == own.observed_at:
                    if ((other.account_count,other.window_start,other.complete,other.expires_at) !=
                            (own.account_count,own.window_start,own.complete,own.expires_at)):
                        pressure_conflicts.add(person.ref.id)
                    if same_person and (other.contact_count != own.contact_count
                            or (other.contact.id != person.ref.id and (other.contact_count or 0) > 0)):
                        pressure_conflicts.add(person.ref.id)
    return permission_conflicts, pressure_conflicts
