from fastapi import FastAPI, HTTPException, Header, Depends
import httpx
from typing import Optional, Dict, Any
from app.schemas import Workflow

app = FastAPI(title="n8n Orchestrator WAN", version="1.1.1")

@app.get("/health")
async def health_check():
    return {"status": "ok"}

async def get_n8n_client(
    x_n8n_api_key: str = Header(None, description="n8n API Key"),
    n8n_host: str = Header(default="http://localhost:5678", description="n8n Host URL")
):
    headers = {"Accept": "application/json"}
    if x_n8n_api_key:
        headers["X-N8n-Api-Key"] = x_n8n_api_key
    return {"host": n8n_host, "headers": headers}

@app.get("/workflows")
async def get_workflows(client_info: dict = Depends(get_n8n_client)):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{client_info['host']}/api/v1/workflows", headers=client_info["headers"])
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        return response.json()

@app.post("/workflows")
async def create_workflow(workflow: Workflow, client_info: dict = Depends(get_n8n_client)):
    """
    Creates a new workflow in n8n.
    The payload is strictly validated against the Workflow schema to prevent 'empty nodes'.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{client_info['host']}/api/v1/workflows",
            json=workflow.model_dump(exclude={"active"}, exclude_unset=True),
            headers=client_info["headers"]
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        return response.json()

@app.put("/workflows/{workflow_id}")
async def update_workflow(workflow_id: str, workflow: Workflow, client_info: dict = Depends(get_n8n_client)):
    async with httpx.AsyncClient() as client:
        response = await client.put(
            f"{client_info['host']}/api/v1/workflows/{workflow_id}",
            json=workflow.model_dump(exclude={"active"}, exclude_unset=True),
            headers=client_info["headers"]
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        return response.json()

@app.post("/workflows/{workflow_id}/activate")
async def activate_workflow(workflow_id: str, client_info: dict = Depends(get_n8n_client)):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{client_info['host']}/api/v1/workflows/{workflow_id}/activate",
            headers=client_info["headers"]
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        return response.json()

@app.post("/workflows/{workflow_id}/deactivate")
async def deactivate_workflow(workflow_id: str, client_info: dict = Depends(get_n8n_client)):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{client_info['host']}/api/v1/workflows/{workflow_id}/deactivate",
            headers=client_info["headers"]
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        return response.json()

@app.post("/executions/{workflow_id}")
async def trigger_execution(workflow_id: str, client_info: dict = Depends(get_n8n_client)):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{client_info['host']}/api/v1/executions",
            json={"workflowId": workflow_id},
            headers=client_info["headers"]
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        return response.json()

@app.get("/executions/{execution_id}")
async def get_execution(execution_id: str, client_info: dict = Depends(get_n8n_client)):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{client_info['host']}/api/v1/executions/{execution_id}",
            headers=client_info["headers"]
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        return response.json()
