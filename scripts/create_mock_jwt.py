
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from dotenv import load_dotenv

# Project root: python-crew-ai-service/
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"

# Explicitly load the project's .env file.
load_dotenv(ENV_FILE, override=False)

SECRET = os.getenv("JWT_SECRET")
ISSUER = os.getenv("JWT_ISSUER", "marineon-test-auth")
AUDIENCE = os.getenv("JWT_AUDIENCE", "marineon-ai")

if not SECRET:
    raise SystemExit(
        f"JWT_SECRET is missing. Check this file: {ENV_FILE}"
    )

now = datetime.now(timezone.utc)

claims = {
    "sub": "user-123",
    "name": "MarineOn Test User",
    "role": "CREW_MANAGER",
    "iss": ISSUER,
    "aud": AUDIENCE,
    "iat": now,
    "exp": now + timedelta(minutes=15),
}

token = jwt.encode(
    claims,
    SECRET,
    algorithm="HS256",
)

print("Mock JWT generated successfully. Expires in 15 minutes.")
print(token)
