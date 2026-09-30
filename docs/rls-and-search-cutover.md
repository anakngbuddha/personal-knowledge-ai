# Production database and web-search cutover

The web process must connect with a PostgreSQL role that has neither `SUPERUSER`
nor `BYPASSRLS`. The Aiven `avnadmin` connection is for schema migrations only.

If Render exits with `RLS_REQUIRED must be true in production` before opening a
port, set `RLS_REQUIRED=true` in the service's Environment settings and redeploy.
The blueprint now supplies this value for Blueprint-managed services; existing
services configured manually must update their environment explicitly. Complete
the database role and migration steps below before redeploying. The port scan
message is a consequence of the settings failure, not a port configuration issue.

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
