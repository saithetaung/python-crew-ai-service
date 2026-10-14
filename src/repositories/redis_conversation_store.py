import json
from redis.asyncio import Redis


class RedisConversationStore:
    """Stores Bedrock session IDs and a bounded application-side transcript."""

    def __init__(self, redis: Redis, ttl_seconds: int, max_qa_pairs: int,
                 lock_timeout_seconds: int = 180, lock_wait_seconds: int = 5):
        self.redis = redis
        self.ttl_seconds = ttl_seconds
        self.max_messages = max_qa_pairs * 2
        self.lock_timeout_seconds = lock_timeout_seconds
        self.lock_wait_seconds = lock_wait_seconds

    @staticmethod
    def base_key(user_id: str, conversation_id: str) -> str:
        return f"marineon:chat:{user_id}:{conversation_id}"

    async def get_bedrock_session_id(self, key: str) -> str | None:
        return await self.redis.get(f"{key}:bedrock-session")

    async def set_bedrock_session_id(self, key: str, session_id: str) -> None:
        await self.redis.set(f"{key}:bedrock-session", session_id, ex=self.ttl_seconds)

    async def load_messages(self, key: str) -> list[dict[str, str]]:
        values = await self.redis.lrange(f"{key}:history", -self.max_messages, -1)
        messages = []
        for raw in values:
            try:
                item = json.loads(raw)
                if item.get("role") in {"user", "assistant"} and isinstance(item.get("content"), str):
                    messages.append({"role": item["role"], "content": item["content"]})
            except (ValueError, AttributeError):
                continue
        return messages

    async def save_completed_turn(self, key: str, question: str, answer: str) -> None:
        history_key = f"{key}:history"
        values = [
            json.dumps({"role": "user", "content": question}, ensure_ascii=False),
            json.dumps({"role": "assistant", "content": answer}, ensure_ascii=False),
        ]
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.rpush(history_key, *values)
            pipe.ltrim(history_key, -self.max_messages, -1)
            pipe.expire(history_key, self.ttl_seconds)
            await pipe.execute()

    def conversation_lock(self, key: str):
        return self.redis.lock(
            f"{key}:lock",
            timeout=self.lock_timeout_seconds,
            blocking_timeout=self.lock_wait_seconds,
        )

    async def clear(self, key: str) -> None:
        await self.redis.delete(
            key,
            f"{key}:history",
            f"{key}:bedrock-session",
        )
