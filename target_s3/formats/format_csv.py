"""CSV output format for target-s3.

Implements the three abstract methods declared on FormatBase
(`_prepare_records`, `_write`, `run`) so the loader can actually serialize
Singer records to CSV and ship them to S3 via the base class's
smart_open-backed writer.
"""

import csv
import io
import json
from datetime import datetime

from bson import ObjectId

from target_s3.formats.format_base import FormatBase


def _stringify(value):
    """Render any value as a CSV-safe scalar.

    The csv module handles quoting + escaping for str/int/float/bool, but
    can't serialize nested dicts/lists or non-JSON types like ObjectId and
    datetime. Mirror the same special-cases the JSON formatter handles so
    behavior is consistent across formats.
    """
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    # Nested dicts/lists or other complex objects: JSON-encode for round-trip.
    return json.dumps(value, default=str)


class FormatCsv(FormatBase):
    def __init__(self, config, context) -> None:
        super().__init__(config, context, "csv")

    def _prepare_records(self):
        # Inherit base behavior (handles optional include_process_date).
        return super()._prepare_records()

    def _write(self) -> None:
        if not self.records:
            return super()._write("")

        # Column union across the batch, ordered first-seen. This handles
        # records with slightly different keys without dropping data.
        fieldnames: list = []
        seen = set()
        for rec in self.records:
            for key in rec:
                if key not in seen:
                    seen.add(key)
                    fieldnames.append(key)

        buf = io.StringIO()
        writer = csv.DictWriter(
            buf,
            fieldnames=fieldnames,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        for rec in self.records:
            writer.writerow({k: _stringify(rec.get(k)) for k in fieldnames})

        return super()._write(buf.getvalue())

    def run(self) -> None:
        return super().run(self.context["records"])
