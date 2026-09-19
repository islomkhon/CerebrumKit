# CerebrumKit Web

Vue 3 + TypeScript + Vite single-page app for CerebrumKit. It ships two panels:

| Panel | Route prefix | Screens |
| --- | --- | --- |
| Admin | `/admin` | Projects, Skills, Tools, Storage, Users |
| Client | `/client` | Projects (the agents the signed-in user can talk to) |

The admin panel is where the agentic system is assembled: you register **tools**
(the functions agents may call), group them into **skills**, and attach those
skills to **agents** inside a **project**. The client panel is the end-user
surface: it only lists the projects that user has been granted, plus the chat
window that drives the agent loop.

## Setup

```bash
npm install
cp .env.example .env      # Windows: copy .env.example .env
```

`.env` only sets the backend origin, and it is required - there is no built-in
address in the code, so a build cannot ship pointing at one particular machine:

```
VITE_API_URL=http://localhost:8000
```

Point it at wherever the FastAPI backend is listening. The app stops with a clear
error if it is unset. Vite reads env files at startup only - restart `npm run dev`
after changing it.

## Scripts

- `npm run dev` - dev server with hot reload. Pass `-- --port 5174` to move it.
- `npm run build` - type-check (`vue-tsc -b`) then emit `dist/`.
- `npm run preview` - serve the built `dist/` locally.

## Layout

```
src/
  api/           axios client + one module per backend router
  components/    shared UI (AppLayout, AppIcon, chat components, ...)
  composables/   useOnlineStatus and friends
  locales/       i18n dictionaries (en, ru, zh, es, de, fr)
  plugins/i18n.ts  i18n setup; lists the locales and the schema type
  router/        routes + role guard (homeFor(role))
  stores/        Pinia stores (auth, chat, ui)
  types/         shared TypeScript types
  utils/         markdown rendering and other helpers
  views/
    admin/       ProjectsView, SkillsView, ToolsView, StorageView, UsersView
    client/      ProjectsView + chat
    LoginView.vue
  style.css      design tokens (38 CSS variables) + global styles
```

## Conventions worth keeping

- **Adding a language**: copy `src/locales/en.json`, translate the values, then
  import it and add the code in `src/plugins/i18n.ts`. All dictionaries share the
  `typeof en` schema, so keep the keys identical.
- **Adding an admin screen**: add the view under `src/views/admin/`, register the
  route in `src/router/index.ts` under the `admin` meta block (so the role guard
  covers it), and add a nav entry in `src/components/AppLayout.vue`.
- **Auth**: the Pinia `auth` store persists the JWT; the axios client attaches it
  and redirects to `/login` on 401. `homeFor(role)` decides where a login lands.
- **Styling**: never hard-code colors. Use the CSS variables declared in
  `src/style.css` so both panels stay visually consistent.
- **Line endings**: locale JSON files are CRLF; edit them with a tool that
  preserves that, or the diff noise will be enormous.
