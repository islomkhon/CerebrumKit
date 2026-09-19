"""Export every table as gzipped CSV, ready to load on the deployed server.

Run on a development machine with the backend venv:

    backend/venv/Scripts/python.exe backend/export_for_deploy.py

Writes to $TEMP/cerebrumkit-data on Windows (or /tmp/cerebrumkit-data
elsewhere) and prints
the tar command to ship it. The column list comes from the ORM metadata rather
than the local catalog, because the deployed schema is built from those same
models - that is what makes the two line up even when a local database has
drifted.
"""
import gzip
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# .env is resolved relative to the working directory, exactly as the service
# does it, so run from the backend directory whether or not that is where the
# script was invoked from.
os.chdir(HERE)

import psycopg2  # noqa: E402

import app.models  # noqa: E402,F401  - registers every model on the metadata
from app.core.config import settings  # noqa: E402
from app.core.database import Base  # noqa: E402

OUT = os.path.join(tempfile.gettempdir(), "cerebrumkit-data")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    conn = psycopg2.connect(settings.database_url)
    cur = conn.cursor()
    manifest = {}

    for name in sorted(t.name for t in Base.metadata.sorted_tables):
        columns = [c.name for c in Base.metadata.tables[name].columns]
        path = os.path.join(OUT, name + ".csv.gz")
        with gzip.open(path, "wb") as fh:
            cur.copy_expert(
                'COPY "%s" (%s) TO STDOUT WITH (FORMAT csv)'
                % (name, ",".join('"%s"' % c for c in columns)),
                fh,
            )
        cur.execute('SELECT count(*) FROM "%s"' % name)
        rows = cur.fetchone()[0]
        manifest[name] = {
            "columns": columns,
            "rows": rows,
            "bytes": os.path.getsize(path),
        }
        print("%-26s %3d cols %8d rows %8.1f KB" % (name, len(columns), rows, os.path.getsize(path) / 1024))

    with io.open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(manifest, indent=1))

    total = sum(v["bytes"] for v in manifest.values()) / 1024
    print("\n%d tables, %.1f KB compressed into %s" % (len(manifest), total, OUT))
    print("ship it with:  tar -czf cerebrumkit-data.tar.gz -C %s ." % OUT)
    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
