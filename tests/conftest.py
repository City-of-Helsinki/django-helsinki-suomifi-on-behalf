from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import Client, RequestFactory
from django.utils.timezone import now


def store_tokens_in_session(client):
    s = client.session
    now_plus_1_hour = now() + timedelta(hours=1)
    s.update(
        {
            "oidc_id_token": "test",
            "oidc_access_token": "test",
            "oidc_refresh_token": "test",
            "oidc_access_token_expires": now_plus_1_hour.isoformat(),
            "oidc_refresh_token_expires": now_plus_1_hour.isoformat(),
            "eauth_id_token": "test",
            "eauth_access_token": "test",
            "eauth_refresh_token": "test",
            "eauth_access_token_expires": now_plus_1_hour.isoformat(),
            "eauth_refresh_token_expires": now_plus_1_hour.isoformat(),
        }
    )
    s.save()


def force_login_user(user) -> Client:
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture()
def user(db):
    return get_user_model().objects.create_user(username="test_user")


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def user_client(user):
    client = force_login_user(user)
    store_tokens_in_session(client)
    return client


@pytest.fixture
def mock_request():
    factory = RequestFactory()
    return factory.get("/", {"code": "test", "state": "test"})


@pytest.fixture
def get_response():
    return HttpResponse()


@pytest.fixture()
def session_request():
    factory = RequestFactory()
    request = factory.get("/")
    middleware = SessionMiddleware(lambda req: HttpResponse())
    middleware.process_request(request)
    request.session.save()

    return request
