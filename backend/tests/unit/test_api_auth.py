from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException, Request

from me4brain.api.middleware.auth import (
    AuthenticatedUser,
    TokenPayload,
    decode_token,
    get_current_user,
    get_optional_user,
    require_role,
    require_tenant,
)


@pytest.fixture
def mock_settings():
    with patch("me4brain.api.middleware.auth.get_settings") as mock:
        settings = MagicMock()
        settings.keycloak_client_id = "test-client"
        mock.return_value = settings
        yield settings


def test_decode_token_success(mock_settings):
    payload = {"sub": "user_123", "tenant_id": "tenant_1", "exp": 2000000000, "azp": "test-client"}
    token = jwt.encode(payload, "secret", algorithm="HS256")

    with patch("me4brain.api.middleware.auth.jwt.decode", return_value=payload):
        result = decode_token(token, "public_key")
        assert result.sub == "user_123"
        assert result.tenant_id == "tenant_1"


def test_decode_token_expired(mock_settings):
    with patch("me4brain.api.middleware.auth.jwt.decode", side_effect=jwt.ExpiredSignatureError()):
        with pytest.raises(HTTPException) as exc:
            decode_token("expired-token", "key")
        assert exc.value.status_code == 401
        assert "expired" in exc.value.detail.lower()


def test_decode_token_invalid(mock_settings):
    """Test token malformato o invalido."""
    with patch(
        "me4brain.api.middleware.auth.jwt.decode",
        side_effect=jwt.InvalidTokenError("Invalid token"),
    ):
        with pytest.raises(HTTPException) as exc:
            decode_token("malformed-token", "key")
        assert exc.value.status_code == 401
        assert "invalid" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_get_current_user(mock_settings):
    request = MagicMock(spec=Request)
    request.state = MagicMock()
    credentials = MagicMock()
    credentials.credentials = "valid-token"

    payload = TokenPayload(sub="u1", tenant_id="t1", exp=2000000000, roles=["admin"])

    with (
        patch("me4brain.api.middleware.auth.get_keycloak_public_key", return_value="key"),
        patch("me4brain.api.middleware.auth.decode_token", return_value=payload),
    ):
        user = await get_current_user(request, credentials)
        assert user.user_id == "u1"
        assert user.tenant_id == "t1"
        assert "admin" in user.roles


@pytest.mark.asyncio
async def test_get_current_user_no_credentials(mock_settings):
    """Test 401 quando non viene fornito token."""
    request = MagicMock(spec=Request)

    with pytest.raises(HTTPException) as exc:
        await get_current_user(request, credentials=None)

    assert exc.value.status_code == 401
    assert "not authenticated" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_get_optional_user_no_token(mock_settings):
    """Test che optional user ritorna None senza token."""
    request = MagicMock(spec=Request)

    result = await get_optional_user(request, credentials=None)

    assert result is None


@pytest.mark.asyncio
async def test_get_optional_user_with_valid_token(mock_settings):
    """Test che optional user ritorna user con token valido."""
    request = MagicMock(spec=Request)
    request.state = MagicMock()
    credentials = MagicMock()
    credentials.credentials = "valid-token"

    payload = TokenPayload(sub="u1", tenant_id="t1", exp=2000000000, roles=["user"])

    with (
        patch("me4brain.api.middleware.auth.get_keycloak_public_key", return_value="key"),
        patch("me4brain.api.middleware.auth.decode_token", return_value=payload),
    ):
        result = await get_optional_user(request, credentials)
        assert result is not None
        assert result.user_id == "u1"


@pytest.mark.asyncio
async def test_require_role_forbidden(mock_settings):
    """Test 403 quando ruolo richiesto non presente."""
    user = AuthenticatedUser(user_id="u1", tenant_id="t1", roles=["user"])

    role_checker = require_role("admin")

    with patch(
        "me4brain.api.middleware.auth.get_current_user",
        return_value=user,
    ):
        # Chiamiamo direttamente il checker interno
        with pytest.raises(HTTPException) as exc:
            await role_checker(user=user)

        assert exc.value.status_code == 403
        assert "admin" in exc.value.detail


@pytest.mark.asyncio
async def test_require_role_success(mock_settings):
    """Test che il ruolo corretto passa."""
    user = AuthenticatedUser(user_id="u1", tenant_id="t1", roles=["admin"])

    role_checker = require_role("admin")

    result = await role_checker(user=user)
    assert result.user_id == "u1"


@pytest.mark.asyncio
async def test_require_tenant_forbidden(mock_settings):
    """Test 403 quando tenant non corrisponde."""
    user = AuthenticatedUser(user_id="u1", tenant_id="tenant_a", roles=["user"])

    tenant_checker = require_tenant("tenant_b")

    with pytest.raises(HTTPException) as exc:
        await tenant_checker(user=user)

    assert exc.value.status_code == 403
    assert "tenant" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_require_tenant_super_admin_bypass(mock_settings):
    """Test che super_admin bypassa il check tenant."""
    user = AuthenticatedUser(user_id="u1", tenant_id="tenant_a", roles=["super_admin"])

    tenant_checker = require_tenant("tenant_b")

    result = await tenant_checker(user=user)
    assert result.user_id == "u1"
