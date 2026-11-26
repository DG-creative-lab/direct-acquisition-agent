"""Bounded recorded JSON inputs, not an authenticated provider connector."""
import json
from pathlib import Path


class ExternalOutcomeFiles:
    def parse(self,raw):
        if type(raw) is not bytes or len(raw)>4*1024*1024:raise ValueError('External evidence exceeds four MiB')
        def pairs(values):
            result={}
            for k,v in values:
                if k in result:raise ValueError('Duplicate JSON field in external evidence')
                result[k]=v
            return result
        def invalid(value):raise ValueError('Non-finite JSON number in external evidence')
        try:result=json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)
        except (UnicodeError,RecursionError) as error:raise ValueError('Use bounded UTF-8 JSON evidence') from error
        if type(result) is not dict:raise ValueError('Use an external evidence object')
        return result
    def read(self,path):
        with Path(path).open('rb') as stream:return self.parse(stream.read(4*1024*1024+1))
