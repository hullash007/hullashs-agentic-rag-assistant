import os

# Set test configuration before importing application modules.
os.environ["LLM_PROVIDER"] = "mock"
os.environ["GEMINI_API_KEY"] = ""
os.environ["GEMINI_MODEL"] = ""
os.environ["GEMINI_TIMEOUT_MS"] = "15000"
os.environ["GEMINI_MAX_OUTPUT_TOKENS"] = "128"


import socket
import pytest


@pytest.fixture(autouse=True)
def block_outbound_network(monkeypatch):
    """Prevent tests from making outbound socket or DNS requests."""
    def blocked(*args, **kwargs):
        raise RuntimeError("Outbound network access is disabled during tests.")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket.socket, "sendto", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
