import logging
import httpx

logger = logging.getLogger(__name__)

class SpringBootToolError(Exception):
    pass

class SpringBootToolClient:
    def __init__(self, http: httpx.AsyncClient, base_url: str, execute_path: str, token: str):
        self.http = http
        self.url = base_url.rstrip("/") + "/" + execute_path.lstrip("/")
        self.token = token

    async def execute(self, *, tool_name: str, arguments: dict, actor: dict, request_id: str):
        if not self.token:
            raise SpringBootToolError("Spring Boot API credentials are not configured")
        try:
            response = await self.http.post(
                self.url,
                json={"requestId": request_id, "tool": tool_name, "arguments": arguments, "actor": actor},
                headers={"Authorization": f"Bearer {self.token}", "X-Request-ID": request_id},
            )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError("Expected object result")
            return result
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Spring Boot tool API failed; request_id=%s", request_id)
            raise SpringBootToolError("Business data is unavailable") from exc
