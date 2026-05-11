from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from domain import ContextChunkEntity, InferenceResultEntity
from infrastructure.config import Settings


class InferenceQueueFullError(RuntimeError):
    pass


class InferenceTimeoutError(RuntimeError):
    pass


class InferenceBackendError(RuntimeError):
    pass


class ServiceIdentityError(RuntimeError):
    pass


class LLMBackendPort(Protocol):
    def infer(
        self,
        *,
        instruction: str,
        contexts: list[ContextChunkEntity],
        temperature: float | None,
        top_p: float | None,
        max_tokens: int | None,
    ) -> tuple[str, str]:
        ...


class ServiceIdentityPort(Protocol):
    def get_service_access_token(self) -> str:
        ...


@dataclass(slots=True)
class _InferenceJob:
    request_id: str
    instruction: str
    contexts: list[ContextChunkEntity]
    temperature: float | None
    top_p: float | None
    max_tokens: int | None
    enqueued_at: float
    future: asyncio.Future[InferenceResultEntity]


class QueuedInferenceService:
    def __init__(
        self,
        *,
        settings: Settings,
        backend: LLMBackendPort,
        service_identity_provider: ServiceIdentityPort,
    ) -> None:
        self._settings = settings
        self._backend = backend
        self._service_identity_provider = service_identity_provider
        self._queue: asyncio.Queue[_InferenceJob] = asyncio.Queue(maxsize=settings.inference_queue_capacity)
        self._workers: list[asyncio.Task[None]] = []
        self._start_lock = asyncio.Lock()
        self._started = False

    @property
    def allowed_caller_service_ids(self) -> set[str]:
        return set(self._settings.allowed_caller_service_ids)

    def queue_depth(self) -> int:
        return self._queue.qsize()

    async def _ensure_started(self) -> None:
        if self._started:
            return

        async with self._start_lock:
            if self._started:
                return

            for worker_index in range(self._settings.max_concurrent_inferences):
                task = asyncio.create_task(self._worker_loop(worker_id=worker_index + 1))
                self._workers.append(task)

            self._started = True

    async def shutdown(self) -> None:
        if not self._workers:
            return

        for task in self._workers:
            task.cancel()

        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        self._started = False

    async def _ensure_service_identity(self) -> None:
        try:
            await asyncio.to_thread(self._service_identity_provider.get_service_access_token)
        except Exception as error:
            raise ServiceIdentityError("failed to authorize LLM Runtime in Auth Service") from error

    async def infer(
        self,
        *,
        instruction: str,
        contexts: list[ContextChunkEntity],
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        request_id: str | None = None,
    ) -> tuple[str, InferenceResultEntity]:
        await self._ensure_started()

        if self._settings.enforce_service_identity:
            await self._ensure_service_identity()

        final_request_id = request_id or str(uuid4())
        loop = asyncio.get_running_loop()
        future: asyncio.Future[InferenceResultEntity] = loop.create_future()
        job = _InferenceJob(
            request_id=final_request_id,
            instruction=instruction,
            contexts=contexts,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            enqueued_at=time.monotonic(),
            future=future,
        )

        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull as error:
            raise InferenceQueueFullError("inference queue is full") from error

        try:
            result = await asyncio.wait_for(future, timeout=self._settings.inference_wait_timeout_seconds)
        except asyncio.TimeoutError as error:
            future.cancel()
            raise InferenceTimeoutError("inference job timed out while waiting in queue") from error

        return final_request_id, result

    async def _worker_loop(self, worker_id: int) -> None:
        _ = worker_id
        while True:
            try:
                job = await self._queue.get()
            except asyncio.CancelledError:
                break

            started_at = time.monotonic()
            queue_wait_ms = int((started_at - job.enqueued_at) * 1000)

            try:
                answer, model = await asyncio.to_thread(
                    self._backend.infer,
                    instruction=job.instruction,
                    contexts=job.contexts,
                    temperature=job.temperature,
                    top_p=job.top_p,
                    max_tokens=job.max_tokens,
                )
                inference_ms = int((time.monotonic() - started_at) * 1000)
                if not job.future.cancelled():
                    job.future.set_result(
                        InferenceResultEntity(
                            answer=answer,
                            model=model,
                            queue_wait_ms=queue_wait_ms,
                            inference_ms=inference_ms,
                        )
                    )
            except Exception as error:
                if not job.future.cancelled():
                    message = str(error).strip() or "inference backend execution failed"
                    job.future.set_exception(InferenceBackendError(message))
            finally:
                self._queue.task_done()
