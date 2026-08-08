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
