"""FastAPI Starter — Production-ready API server

Features:
- Health check endpoint
- CORS middleware
- Structured logging
- Example CRUD endpoints (in-memory store)
"""

import os
import logging
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Config
PORT = int(os.environ.get("PORT", "8000"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "info")

logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger("fastapi-starter")

app = FastAPI(title="Berth FastAPI Starter", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store
items: dict[str, dict] = {}


class Item(BaseModel):
    name: str
    description: str = ""
    price: float = 0.0


@app.get("/health")
def health():
    return {"status": "ok", "items_count": len(items)}


@app.get("/items")
def list_items():
    return {"items": list(items.values())}


@app.get("/items/{item_id}")
def get_item(item_id: str):
    if item_id not in items:
        raise HTTPException(status_code=404, detail="Item not found")
    return items[item_id]


@app.post("/items", status_code=201)
def create_item(item: Item):
    import uuid
    item_id = str(uuid.uuid4())[:8]
    record = {"id": item_id, **item.model_dump()}
    items[item_id] = record
    logger.info(f"Created item {item_id}: {item.name}")
    return record


@app.delete("/items/{item_id}")
def delete_item(item_id: str):
    if item_id not in items:
        raise HTTPException(status_code=404, detail="Item not found")
    del items[item_id]
    logger.info(f"Deleted item {item_id}")
    return {"deleted": item_id}


if __name__ == "__main__":
    print(f"Starting FastAPI server on port {PORT}...")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level=LOG_LEVEL)
