import os
from fastapi import FastAPI

app = FastAPI()

PORT = int(os.getenv("PORT", 3001))

@app.get("/state")
def state():
    return {"state": "leader"}

@app.get("/status")
def status():
    return {
        "node": f"leader-{PORT}",
        "state": "leader"
    }

@app.post("/client_request")
def request(data: dict):
    print(f"[LEADER] Received:", data)
    return {"message": "handled by leader"}