# Q-ERP

Django-based, multi-tenant ERP prototype. Shared-schema tenancy, server-rendered UI, 10 module skeletons (3 core + 7 add-on), per-tenant subscriptions / seats / permissions, and a full activity log.

## Quickstart (Windows / PowerShell)

```powershell
# 1. Install deps
py -3 -m pip install -r requirements.txt

# 2. Migrate
py -3 manage.py migrate

# 3. Register modules + permissions
py -3 manage.py sync_modules

# 4. Seed three demo tenants and users
py -3 manage.py seed_demo

# 5. Run
py -3 manage.py runserver
```

Then open <http://127.0.0.1:8000/accounts/login/>.

### Demo accounts

| Username        | Password | Role                                | Tenant   |
|-----------------|----------|-------------------------------------|----------|
| `admin`         | `admin`  | Global system admin (also superuser)| — (`/sys/`) |
| `acme-admin`    | `pass`   | Tenant administrator                | acme (core only) |
| `acme-user`     | `pass`   | Module Users group (read-only)      | acme     |
| `globex-admin`  | `pass`   | Tenant administrator                | globex (core + HR/CRM/Sales) |
| `initech-admin` | `pass`   | Tenant administrator                | initech (all modules) |

### Key URLs

- `/accounts/login/` — login
- `/sys/` — system admin console (global view of tenants, plans, modules, activity)
- `/t/<slug>/dashboard/` — tenant dashboard (e.g. `/t/acme/dashboard/`)
- `/t/<slug>/admin/` — tenant admin (users, groups, settings, activity log)
- `/t/<slug>/<module>/<entity>/` — per-module CRUD

### Modules (16 total)

**Core (always on, system-admin-only disable):** finance, inventory, procurement, org, tasks, messaging, automation, statistics

**Add-on (opt-in via plan):** hr, crm, manufacturing, documents, sales, projects, assets, support_tickets

#### Cross-cutting modules

- **org** — Department / Team / Membership tree. `Membership.is_head_of_department` and `is_head_of_team` flag heads-of; unique-per-scope enforced at the DB level. Heads-of are pure metadata (no automatic permission inheritance); the automation engine can target them.
- **tasks** — Canonical `Task` with optional `project` FK. Both standalone and project-linked tasks live here. `projects.Task` is intentionally absent.
- **messaging** — Unified inbox: user-to-user `DIRECT`/`GROUP` threads plus a `NOTIFICATION` kind that the automation engine writes into. Read state via `Participant.last_read_at`.
- **automation** — Rule/Event/Action engine, synchronous and in-process. See "Automation" below.
- **statistics** — Per-tenant configurable dashboard with built-in widgets that compute from active modules.
- **support_tickets** — Tickets, categories, replies (with `is_internal` flag).

### Automation (triggers / events / actions)

Each tenant admin can create `Rule` rows. When module write paths emit events, the engine evaluates each rule's condition and dispatches the action synchronously.

- **Events** are registered in code (`apps/automation/builtin_events.py`). The generic CRUD scaffold automatically emits `<app_label>.<model_name>.saved` for every model save; modules can register additional events (e.g. `inventory.item.below_threshold`).
- **Conditions** are a small JSON DSL evaluated by `apps/automation/conditions.py`. Example: `{"qty": {"<": 10}}` or `{"$any": [{"a": {"==": 1}}, {"b": {"==": 2}}]}`. Empty/missing condition = always match.
- **Actions** are registered handlers in `apps/automation/actions.py`:
  - `send_notification` — posts to a user's notification inbox.
  - `create_task` — creates a Task assigned to a user.
  - `create_purchase_request` — creates a draft PO for a supplier (the inventory-below-threshold use case).
  - `notify_head_of_department` / `notify_head_of_team` — looks up the User flagged `is_head_of_department=True` / `is_head_of_team=True` on the org module's Department/Team and sends them a notification. Wires org heads-of into the trigger engine.
  - `log_activity` — writes a custom row to `ActivityLog`.
  - Action params support `{payload.path}` placeholders that resolve against the event payload.
- **Audit**: every rule firing creates a `RuleRun` row (`MATCHED` / `SKIPPED` / `ERROR`) visible at `/t/<slug>/automation/runs/`. Handler exceptions never break the originating request.

Example: "When an inventory item is below threshold, create a draft PO to supplier X for 100 units"
- Event: `inventory.item.below_threshold` (emitted by the inventory app; for the prototype trigger this manually or extend the item-save path).
- Condition: `{"qty_on_hand": {"<=": 5}}` (or just `{}` to match any low-stock event).
- Action: `create_purchase_request`, params `{"supplier_id": 42, "total": 1000}`.

## Architecture

- **Tenant isolation:** shared schema with `tenant_id` FK on every domain row. The default `TenantManager` filters by a thread-local `request.tenant`; system admin code uses `.unscoped` explicitly.
- **Middleware chain:** `TenantResolutionMiddleware` → `TenantAccessMiddleware` → `SubscriptionEnforcementMiddleware` → `ActivityLoggingMiddleware`.
- **Custom user model** (`accounts.User`) with `tenant`, `is_system_admin`, `is_global_admin`, `is_disabled`. Mutual exclusion enforced in `clean()`.
- **Module registry:** each app under `apps/` ships a `module_meta.py` with code, name, permissions, menu. `sync_modules` imports them and creates `Module` rows + auth permissions on each `*Area` marker model.
- **Generic CRUD:** `apps/core/crud.py` provides `ModuleCRUDConfig` + `build_module_urls()`. Each module declares one config per model, gets list/detail/create/edit/delete with tenant-scoped queryset + permission checks + activity logging.
- **Permission gating happens at three layers:** middleware (URL prefix → active module), view mixin (`TenantPermissionRequiredMixin` checks `has_perm`), and manager scoping (always tenant-filtered by default).
- **Activity log:** every authenticated request produces ≤ 1 row via middleware. Auth events come from `user_logged_in/out/failed` signals. Write views call `log_change(request, action=..., obj=...)` to enrich the payload.

## Management commands

- `sync_modules` — idempotently sync `Module` rows + Django permissions from each app's `module_meta.py`. Run after deploys.
- `seed_demo` — create three plans (starter / growth / enterprise), three tenants (acme / globex / initech), and demo users.
- `prune_activity --older-than 90 [--category MODULE_READ] [--dry-run]` — delete old activity log rows. Useful for the high-volume `MODULE_READ` category.

## Tests

```powershell
py -3 -m pytest tests/
```

34 tests cover tenant isolation, manager scoping, post-login routing, cross-tenant 403, subscription middleware gating, seat limits, permission checks, system admin scoping, activity log scoping, the automation condition evaluator, end-to-end rule firing, the messaging direct/notification helpers, head-of-department uniqueness, and statistics dashboard rendering.

## Project layout

```
qerp/                       project package (settings.{base,dev,prod}, urls)
apps/
  core/                     abstract TenantOwnedModel, TenantManager, mixins, generic CRUD
  accounts/                 custom User, SystemAdminTenant, auth signals
  tenants/                  Tenant, TenantSettings, Module, Plan, Subscription, TenantModule, TenantGroup, middleware, sync_modules
  activity/                 ActivityLog, middleware, prune_activity
  dashboard/                tenant dashboard
  tenant_admin/             tenant self-service UI
  sys_admin/                /sys/ console
  finance/ inventory/ procurement/                  core domain modules
  org/                                              departments / teams / heads-of
  tasks/                                            canonical Task (optional project link)
  messaging/                                        unified inbox (DM + notifications)
  automation/                                       rules engine (events + conditions + actions)
  statistics/                                       per-tenant dashboard widgets
  hr/ crm/ manufacturing/ documents/ sales/         add-on modules
  projects/ assets/ support_tickets/
templates/
  base.html sys_base.html   shared layouts
  module/                   generic list/detail/form/confirm_delete used by every module
  tenant_admin/ sys_admin/  area-specific templates
media/                      tenant logos and document uploads (FileSystemStorage)
```

## Breaking change: schema regeneration

The `hr.Department` model was removed (departments now live in `apps/org`) and `projects.Task` was removed (the canonical Task is `apps/tasks.Task`). To keep the prototype's migration history clean, the `hr/` and `projects/` migration sets were **deleted and regenerated**. There is no data-migration path from any earlier migration state.

Consequences:

- A fresh checkout works as documented (`migrate` from scratch).
- Any environment with the old `hr` / `projects` migrations already applied will fail `migrate` with `InconsistentMigrationHistory` and/or silently lose `Employee.department` / `Timesheet.task` links.
- To upgrade an existing local DB, drop the database and re-run `migrate` + `sync_modules` + `seed_demo`. This is a prototype only; do not run against any data you care about.

If you later move past prototype stage, before any non-greenfield rollout: write proper `RunPython` data migrations to copy `hr_department` → `org_department` (preserving ids or a code→pk map and rewriting `hr_employee.department_id`) and the analogous remap from `projects_task` → `tasks_task` for `projects_timesheet.task_id`.

## Migration to PostgreSQL

`qerp/settings/prod.py` already declares a Postgres backend driven by `DB_*` env vars. The schema is Postgres-compatible (no SQLite-only types, every tenant-owned table includes `tenant_id` in its unique constraints). To migrate:

1. Set `DJANGO_SETTINGS_MODULE=qerp.settings.prod` and the `DB_*` / `DJANGO_SECRET_KEY` / `DJANGO_ALLOWED_HOSTS` env vars.
2. `py -3 manage.py migrate` against the empty Postgres database.
3. `py -3 manage.py sync_modules`.
4. Transfer data via `dumpdata` / `loaddata` if needed.

Postgres-only optimisations to consider later: GIN index on `ActivityLog.extra`, monthly partitioning of `ActivityLog`, row-level security policies on `tenant_id`.

## Production deployment

Operator checklist for going from `qerp.settings.dev` (SQLite, single worker) to `qerp.settings.prod` (Postgres, multi-worker behind a TLS proxy). Every item below is enforced at import time or via documented overrides; misconfiguration fails fast rather than silently degrading.

### Required environment variables

These three abort the process at settings import if missing or empty:

- `DJANGO_SECRET_KEY` — the standard Django secret key. Generate per-environment, never commit, rotate on suspected leak.
- `DJANGO_ALLOWED_HOSTS` — comma-separated list of host headers the app will accept. Empty entries are dropped; at least one non-empty host is required.
- `DB_PASSWORD` — Postgres password. The user / host / port / db name fall back to documented defaults (`qerp` / `localhost` / `5432` / `qerp`) but the password has no default by design.

### TLS / proxy headers

`prod.py` trusts `X-Forwarded-Proto` via `SECURE_PROXY_SSL_HEADER`. This places two hard requirements on the upstream proxy (nginx / Caddy / ALB / Cloud Run / …):

1. The proxy **MUST** set `X-Forwarded-Proto` on every request based on the actual scheme it terminated. Without this, `SECURE_SSL_REDIRECT=True` is unable to recognise already-HTTPS requests and you will get an infinite redirect loop the moment traffic reaches the app.
2. The proxy **MUST** strip any client-supplied `X-Forwarded-Proto` header before forwarding. Without this, an attacker can spoof `X-Forwarded-Proto: https` and bypass the SSL-only redirect logic, defeating cookie `Secure` flag detection downstream.

### Recommended first-deploy overrides

Configure the following env vars **for the first 24 hours** of a new deployment, then raise to the defaults once the TLS chain is verified end-to-end:

- `DJANGO_SSL_REDIRECT=0` until you've confirmed (1) above. Once verified, unset or set to `1`.
- `DJANGO_HSTS_SECONDS=60` (one minute). HSTS is sticky in browsers: a 1-year HSTS header sent in error cannot be rolled back from the server side; users who received it cannot reach your site over HTTP for a year regardless of what you change. After 24 hours of stable HTTPS, raise to `31536000` (1 year, the production default).

### Cache backend (`DJANGO_CACHE_BACKEND`)

`base.py` declares a per-process `LocMemCache` as the default. This is only correct for **single-worker** deploys; under gunicorn/uwsgi with `>=2` workers each worker has its own cache and invalidations (e.g. menu cache bumps fired by `tenant_module_toggle`) only reach the worker that handled the event. Production must override this.

`DJANGO_CACHE_BACKEND` accepts either of:

- A JSON object string used verbatim as `CACHES["default"]`, e.g. `{"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": "redis://cache:6379/1"}`.
- A bare dotted backend path, used as just the `BACKEND` (no extra options), e.g. `django.core.cache.backends.memcached.PyMemcacheCache`.

Invalid JSON raises `ImproperlyConfigured` at import time.

### Seed / module hygiene

- `seed_demo` refuses to run when `DEBUG=False` unless `ALLOW_SEED_DEMO=1` is also set. The override exists so CI and ephemeral preview environments can populate demo data; **NEVER** set it on a real production deployment — it overwrites tenant data.
- `sync_modules --prune` requires `--yes` AND will refuse to prune any module with `is_core=True`. Always run a `--dry-run` first to confirm the intended targets.

## Deploy to PythonAnywhere (free tier)

PythonAnywhere's free "Beginner" account gives you a persistent Linux home directory, free HTTPS on `https://<username>.pythonanywhere.com`, and a Python 3.13 runtime. It's the lowest-friction way to put this prototype online for a small audience.

### One-time setup

1. Sign up at <https://www.pythonanywhere.com/registration/register/beginner/>. Note your username; the site will live at `https://<username>.pythonanywhere.com`.

2. Open the **Bash console** (Consoles tab → "Bash") and clone the repo plus create a virtualenv:

   ```bash
   git clone https://github.com/<you>/q-erp.git
   mkdir -p ~/qerp-data/media
   mkvirtualenv qerp --python=/usr/bin/python3.13
   cd ~/q-erp
   pip install -r requirements.txt
   ```

3. **Web tab** → "Add a new web app":
   - Domain: accept the default
   - Framework: **Manual configuration** (NOT "Django" — that scaffolds a new project)
   - Python version: **3.13**

4. In the Web tab:
   - **Source code**: `/home/<username>/q-erp`
   - **Working directory**: `/home/<username>/q-erp`
   - **Virtualenv**: `/home/<username>/.virtualenvs/qerp`
   - **Static files** → add two mappings:
     - URL `/static/` → Directory `/home/<username>/q-erp/staticfiles/`
     - URL `/media/` → Directory `/home/<username>/qerp-data/media/`

5. Edit the **WSGI configuration file** (the link in the Web tab — usually `/var/www/<username>_pythonanywhere_com_wsgi.py`). Replace its contents with:

   ```python
   import os
   import sys

   project_dir = "/home/<username>/q-erp"
   if project_dir not in sys.path:
       sys.path.insert(0, project_dir)

   os.environ["DJANGO_SECRET_KEY"] = "REPLACE-WITH-A-LONG-RANDOM-STRING"
   os.environ["DJANGO_ALLOWED_HOSTS"] = "<username>.pythonanywhere.com"
   os.environ["QERP_DB_PATH"] = "/home/<username>/qerp-data/db.sqlite3"
   os.environ["QERP_MEDIA_ROOT"] = "/home/<username>/qerp-data/media"
   os.environ["DJANGO_SETTINGS_MODULE"] = "qerp.settings.pythonanywhere"

   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```

   Generate a real `DJANGO_SECRET_KEY` on your laptop with `py -3 -c "import secrets; print(secrets.token_urlsafe(64))"` and paste the result.

6. Back in the Bash console, initialize the DB and seed demo data:

   ```bash
   cd ~/q-erp
   workon qerp
   export DJANGO_SETTINGS_MODULE=qerp.settings.pythonanywhere
   export DJANGO_SECRET_KEY="paste-the-same-secret-from-step-5"
   export DJANGO_ALLOWED_HOSTS="<username>.pythonanywhere.com"
   export QERP_DB_PATH="/home/<username>/qerp-data/db.sqlite3"
   export QERP_MEDIA_ROOT="/home/<username>/qerp-data/media"
   export ALLOW_SEED_DEMO=1

   python manage.py migrate
   python manage.py sync_modules
   python manage.py collectstatic --noinput
   python manage.py seed_demo
   ```

   `ALLOW_SEED_DEMO=1` overrides the production guard that normally refuses to seed when `DEBUG=False`. Safe here because this is a "viewing only" deploy with the well-known `admin/admin` superuser; do not reuse this env on a real production deploy.

7. Click the green **"Reload"** button in the Web tab. Visit `https://<username>.pythonanywhere.com/accounts/login/` and sign in with the seeded accounts (see "Demo accounts" above).

### Updating after first deploy

```bash
cd ~/q-erp
git pull
workon qerp
pip install -r requirements.txt           # if requirements changed
python manage.py migrate                  # if new migrations
python manage.py sync_modules             # if module catalog changed
python manage.py collectstatic --noinput  # if static files changed
# Web tab → click "Reload"
```

The SQLite database and uploaded documents live at `~/qerp-data/` — outside the repo — so `git pull` never touches them.

### Constraints of the free tier

- **Custom domain is paid-only.** You're stuck with `<username>.pythonanywhere.com`. That's why `qerp/settings/pythonanywhere.py` ships HSTS and SSL-redirect OFF by default — don't pin a hostname you don't own.
- **CPU seconds are capped per day.** For a few users clicking around you won't hit it; if you do, the site stays up but Python becomes slow until the daily reset.
- **No background workers** on free tier. The automation engine is synchronous in-process so this is fine. `prune_activity` and `prune_rule_runs` must be run manually from the Bash console.
- **No managed Postgres** on free tier. SQLite is fine for this workload size; if you outgrow it, upgrade to PA's paid tier (which adds Postgres) or switch to a different host.

## Deferred / out-of-scope

- Billing / payments
- Deep business logic per module (GL postings, MRP, costing, payroll, …)
- Reporting & BI cross-module ad-hoc queries (statistics module ships a fixed widget catalog only)
- Background jobs (the automation engine is synchronous and in-process)
- Email delivery (notifications stay in the in-app inbox)
- DRF / REST API layer
- S3-compatible document storage backend (local `FileSystemStorage` only)
- Tailwind / SPA frontend
- Permission inheritance from "head of department/team" (heads-of are pure metadata)
