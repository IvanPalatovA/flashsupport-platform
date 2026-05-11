import asyncio
import time

import pytest

from domain import ContextChunkEntity
from infrastructure.config import Settings
from services import InferenceQueueFullError, QueuedInferenceService


class FakeBackend:
    def __init__(self, delay_seconds: float = 0.0) -> None:
        self.delay_seconds = delay_seconds
        self.calls: int = 0

    def infer(
        self,
        *,
        instruction: str,
        contexts: list[ContextChunkEntity],
        temperature: float | None,
        top_p: float | None,
        max_tokens: int | None,
    ) -> tuple[str, str]:
        _ = instruction
        _ = contexts
        _ = temperature
        _ = top_p
        _ = max_tokens

        self.calls += 1
        if self.delay_seconds > 0:
            time.sleep(self.delay_seconds)
        return "generated answer", "fake-model"


class FakeIdentityProvider:
    def __init__(self) -> None:
        self.calls: int = 0

    def get_service_access_token(self) -> str:
        self.calls += 1
        return "service-token"


def build_settings(*, queue_capacity: int = 8, wait_timeout: float = 3.0) -> Settings:
    return Settings(
        app_name="llm-runtime",
        env="test",
        host="0.0.0.0",
        port=8100,
        log_level="INFO",
        ollama_base_url="http://localhost:11434",
        llm_model_name="llama3.1:8b",
        llm_system_prompt="You are a test assistant",
        llm_temperature=0.2,
        llm_top_p=0.9,
        llm_max_tokens=512,
        ollama_request_timeout_seconds=30,
        max_concurrent_inferences=1,
        inference_queue_capacity=queue_capacity,
        inference_wait_timeout_seconds=wait_timeout,
        enforce_service_identity=True,
        auth_service_url="http://localhost:8070",
        auth_public_key_path="config/keys/auth/public.pem",
        auth_token_issuer="flashsupport-auth-service",
        user_access_token_audience="flashsupport-services",
        incoming_service_token_audience="rag-service",
        allowed_caller_service_ids=["rag-service", "chat-orchestrator"],
        service_id="llm-runtime",
        service_private_key_path="config/keys/services/llm-runtime.private.pem",
        service_token_audience="rag-service",
        service_assertion_audience="auth-service",
        service_assertion_ttl_seconds=60,
        service_token_refresh_skew_seconds=60,
        clock_skew_seconds=10,
    )


def test_inference_service_returns_result_and_checks_identity() -> None:
    async def scenario() -> None:
        backend = FakeBackend()
        identity_provider = FakeIdentityProvider()
        service = QueuedInferenceService(
            settings=build_settings(),
            backend=backend,
            service_identity_provider=identity_provider,
        )

        request_id, result = await service.infer(
            request_id="req-1",
            instruction="How to reset password?",
            contexts=[
                ContextChunkEntity(
                    chunk_id=1,
                    document_id=10,
                    document_title="Password reset",
                    chunk_index=0,
                    score=0.9,
                    text="Open profile and click reset password",
                )
            ],
        )

        assert request_id == "req-1"
        assert result.answer == "generated answer"
        assert result.model == "fake-model"
        assert identity_provider.calls == 1
        assert backend.calls == 1

        await service.shutdown()

    asyncio.run(scenario())


def test_inference_service_rejects_when_queue_is_full() -> None:
    async def scenario() -> None:
        backend = FakeBackend(delay_seconds=0.2)
        identity_provider = FakeIdentityProvider()
        service = QueuedInferenceService(
            settings=build_settings(queue_capacity=1, wait_timeout=5.0),
            backend=backend,
            service_identity_provider=identity_provider,
        )

        task_1 = asyncio.create_task(service.infer(instruction="first", contexts=[]))
        await asyncio.sleep(0.02)
        task_2 = asyncio.create_task(service.infer(instruction="second", contexts=[]))

        for _ in range(20):
            if service.queue_depth() >= 1:
                break
            await asyncio.sleep(0.01)

        with pytest.raises(InferenceQueueFullError):
            await service.infer(instruction="third", contexts=[])

        await task_1
        await task_2

        await service.shutdown()

    asyncio.run(scenario())
