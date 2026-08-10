-- Schedule the warehouse sweep.
--
-- Two jobs that only happen if something runs them, and until this existed
-- nothing did.
--
-- PURGE. A spent or expired capability is a row nobody can use that goes on
-- naming a recipient and an item indefinitely. kjerne_platform.work.tokens
-- has had purge() since the dual path shipped and nothing ever called it.
--
-- ASK. Every stock quantity is really a claim about when a person last looked
-- at a shelf, and the freshness clock is the honest part of this whole
-- feature. It only stays honest if holders are prompted to move it — a listing
-- nobody has confirmed in three weeks is not wrong, it is unverified, and only
-- its holder can say which.
--
-- 08:00 UTC / 04:00 ET, an hour before the attestation so the two never
-- contend and a slow sweep cannot delay the chain.
--
-- max_attempts = 1: the sweep is idempotent but a retry would send a second
-- round of notices to the same holders, and being asked twice about the same
-- pallet is how a useful prompt becomes noise somebody filters.
--
-- next_run_at MUST be set -- _check_schedules requires it NOT NULL, and a NULL
-- schedule silently never fires. stripe-fee-backfill is sitting in `tempora ls`
-- right now reading NEVER (no next_run_at), which is what that looks like.
--
-- ---------------------------------------------------------------------------
-- BEFORE RUNNING: replace REPLACE_WITH_DUGNADSAND_ATTEST_TOKEN with the value
-- of DUGNADSAND_ATTEST_TOKEN from /etc/svend/sites/dugnadsand.env. The sweep
-- shares the attestation's token: both are Tempora-only endpoints on this site
-- and a second secret would be a second thing to rotate for no extra safety.
-- ---------------------------------------------------------------------------

INSERT INTO task_schedule (name, task_name, payload, cron, enabled, max_attempts, next_run_at)
VALUES (
    'dugnadsand-warehouse-sweep',
    'workers.http_dispatch.dispatch',
    jsonb_build_object(
        'requests', jsonb_build_array(
            jsonb_build_object(
                'url', 'http://127.0.0.1:8013/warehouse/sweep/',
                'method', 'POST',
                'label', 'dugnadsand',
                'headers', jsonb_build_object(
                    'Authorization', 'Bearer REPLACE_WITH_DUGNADSAND_ATTEST_TOKEN'
                )
            )
        )
    ),
    '0 8 * * *',
    true,
    1,
    ((now() AT TIME ZONE 'UTC')::date + time '08:00'
       + CASE WHEN (now() AT TIME ZONE 'UTC')::time < time '08:00'
              THEN interval '0' ELSE interval '1 day' END) AT TIME ZONE 'UTC'
)
ON CONFLICT (name) DO NOTHING;
