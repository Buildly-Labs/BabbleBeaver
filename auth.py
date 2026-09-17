"""
Simple API Key Authentication for BabbleBeaver.
Supports both environment variable token (legacy) and database-backed tokens.
"""

import os
from typing import Optional
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from token_manager import token_manager

# Legacy API key from environment (optional, for backward compatibility)
API_KEY = os.getenv("API_KEY")

# Admin credentials from environment
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")

# Whether public-facing inference endpoints (e.g. /chatbot) require a bearer token.
# Defaults to false so existing callers aren't broken until they're updated to send one.
REQUIRE_CHATBOT_AUTH = os.getenv("REQUIRE_CHATBOT_AUTH", "false").lower() == "true"

# HTTP Bearer token scheme
security = HTTPBearer()
# Same scheme, but doesn't error when the header is missing (used where auth is optional)
optional_security = HTTPBearer(auto_error=False)


def verify_admin_credentials(username: str, password: str) -> bool:
    """Verify admin username and password against environment variables."""
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD


async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    """
    Dependency to verify API key from bearer token.
    Checks environment variable first (priority), then database.
    
    Args:
        credentials: HTTP authorization credentials
        
    Returns:
        User info dict
        
    Raises:
        HTTPException: If authentication fails
    """
    token = credentials.credentials
    
    # PRIORITY 1: Check environment variable token (if configured)
    if API_KEY and token == API_KEY:
        return {"authenticated": True, "type": "api_key", "sub": "env_token"}
    
    # PRIORITY 2: Check database tokens
    if token_manager.verify_token(token):
        return {"authenticated": True, "type": "api_key", "sub": "api_access"}
    
    # Both checks failed
    raise HTTPException(
        status_code=401,
        detail="Invalid or expired API token"
    )


def verify_token(token: str) -> dict:
    """
    Verify a token synchronously (for non-FastAPI contexts like static file serving).
    
    Args:
        token: The API token to verify
        
    Returns:
        User info dict
        
    Raises:
        HTTPException: If authentication fails
    """
    # Check environment variable token first
    if API_KEY and token == API_KEY:
        return {"authenticated": True, "type": "api_key", "sub": "env_token"}
    
    # Check database tokens
    if token_manager.verify_token(token):
        return {"authenticated": True, "type": "api_key", "sub": "api_access"}
    
    raise HTTPException(
        status_code=401,
        detail="Invalid or expired API token"
    )


async def require_admin(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    """
    Dependency to require admin API key authentication.
    Same as get_current_user for simple API key auth.
    
    Args:
        credentials: HTTP authorization credentials
        
    Returns:
        User info dict
        
    Raises:
        HTTPException: If authentication fails
    """
    return await get_current_user(credentials)


async def require_chatbot_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(optional_security)
) -> Optional[dict]:
    """
    Dependency for public-facing inference endpoints (e.g. /chatbot).

    Enforces bearer-token auth only when REQUIRE_CHATBOT_AUTH=true, so callers
    can be migrated onto tokens before the check is turned on. When disabled,
    requests pass through unauthenticated regardless of whether a token is sent.

    Raises:
        HTTPException: If auth is required and the token is missing or invalid
    """
    if not REQUIRE_CHATBOT_AUTH:
        return None

    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    return await get_current_user(credentials)
