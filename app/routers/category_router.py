from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from typing import List, Optional
from bson import ObjectId
from app.core.database import get_db

router = APIRouter(prefix="/categories", tags=["Categories"])


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fix_id(doc: dict) -> dict:
    """Convert ObjectId to string for JSON serialisation."""
    doc["id"] = str(doc.pop("_id"))
    return doc


# ── Schemas ───────────────────────────────────────────────────────────────────

class CategoryCreate(BaseModel):
    name: str
    slug: Optional[str] = None
    sources: List[str] = []
    is_active: bool = True


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    sources: Optional[List[str]] = None
    is_active: Optional[bool] = None


class SourcesUpdate(BaseModel):
    sources: List[str]


# ── CRUD: Categories ──────────────────────────────────────────────────────────

@router.get("/", summary="List all categories")
async def list_categories():
    db = get_db()
    docs = await db["categories"].find().to_list(length=None)
    return [_fix_id(d) for d in docs]


@router.post("/", summary="Create a new category", status_code=201)
async def create_category(payload: CategoryCreate):
    db = get_db()
    # Auto-generate slug if not provided
    slug = payload.slug or payload.name.lower().replace(" ", "-")
    # Ensure unique slug
    existing = await db["categories"].find_one({"slug": slug})
    if existing:
        raise HTTPException(status_code=409, detail=f"Category with slug '{slug}' already exists.")
    data = payload.dict()
    data["slug"] = slug
    result = await db["categories"].insert_one(data)
    new_doc = await db["categories"].find_one({"_id": result.inserted_id})
    return _fix_id(new_doc)


@router.get("/{cat_id}", summary="Get a single category")
async def get_category(cat_id: str):
    db = get_db()
    doc = await db["categories"].find_one({"_id": ObjectId(cat_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Category not found")
    return _fix_id(doc)


@router.put("/{cat_id}", summary="Update a category")
async def update_category(cat_id: str, payload: CategoryUpdate):
    db = get_db()
    update_data = {k: v for k, v in payload.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = await db["categories"].update_one(
        {"_id": ObjectId(cat_id)},
        {"$set": update_data}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Category not found")
    doc = await db["categories"].find_one({"_id": ObjectId(cat_id)})
    return _fix_id(doc)


@router.delete("/{cat_id}", summary="Delete a category")
async def delete_category(cat_id: str):
    db = get_db()
    result = await db["categories"].delete_one({"_id": ObjectId(cat_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"message": "Category deleted successfully"}


# ── CRUD: Sources within a Category ──────────────────────────────────────────

@router.get("/{cat_id}/sources", summary="List sources for a category")
async def list_sources(cat_id: str):
    db = get_db()
    doc = await db["categories"].find_one({"_id": ObjectId(cat_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"category_id": cat_id, "sources": doc.get("sources", [])}


@router.post("/{cat_id}/sources", summary="Add a source to a category", status_code=201)
async def add_source(cat_id: str, source: str = Body(..., embed=True)):
    db = get_db()
    doc = await db["categories"].find_one({"_id": ObjectId(cat_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Category not found")
    if source in doc.get("sources", []):
        raise HTTPException(status_code=409, detail=f"Source '{source}' already exists in this category.")
    await db["categories"].update_one(
        {"_id": ObjectId(cat_id)},
        {"$push": {"sources": source}}
    )
    updated = await db["categories"].find_one({"_id": ObjectId(cat_id)})
    return _fix_id(updated)


@router.put("/{cat_id}/sources", summary="Replace all sources for a category")
async def replace_sources(cat_id: str, payload: SourcesUpdate):
    db = get_db()
    result = await db["categories"].update_one(
        {"_id": ObjectId(cat_id)},
        {"$set": {"sources": payload.sources}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Category not found")
    doc = await db["categories"].find_one({"_id": ObjectId(cat_id)})
    return _fix_id(doc)


@router.delete("/{cat_id}/sources/{source_name}", summary="Remove a source from a category")
async def remove_source(cat_id: str, source_name: str):
    db = get_db()
    doc = await db["categories"].find_one({"_id": ObjectId(cat_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Category not found")
    if source_name not in doc.get("sources", []):
        raise HTTPException(status_code=404, detail=f"Source '{source_name}' not found in this category.")
    await db["categories"].update_one(
        {"_id": ObjectId(cat_id)},
        {"$pull": {"sources": source_name}}
    )
    updated = await db["categories"].find_one({"_id": ObjectId(cat_id)})
    return _fix_id(updated)
