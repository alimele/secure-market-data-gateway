import os
import logging
import jwt
from fastapi import HTTPException, status

_JWT_SECRET = os.getenv("JWT_SECRET", "demo-secret-key-not-for-production")
_JWT_ALGORITHM = "HS256"
_JWT_AUDIENCE = "adx-demo-gateway"
_JWT_ISSUER = "adx-demo-idp"
_REQUIRED_CLAIMS = {"sub", "role", "entitlements", "exp", "aud"}


def validate_jwt(token: str) -> dict:
    """Validate a HS256 JWT and return its claims. Raises HTTPException on any failure.

    Checks performed (all mandatory — fail closed on any error):
      - Signature verification (HS256, key from JWT_SECRET env var)
      - Expiry (exp claim)
      - Audience (must be adx-demo-gateway)
      - Issuer (must be adx-demo-idp)
      - Required claims presence: sub, role, entitlements, exp, aud
    """
    try:
        claims = jwt.decode(
            token,
            _JWT_SECRET,
            algorithms=[_JWT_ALGORITHM],
            audience=_JWT_AUDIENCE,
            issuer=_JWT_ISSUER,
            options={"require": list(_REQUIRED_CLAIMS)},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"reason_code": "TOKEN_EXPIRED", "message": "Token has expired"},
        )
    except jwt.InvalidAudienceError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"reason_code": "TOKEN_AUDIENCE_INVALID", "message": "Invalid token audience"},
        )
    except jwt.InvalidIssuerError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"reason_code": "TOKEN_AUDIENCE_INVALID", "message": "Invalid token issuer"},
        )
    except jwt.DecodeError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"reason_code": "TOKEN_INVALID", "message": "Token could not be decoded"},
        )
    except jwt.MissingRequiredClaimError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"reason_code": "TOKEN_INVALID", "message": "Token is missing required claims"},
        )
    except Exception:
        logging.exception("Unexpected error during JWT validation")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"reason_code": "POLICY_UNAVAILABLE", "message": "Policy service unavailable"},
        )
    return claims
