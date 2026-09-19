"""Set up a fresh install in one command.

Runs the steps in the order they depend on each other:

1. migrate.py            - create the tables from the models
2. seed_countries.py     - the country list user profiles pick from
3. seed.py               - the admin and client accounts you sign in with
4. seed_general_tools.py - the tools and skills that are not domain specific
5. seed_system_project.py- the System project and its Project Manager agent
6. seed_system_descriptions.py - the comments the storage library shows

Each step is idempotent, so running this again is safe: it reports what it
changed and leaves the rest alone. Arguments are passed to seed.py, so
``python seed_all.py --force`` wipes the data and seeds again.

    python seed_all.py
"""

import os
import subprocess
import sys

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))

STEPS = [
    "migrate.py",
    "seed_countries.py",
    "seed.py",
    "seed_general_tools.py",
    "seed_system_project.py",
    "seed_system_descriptions.py",
]

# Only seed.py understands extra arguments (--force).
ARGS_FOR = {"seed.py"}


def main():
    extra = sys.argv[1:]
    for step in STEPS:
        print()
        print("=" * 68)
        print("== %s" % step)
        print("=" * 68)
        command = [sys.executable, os.path.join(BACKEND_DIR, step)]
        if step in ARGS_FOR:
            command.extend(extra)
        result = subprocess.run(command, cwd=BACKEND_DIR)
        if result.returncode != 0:
            print()
            print("[FAIL] %s exited with %d; stopping here." % (step, result.returncode))
            return result.returncode

    print()
    print("=" * 68)
    print("Ready. Start the backend and open the panel:")
    print("  uvicorn app.main:app --host 127.0.0.1 --port 8000")
    print("Sign in with the SEED_ADMIN_EMAIL / SEED_PASSWORD from your .env.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
