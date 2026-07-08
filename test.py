import httpx
import asyncio
import json

API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZTUwMTIxMS1iYmYyLTRjYTQtOTE3OC02ZGFlMGI1NjBjMDQiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiZTdmNGM2OTktNjc4NS00ZDE0LWI4NmQtYzY3ZmFhYmQwMzgzIiwiaWF0IjoxNzgzMzA1NzUwLCJleHAiOjE3OTEwNzIwMDB9.ThLUJrqdQpr50w3rOlM2BTV3VN82ncbttENsV2gRmmw"
PROXY_URL = "http://127.0.0.1:8000/workflows"

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
    print("Testing Workflow Creation via n8n-orchestrator-wan proxy...")
    async with httpx.AsyncClient() as client:
        res = await client.post(
            PROXY_URL,
            json=workflow_payload,
            headers={
                "X-N8n-Api-Key": API_KEY,
                "n8n-host": "http://127.0.0.1:5678"
            }
        )
        print(f"Status Code: {res.status_code}")
        print(f"Response: {json.dumps(res.json(), indent=2)}")

if __name__ == "__main__":
    asyncio.run(run())
