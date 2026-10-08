from app.core.config import Settings


def test_empty_temperature_means_none(monkeypatch):
    monkeypatch.setenv("LLM_TEMPERATURE", "")
    assert Settings().llm_temperature is None


def test_api_keys_split_and_secret_not_printed():
    s = Settings(service_api_keys=" a , b,,")
    assert s.api_keys == {"a", "b"}
    assert "a , b" not in repr(s)          # SecretStr: nilai rahasia tidak ikut tercetak
