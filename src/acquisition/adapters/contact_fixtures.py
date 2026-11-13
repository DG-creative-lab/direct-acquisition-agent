"""Installed synthetic source attestations. No customer data or arbitrary file paths."""

from dataclasses import asdict, replace
from datetime import datetime, timezone
import json

from acquisition.audiences import (ContactConnection, NativeReference, ContactAccount, ContactPerson,
    PermissionObservation, ContactPressure, ContactSnapshot, contact_snapshot_from)
from acquisition.contracts import NotFound, canonical


class RecordedContactSource:
    def __init__(self, organization, snapshots):
        self.organization = organization
        self._payloads = {}
        for snapshot in snapshots:
            if snapshot.connection.organization != organization:
                raise ValueError('Installed source belongs to another organization')
            key = (snapshot.connection.key, snapshot.version)
            if key in self._payloads:
                raise ValueError('A source version must identify one exact snapshot')
            self._payloads[key] = canonical(asdict(snapshot))

    def read(self, organization, connection_key, version):
        if organization != self.organization or type(version) is not int:
            raise NotFound('Contact source is unavailable in this organization')
        payload = self._payloads.get((connection_key, version))
        if payload is None:
            raise NotFound('Unknown installed contact source version')
        return contact_snapshot_from(json.loads(payload))

    def identity(self, organization, connection_key, version):
        return self.read(organization, connection_key, version).id


def synthetic_contact_snapshots(organization, profile):
    observed = datetime(2026, 11, 13, tzinfo=timezone.utc).timestamp() - 3600
    expiry = datetime(2026, 11, 24, tzinfo=timezone.utc).timestamp()
    for suffix in ('a', 'b'):
        connection = ContactConnection(organization, profile.key + '-crm-' + suffix,
                                      'synthetic-crm', profile.key + '-provider-' + suffix, 'mapping-v1')
        accounts = tuple(ContactAccount(NativeReference(connection, 'Company', str(i), 'account'),
            profile.key + '-' + suffix + '-business-' + str(i), profile.taxonomy.segments[(i-1) % len(profile.taxonomy.segments)].key)
            for i in (1, 2))
        people = tuple(ContactPerson(NativeReference(connection, 'Person', str(i), 'contact'),
            (accounts[0 if i < 3 else 1].ref,), 'person' + str(i) + '@' + suffix + '.example.invalid',
            'DEMO ONLY DO NOT CALL: synthetic person ' + str(i)) for i in (1, 2, 3))
        permissions = tuple(PermissionObservation(p.ref, channel, 'acquisition', 'granted',
            'synthetic-permission-v1', observed, expiry) for p in people for channel in ('email', 'human_call', 'direct_mail'))
        pressure = tuple(ContactPressure(p.ref, accounts[0 if i < 2 else 1].experiment_unit, 0, 0,
            observed-90*86400, observed, expiry, True, 'synthetic-shared-pressure-v1') for i,p in enumerate(people))
        original = ContactSnapshot(connection, 1, profile.id, observed, expiry, 2, 3, True, None,
                                   accounts, people, permissions, pressure)
        yield original
        merged = replace(people[0], state='merged', merged_into=people[1].ref)
        second = replace(original, version=2, contacts=(merged, *people[1:]))
        yield second
        yield replace(second, version=3, accounts=(replace(accounts[0], state='deleted'), accounts[1]))
