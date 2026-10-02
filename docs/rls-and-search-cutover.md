# Production database and web-search cutover

The web process must connect with a PostgreSQL role that has neither `SUPERUSER`
nor `BYPASSRLS`. The Aiven `avnadmin` connection is for schema migrations only.

If Render exits with `RLS_REQUIRED must be true in production` before opening a
port, set `RLS_REQUIRED=true` in the service's Environment settings and redeploy.
The blueprint now supplies this value for Blueprint-managed services; existing
services configured manually must update their environment explicitly. Complete
the database role and migration steps below before redeploying. The port scan
message is a consequence of the settings failure, not a port configuration issue.

If startup instead reports `role 'avnadmin' has BYPASSRLS`, the database connection
still uses the administrator. A code redeploy cannot change credentials stored in
Render. Complete the steps below and replace Render's `DATABASE_URL` with the
restricted user's full connection URI (including its own password and the existing
SSL options). Do not merely replace the username in the administrator URI.

1. Create an Aiven service user named `pka_app` in the Aiven console. Connect as
   `avnadmin` and confirm `rolsuper = false` and `rolbypassrls = false` in
   `pg_roles` for `pka_app`. Do not grant it the admin role or ownership of the
   tenant tables.
2. As `avnadmin`, grant `pka_app` `CONNECT` on the application database,
   `USAGE` on the application schema, and `SELECT, INSERT, UPDATE, DELETE` on
   all application tables. Grant `USAGE, SELECT` on all sequences. Set matching
   default privileges for tables and sequences created by `avnadmin` in future
   migrations. Keep schema creation and extension privileges with `avnadmin`.
3. Run `python -m app.db.migrate_cli` from `backend/` with the admin
   `DATABASE_URL`. Run the backend PostgreSQL RLS tests and a staging login,
   ingestion, worker and answer flow using the restricted user.
4. Set Render's `DATABASE_URL` to the `pka_app` connection, `AUTO_MIGRATE=false`,
   and `RLS_REQUIRED=true` in the same deployment. Confirm the boot posture check
   succeeds. A startup failure means the role, policies or grants need repair;
   never turn the posture check off to restore service.
5. Create a Tavily Researcher free-plan API key and set `TAVILY_API_KEY` in
   Render. The key stays in Render secrets; do not commit it. Test a question
   with no matching documents and confirm web citations appear. The free plan
   stops when its monthly credits run out; the app should report this state.

Before every later deployment that changes the schema, run the admin migration
command first. The web service never performs DDL at startup.

To perform steps 2 and 3 together, create the service user first, then run from
`backend/` with the administrator `DATABASE_URL` supplied through your local
environment (never commit it):

```sh
python -m app.db.migrate_cli --grant-runtime-role pka_app
```

The command applies migrations and reconciles table RLS first, even when every
migration is already recorded. It then rejects missing users, superusers,
`BYPASSRLS` roles and roles that cannot log in, then grants access to the current
database and schema. It grants only `CONNECT`, schema `USAGE`, table
`SELECT/INSERT/UPDATE/DELETE`, and sequence `USAGE/SELECT`. Default privileges apply
to future objects created by the same migration user in that schema, so run later
migrations with that same administrator connection. It does not create a password,
grant admin membership, or transfer ownership. The command is safe to rerun.

Verify the service user using your database query tool:

```sql
SELECT rolname, rolsuper, rolbypassrls, rolcanlogin
FROM pg_roles WHERE rolname = 'pka_app';
```

Expected values are `pka_app`, `false`, `false`, `true`. Set `DATABASE_URL` to this
user's connection in Render, keep `AUTO_MIGRATE=false` and `RLS_REQUIRED=true`,
save the environment and redeploy. Confirm `/health` responds and the logs show
`Application startup complete` before considering the recovery complete.

## Recovering missing RLS flags and unexpected tenant policies

If Render reports `tables without ENABLE+FORCE RLS` or `tables with unexpected
tenant policies`, the database does not match the deployed application's security
requirements. Older policies allowed `org_id IS NULL`, and older versions left
`organization_memberships`, `messages`, `product_capabilities`,
`reference_architecture_products`, and `evaluation_questions` unprotected.
Replacing the runtime username alone cannot repair these tables. The subsequent
port-scan message is a consequence of the startup failure.

1. Use the fixed application's checkout and the administrator `DATABASE_URL`
   targeting the same database and schema as Render. From `backend/`, run:

   ```sh
   python -m app.db.migrate_cli --grant-runtime-role pka_app
   ```

   This always restores ENABLE and FORCE flags and recreates the current
   `tenant_isolation` policies, without deleting data or migration history. It
   retires the app's former `tenant_isolation_policy` name in the same transaction
   as creating the current policy. If replacement fails, both prior policies are
   restored by rollback. No unrelated policy names are deleted.
   Derived tables use parent ownership checks; evaluation questions remain
   accessible only to trusted system sessions. Repair uses one transaction per
   table, with bounded retries for lock conflicts. If interrupted, rerun the same
   command. Validation must succeed before default data or runtime grants proceed.

2. If reconciliation reports an unexpected policy, it names the table and its
   policies. Additional custom policies are preserved. Have the database administrator
   review them before rerunning; do not disable the startup check or automatically
   delete custom policies. Resolve permission or schema errors with the admin
   connection. An admin role's BYPASSRLS is expected during migration and does not
   prove that the application's runtime connection is safe.

3. Verify the restricted connection before deployment. Set
   `RLS_RUNTIME_DATABASE_URL` to the complete `pka_app` connection URI, set
   `PYTHONPATH=.` in the shell environment, and run from `backend/`:

   ```sh
   python ../scripts/check_ci_rls.py
   ```

   Require `Restricted runtime RLS posture verified`: `enforced` must be true and
   the unprotected-table and invalid-policy lists must be empty. Do not print or
   commit connection credentials.

4. Set Render's `DATABASE_URL` to that verified restricted URI, preserving SSL
   options. Keep `AUTO_MIGRATE=false` and `RLS_REQUIRED=true`, then redeploy the
   tested application revision. Require `Application startup complete`, HTTP 200
   from `/health`, and successful authenticated login, ingestion, and answer flows.

Run migrations separately before deploying schema changes. This repository uses
Render's free plan; [pre-deploy commands require paid services](https://render.com/docs/deploys).
The web service's startup command remains `uvicorn`; it does not repair security
or use administrator credentials.

Aiven's service-user creation instructions are available in its
[official documentation](https://aiven.io/docs/products/postgresql/howto/manage-service-users).

If the earlier repair failed with `(tenant_isolation, tenant_isolation_policy)`
on otherwise protected tables, rerun the updated administrator migration command.
The second name is from this repository's older migrations, before the RBAC
rewrite in commit `0c3b70b`. Reconciliation now retires that alias while preserving
other policies. Do not change `RLS_REQUIRED` to bypass the failure.

## Migration appears to hang while replacing triggers

The migration CLI now logs its bootstrap stage, migration name, and the table whose
tenant guards it is installing. Trigger replacement uses transaction-local
`lock_timeout=5s` and `statement_timeout=30s`. Deadlocks and lock timeouts retry at
most five times, then fail with the table name. All guards for one table are
replaced in one transaction, so failure preserves the previous triggers.

If the command reports a blocked tenant guard migration, use your administrator
database query tool to identify the blocker:

```sql
SELECT pid, state, wait_event_type, wait_event,
       pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
  AND cardinality(pg_blocking_pids(pid)) > 0;
```

Have the owner of the blocking transaction finish or roll back that transaction,
then rerun the migration. Identify the affected application or worker before
stopping it; this command does not terminate database sessions automatically.
The earlier `query cancellation failed: cancellation timeout expired` message
does not establish which session held the lock; the blocking-PID query provides
that evidence. Do not redeploy until the migration and restricted-role checks
succeed.

For a local retry after Ctrl+C, the prior PowerShell `finally` block removes
`DATABASE_URL`. Set it again from the existing secure variable before rerunning:

```powershell
$env:DATABASE_URL = [System.Net.NetworkCredential]::new('', $adminUri).Password
try {
    python -u -m app.db.migrate_cli --grant-runtime-role pka_app
} finally {
    Remove-Item Env:DATABASE_URL
}
```

If that shell was closed, enter the administrator URI again using `Read-Host
-AsSecureString`. Never print the URI or include it in an error report.

See PostgreSQL's documentation for [transaction-local timeouts](https://www.postgresql.org/docs/current/runtime-config-client.html)
and [blocking-session identification](https://www.postgresql.org/docs/current/functions-info.html).
