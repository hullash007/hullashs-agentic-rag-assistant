import logging
import socket

import pytest
from fastapi.testclient import TestClient

from apps.api import main


def test_socket_connect_is_blocked():
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(RuntimeError, match="Outbound network access is disabled"):
            connection.connect(("127.0.0.1", 1))
    finally:
        connection.close()


def test_socket_connect_ex_is_blocked():
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(RuntimeError, match="Outbound network access is disabled"):
            connection.connect_ex(("127.0.0.1", 1))
    finally:
        connection.close()


def test_dns_resolution_is_blocked():
    with pytest.raises(RuntimeError, match="Outbound network access is disabled"):
        socket.getaddrinfo("example.invalid", 443)


def test_create_connection_is_blocked():
    with pytest.raises(RuntimeError, match="Outbound network access is disabled"):
        socket.create_connection(("127.0.0.1", 1))


@pytest.mark.parametrize(
    ("exception", "expected_status"),
    [
        (RuntimeError("PRIVATE_RUNTIME_EXCEPTION_CONTENT"), 503),
        (Exception("PRIVATE_GENERIC_EXCEPTION_CONTENT"), 502),
    ],
)
def test_api_does_not_log_exception_content_or_prompt(
    monkeypatch, caplog, exception, expected_status
):
    prompt = "PRIVATE_REQUEST_PROMPT_CONTENT"

    def fail_invoke(*args, **kwargs):
        raise exception

    monkeypatch.setattr(main.agent, "invoke", fail_invoke)
    caplog.set_level(logging.INFO, logger="apps.api.main")

    response = TestClient(main.app).post(
        "/chat",
        json={"message": prompt},
    )

    assert response.status_code == expected_status
    assert prompt not in caplog.text
    assert str(exception) not in caplog.text
    assert "Traceback" not in caplog.text
    assert type(exception).__name__ in caplog.text
