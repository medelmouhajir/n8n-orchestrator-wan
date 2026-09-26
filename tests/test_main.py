import pytest
import jwt
import httpx
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.main import app, get_n8n_headers, get_n8n_host, sanitize_nodes, has_trigger_node

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


def test_update_workflow_smart_merge(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")

    existing_wf = {
        "id": "wf-999",
        "name": "Original Name",
        "nodes": [{"id": "n1", "name": "Start", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "position": [0, 0], "parameters": {}}],
        "connections": {"Start": {"main": [[{"node": "Next", "type": "main", "index": 0}]]}},
        "settings": {"saveExecutionProgress": True},
        "active": False
    }

    # Partial update: changing only name
    partial_payload = {
        "workflow_id": "wf-999",
        "name": "Updated Name Only"
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
         patch("httpx.AsyncClient.put", new_callable=AsyncMock) as mock_put:
        mock_get.return_value = httpx.Response(200, json=existing_wf)
        mock_put.return_value = httpx.Response(200, json={"id": "wf-999", "name": "Updated Name Only"})

        res = client.post("/update_workflow", json=partial_payload)
        assert res.status_code == 200
        assert res.json()["name"] == "Updated Name Only"

        # Verify GET was called to fetch existing state
        mock_get.assert_called_once()
        assert mock_get.call_args[0][0] == "http://n8n.internal:5678/api/v1/workflows/wf-999"

        # Verify PUT was called with merged body preserving existing nodes, connections, and settings
        args, kwargs = mock_put.call_args
        assert args[0] == "http://n8n.internal:5678/api/v1/workflows/wf-999"
        assert kwargs["json"]["name"] == "Updated Name Only"
        assert kwargs["json"]["nodes"] == existing_wf["nodes"]
        assert kwargs["json"]["connections"] == existing_wf["connections"]
        assert kwargs["json"]["settings"] == existing_wf["settings"]


def test_update_workflow_node_sanitization(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")

    existing_wf = {
        "id": "wf-raw",
        "name": "Raw Flow",
        "nodes": [],
        "connections": {},
        "settings": {},
        "active": False
    }

    raw_payload = {
        "workflow_id": "wf-raw",
        "nodes": [
            {
                "name": "Hallucinated NoOp",
                "type": "nodes.none"
                # Missing id, position, typeVersion, parameters
            }
        ]
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
         patch("httpx.AsyncClient.put", new_callable=AsyncMock) as mock_put:
        mock_get.return_value = httpx.Response(200, json=existing_wf)
        mock_put.return_value = httpx.Response(200, json={"id": "wf-raw"})

        res = client.post("/update_workflow", json=raw_payload)
        assert res.status_code == 200

        sanitized_node = mock_put.call_args[1]["json"]["nodes"][0]
        assert sanitized_node["type"] == "n8n-nodes-base.noOp"
        assert "id" in sanitized_node and len(sanitized_node["id"]) > 0
        assert sanitized_node["position"] == [250.0, 300.0]
        assert sanitized_node["typeVersion"] == 1
        assert sanitized_node["parameters"] == {}


def test_update_workflow_active_without_trigger_deactivates_first(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")

    existing_wf = {
        "id": "wf-active",
        "name": "Active Flow",
        "active": True,
        "nodes": [{"id": "t1", "name": "Trigger", "type": "n8n-nodes-base.scheduleTrigger"}],
        "connections": {},
        "settings": {}
    }

    # Replacing nodes with a noOp node (no trigger)
    update_payload = {
        "workflow_id": "wf-active",
        "nodes": [{"name": "Only Action", "type": "n8n-nodes-base.noOp"}]
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("httpx.AsyncClient.put", new_callable=AsyncMock) as mock_put:
        mock_get.return_value = httpx.Response(200, json=existing_wf)
        mock_post.return_value = httpx.Response(200, json={"active": False})
        mock_put.return_value = httpx.Response(200, json={"id": "wf-active"})

        res = client.post("/update_workflow", json=update_payload)
        assert res.status_code == 200

        # Verify unpublish was called before PUT
        mock_post.assert_called_once()
        assert mock_post.call_args[0][0] == "http://n8n.internal:5678/api/v1/workflows/wf-active/unpublish"
        mock_put.assert_called_once()


def test_update_workflow_guarantees_empty_objects(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")

    existing_wf = {
        "id": "wf-empty",
        "name": "Empty Flow",
        "nodes": [],
        "connections": None,
        "settings": None,
        "active": False
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
         patch("httpx.AsyncClient.put", new_callable=AsyncMock) as mock_put:
        mock_get.return_value = httpx.Response(200, json=existing_wf)
        mock_put.return_value = httpx.Response(200, json={"id": "wf-empty", "name": "Empty Flow"})

        res = client.post("/update_workflow", json={"workflow_id": "wf-empty"})
        assert res.status_code == 200

        put_kwargs = mock_put.call_args[1]
        assert isinstance(put_kwargs["json"]["connections"], dict)
        assert isinstance(put_kwargs["json"]["settings"], dict)


def test_activate_workflow_publish(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(200, json={"active": True})
        res = client.post("/activate_workflow", json={"workflow_id": "wf-123"})
        assert res.status_code == 200
        assert res.json() == {"active": True}

        # Should call /publish
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://n8n.internal:5678/api/v1/workflows/wf-123/publish"


def test_activate_workflow_fallback_to_activate(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [
            httpx.Response(404, json={"message": "Not found"}),
            httpx.Response(200, json={"active": True})
        ]
        res = client.post("/activate_workflow", json={"workflow_id": "wf-123"})
        assert res.status_code == 200
        assert res.json() == {"active": True}
        assert mock_post.call_count == 2
        assert mock_post.call_args_list[0][0][0] == "http://n8n.internal:5678/api/v1/workflows/wf-123/publish"
        assert mock_post.call_args_list[1][0][0] == "http://n8n.internal:5678/api/v1/workflows/wf-123/activate"


def test_activate_workflow_no_trigger_error_surfacing(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")

    error_msg = "Workflow cannot be activated because it has no trigger node. At least one trigger, webhook, or polling node is required."
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(400, json={"message": error_msg})
        res = client.post("/activate_workflow", json={"workflow_id": "wf-no-trigger"})
        assert res.status_code == 400
        assert res.json()["detail"] == error_msg


def test_deactivate_workflow_unpublish(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(200, json={"active": False})
        res = client.post("/deactivate_workflow", json={"workflow_id": "wf-123"})
        assert res.status_code == 200
        assert res.json() == {"active": False}

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://n8n.internal:5678/api/v1/workflows/wf-123/unpublish"


def test_deactivate_workflow_fallback_to_deactivate(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [
            httpx.Response(404, json={"message": "Not found"}),
            httpx.Response(200, json={"active": False})
        ]
        res = client.post("/deactivate_workflow", json={"workflow_id": "wf-123"})
        assert res.status_code == 200
        assert res.json() == {"active": False}
        assert mock_post.call_count == 2
        assert mock_post.call_args_list[0][0][0] == "http://n8n.internal:5678/api/v1/workflows/wf-123/unpublish"
        assert mock_post.call_args_list[1][0][0] == "http://n8n.internal:5678/api/v1/workflows/wf-123/deactivate"


def test_trigger_execution_via_webhook_active(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")

    workflow_with_webhook = {
        "id": "wf-hook",
        "name": "Webhook Flow",
        "active": True,
        "nodes": [
            {
                "id": "node-hook",
                "name": "Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 1,
                "position": [100, 200],
                "parameters": {
                    "path": "my-trigger-path",
                    "httpMethod": "POST"
                }
            }
        ]
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_get.return_value = httpx.Response(200, json=workflow_with_webhook)
        mock_post.return_value = httpx.Response(200, json={"message": "Workflow was started"})

        res = client.post("/trigger_execution", json={"workflow_id": "wf-hook", "payload": {"foo": "bar"}})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "triggered"
        assert data["webhook_path"] == "my-trigger-path"
        assert data["response"]["message"] == "Workflow was started"

        # Verify workflow was fetched
        mock_get.assert_called_once()
        assert mock_get.call_args[0][0] == "http://n8n.internal:5678/api/v1/workflows/wf-hook"

        # Verify webhook was called at /webhook/my-trigger-path with payload
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://n8n.internal:5678/webhook/my-trigger-path"
        assert kwargs["json"] == {"foo": "bar"}


def test_trigger_execution_finds_webhook_in_active_version(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")

    # Draft canvas only has NoOp, but activeVersion has Webhook
    workflow_data = {
        "id": "wf-v2",
        "name": "Versioned Flow",
        "active": True,
        "nodes": [
            {"id": "noop-1", "name": "NoOp", "type": "n8n-nodes-base.noOp"}
        ],
        "activeVersion": {
            "nodes": [
                {
                    "id": "hook-node",
                    "name": "Webhook",
                    "type": "n8n-nodes-base.webhook",
                    "parameters": {"path": "isli-probe-hook"}
                }
            ]
        }
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_get.return_value = httpx.Response(200, json=workflow_data)
        mock_post.return_value = httpx.Response(200, json={"message": "Workflow was started"})

        res = client.post("/trigger_execution", json={"workflow_id": "wf-v2"})
        assert res.status_code == 200
        assert res.json()["webhook_path"] == "isli-probe-hook"

        mock_post.assert_called_once()
        assert mock_post.call_args[0][0] == "http://n8n.internal:5678/webhook/isli-probe-hook"


def test_trigger_execution_auto_activates_if_inactive(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")

    workflow_inactive = {
        "id": "wf-inactive",
        "name": "Inactive Flow",
        "active": False,
        "nodes": [
            {
                "id": "hook-node",
                "name": "Webhook",
                "type": "n8n-nodes-base.webhook",
                "parameters": {"path": "inactive-hook"}
            }
        ]
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_get.return_value = httpx.Response(200, json=workflow_inactive)
        # First call is /publish, second call is /webhook/inactive-hook
        mock_post.side_effect = [
            httpx.Response(200, json={"active": True}),
            httpx.Response(200, json={"message": "Workflow was started"})
        ]

        res = client.post("/trigger_execution", json={"workflow_id": "wf-inactive"})
        assert res.status_code == 200
        assert res.json()["status"] == "triggered"

        # Verify publish was invoked first
        assert mock_post.call_count == 2
        assert mock_post.call_args_list[0][0][0] == "http://n8n.internal:5678/api/v1/workflows/wf-inactive/publish"
        assert mock_post.call_args_list[1][0][0] == "http://n8n.internal:5678/webhook/inactive-hook"


def test_trigger_execution_no_webhook_node(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")

    workflow_without_webhook = {
        "id": "wf-no-hook",
        "name": "Schedule Flow",
        "active": True,
        "nodes": [
            {
                "id": "node-1",
                "name": "Schedule Trigger",
                "type": "n8n-nodes-base.scheduleTrigger",
                "parameters": {}
            }
        ]
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = httpx.Response(200, json=workflow_without_webhook)
        res = client.post("/trigger_execution", json={"workflow_id": "wf-no-hook"})
        assert res.status_code == 400
        assert "no Webhook node found" in res.json()["detail"]


def test_trigger_execution_missing_path(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("N8N_HOST", "http://n8n.internal:5678")

    workflow_empty_webhook = {
        "id": "wf-bad-hook",
        "name": "Bad Webhook",
        "active": True,
        "nodes": [
            {
                "id": "node-hook",
                "name": "Webhook",
                "type": "n8n-nodes-base.webhook",
                "parameters": {}
            }
        ]
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = httpx.Response(200, json=workflow_empty_webhook)
        res = client.post("/trigger_execution", json={"workflow_id": "wf-bad-hook"})
        assert res.status_code == 400
        assert "no path configured" in res.json()["detail"]


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
        mock_get.return_value = httpx.Response(404, json={"message": "Workflow not found"})
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
