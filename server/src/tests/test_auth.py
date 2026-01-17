"""
Tests for authentication endpoints.

Covers:
- Registration (happy path, duplicates, validation)
- Login (happy path, wrong credentials)
- Security tests (SQL injection)
- Ban and timeout enforcement
"""

import pytest
from datetime import timedelta
from httpx import AsyncClient


class TestRegistration:
    """Tests for the /auth/register endpoint."""

    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient):
        """Valid registration should create a new player."""
        response = await client.post(
            "/auth/register",
            json={"username": "newplayer", "password": "securepass123"},
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "newplayer"
        assert "id" in data
        assert "password" not in data
        assert "hashed_password" not in data

    @pytest.mark.asyncio
    async def test_register_duplicate_username(self, client: AsyncClient, create_test_player):
        """Registration with an existing username should fail."""
        # Create a player first
        await create_test_player("existinguser", "password123")
        
        # Try to register with the same username
        response = await client.post(
            "/auth/register",
            json={"username": "existinguser", "password": "differentpass"},
        )
        
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_register_username_too_short(self, client: AsyncClient):
        """Username shorter than 3 characters should be rejected."""
        response = await client.post(
            "/auth/register",
            json={"username": "ab", "password": "validpassword"},
        )
        
        assert response.status_code == 422
        # Pydantic validation error

    @pytest.mark.asyncio
    async def test_register_username_too_long(self, client: AsyncClient):
        """Username longer than 50 characters should be rejected."""
        long_username = "a" * 51
        response = await client.post(
            "/auth/register",
            json={"username": long_username, "password": "validpassword"},
        )
        
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_empty_password(self, client: AsyncClient):
        """Empty password should be rejected."""
        response = await client.post(
            "/auth/register",
            json={"username": "validuser", "password": ""},
        )
        
        # Empty string may pass or fail depending on validation
        # At minimum, it should not create a user with empty password
        assert response.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_register_missing_fields(self, client: AsyncClient):
        """Missing required fields should be rejected."""
        # Missing password
        response = await client.post(
            "/auth/register",
            json={"username": "validuser"},
        )
        assert response.status_code == 422
        
        # Missing username
        response = await client.post(
            "/auth/register",
            json={"password": "validpassword"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_sql_injection_attempt(self, client: AsyncClient):
        """SQL injection in username should be safely handled."""
        malicious_username = "'; DROP TABLE players; --"
        response = await client.post(
            "/auth/register",
            json={"username": malicious_username, "password": "password123"},
        )
        
        # Should either reject due to validation or safely escape
        # Should NOT cause a 500 error
        assert response.status_code in (201, 400, 422)

    @pytest.mark.asyncio
    async def test_register_unicode_username(self, client: AsyncClient):
        """Unicode characters in username should be handled properly."""
        response = await client.post(
            "/auth/register",
            json={"username": "ユーザー名", "password": "password123"},
        )
        
        # Either accept unicode or reject gracefully
        assert response.status_code in (201, 400, 422)


class TestLogin:
    """Tests for the /auth/login endpoint."""

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, create_test_player):
        """Valid credentials should return a JWT token."""
        await create_test_player("loginuser", "correctpassword")
        
        response = await client.post(
            "/auth/login",
            data={"username": "loginuser", "password": "correctpassword"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient, create_test_player):
        """Wrong password should be rejected."""
        await create_test_player("loginuser2", "correctpassword")
        
        response = await client.post(
            "/auth/login",
            data={"username": "loginuser2", "password": "wrongpassword"},
        )
        
        assert response.status_code == 401
        assert "incorrect" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Login with non-existent username should fail."""
        response = await client.post(
            "/auth/login",
            data={"username": "nosuchuser", "password": "anypassword"},
        )
        
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_empty_credentials(self, client: AsyncClient):
        """Empty credentials should be rejected."""
        response = await client.post(
            "/auth/login",
            data={"username": "", "password": ""},
        )
        
        assert response.status_code in (401, 422)

    @pytest.mark.asyncio
    async def test_login_case_sensitivity(self, client: AsyncClient, create_test_player):
        """Username should be case-sensitive."""
        await create_test_player("CaseSensitive", "password123")
        
        # Try with different case
        response = await client.post(
            "/auth/login",
            data={"username": "casesensitive", "password": "password123"},
        )
        
        # Should fail if usernames are case-sensitive
        # or succeed if case-insensitive - just shouldn't error
        assert response.status_code in (200, 401)

    @pytest.mark.asyncio
    async def test_login_sql_injection_attempt(self, client: AsyncClient):
        """SQL injection in login should be safely handled."""
        response = await client.post(
            "/auth/login",
            data={
                "username": "' OR '1'='1",
                "password": "' OR '1'='1",
            },
        )
        
        # Should safely reject, not cause server error or bypass auth
        assert response.status_code in (401, 422)

    @pytest.mark.asyncio
    async def test_login_timing_attack_resistance(self, client: AsyncClient, create_test_player):
        """
        Login should not reveal whether username exists via timing.
        
        Note: This is a basic check. Real timing attack testing requires
        statistical analysis of many requests.
        """
        import uuid
        unique_username = f"timinguser_{uuid.uuid4().hex[:8]}"
        await create_test_player(unique_username, "password123")
        
        # Both should return 401, regardless of whether user exists
        response1 = await client.post(
            "/auth/login",
            data={"username": unique_username, "password": "wrongpassword"},
        )
        response2 = await client.post(
            "/auth/login",
            data={"username": "nonexistentuser_timing_test", "password": "wrongpassword"},
        )
        
        # Both should return the same error code and similar message
        assert response1.status_code == response2.status_code == 401


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Root endpoint should return OK status."""
        response = await client.get("/")
        
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_version_endpoint(self, client: AsyncClient):
        """Version endpoint should return version info."""
        response = await client.get("/version")
        
        assert response.status_code == 200
        assert "version" in response.json()


class TestBanAndTimeout:
    """Tests for ban and timeout enforcement during login."""

    @pytest.mark.asyncio
    async def test_login_banned_user(self, client: AsyncClient, create_test_player, set_player_banned):
        """Banned user cannot login."""
        await create_test_player("banneduser", "password123")
        await set_player_banned("banneduser")

        response = await client.post(
            "/auth/login",
            data={"username": "banneduser", "password": "password123"},
        )

        assert response.status_code == 403
        assert "banned" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_login_timed_out_user(self, client: AsyncClient, create_test_player, set_player_timeout):
        """Timed out user cannot login."""
        await create_test_player("timedoutuser", "password123")
        await set_player_timeout("timedoutuser", timedelta(hours=1))

        response = await client.post(
            "/auth/login",
            data={"username": "timedoutuser", "password": "password123"},
        )

        assert response.status_code == 403
        assert "timed out" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_login_expired_timeout_succeeds(self, client: AsyncClient, create_test_player, set_player_timeout):
        """User with expired timeout can login."""
        await create_test_player("expiredtimeout", "password123")
        # Set timeout to 1 hour in the past (already expired)
        await set_player_timeout("expiredtimeout", timedelta(hours=-1))

        response = await client.post(
            "/auth/login",
            data={"username": "expiredtimeout", "password": "password123"},
        )

        assert response.status_code == 200
        assert "access_token" in response.json()
