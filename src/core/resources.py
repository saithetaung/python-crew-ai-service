
import boto3
from botocore.config import Config
from redis.asyncio import Redis

from src.core.config import Settings
from src.providers.bedrock_rag_client import BedrockRagClient
from src.providers.bedrock_tool_client import BedrockToolClient
from src.repositories.redis_conversation_store import (
    RedisConversationStore,
)
from src.services.chat_service import ChatService


class Resources:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.redis = None
        self.bedrock_client = None
        self.bedrock_runtime_client = None
        self.tool_client = None
        self.chat_service = None

    async def start(self):
        self.redis = Redis.from_url(
            self.settings.redis_url.get_secret_value(),
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=10,
            health_check_interval=30,
        )
        await self.redis.ping()

        # Create the AWS session before either Bedrock client.
        session = boto3.Session(
            region_name=self.settings.aws_region
        )

        bedrock_config = Config(
            connect_timeout=3,
            read_timeout=90,
            retries={
                "max_attempts": 3,
                "mode": "standard",
            },
        )

        # Existing Knowledge Base RetrieveAndGenerate client.
        self.bedrock_client = session.client(
            "bedrock-agent-runtime",
            config=bedrock_config,
        )

        # Converse client for custom tool calling.
        self.bedrock_runtime_client = session.client(
            "bedrock-runtime",
            config=bedrock_config,
        )

        store = RedisConversationStore(
            redis=self.redis,
            ttl_seconds=self.settings.chat_memory_ttl_seconds,
            max_qa_pairs=self.settings.chat_memory_max_qa_pairs,
            lock_timeout_seconds=self.settings.chat_lock_timeout_seconds,
            lock_wait_seconds=self.settings.chat_lock_wait_seconds,
        )

        rag = BedrockRagClient(
            client=self.bedrock_client,
            knowledge_base_id=self.settings.knowledge_base_id,
            model_arn=self.settings.model_arn,
        )

        self.tool_client = BedrockToolClient(
            client=self.bedrock_runtime_client,
            model_id=self.settings.model_arn,
        )

        self.chat_service = ChatService(
            settings=self.settings,
            store=store,
            rag=rag,
            tool_client=self.tool_client,
        )

    async def close(self):
        if self.redis is not None:
            await self.redis.aclose()
