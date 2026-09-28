# The hosted demo

<https://islomkhon.github.io/CerebrumKit/>

The real panel - the same Vue build a deployment ships - served as static files
from GitHub Pages. It reads a snapshot of a seeded install instead of talking to
a backend, so it can be looked at without installing anything and without
spending a Codespaces allowance.

## What is real, and what is not

Real: the panel itself. The admin and client panels, the workflow canvas with two
agents on it, skills and tools, the tools table where each function spec sits
beside the Python body that would run, the storage library with the `customers`
and `orders` tables, users, roles, and the routing between all of it. It is the
same bundle, so if the demo looks wrong the panel is wrong.

Not real, and stated on the page rather than left to be discovered:

- **No model.** GitHub Pages serves files; it cannot run FastAPI. The demo
  install has no working key, so the chat replies are canned. The canned reply
  does not pretend otherwise, and it names what a working loop would have done.
- **No persistence.** Writes are accepted and dropped, because a public page
  with a writable database is a page someone will fill with spam. Reload and you
  are back to the snapshot.
- **No real data.** The customers and orders are invented. The one key in the
  snapshot is the string `sk-demo-placeholder-not-a-real-key`.

## How it is built

`.github/workflows/pages.yml` runs `npm run build:demo`, which is the ordinary
build plus `--mode demo`. Vite then reads `frontend/cerebrumkit-vue/.env.demo`:

- `VITE_DEMO=1` is what makes the bundle answer from `src/demo/fixtures.json`.
  It is a build-time constant rather than a runtime setting, so no query string
  and no stored value can switch a deployed build into demo mode: in that build
  the flag is `false`, and the snapshot, the adapter and the demo socket are
  folded out of the bundle entirely. The one thing a production bundle does still
  carry is the banner's own wording - `App.vue` imports the component
  unconditionally and hides it behind the same constant - which is a dead string
  rather than a reachable code path.
- `VITE_BASE` is passed by the workflow (`/<repository-name>/`), so a fork
  publishes under its own path without editing a file. It would have to be `/`
  for a `<user>.github.io` repository or a custom domain.

Two consequences of Pages being a file server rather than an application server:

- **Deep links need a fallback.** Pages has no rewrite rules, so
  `/CerebrumKit/client/projects` is a 404. The workflow copies `dist/index.html`
  to `dist/404.html`; Pages answers the 404 with that file, the shell boots, and
  Vue Router reads the path back out of the address bar.
- **Nothing is server-rendered.** The first paint is the shell, then the panel.

## Regenerating the snapshot

`src/demo/fixtures.json` is generated from a seeded database, not written by
hand. To rebuild it:

```bash
cd backend
python seed_all.py             # the machinery: System project, Project Manager
python seed_demo_showcase.py   # the showcase slice: two agents, customers, orders
python export_demo_fixtures.py # -> frontend/cerebrumkit-vue/src/demo/fixtures.json
```

`seed_demo_showcase.py` is idempotent, and the rows are inserted under explicit
ids so re-running does not duplicate them or change what the panel is built
against. `export_demo_fixtures.py` reads through the application's own pydantic
schemas, so the snapshot cannot drift from the shapes the panel expects; it takes
an optional output path as its only argument.

It also replaces every platform key with the placeholder before writing. That
matters because the database it runs against is a development database, and a
development database has a live key in it. Re-running it against one is safe on
purpose rather than by luck, and the workflow refuses to publish a build that
contains a key-shaped string other than the placeholder - so if that redaction
ever stops working, the deployment fails instead of the secret.

## Turning it on

Once per repository, by an owner: **Settings -> Pages -> Build and deployment ->
Source -> GitHub Actions**. Until that is set the workflow fails at
`configure-pages`, because a repository with no Pages site has nothing to
configure. After that it runs on every push to `main` that touches the panel, and
on demand from the Actions tab.

## Limits worth knowing

- The Codespaces path and the demo have the same hole from different directions:
  neither ships a model. The demo at least says so on screen.
- The demo build and a real build share `src/api/client.ts` and
  `src/api/baseUrl.ts`. The `IS_DEMO` checks are the only thing keeping the two
  apart, so a change there should be checked against both builds.