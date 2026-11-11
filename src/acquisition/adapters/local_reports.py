"""Read a bounded synthetic provider snapshot from a local file."""

import json


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field in provider report")
        result[key] = value
    return result


class LocalSyntheticReports:
    def parse(self, raw):
        if type(raw) is not bytes or len(raw) > 4 * 1024 * 1024:
            raise ValueError("Provider report exceeds the 4 MiB limit")
        return json.loads(raw, object_pairs_hook=_unique_fields)

    def read(self, path):
        limit = 4 * 1024 * 1024
        try:
            with path.open("rb") as stream:
                raw = stream.read(limit + 1)
        except OSError as error:
            raise ValueError(f"Could not read provider report: {error}") from error
        return self.parse(raw)
