"""Bounded versioned local source. No caller-controlled paths or remote URLs."""
import hashlib
import json
import os
from pathlib import Path
import re

from acquisition.audiences import Business, Snapshot, DatasetVersion
from acquisition.contracts import Conflict, NotFound

MAX_BYTES = 4_000_000


def parse_json(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:
                raise ValueError('Duplicate field in audience source')
            result[key]=value
        return result
    try:
        return json.loads(raw,object_pairs_hook=unique)
    except (UnicodeError,json.JSONDecodeError):
        raise ValueError('Invalid audience source JSON') from None


class LocalAudienceSource:
    def __init__(self, root):
        self.root=Path(root).resolve()

    def _bytes(self, name, maximum=MAX_BYTES):
        if type(name) is not str or not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]{0,100}\.json',name):
            raise ValueError('Audience source must use an installed local filename')
        path=self.root/name
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise ValueError('Audience source path is outside its installed root')
        try:
            with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as source:
                raw=source.read(maximum+1)
        except OSError:
            raise NotFound('Installed audience source is unavailable') from None
        if len(raw)>maximum:
            raise ValueError('Audience source exceeds its byte limit')
        return raw

    def _entries(self):
        value=parse_json(self._bytes('catalogue.json',200_000))
        if type(value) is not dict or set(value)!={'schema','entries'} or value['schema']!='audience-catalogue/v1':
            raise ValueError('Unsupported audience catalogue')
        if type(value['entries']) is not list or len(value['entries'])>100:
            raise ValueError('Audience catalogue is not bounded')
        result=[];seen=set()
        for row in value['entries']:
            if type(row) is not dict or 'file' not in row:
                raise ValueError('Invalid audience catalogue entry')
            data={k:v for k,v in row.items() if k!='file'}
            try:
                data['segments']=tuple(data['segments'])
                manifest=DatasetVersion(**data)
            except (KeyError,TypeError):
                raise ValueError('Invalid audience manifest fields') from None
            key=(manifest.organization,manifest.dataset_id,manifest.version)
            if key in seen:
                raise Conflict('Duplicate dataset version in catalogue')
            seen.add(key);result.append((manifest,row['file']))
        return result

    def listing(self, organization):
        return tuple(sorted((m for m,_ in self._entries() if m.organization==organization),key=lambda m:(m.dataset_id,m.version)))

    def read(self, organization, dataset_id, version, checksum, manifest_id):
        entry=next(((m,name) for m,name in self._entries() if (m.organization,m.dataset_id,m.version)==(organization,dataset_id,version)),None)
        if entry is None:
            raise NotFound('Dataset version not found in this organization')
        manifest,name=entry
        if checksum != manifest.checksum or manifest_id != manifest.id:
            raise Conflict('Dataset selection changed; inspect the catalogue again')
        raw=self._bytes(name)
        if hashlib.sha256(raw).hexdigest()!=checksum:
            raise Conflict('Dataset bytes do not match the selected checksum')
        payload=parse_json(raw)
        expected={'organization','as_of','records','seed','complete','schema_version','model_version','score_semantics'}
        if type(payload) is not dict or set(payload)!=expected or type(payload['records']) is not list or len(payload['records'])>10000:
            raise ValueError('Unsupported or unbounded audience payload')
        try:
            payload['records']=tuple(Business(**r) for r in payload['records'])
            snapshot=Snapshot(**payload)
        except (KeyError,TypeError):
            raise ValueError('Invalid audience record schema') from None
        return manifest,snapshot
