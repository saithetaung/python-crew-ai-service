# Ship Crew AI Service

Online-only FastAPI + Amazon Bedrock + Bedrock Knowledge Bases + Redis.
Spring Boot remains a separate service and is the only gateway to business data.

## Run locally
1. Copy `.env.example` to `.env` and configure AWS/Bedrock/Redis/Spring Boot values.
2. `python -m venv .venv`
3. Activate the venv, then `pip install -r requirements.txt`
4. `docker compose up -d redis`
5. `uvicorn src.app:app --reload`
6. Check `/health/live` and `/health/ready`.

Call `POST /internal/v1/chat` only from authenticated Spring Boot service code, never directly from the browser.
This is a production-oriented starter scaffold: finish the security, deployment, and integration-test checklist before production use.
