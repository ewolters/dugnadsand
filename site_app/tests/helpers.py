"""Shared test helpers.

`sign_in` exists because every member route now sits behind a second factor.
Tests that are about offerings or the ledger should not each have to mock TOTP,
but they also should not be able to pretend the gate is not there — so the
helper marks the session as having passed it, the same flag the middleware
reads, and nothing else.
"""

MFA_SESSION_FLAG = "mfa_ok"


class SignedIn:
    """Mix in to reach member routes without re-testing the second factor."""

    def sign_in(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[MFA_SESSION_FLAG] = True
        session.save()
        return user


class CleansPlatformTokens:
    """Remove any work_action_token this test created.

    The token table lives in the SHARED platform database, outside Django's
    test transaction, so nothing here is rolled back — a test that mints one
    leaves it in a production table forever. That is how 94 rows accumulated
    before anybody looked.

    Per-test bookkeeping did not hold: it caught tokens the test minted itself
    and missed the ones minted for it, by invite() and by rendering a manifest.
    So this snapshots what existed before and deletes what is new, which needs
    no test to remember anything.
    """

    SITE = "dugnadsand"

    def _tokens(self):
        from kjerne_platform.db import get_conn

        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT token FROM work_action_token WHERE site = %s",
                        (self.SITE,))
            return {row[0] for row in cur.fetchall()}

    def setUp(self):
        self._tokens_before = self._tokens()
        super().setUp()

    def tearDown(self):
        super().tearDown()
        # A subclass whose setUp forgets to chain would otherwise fail here
        # with an AttributeError that says nothing about the real mistake.
        before = getattr(self, "_tokens_before", None)
        if before is None:
            raise AssertionError(
                f"{type(self).__name__} uses CleansPlatformTokens but its "
                f"setUp does not call super().setUp(), so nothing was recorded "
                f"and platform tokens will leak.")
        new = self._tokens() - before
        if not new:
            return
        from kjerne_platform.db import get_conn

        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM work_action_token WHERE token = ANY(%s)",
                        (list(new),))
            conn.commit()


class TrialDoorsOpen:
    """Run a test as though the trial period were not on.

    Applications and blind requests are closed while the network's future is
    being decided (see site_app/trial.py). The tests that exercise those doors
    are not deleted for it — the behaviour has to keep working, and it has to
    still be described somewhere when they reopen. They open the door for the
    duration of the test instead.

    The tests for the CLOSED behaviour are separate and do not use this.

    A subclass defining its own setUp MUST call super().setUp(), or this one
    never runs and the door stays shut — which shows up as every test in the
    class failing on an empty table rather than as anything to do with the
    trial period.
    """

    def setUp(self):
        from unittest.mock import patch

        for flag in ("APPLICATIONS_OPEN", "REQUESTS_OPEN"):
            patcher = patch(f"site_app.trial.{flag}", True)
            patcher.start()
            self.addCleanup(patcher.stop)
        super().setUp()
