"""
OAuth2 + SAML Bearer Token Exchange Layer
==========================================
Flow:
  1. Frontend sends a session JWT (mocked as base64-encoded employee ID for now).
  2. FastAPI validates the incoming token.
  3. FastAPI performs an OAuth2SAMLBearer token exchange with the Identity Provider (IDP)
     to mint a short-lived SAP-specific access token.
  4. The SAP token is injected per-request into the query_sap_odata tool.
  
Real-world IDP endpoints to configure:
  - IDP_TOKEN_URL: e.g. https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token
  - SAP_ODATA_BASE_URL: e.g. https://{sap-host}/sap/opu/odata/sap/
  - SAP_SAML_ISSUER: The SAML2 issuer configured in SAP transaction SAML2 / SU01 user mapping
"""

import base64
import json
import time
import httpx
from fastapi import HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# ── Placeholder constants (replace with real IDP/SAP config) ─────────────────
IDP_TOKEN_URL = "[IDP_TOKEN_URL_PLACEHOLDER]"          # e.g. Azure AD token endpoint
IDP_CLIENT_ID = "[IDP_CLIENT_ID_PLACEHOLDER]"
IDP_CLIENT_SECRET = "[IDP_CLIENT_SECRET_PLACEHOLDER]"
SAP_ODATA_SCOPE = "[SAP_ODATA_SCOPE_PLACEHOLDER]"      # e.g. api://{sap-client-id}/.default
SAP_AUTH_TOKEN_PLACEHOLDER = "[SAP_AUTH_TOKEN_PLACEHOLDER]"

# Whether we are running in mock mode (no real IDP available)
MOCK_AUTH = True

bearer_scheme = HTTPBearer(auto_error=True)


def decode_mock_token(token: str) -> dict:
    """
    Decodes the mock Base64 session token issued by our login page.
    Returns a dict with { employee_id, issued_at }.
    In production, this is replaced by a real JWT verification (e.g. python-jose).
    """
    try:
        padded = token + "=" * (-len(token) % 4)
        decoded = base64.b64decode(padded).decode("utf-8")
        payload = json.loads(decoded)
        # Validate expiry (mock tokens are valid for 8 hours)
        if time.time() - payload.get("iat", 0) > 28800:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
        return payload
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token. Please log in again."
        )


async def exchange_for_sap_token(user_token: str, employee_id: str) -> str:
    """
    OAuth2 On-Behalf-Of (OBO) / SAML Bearer Token Exchange.
    
    Sends the user's JWT to the IDP and requests a SAP-scoped access token.
    The IDP uses the SAML assertion to map the UPN to the SAP named user (SU01).
    
    SAP side config required:
      - Transaction SAML2: Configure your IDP as a trusted provider
      - Transaction SU01: Map IDP UPN to SAP username
      - SAP OAuth2 client: Register with grant_type=urn:ietf:params:oauth:grant-type:saml2-bearer
    """
    if MOCK_AUTH:
        # Mock: return a signed placeholder token scoped to the employee
        return f"MOCK_SAP_TOKEN_FOR_{employee_id}_{int(time.time())}"

    # Real OAuth2 SAML Bearer exchange (uncomment when IDP is configured)
    # async with httpx.AsyncClient() as client:
    #     resp = await client.post(IDP_TOKEN_URL, data={
    #         "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
    #         "client_id": IDP_CLIENT_ID,
    #         "client_secret": IDP_CLIENT_SECRET,
    #         "assertion": user_token,
    #         "scope": SAP_ODATA_SCOPE,
    #         "requested_token_use": "on_behalf_of",
    #     })
    #     resp.raise_for_status()
    #     return resp.json()["access_token"]

    raise HTTPException(status_code=501, detail="IDP not configured. Set MOCK_AUTH=True or configure IDP_TOKEN_URL.")


def validate_and_extract(credentials: HTTPAuthorizationCredentials) -> dict:
    """
    Validates the incoming Bearer token and returns the decoded user context.
    In production: verify signature with IDP public key (JWKS endpoint).
    """
    token = credentials.credentials
    return decode_mock_token(token)
