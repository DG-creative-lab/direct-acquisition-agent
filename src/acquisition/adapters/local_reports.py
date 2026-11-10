"""Read a bounded synthetic provider snapshot from a local file."""

import json


class LocalSyntheticReports:
    def read(self, path):
        limit = 4 * 1024 * 1024
        try:
            with path.open("rb") as stream:
                raw = stream.read(limit + 1)
        except OSError as error:
            raise ValueError(f"Could not read provider report: {error}") from error
        if len(raw) > limit:
            raise ValueError("Provider report exceeds the 4 MiB limit")
        return json.loads(raw)
