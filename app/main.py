import os
import uuid
import jwt
import httpx
import logging
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Request, Depends
from pydantic import BaseModel
from app.schemas import Workflow

logger = logging.getLogger("n8n-skill")
app = FastAPI(title="n8n Orchestrator WAN", version="1.3.1")

NODE_TYPE_ALIASES = {
    "nodes.none": "n8n-nodes-base.noOp",
    "none": "n8n-nodes-base.noOp",
    "noop": "n8n-nodes-base.noOp",
    "noOp": "n8n-nodes-base.noOp",
    "webhook": "n8n-nodes-base.webhook",
    "schedule": "n8n-nodes-base.scheduleTrigger",
}

def sanitize_nodes(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ensure all nodes have valid n8n types, IDs, positions, and parameters."""
    sanitized = []
    for idx, raw_node in enumerate(nodes):
        node = dict(raw_node)
        raw_type = str(node.get("type", ""))
        node["type"] = NODE_TYPE_ALIASES.get(raw_type, raw_type)

        if not node.get("id"):
            node["id"] = str(uuid.uuid4())

        pos = node.get("position")
        if not isinstance(pos, list) or len(pos) < 2:
            node["position"] = [250.0, 300.0 + (idx * 100.0)]

        if not node.get("typeVersion"):
            node["typeVersion"] = 1
        if not isinstance(node.get("parameters"), dict):
            node["parameters"] = {}

        sanitized.append(node)
    return sanitized

def has_trigger_node(nodes: List[Dict[str, Any]]) -> bool:
    """Check if the node list contains at least one trigger node."""
    for node in nodes:
        ntype = str(node.get("type", "")).lower()
        if "trigger" in ntype or "webhook" in ntype or "poll" in ntype:
            return True
    return False

def get_n8n_host() -> str:
    return os.getenv("N8N_HOST", os.getenv("n8n-host", "http://host.docker.internal:5678")).rstrip("/")

def get_n8n_api_key() -> str:
    return os.getenv("N8N_API_KEY", os.getenv("X-N8n-Api-Key", ""))

def get_jwt_secret() -> Optional[str]:
    return os.getenv("JWT_SECRET")

async def verify_jwt(request: Request):
    jwt_secret = get_jwt_secret()
    if not jwt_secret:
        return
    auth_header = request.headers.get("X-Internal-Auth")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    try:
        return jwt.decode(auth_header, jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

def get_n8n_headers():
    headers = {"Accept": "application/json"}
    api_key = get_n8n_api_key()
    if api_key:
        headers["X-N8n-Api-Key"] = api_key
    return headers

def parse_n8n_error(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict):
            return data.get("message") or data.get("detail") or data.get("errorMessage") or resp.text
        return str(data)
    except Exception:
        return resp.text

@app.get("/health")
async def health_check():
    return {"status": "ok"}

class WorkflowIdRequest(BaseModel):
    workflow_id: str

class UpdateWorkflowRequest(BaseModel):
    workflow_id: str
    name: Optional[str] = None
    nodes: Optional[List[Dict[str, Any]]] = None
    connections: Optional[Dict[str, Any]] = None
    settings: Optional[Dict[str, Any]] = None

class TriggerExecutionRequest(BaseModel):
    workflow_id: str
    payload: Optional[Dict[str, Any]] = None

class ExecutionIdRequest(BaseModel):
    execution_id: str

@app.post("/get_workflows", dependencies=[Depends(verify_jwt)])
async def get_workflows():
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.get(f"{get_n8n_host()}/api/v1/workflows", headers=get_n8n_headers())
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=parse_n8n_error(resp))
            return resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to n8n at {get_n8n_host()}: {exc}")

@app.post("/create_workflow", dependencies=[Depends(verify_jwt)])
async def create_workflow(workflow: Workflow):
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.post(
                f"{get_n8n_host()}/api/v1/workflows",
                json=workflow.model_dump(exclude={"active"}, exclude_unset=True),
                headers=get_n8n_headers()
            )
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=parse_n8n_error(resp))
            return resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to n8n: {exc}")

@app.post("/update_workflow", dependencies=[Depends(verify_jwt)])
async def update_workflow(payload: UpdateWorkflowRequest):
    """Update workflow with smart merge, node sanitization, and active-state protection."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        # 1. Fetch existing workflow
        try:
            get_resp = await client.get(
                f"{get_n8n_host()}/api/v1/workflows/{payload.workflow_id}",
                headers=get_n8n_headers()
            )
            if get_resp.status_code >= 400:
                raise HTTPException(status_code=get_resp.status_code, detail=parse_n8n_error(get_resp))
            existing_wf = get_resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to n8n: {exc}")

        # 2. Merge and sanitize
        name = payload.name if payload.name is not None else existing_wf.get("name", "Untitled")
        raw_nodes = payload.nodes if payload.nodes is not None else existing_wf.get("nodes", [])
        nodes = sanitize_nodes(raw_nodes)

        connections = payload.connections if payload.connections is not None else existing_wf.get("connections")
        if not isinstance(connections, dict):
            connections = {}

        settings = payload.settings if payload.settings is not None else existing_wf.get("settings")
        if not isinstance(settings, dict):
            settings = {}

        is_currently_active = bool(existing_wf.get("active"))
        will_have_trigger = has_trigger_node(nodes)

        # 3. If an active workflow is updated without a trigger, deactivate it first so n8n doesn't reject the PUT
        if is_currently_active and not will_have_trigger:
            unpub_resp = await client.post(
                f"{get_n8n_host()}/api/v1/workflows/{payload.workflow_id}/unpublish",
                headers=get_n8n_headers()
            )
            if unpub_resp.status_code in (404, 405):
                await client.post(
                    f"{get_n8n_host()}/api/v1/workflows/{payload.workflow_id}/deactivate",
                    headers=get_n8n_headers()
                )

        body: Dict[str, Any] = {
            "name": name,
            "nodes": nodes,
            "connections": connections,
            "settings": settings,
        }

        # 4. PUT merged workflow
        try:
            resp = await client.put(
                f"{get_n8n_host()}/api/v1/workflows/{payload.workflow_id}",
                json=body,
                headers=get_n8n_headers()
            )
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=parse_n8n_error(resp))
            return resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to n8n: {exc}")

@app.post("/activate_workflow", dependencies=[Depends(verify_jwt)])
async def activate_workflow(payload: WorkflowIdRequest):
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            # In n8n 2.x, activation is done via /publish. Fallback to /activate for 1.x if needed.
            resp = await client.post(
                f"{get_n8n_host()}/api/v1/workflows/{payload.workflow_id}/publish",
                headers=get_n8n_headers()
            )
            if resp.status_code in (404, 405):
                resp = await client.post(
                    f"{get_n8n_host()}/api/v1/workflows/{payload.workflow_id}/activate",
                    headers=get_n8n_headers()
                )
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=parse_n8n_error(resp))
            return resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to n8n: {exc}")

@app.post("/deactivate_workflow", dependencies=[Depends(verify_jwt)])
async def deactivate_workflow(payload: WorkflowIdRequest):
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            # In n8n 2.x, deactivation is done via /unpublish. Fallback to /deactivate for 1.x if needed.
            resp = await client.post(
                f"{get_n8n_host()}/api/v1/workflows/{payload.workflow_id}/unpublish",
                headers=get_n8n_headers()
            )
            if resp.status_code in (404, 405):
                resp = await client.post(
                    f"{get_n8n_host()}/api/v1/workflows/{payload.workflow_id}/deactivate",
                    headers=get_n8n_headers()
                )
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=parse_n8n_error(resp))
            return resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to n8n: {exc}")

@app.post("/trigger_execution", dependencies=[Depends(verify_jwt)])
async def trigger_execution(payload: TriggerExecutionRequest):
    """Trigger workflow via Webhook node, inspecting both activeVersion and draft nodes."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Fetch workflow definition
        try:
            wf_resp = await client.get(
                f"{get_n8n_host()}/api/v1/workflows/{payload.workflow_id}",
                headers=get_n8n_headers()
            )
            if wf_resp.status_code >= 400:
                raise HTTPException(status_code=wf_resp.status_code, detail=parse_n8n_error(wf_resp))
            workflow_data = wf_resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to n8n: {exc}")

        # 2. Search for Webhook node across activeVersion and draft nodes
        nodes_to_search = []
        if isinstance(workflow_data.get("activeVersion"), dict):
            nodes_to_search.extend(workflow_data["activeVersion"].get("nodes", []))
        nodes_to_search.extend(workflow_data.get("nodes", []))

        webhook_node = None
        for node in nodes_to_search:
            node_type = str(node.get("type", ""))
            if node_type == "n8n-nodes-base.webhook" or "webhook" in node_type.lower():
                webhook_node = node
                break

        if not webhook_node:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Workflow '{payload.workflow_id}' cannot be triggered: no Webhook node found. "
                    "In n8n, workflows must contain a Webhook node (n8n-nodes-base.webhook) "
                    "to be triggered on demand via API."
                )
            )

        parameters = webhook_node.get("parameters", {})
        path = parameters.get("path") or webhook_node.get("webhookId")
        if not path:
            raise HTTPException(
                status_code=400,
                detail=f"Webhook node in workflow '{payload.workflow_id}' has no path configured."
            )

        # 3. Ensure workflow is active so n8n registers the webhook URL
        if not workflow_data.get("active"):
            pub_resp = await client.post(
                f"{get_n8n_host()}/api/v1/workflows/{payload.workflow_id}/publish",
                headers=get_n8n_headers()
            )
            if pub_resp.status_code in (404, 405):
                await client.post(
                    f"{get_n8n_host()}/api/v1/workflows/{payload.workflow_id}/activate",
                    headers=get_n8n_headers()
                )

        # 4. Dispatch request to webhook URL
        path = str(path).lstrip("/")
        webhook_url = f"{get_n8n_host()}/webhook/{path}"
        http_method = parameters.get("httpMethod", "POST").upper()
        req_payload = payload.payload or {}

        try:
            if http_method == "GET" and not req_payload:
                trigger_resp = await client.get(webhook_url, headers=get_n8n_headers())
            else:
                trigger_resp = await client.post(webhook_url, json=req_payload, headers=get_n8n_headers())

            if trigger_resp.status_code >= 400:
                raise HTTPException(status_code=trigger_resp.status_code, detail=parse_n8n_error(trigger_resp))

            try:
                hook_data = trigger_resp.json()
            except Exception:
                hook_data = {"message": trigger_resp.text}

            return {
                "status": "triggered",
                "workflow_id": payload.workflow_id,
                "webhook_path": path,
                "response": hook_data
            }
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to trigger webhook at {webhook_url}: {exc}")

@app.post("/get_execution", dependencies=[Depends(verify_jwt)])
async def get_execution(payload: ExecutionIdRequest):
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.get(
                f"{get_n8n_host()}/api/v1/executions/{payload.execution_id}",
                headers=get_n8n_headers()
            )
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=parse_n8n_error(resp))
            return resp.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to n8n: {exc}")
