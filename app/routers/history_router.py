from fastapi import APIRouter, HTTPException, Depends
from typing import List
from app.models.data import HistoryItem
from app.core.database import get_db
from bson import ObjectId
from datetime import datetime

router = APIRouter(prefix="/history", tags=["history"])

@router.get("/", response_model=List[HistoryItem])
async def get_history(limit: int = 20):
    db = get_db()
    cursor = db["history"].find().sort("created_at", -1).limit(limit)
    history = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        # Ensure config_used exists for older docs if any
        if "config_used" not in doc and doc.get("articles"):
            doc["config_used"] = doc["articles"][0].get("config_used")
        history.append(HistoryItem(**doc))
    return history

# Editor History Endpoints
@router.get("/editor", response_model=List[HistoryItem])
async def get_editor_history(limit: int = 20):
    db = get_db()
    cursor = db["editor_history"].find().sort("created_at", -1).limit(limit)
    history = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        if "config_used" not in doc and doc.get("articles"):
            doc["config_used"] = doc["articles"][0].get("config_used")
        history.append(HistoryItem(**doc))
    return history

@router.delete("/editor/clear")
async def clear_editor_history():
    db = get_db()
    await db["editor_history"].delete_many({})
    return {"status": "success"}

@router.get("/{history_id}", response_model=HistoryItem)
async def get_history_item(history_id: str):
    db = get_db()
    try:
        doc = await db["history"].find_one({"_id": ObjectId(history_id)})
        if not doc:
            raise HTTPException(status_code=404, detail="History item not found")
        doc["_id"] = str(doc["_id"])
        # Ensure config_used exists
        if "config_used" not in doc and doc.get("articles"):
            doc["config_used"] = doc["articles"][0].get("config_used")
        return HistoryItem(**doc)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid ID format or item not found")

@router.delete("/{history_id}")
async def delete_history(history_id: str):
    db = get_db()
    try:
        res = await db["history"].delete_one({"_id": ObjectId(history_id)})
        if res.deleted_count == 0:
            raise HTTPException(status_code=404, detail="History item not found")
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid ID format")

@router.delete("/clear")
async def clear_history():
    db = get_db()
    await db["history"].delete_many({})
    return {"status": "success"}

@router.put("/{history_id}")
async def update_history(history_id: str, update_data: dict):
    db = get_db()
    try:
        # Remove _id from update_data if present
        if "_id" in update_data:
            del update_data["_id"]
        
        res = await db["history"].update_one(
            {"_id": ObjectId(history_id)},
            {"$set": update_data}
        )
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail="History item not found")
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

