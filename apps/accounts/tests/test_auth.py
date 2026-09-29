import pytest

from apps.accounts.models import User
from apps.students.models import Student

pytestmark = pytest.mark.django_db


def _payload(**overrides):
    payload = {
        "username": "charan",
        "full_name": "P Charan Chandra",
        "email": "charan@bmsit.in",
        "password": "correct-horse-battery",
        "role": "TEACHER",
    }
    payload.update(overrides)
    return payload


class TestRegister:
    def test_register_teacher_returns_token_pair(self, api_client):
        response = api_client.post("/api/auth/register/", _payload(), format="json")

        assert response.status_code == 201
        assert set(response.data.keys()) == {"access", "refresh"}
        user = User.objects.get(username="charan")
        assert user.role == User.Role.TEACHER
        assert user.full_name == "P Charan Chandra"
        assert user.check_password("correct-horse-battery")

    def test_register_student_requires_usn(self, api_client):
        response = api_client.post(
            "/api/auth/register/", _payload(role="STUDENT", username="deepika"), format="json"
        )

        assert response.status_code == 400
        assert "usn" in response.data
        assert not User.objects.filter(username="deepika").exists()

    def test_register_student_rejects_malformed_usn(self, api_client):
        response = api_client.post(
            "/api/auth/register/",
            _payload(role="STUDENT", username="deepika", usn="!!"),
            format="json",
        )
        assert response.status_code == 400
        assert "malformed" in str(response.data["usn"]).lower()

    def test_register_student_creates_and_links_student_row(self, api_client):
        response = api_client.post(
            "/api/auth/register/",
            _payload(role="STUDENT", username="deepika", usn="1by22cs099"),
            format="json",
        )

        assert response.status_code == 201
        student = Student.objects.get(usn="1BY22CS099")  # normalised to uppercase
        assert student.user.username == "deepika"
        assert student.name == "P Charan Chandra"

    def test_register_student_links_to_a_pre_imported_student_row(self, api_client):
        # A teacher CSV-imported the class list before this person ever signed
        # up (Phase B2) — the row exists but is unclaimed. Registration must
        # LINK it, not reject it as a duplicate.
        pre_imported = Student.objects.create(usn="1BY22CS050", name="A Deepika", email="")

        response = api_client.post(
            "/api/auth/register/",
            _payload(role="STUDENT", username="deepika", usn="1BY22CS050"),
            format="json",
        )

        assert response.status_code == 201
        pre_imported.refresh_from_db()
        assert pre_imported.user.username == "deepika"

    def test_register_student_rejects_a_usn_already_claimed(self, api_client):
        owner = User.objects.create_user(username="owner", password="x", role=User.Role.STUDENT)
        Student.objects.create(usn="1BY22CS050", name="Someone", user=owner)

        response = api_client.post(
            "/api/auth/register/",
            _payload(role="STUDENT", username="impersonator", usn="1BY22CS050"),
            format="json",
        )

        assert response.status_code == 400
        assert "already registered" in str(response.data["usn"]).lower()

    def test_register_teacher_rejects_a_usn(self, api_client):
        response = api_client.post(
            "/api/auth/register/", _payload(role="TEACHER", usn="1BY22CS050"), format="json"
        )
        assert response.status_code == 400
        assert "usn" in response.data

    def test_register_rejects_duplicate_username(self, api_client, teacher_user):
        response = api_client.post(
            "/api/auth/register/", _payload(username=teacher_user.username), format="json"
        )
        assert response.status_code == 400
        assert "already exists" in str(response.data["username"]).lower()

    def test_register_rejects_short_password(self, api_client):
        response = api_client.post("/api/auth/register/", _payload(password="short"), format="json")
        assert response.status_code == 400
        assert "password" in response.data

    def test_register_omitted_usn_for_teacher_is_accepted(self, api_client):
        # The frontend omits the `usn` key entirely for teachers rather than
        # sending "" (frontend/src/pages/Signup.tsx) — confirm the absent-key
        # case, not just the empty-string case.
        payload = _payload()
        assert "usn" not in payload
        response = api_client.post("/api/auth/register/", payload, format="json")
        assert response.status_code == 201


class TestLoginRefreshMe:
    def test_login_returns_token_pair(self, api_client, teacher_user):
        response = api_client.post(
            "/api/auth/login/",
            {"username": teacher_user.username, "password": "testpass123"},
            format="json",
        )
        assert response.status_code == 200
        assert set(response.data.keys()) == {"access", "refresh"}

    def test_login_rejects_wrong_password(self, api_client, teacher_user):
        response = api_client.post(
            "/api/auth/login/",
            {"username": teacher_user.username, "password": "wrong"},
            format="json",
        )
        assert response.status_code == 401

    def test_refresh_rotates_and_blacklists_the_old_token(self, api_client, teacher_user):
        login = api_client.post(
            "/api/auth/login/",
            {"username": teacher_user.username, "password": "testpass123"},
            format="json",
        )
        old_refresh = login.data["refresh"]

        first = api_client.post("/api/auth/refresh/", {"refresh": old_refresh}, format="json")
        assert first.status_code == 200
        assert first.data["refresh"] != old_refresh

        # This is exactly the scenario frontend/src/tests/auth.test.ts exercises
        # client-side: presenting an already-rotated refresh token must fail,
        # which is what makes the single-flight refresh test meaningful.
        second = api_client.post("/api/auth/refresh/", {"refresh": old_refresh}, format="json")
        assert second.status_code == 401

    def test_me_returns_role_and_full_name(self, auth_client, teacher_user):
        response = auth_client.get("/api/auth/me/")
        assert response.status_code == 200
        assert response.data["username"] == teacher_user.username
        assert response.data["role"] == "TEACHER"

    def test_me_requires_authentication(self, api_client):
        response = api_client.get("/api/auth/me/")
        assert response.status_code == 401


class TestAuthThrottling:
    """Login/register/refresh share a "auth" throttle scope, 20/min
    (config/settings/base.py) — brute-forcing a password or hammering
    signup is rate-limited at the view layer, not left to whatever the
    database can absorb."""

    def test_the_auth_scope_throttles_after_its_configured_rate(self, api_client, teacher_user):
        from django.core.cache import cache

        # DRF's ScopedRateThrottle cache is process-global and would
        # otherwise accumulate hits from every other auth-hitting test in
        # this session (all keyed by the test client's shared IP) — clear
        # it first so this test's count starts from zero, and clear it
        # again after so it doesn't throttle whatever runs next.
        cache.clear()
        try:
            responses = [
                api_client.post(
                    "/api/auth/login/",
                    {"username": teacher_user.username, "password": "wrong-password"},
                    format="json",
                )
                for _ in range(21)  # DEFAULT_THROTTLE_RATES["auth"] = "20/min"
            ]
        finally:
            cache.clear()

        assert responses[-1].status_code == 429
        assert all(r.status_code != 429 for r in responses[:20])
