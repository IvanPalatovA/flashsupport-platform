from infrastructure.config import Settings
from infrastructure.model_admin import ModelAdminError, ModelAdminService, RegisteredModel
from infrastructure.ollama_client import OllamaClientError


class FailingListBackend:
    def __init__(self) -> None:
        self.active_model = "llama3.1:8b"

    def list_models(self) -> list[str]:
        raise OllamaClientError("failed to query ollama model list")

    def get_active_model(self) -> str:
        return self.active_model

    def get_device(self) -> str:
        return "auto"

    def get_device_warning(self) -> str | None:
        return None

    def set_active_model(self, model_name: str) -> None:
        self.active_model = model_name

    def stop_model(self, model_name: str) -> None:
        _ = model_name


def build_settings() -> Settings:
    return Settings(
        app_name="llm-runtime",
        env="test",
        host="0.0.0.0",
        port=8100,
        log_level="INFO",
        ollama_base_url="http://localhost:11434",
        model_storage_dir="/tmp/flashsupport-models-test",
        llm_model_name="llama3.1:8b",
        llm_device="auto",
        llm_system_prompt="You are a test assistant",
        llm_temperature=0.2,
        llm_top_p=0.9,
        llm_max_tokens=512,
        ollama_request_timeout_seconds=30,
        max_concurrent_inferences=1,
        inference_queue_capacity=8,
        inference_wait_timeout_seconds=3.0,
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


def test_parse_tree_url_extracts_revision_and_path() -> None:
    service = ModelAdminService(
        settings=build_settings(),
        backend=FailingListBackend(),
    )

    repo_id, revision, file_path = service._parse_hf_url(
        "https://huggingface.co/Qwen/Qwen1.5-0.5B-Chat-GGUF/tree/main/qwen1_5-0_5b-chat-q4_0.gguf"
    )

    assert repo_id == "Qwen/Qwen1.5-0.5B-Chat-GGUF"
    assert revision == "main"
    assert file_path == "qwen1_5-0_5b-chat-q4_0.gguf"


def test_list_models_does_not_fail_when_ollama_is_unreachable() -> None:
    service = ModelAdminService(
        settings=build_settings(),
        backend=FailingListBackend(),
    )

    payload = service.list_models()

    assert payload["active_model"] == "llama3.1:8b"
    assert payload["models"] == []
    assert payload["download"]["status"] == "idle"


def test_resolve_repo_file_supports_safetensors() -> None:
    service = ModelAdminService(
        settings=build_settings(),
        backend=FailingListBackend(),
    )

    def fake_get(*args, **kwargs):  # type: ignore[no-untyped-def]
        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {
                    "siblings": [
                        {"rfilename": "config.json"},
                        {"rfilename": "model.safetensors", "size": 123},
                    ]
                }

        return FakeResponse()

    import infrastructure.model_admin as model_admin_module

    original_get = model_admin_module.httpx.get
    model_admin_module.httpx.get = fake_get
    try:
        file_path, size, model_format = service._resolve_repo_file("Qwen/Qwen1.5-0.5B", "main", None, None)
        assert file_path == "model.safetensors"
        assert size == 123
        assert model_format == "safetensors"
    finally:
        model_admin_module.httpx.get = original_get


def test_error_message_for_repo_without_supported_formats_is_actionable() -> None:
    service = ModelAdminService(
        settings=build_settings(),
        backend=FailingListBackend(),
    )

    def fake_get(*args, **kwargs):  # type: ignore[no-untyped-def]
        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {
                    "siblings": [
                        {"rfilename": "config.json"},
                        {"rfilename": "README.md"},
                    ]
                }

        return FakeResponse()

    import infrastructure.model_admin as model_admin_module

    original_get = model_admin_module.httpx.get
    model_admin_module.httpx.get = fake_get
    try:
        try:
            service._resolve_repo_file("some/repo", "main", None, None)
        except ModelAdminError as error:
            message = str(error)
            assert "some/repo" in message
            assert "no supported model files" in message
            assert ".gguf" in message
            assert ".safetensors" in message
        else:
            raise AssertionError("expected ModelAdminError")
    finally:
        model_admin_module.httpx.get = original_get


def test_activate_rejects_download_only_model() -> None:
    service = ModelAdminService(
        settings=build_settings(),
        backend=FailingListBackend(),
    )

    service._registered_models["Qwen--download-only"] = RegisteredModel(
        local_file="/tmp/model.safetensors",
        source="huggingface",
        model_format="safetensors",
        backend="manual",
        runnable=False,
    )

    try:
        service.activate_model("Qwen--download-only")
    except ModelAdminError as error:
        assert "cannot be activated in Ollama directly" in str(error)
    else:
        raise AssertionError("expected ModelAdminError")
