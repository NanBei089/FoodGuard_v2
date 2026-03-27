from __future__ import annotations

import importlib
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.error_handlers import register_exception_handlers
from app.models.user import User
from tests.conftest import load_required_env


def _build_users_app(monkeypatch):
    load_required_env(monkeypatch)
    api_module = importlib.reload(importlib.import_module("app.api.v1.users"))
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(api_module.router, prefix="/users")
    return app, api_module


def _build_preferences_app(monkeypatch):
    load_required_env(monkeypatch)
    api_module = importlib.reload(importlib.import_module("app.api.v1.preferences"))
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(api_module.router, prefix="/preferences")
    return app, api_module


def _current_user() -> User:
    user = User(
        email="user@example.com",
        password_hash="hashed",
        is_verified=True,
        is_active=True,
    )
    user.id = uuid.uuid4()
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    return user


def test_users_router_endpoints(monkeypatch) -> None:
    app, api_module = _build_users_app(monkeypatch)
    current_user = _current_user()
    fake_db = AsyncMock()

    async def override_db():
        yield fake_db

    async def override_user():
        return current_user

    async def fake_get_user_profile(user):
        return api_module.UserProfileResponse(
            user_id=user.id,
            email=user.email,
            display_name="李雷",
            avatar_url=None,
            is_verified=True,
            created_at=user.created_at,
        )

    async def fake_update_user_profile(user, *, display_name, avatar_url, db):
        assert display_name == "韩梅梅"
        assert avatar_url == "https://example.com/avatar.png"
        return api_module.UserProfileResponse(
            user_id=user.id,
            email=user.email,
            display_name=display_name,
            avatar_url=avatar_url,
            is_verified=True,
            created_at=user.created_at,
        )

    async def fake_change_user_password(
        user, *, current_password, new_password, db
    ) -> None:
        assert current_password == "OldPass123"
        assert new_password == "NewPass123"

    async def fake_deactivate_user(user, db) -> None:
        assert user.id == current_user.id

    app.dependency_overrides[api_module.get_db] = override_db
    app.dependency_overrides[api_module.get_current_user] = override_user
    monkeypatch.setattr(api_module, "get_user_profile", fake_get_user_profile)
    monkeypatch.setattr(api_module, "update_user_profile", fake_update_user_profile)
    monkeypatch.setattr(api_module, "change_user_password", fake_change_user_password)
    monkeypatch.setattr(api_module, "deactivate_user", fake_deactivate_user)

    with TestClient(app) as client:
        get_response = client.get("/users/me")
        patch_response = client.patch(
            "/users/me",
            json={
                "display_name": "韩梅梅",
                "avatar_url": "https://example.com/avatar.png",
            },
        )
        password_response = client.post(
            "/users/change-password",
            json={"current_password": "OldPass123", "new_password": "NewPass123"},
        )
        delete_response = client.delete("/users/me")

    assert get_response.status_code == 200
    assert get_response.json()["data"]["display_name"] == "李雷"
    assert patch_response.status_code == 200
    assert patch_response.json()["data"]["display_name"] == "韩梅梅"
    assert password_response.json() == {"code": 0, "message": "ok", "data": None}
    assert delete_response.json() == {"code": 0, "message": "ok", "data": None}


def test_preferences_router_endpoints(monkeypatch) -> None:
    app, api_module = _build_preferences_app(monkeypatch)
    current_user = _current_user()
    fake_db = AsyncMock()

    async def override_db():
        yield fake_db

    async def override_user():
        return current_user

    async def fake_get_user_preferences(user, db):
        return api_module.UserPreferenceResponse(
            focus_groups=["adult"],
            health_conditions=["hypertension"],
            allergies=["花生"],
            updated_at=datetime.now(timezone.utc),
        )

    async def fake_upsert_user_preferences(
        user, *, focus_groups, health_conditions, allergies, db
    ):
        assert focus_groups == ["adult"]
        assert health_conditions == ["hypertension"]
        assert allergies == ["花生"]
        return api_module.UserPreferenceResponse(
            focus_groups=["adult"],
            health_conditions=["hypertension", "allergy"],
            allergies=["花生"],
            updated_at=datetime.now(timezone.utc),
        )

    app.dependency_overrides[api_module.get_db] = override_db
    app.dependency_overrides[api_module.get_current_user] = override_user
    monkeypatch.setattr(api_module, "get_user_preferences", fake_get_user_preferences)
    monkeypatch.setattr(
        api_module, "upsert_user_preferences", fake_upsert_user_preferences
    )

    with TestClient(app) as client:
        get_response = client.get("/preferences/me")
        put_response = client.put(
            "/preferences/me",
            json={
                "focus_groups": ["adult"],
                "health_conditions": ["hypertension"],
                "allergies": ["花生"],
            },
        )

    assert get_response.status_code == 200
    assert get_response.json()["data"]["allergies"] == ["花生"]
    assert put_response.status_code == 200
    assert put_response.json()["data"]["health_conditions"] == [
        "hypertension",
        "allergy",
    ]
