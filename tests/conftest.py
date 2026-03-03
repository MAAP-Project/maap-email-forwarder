import pytest


@pytest.fixture(autouse=True)
def config_env_vars(monkeypatch):
    monkeypatch.setenv("FROM_EMAIL", "from@example.com")
    monkeypatch.setenv("EMAIL_BUCKET", "test-bucket")
    monkeypatch.setenv(
        "FORWARD_MAPPING",
        '{"example@maap-project.org":["forward.address@maap-project.org"]}',
    )