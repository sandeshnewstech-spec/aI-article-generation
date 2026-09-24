from fastapi import APIRouter, HTTPException, Depends
from typing import List
from pydantic import BaseModel
from app.models.data import HistoryItem
from app.core.database import get_db
from bson import ObjectId
from datetime import datetime

router = APIRouter(prefix="/history", tags=["history"])

@router.get("/", response_model=List[HistoryItem])
async def get_history(limit: int = 1000):
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

class PaginatedHistoryResponse(BaseModel):
    items: List[HistoryItem]
    total: int
    page: int
    limit: int
    total_pages: int

# Editor History Endpoints
@router.get("/editor", response_model=PaginatedHistoryResponse)
async def get_editor_history(page: int = 1, limit: int = 10, search: str = ""):
    from math import ceil
    db = get_db()
    
    query = {}
    if search:
        # Assuming we might want to search by topic or headline if they exist inside articles
        # A full text search could be complex in MongoDB without a text index, 
        # but let's do a basic regex on nested properties if needed, 
        # or just fallback to simple username search for now.
        import re
        search_regex = re.compile(search, re.IGNORECASE)
        or_conditions = [
            {"username": search_regex},
            {"created_by_name": search_regex},
            {"topic": search_regex},
            {"articles.headline": search_regex},
            {"config_used.topic": search_regex},
            {"status": search_regex}
        ]
        
        try:
            from dateutil.parser import parse as parse_date
            parsed_date = parse_date(search)
            start_date = parsed_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = parsed_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            or_conditions.append({"created_at": {"$gte": start_date, "$lte": end_date}})
        except Exception:
            pass
        
        if "draft" in search.lower():
            or_conditions.append({"status": {"$exists": False}})
            or_conditions.append({"status": None})
            
        if "admin" in search.lower():
            or_conditions.append({"username": {"$exists": False}})
            or_conditions.append({"username": None})
            or_conditions.append({"created_by_name": {"$exists": False}})
            or_conditions.append({"created_by_name": None})
            
        query = {"$or": or_conditions}
        
    total = await db["editor_history"].count_documents(query)
    skip = (page - 1) * limit
    
    cursor = db["editor_history"].find(query).sort("created_at", -1).skip(skip).limit(limit)
    history = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        if "config_used" not in doc and doc.get("articles"):
            doc["config_used"] = doc["articles"][0].get("config_used")
        history.append(HistoryItem(**doc))
        
    return PaginatedHistoryResponse(
        items=history,
        total=total,
        page=page,
        limit=limit,
        total_pages=ceil(total / limit) if limit > 0 else 1
    )

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
            doc = await db["editor_history"].find_one({"_id": ObjectId(history_id)})
        if not doc:
            raise HTTPException(status_code=404, detail="History item not found")
        doc["_id"] = str(doc["_id"])
        # Ensure config_used exists
        if "config_used" not in doc and doc.get("articles"):
            doc["config_used"] = doc["articles"][0].get("config_used")
        return HistoryItem(**doc)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid ID format or item not found")

@router.delete("/{history_id}")
async def delete_history(history_id: str):
    db = get_db()
    try:
        res = await db["history"].delete_one({"_id": ObjectId(history_id)})
        if res.deleted_count == 0:
            res = await db["editor_history"].delete_one({"_id": ObjectId(history_id)})
        if res.deleted_count == 0:
            raise HTTPException(status_code=404, detail="History item not found")
        return {"status": "success"}
    except HTTPException as he:
        raise he
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
        
        # Try updating in 'history' first
        res = await db["history"].update_one(
            {"_id": ObjectId(history_id)},
            {"$set": update_data}
        )
        
        # If not found in 'history', try 'editor_history'
        if res.matched_count == 0:
            res = await db["editor_history"].update_one(
                {"_id": ObjectId(history_id)},
                {"$set": update_data}
            )
            
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail="History item not found in any collection")
            
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

