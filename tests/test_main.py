import pytest
import jwt
import httpx
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.main import app, get_n8n_headers, get_n8n_host

client = TestClient(app)

SAMPLE_WORKFLOW_PAYLOAD = {
    "name": "Test Workflow",
    "nodes": [
        {
            "id": "node-1",
            "name": "Start",
            "type": "n8n-nodes-base.manualTrigger",
            "typeVersion": 1,
            "position": [100.0, 200.0],
            "parameters": {}
        }
    ],
    "connections": {},
    "settings": {},
    "active": False
}


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_jwt_verification(monkeypatch):
    secret = "super-secret-jwt-key-with-at-least-32-bytes!"
    monkeypatch.setenv("JWT_SECRET", secret)

    # 1. Missing header -> 401
    res = client.post("/get_workflows")
    assert res.status_code == 401
    assert "Missing authorization header" in res.json()["detail"]

    # 2. Invalid token -> 401
    res = client.post("/get_workflows", headers={"X-Internal-Auth": "invalid.jwt.token"})
    assert res.status_code == 401
    assert "Invalid token" in res.json()["detail"]

    # 3. Valid token
    valid_token = jwt.encode({"sub": "isli-agent"}, secret, algorithm="HS256")
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = httpx.Response(200, json={"data": []})
        res = client.post("/get_workflows", headers={"X-Internal-Auth": valid_token})
        assert res.status_code == 200
        assert res.json() == {"data": []}


def test_get_workflows(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")
    monkeypatch.setenv("N8N_API_KEY", "test-api-key")

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = httpx.Response(200, json=[{"id": "wf-1", "name": "Flow 1"}])
        res = client.post("/get_workflows", json={})
        assert res.status_code == 200
        assert res.json() == [{"id": "wf-1", "name": "Flow 1"}]
        
        # Verify URL and headers
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert args[0] == "http://n8n.internal:5678/api/v1/workflows"
        assert kwargs["headers"]["X-N8n-Api-Key"] == "test-api-key"


def test_create_workflow(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(201, json={"id": "new-wf-1", "name": "Test Workflow"})
        res = client.post("/create_workflow", json=SAMPLE_WORKFLOW_PAYLOAD)
        assert res.status_code == 200
        assert res.json() == {"id": "new-wf-1", "name": "Test Workflow"}

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://n8n.internal:5678/api/v1/workflows"
        # Ensure active was stripped
        assert "active" not in kwargs["json"]
        assert kwargs["json"]["name"] == "Test Workflow"


def test_update_workflow(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")

    payload = {
        "workflow_id": "wf-999",
        "name": "Updated Flow",
        "nodes": [
            {
                "id": "node-1",
                "name": "Start",
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "position": [0, 0],
                "parameters": {}
            }
        ],
        "connections": {},
        "settings": {}
    }

    with patch("httpx.AsyncClient.put", new_callable=AsyncMock) as mock_put:
        mock_put.return_value = httpx.Response(200, json={"id": "wf-999", "name": "Updated Flow"})
        res = client.post("/update_workflow", json=payload)
        assert res.status_code == 200
        assert res.json()["name"] == "Updated Flow"

        mock_put.assert_called_once()
        args, kwargs = mock_put.call_args
        assert args[0] == "http://n8n.internal:5678/api/v1/workflows/wf-999"
        assert "workflow_id" not in kwargs["json"]
        assert kwargs["json"]["name"] == "Updated Flow"


def test_activate_workflow(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(200, json={"active": True})
        res = client.post("/activate_workflow", json={"workflow_id": "wf-123"})
        assert res.status_code == 200
        assert res.json() == {"active": True}

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://n8n.internal:5678/api/v1/workflows/wf-123/activate"


def test_deactivate_workflow(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(200, json={"active": False})
        res = client.post("/deactivate_workflow", json={"workflow_id": "wf-123"})
        assert res.status_code == 200
        assert res.json() == {"active": False}

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://n8n.internal:5678/api/v1/workflows/wf-123/deactivate"


def test_trigger_execution(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(200, json={"id": "exec-456", "status": "running"})
        res = client.post("/trigger_execution", json={"workflow_id": "wf-123"})
        assert res.status_code == 200
        assert res.json() == {"id": "exec-456", "status": "running"}

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://n8n.internal:5678/api/v1/executions"
        assert kwargs["json"] == {"workflowId": "wf-123"}


def test_get_execution(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = httpx.Response(200, json={"id": "exec-456", "status": "success"})
        res = client.post("/get_execution", json={"execution_id": "exec-456"})
        assert res.status_code == 200
        assert res.json() == {"id": "exec-456", "status": "success"}

        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert args[0] == "http://n8n.internal:5678/api/v1/executions/exec-456"


def test_n8n_upstream_error_propagation(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = httpx.Response(404, text="Workflow not found")
        res = client.post("/get_workflows")
        assert res.status_code == 404
        assert "Workflow not found" in res.json()["detail"]


def test_n8n_connection_error(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.ConnectError("Connection refused")
        res = client.post("/get_workflows")
        assert res.status_code == 502
        assert "Failed to connect to n8n" in res.json()["detail"]
