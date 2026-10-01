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

The command applies migrations first, rejects missing users, superusers,
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

Aiven's service-user creation instructions are available in its
[official documentation](https://aiven.io/docs/products/postgresql/howto/manage-service-users).
