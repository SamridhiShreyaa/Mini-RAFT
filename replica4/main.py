import os
from fastapi import FastAPI

app = FastAPI()

PORT = int(os.getenv("PORT", 3002))

@app.get("/state")
def state():
    return {"state": "follower"}

@app.get("/status")
def status():
    return {
        "node": f"follower-{PORT}",
        "state": "follower"
    }

@app.post("/client_request")
def request(data: dict):
    print(f"[FOLLOWER {PORT}] Forwarding:", data)
    return {"message": "forwarded"}