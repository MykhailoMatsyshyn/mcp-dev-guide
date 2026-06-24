import json
import logging
from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer
from fastapi.responses import JSONResponse
from scalekit import ScalekitClient
from scalekit.common.scalekit import TokenValidationOptions
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Security scheme for Bearer token
security = HTTPBearer()

# Initialize ScaleKit client
scalekit_client = ScalekitClient(
    settings.SCALEKIT_ENVIRONMENT_URL,
    settings.SCALEKIT_CLIENT_ID,
    settings.SCALEKIT_CLIENT_SECRET
)

# Authentication middleware
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/.well-known/"):
            return await call_next(request)

        try:
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

            token = auth_header.split(" ")[1]

            request_body = await request.body()
            
            # Parse JSON from bytes
            try:
                request_data = json.loads(request_body.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                request_data = {}
            
            # Accept the audience with or without a trailing slash, since the
            # value issued in the token can differ from the registered one.
            _aud = settings.SCALEKIT_AUDIENCE_NAME.rstrip("/")
            validation_options = TokenValidationOptions(
              issuer=settings.SCALEKIT_ENVIRONMENT_URL,
              audience=[_aud, _aud + "/"],
            )
            
            is_tool_call = request_data.get("method") == "tools/call"
            
            required_scopes = []
            if is_tool_call:
                required_scopes = ["search:read"] # get required scope for your tool
                validation_options.required_scopes = required_scopes  
            
            try:
                scalekit_client.validate_token(token, options=validation_options)

            except Exception as e:
                # Surface the real reason: decode the token (no signature check)
                # so the logs show the actual aud/iss/scope vs. what we expect.
                try:
                    import jwt
                    claims = jwt.decode(token, options={"verify_signature": False})
                    logger.error(
                        "Token validation failed: %s | token aud=%r iss=%r scope=%r | expected aud in %r iss=%r",
                        e, claims.get("aud"), claims.get("iss"),
                        claims.get("scope") or claims.get("scopes"),
                        validation_options.audience, settings.SCALEKIT_ENVIRONMENT_URL,
                    )
                except Exception as decode_err:
                    logger.error("Token validation failed: %s (could not decode token: %s)", e, decode_err)
                raise HTTPException(status_code=401, detail="Token validation failed")

        except HTTPException as e:
            return JSONResponse(
                status_code=e.status_code,
                content={"error": "unauthorized" if e.status_code == 401 else "forbidden", "error_description": e.detail},
                headers={
                    "WWW-Authenticate": f'Bearer realm="OAuth", resource_metadata="{settings.SCALEKIT_RESOURCE_METADATA_URL}"'
                }
            )

        return await call_next(request)