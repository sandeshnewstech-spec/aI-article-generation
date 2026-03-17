from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from bson import ObjectId
from app.core.database import get_db

router = APIRouter(prefix="/slots", tags=["Slots"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fix_id(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc


# ── Schemas ───────────────────────────────────────────────────────────────────

class SlotCreate(BaseModel):
    name: str
    column_span: int = 3
    slot_count: int = 1
    description: Optional[str] = ""
    is_active: bool = True
    wc_headline: int = 10
    wc_intro: int = 70
    wc_body: int = 170


class SlotUpdate(BaseModel):
    name: Optional[str] = None
    column_span: Optional[int] = None
    slot_count: Optional[int] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    wc_headline: Optional[int] = None
    wc_intro: Optional[int] = None
    wc_body: Optional[int] = None


# ── CRUD: Slots ───────────────────────────────────────────────────────────────

@router.get("/", summary="List all slots")
async def list_slots():
    db = get_db()
    docs = await db["slots"].find().to_list(length=None)
    return [_fix_id(d) for d in docs]


@router.post("/", summary="Create a new slot", status_code=201)
async def create_slot(payload: SlotCreate):
    db = get_db()
    # Validate ranges
    if not (1 <= payload.column_span <= 8):
        raise HTTPException(status_code=400, detail="column_span must be between 1 and 8")
    if not (1 <= payload.slot_count <= 4):
        raise HTTPException(status_code=400, detail="slot_count must be between 1 and 4")
    data = payload.dict()
    result = await db["slots"].insert_one(data)
    new_doc = await db["slots"].find_one({"_id": result.inserted_id})
    return _fix_id(new_doc)


@router.get("/{slot_id}", summary="Get a single slot")
async def get_slot(slot_id: str):
    db = get_db()
    doc = await db["slots"].find_one({"_id": ObjectId(slot_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Slot not found")
    return _fix_id(doc)


@router.put("/{slot_id}", summary="Update a slot")
async def update_slot(slot_id: str, payload: SlotUpdate):
    db = get_db()
    update_data = {k: v for k, v in payload.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    # Validate ranges if provided
    if "column_span" in update_data and not (1 <= update_data["column_span"] <= 8):
        raise HTTPException(status_code=400, detail="column_span must be between 1 and 8")
    if "slot_count" in update_data and not (1 <= update_data["slot_count"] <= 4):
        raise HTTPException(status_code=400, detail="slot_count must be between 1 and 4")
    result = await db["slots"].update_one(
        {"_id": ObjectId(slot_id)},
        {"$set": update_data}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Slot not found")
    doc = await db["slots"].find_one({"_id": ObjectId(slot_id)})
    return _fix_id(doc)


@router.delete("/{slot_id}", summary="Delete a slot")
async def delete_slot(slot_id: str):
    db = get_db()
    result = await db["slots"].delete_one({"_id": ObjectId(slot_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Slot not found")
    return {"message": "Slot deleted successfully"}
