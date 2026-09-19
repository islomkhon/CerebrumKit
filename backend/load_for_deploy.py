"""Load an export made by export_for_deploy.py into the database in .env.

Run on the deployed server with the backend venv:

    cd /var/www/cerebrumkit/backend
    ./venv/bin/python load_for_deploy.py [data-dir]

Tables are loaded parent-first so the foreign keys hold. One needs care and
gets a staging pass: `chats.last_message_id` points at `messages`, which cannot
exist yet. At the end every sequence is moved past the highest id that just
landed, otherwise the next insert collides.
"""
import gzip
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# .env is resolved relative to the working directory, exactly as the service
# does it, so run from the backend directory whether or not that is where the
# script was invoked from.
os.chdir(HERE)

import psycopg2  # noqa: E402

from app.core.config import settings  # noqa: E402

DATA = sys.argv[1] if len(sys.argv) > 1 else "/root/backups/cerebrumkit-data"

# Parent-first; the second element marks the tables that get a staging pass.
ORDER = [
    ("countries", None), ("users", None), ("projects", None),
    ("agents", None), ("skills", None), ("tools", None),
    ("project_tables", None), ("user_project", None), ("agent_project", None),
    ("agent_skill", None), ("skill_tool", None),
    ("chats", "chats"),
    ("messages", None), ("memory", None),
]
ALL = [name for name, _ in ORDER]

with io.open(os.path.join(DATA, "manifest.json"), encoding="utf-8") as fh:
    manifest = json.load(fh)

conn = psycopg2.connect(settings.database_url)
cur = conn.cursor()


def collist(table, transform=None):
    parts = []
    for name in manifest[table]["columns"]:
        if transform and name in transform:
            parts.append('%s AS "%s"' % (transform[name], name))
        else:
            parts.append('"%s"' % name)
    return ",".join(parts)


def copy_from(table, target=None):
    target = target or table
    with gzip.open(os.path.join(DATA, table + ".csv.gz"), "rb") as fh:
        cur.copy_expert(
            'COPY "%s" (%s) FROM STDIN WITH (FORMAT csv)' % (target, collist(table)),
            fh,
        )


def load_chats():
    """last_message_id points at messages, so it goes in null and is filled later."""
    cur.execute("CREATE TEMP TABLE stage_chats (LIKE chats)")
    copy_from("chats", target="stage_chats")
    cur.execute('INSERT INTO chats (%s) SELECT %s FROM stage_chats'
                % (collist("chats"), collist("chats", transform={"last_message_id": "NULL"})))
    return cur.rowcount


loaded = {}
for table, special in ORDER:
    if special == "chats":
        loaded[table] = load_chats()
    else:
        copy_from(table)
        cur.execute('SELECT count(*) FROM "%s"' % table)
        loaded[table] = cur.fetchone()[0]
    print("loaded %-26s %7d" % (table, loaded[table]), flush=True)

cur.execute('UPDATE chats c SET last_message_id = s."last_message_id" '
            'FROM stage_chats s WHERE s.id = c.id '
            'AND s."last_message_id" IS NOT NULL')
print("chats given their last message:", cur.rowcount, flush=True)

cur.execute("SELECT table_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name = 'id'")
has_id = {row[0] for row in cur.fetchall()}
for table in ALL:
    if table not in has_id:
        continue  # pivot tables have no id of their own
    cur.execute("SELECT pg_get_serial_sequence(%s, 'id')", (table,))
    seq = cur.fetchone()[0]
    if not seq:
        continue
    cur.execute('SELECT max(id) FROM "%s"' % table)
    top = cur.fetchone()[0]
    if top:
        cur.execute("SELECT setval(%s, %s)", (seq, top))
    else:
        cur.execute("SELECT setval(%s, 1, false)", (seq,))

conn.commit()

print("\n%-26s %9s %9s" % ("table", "exported", "in db"))
ok = True
for table in ALL:
    cur.execute('SELECT count(*) FROM "%s"' % table)
    have = cur.fetchone()[0]
    want = manifest[table]["rows"]
    flag = "" if have == want else "  <-- MISMATCH"
    if flag:
        ok = False
    print("%-26s %9d %9d%s" % (table, want, have, flag))

cur.close()
conn.close()
print("\nLOAD OK" if ok else "\nLOAD HAD MISMATCHES")
sys.exit(0 if ok else 1)
