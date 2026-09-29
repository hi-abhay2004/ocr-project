"""
Root-level so it reaches every test package: `apps/*/tests/` AND `tests/`.
A conftest.py placed inside `tests/` only applies to that subtree — it would
never be found for `apps/core/tests/test_health.py`, which is why this file
lives next to manage.py instead.
"""

import pytest

from ai.providers.mock import MockEmbeddingProvider, MockLLMProvider, MockVLMProvider


@pytest.fixture
def mock_llm():
    return MockLLMProvider()


@pytest.fixture
def mock_vlm():
    return MockVLMProvider()


@pytest.fixture
def mock_embedder():
    return MockEmbeddingProvider()


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def teacher_user(db):
    from apps.accounts.models import User

    return User.objects.create_user(
        username="teacher1", password="testpass123", role=User.Role.TEACHER
    )


@pytest.fixture
def student_user(db):
    from apps.accounts.models import User

    return User.objects.create_user(
        username="student1", password="testpass123", role=User.Role.STUDENT
    )


@pytest.fixture
def other_teacher_user(db):
    """A second, distinct teacher — for asserting cross-teacher isolation
    (BACKEND_PLAN.md §B2 gate: 'a teacher must never see another teacher's
    exam'). A single-user test suite can't tell scoped-to-user apart from
    scoped-to-nothing; this fixture is what makes that distinction visible."""
    from apps.accounts.models import User

    return User.objects.create_user(
        username="teacher2", password="testpass123", role=User.Role.TEACHER
    )


def _token_client(api_client, user):
    from rest_framework_simplejwt.tokens import RefreshToken

    token = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return api_client


@pytest.fixture
def auth_client(api_client, teacher_user):
    """APIClient authenticated as a teacher via a real JWT — exercises the
    same SimpleJWT auth path a browser request takes, not a permission bypass."""
    return _token_client(api_client, teacher_user)


@pytest.fixture
def other_auth_client(db, other_teacher_user):
    from rest_framework.test import APIClient

    return _token_client(APIClient(), other_teacher_user)


@pytest.fixture
def student_client(db, student_user):
    from rest_framework.test import APIClient

    return _token_client(APIClient(), student_user)
