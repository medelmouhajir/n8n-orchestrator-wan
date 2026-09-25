import os
import httpx
import asyncio
import json

# Optionally provide JWT_SECRET if testing with auth enabled
JWT_SECRET = os.getenv("JWT_SECRET")
PROXY_URL = "http://127.0.0.1:8000/create_workflow"

workflow_payload = {
    "name": "Test Workflow from ISLI Skill",
    "nodes": [
        {
            "id": "node-1",
            "name": "Start",
            "type": "n8n-nodes-base.manualTrigger",
            "typeVersion": 1,
            "position": [250, 300],
            "parameters": {}
        }
    ],
    "connections": {},
    "settings": {},
    "active": False
}

async def run():
    print("Testing Workflow Creation via n8n-orchestrator-wan proxy (/create_workflow)...")
    headers = {"Content-Type": "application/json"}
    if JWT_SECRET:
        import jwt
        token = jwt.encode({"sub": "test-user"}, JWT_SECRET, algorithm="HS256")
        headers["X-Internal-Auth"] = token

    async with httpx.AsyncClient() as client:
        res = await client.post(
            PROXY_URL,
            json=workflow_payload,
            headers=headers
        )
        print(f"Status Code: {res.status_code}")
        print(f"Response: {json.dumps(res.json(), indent=2)}")

if __name__ == "__main__":
    asyncio.run(run())
