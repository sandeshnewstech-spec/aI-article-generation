from fastapi import APIRouter, HTTPException
from typing import List
from bson import ObjectId
from app.core.database import get_db
from app.models.advt import AdvtCategoryCreate, AdvtCategoryUpdate

router = APIRouter(prefix="/advt-categories", tags=["ADVT Categories"])

def _fix_id(doc: dict) -> dict:
    """Convert ObjectId to string for JSON serialisation."""
    if doc and "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc

@router.get("/", summary="List all ADVT categories")
async def list_advt_categories():
    db = get_db()
    docs = await db["advt_categories"].find().to_list(length=None)
    return [_fix_id(d) for d in docs]

@router.get("/{category_id}", summary="Get a single ADVT category")
async def get_advt_category(category_id: str):
    db = get_db()
    if not ObjectId.is_valid(category_id):
        raise HTTPException(status_code=400, detail="Invalid ID format")
    doc = await db["advt_categories"].find_one({"_id": ObjectId(category_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Category not found")
    return _fix_id(doc)

@router.post("/", summary="Create a new ADVT category", status_code=201)
async def create_advt_category(payload: AdvtCategoryCreate):
    db = get_db()
    
    # Check if category with same name exists
    existing = await db["advt_categories"].find_one({"name": {"$regex": f"^{payload.name}$", "$options": "i"}})
    if existing:
        raise HTTPException(status_code=400, detail="Category with this name already exists")
        
    doc = payload.model_dump()
    result = await db["advt_categories"].insert_one(doc)
    doc["_id"] = result.inserted_id
    return _fix_id(doc)

@router.put("/{category_id}", summary="Update an ADVT category")
async def update_advt_category(category_id: str, payload: AdvtCategoryUpdate):
    db = get_db()
    if not ObjectId.is_valid(category_id):
        raise HTTPException(status_code=400, detail="Invalid ID format")
        
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # If updating name, check for duplicates
    if "name" in update_data:
        existing = await db["advt_categories"].find_one({
            "name": {"$regex": f"^{update_data['name']}$", "$options": "i"},
            "_id": {"$ne": ObjectId(category_id)}
        })
        if existing:
            raise HTTPException(status_code=400, detail="Another category with this name already exists")

    result = await db["advt_categories"].update_one(
        {"_id": ObjectId(category_id)},
        {"$set": update_data}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Category not found")
    
    updated_doc = await db["advt_categories"].find_one({"_id": ObjectId(category_id)})
    return _fix_id(updated_doc)

@router.delete("/{category_id}", summary="Delete an ADVT category")
async def delete_advt_category(category_id: str):
    db = get_db()
    if not ObjectId.is_valid(category_id):
        raise HTTPException(status_code=400, detail="Invalid ID format")
        
    result = await db["advt_categories"].delete_one({"_id": ObjectId(category_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Category not found")
    
    return {"message": "Category deleted successfully"}
