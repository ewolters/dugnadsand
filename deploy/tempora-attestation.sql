-- Schedule the daily policy attestation.
--
-- The manifest in policy/manifest.toml claims things about how this software
-- behaves. A claim that is only checked when someone remembers to check it is
-- not a claim, so Tempora runs it daily and the result is appended to the
-- hash chain in the site's own database.
--
-- Why HTTP rather than a Tempora worker: workers.http_dispatch.dispatch lets
-- any app schedule work without Tempora depending on that app. Dugnadsand
-- keeps its own checks, its own chain and its own deploy cycle.
--
-- Why the result lands in Postgres and not a file in this repository: a
-- scheduled job that writes a git-TRACKED artifact loses its output on every
-- tree clean, and the schedule keeps reporting healthy while the artifact
-- quietly freezes. The attestation is a row, not a file.
--
-- 09:00 UTC / 05:00 ET. Nothing else is scheduled then, and it is early enough
-- that a BREACHED result is in the inbox before the working day.
--
-- max_attempts = 1: a breached manifest breaches identically on retry, and a
-- retry would append a second near-identical entry to the chain for no gain.
--
-- next_run_at MUST be set -- _check_schedules requires it NOT NULL, and a NULL
-- schedule silently never fires.
--
-- ---------------------------------------------------------------------------
-- BEFORE RUNNING: replace REPLACE_WITH_DUGNADSAND_ATTEST_TOKEN with the value
-- of DUGNADSAND_ATTEST_TOKEN from /etc/svend/sites/dugnadsand.env. The token is
-- deliberately not committed here.
-- ---------------------------------------------------------------------------

INSERT INTO task_schedule (name, task_name, payload, cron, enabled, max_attempts, next_run_at)
VALUES (
    'dugnadsand-attestation',
    'workers.http_dispatch.dispatch',
    jsonb_build_object(
        'requests', jsonb_build_array(
            jsonb_build_object(
                'url', 'http://127.0.0.1:8013/attestation/run/',
                'method', 'POST',
                'label', 'dugnadsand',
                'headers', jsonb_build_object(
                    'Authorization', 'Bearer REPLACE_WITH_DUGNADSAND_ATTEST_TOKEN'
                )
            )
        )
    ),
    '0 9 * * *',
    true,
    1,
    ((now() AT TIME ZONE 'UTC')::date + time '09:00'
       + CASE WHEN (now() AT TIME ZONE 'UTC')::time < time '09:00'
              THEN interval '0' ELSE interval '1 day' END) AT TIME ZONE 'UTC'
)
ON CONFLICT (name) DO NOTHING;
