-- [agentic] Fast, connection-preserving database reset.
--
-- agentic_snapshot() copies every application table into schema "snap".
-- agentic_reset() truncates the live tables and copies the snapshot back, then
-- realigns the id sequences. Backend connections stay open, so a reset takes
-- well under a second and never surfaces as a 500 to a running browser.

CREATE OR REPLACE FUNCTION agentic_app_tables() RETURNS SETOF text
LANGUAGE sql STABLE AS $$
  SELECT tablename::text FROM pg_tables
  WHERE schemaname = 'public' AND tablename <> '_prisma_migrations'
  ORDER BY tablename;
$$;

CREATE OR REPLACE FUNCTION agentic_snapshot() RETURNS void
LANGUAGE plpgsql AS $$
DECLARE t text;
BEGIN
  DROP SCHEMA IF EXISTS snap CASCADE;
  CREATE SCHEMA snap;
  FOR t IN SELECT * FROM agentic_app_tables() LOOP
    EXECUTE format('CREATE TABLE snap.%I AS TABLE public.%I', t, t);
  END LOOP;
END $$;

CREATE OR REPLACE FUNCTION agentic_reset() RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
  t text;
  seq text;
  col text;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'snap') THEN
    RAISE EXCEPTION 'no snapshot: run agentic_snapshot() after seeding';
  END IF;
  EXECUTE (
    SELECT 'TRUNCATE ' || string_agg(format('public.%I', x), ', ') || ' RESTART IDENTITY CASCADE'
    FROM agentic_app_tables() AS x
  );
  -- Skip FK triggers while restoring (tables are copied in name order). The
  -- snapshot is a consistent copy, so constraints hold once the copy ends.
  SET LOCAL session_replication_role = replica;
  FOR t IN SELECT * FROM agentic_app_tables() LOOP
    EXECUTE format('INSERT INTO public.%I SELECT * FROM snap.%I', t, t);
  END LOOP;
  SET LOCAL session_replication_role = origin;
  -- Realign serial sequences with the restored ids.
  FOR t, col, seq IN
    SELECT c.table_name, c.column_name, pg_get_serial_sequence(format('public.%I', c.table_name), c.column_name)
    FROM information_schema.columns c
    WHERE c.table_schema = 'public' AND c.column_default LIKE 'nextval%'
  LOOP
    EXECUTE format('SELECT setval(%L, COALESCE((SELECT max(%I) FROM public.%I), 0) + 1, false)', seq, col, t);
  END LOOP;
END $$;
