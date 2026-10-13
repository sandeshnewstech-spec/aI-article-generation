import os
import shutil
import tempfile
import re
import jwt
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request
from typing import List, Optional
from bson import ObjectId
from datetime import datetime

from app.models.advt import AdvtModel
from app.core.database import get_db
from app.core.security import SECRET_KEY, ALGORITHM
from app.services.advt_service import AdvtService

router = APIRouter(prefix="/advt", tags=["advt"])
advt_service = AdvtService()

@router.post("/upload", response_model=dict)
async def upload_advt_file(
    request: Request,
    file: UploadFile = File(...),
    advt_type: str = Form(""),
    height: float = Form(0.0),
    width: float = Form(0.0),
    unit: str = Form("cm"),
    blank_file: Optional[UploadFile] = File(None),
    eng_to_guj: bool = Form(False),
    add_keypoints: bool = Form(False),
    legal_notice: bool = Form(False),
    username: Optional[str] = Form(None)
):
    """Upload an advertisement file (PDF, Image, Word), extract and translate text"""
    try:
        db = get_db()
        
        # Save file to a temporary location
        suffix = os.path.splitext(file.filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name

        import time
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        static_dir = os.path.join(base_dir, "static", "advt_images")
        os.makedirs(static_dir, exist_ok=True)
        
        orig_filename = f"orig_{int(time.time())}{suffix}"
        orig_path = os.path.join(static_dir, orig_filename)
        shutil.copy2(tmp_path, orig_path)
        original_file_url = f"/static/advt_images/{orig_filename}"

        blank_url = ""
        if blank_file and blank_file.filename:
            blank_ext = os.path.splitext(blank_file.filename)[1].lower()
            
            if blank_ext == ".pdf":
                # Convert PDF first page to Image using PyMuPDF
                import fitz
                pdf_bytes = await blank_file.read()
                pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
                if len(pdf_document) > 0:
                    page = pdf_document[0]
                    pix = page.get_pixmap(dpi=150)
                    blank_filename = f"blank_{int(time.time())}.png"
                    blank_path = os.path.join(static_dir, blank_filename)
                    pix.save(blank_path)
                    blank_url = f"/static/advt_images/{blank_filename}"
            else:
                if not blank_ext:
                    blank_ext = ".jpg"
                blank_filename = f"blank_{int(time.time())}{blank_ext}"
                blank_path = os.path.join(static_dir, blank_filename)
                with open(blank_path, "wb") as f:
                    shutil.copyfileobj(blank_file.file, f)
                blank_url = f"/static/advt_images/{blank_filename}"

        translated_text = ""
        file_type = file.content_type

        try:
            # Process based on file type
            if "wordprocessingml.document" in file_type or suffix.lower() == '.docx':
                translated_text, generated_image_url = await advt_service.process_docx(
                    tmp_path, advt_type, height, width, unit, blank_url, eng_to_guj, add_keypoints, legal_notice
                )
            elif "pdf" in file_type or "image" in file_type:
                # Use Gemini directly for PDF and Images
                translated_text, generated_image_url = await advt_service.process_and_translate(
                    tmp_path, file_type, advt_type, height, width, unit, blank_url, eng_to_guj, add_keypoints, legal_notice
                )
            else:
                raise HTTPException(status_code=400, detail="Unsupported file format. Please upload PDF, Word (.docx), or an Image.")
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        # Extract uploader username
        uploader = username
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                sub = payload.get("sub")
                if sub:
                    uploader = sub
            except Exception:
                pass

        if not uploader:
            uploader = request.headers.get("x-username") or username or "Admin"

        # Create record in MongoDB
        advt_record = {
            "filename": file.filename,
            "file_type": file_type,
            "advt_type": advt_type,
            "height": height,
            "width": width,
            "unit": unit,
            "translated_text": translated_text,
            "generated_image_url": generated_image_url,
            "original_file_url": original_file_url,
            "status": "Completed",
            "created_at": datetime.utcnow(),
            "username": uploader,
            "created_by": uploader
        }
        
        res = await db["advt"].insert_one(advt_record)
        advt_record["_id"] = str(res.inserted_id)
        
        return {"message": "File processed successfully", "data": advt_record}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] ADVT Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[dict])
@router.get("", response_model=List[dict])
async def get_all_advts(
    request: Request,
    username: Optional[str] = None,
    role: Optional[str] = None,
    search: Optional[str] = None
):
    """Retrieve all advertisement translations with role-based and search filtering:
       - super_admin and advt_admin see all advertisements
       - advt_editor and other users only see their own advertisements
       - search filters by filename, username, and created_by
    """
    try:
        db = get_db()
        current_username = username
        current_role = role

        # Try resolving user & role from Authorization Bearer token first
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                sub = payload.get("sub")
                if sub:
                    current_username = sub
                    user_doc = await db["users"].find_one({"username": sub})
                    if user_doc:
                        current_role = user_doc.get("role")
            except Exception:
                pass

        if not current_role:
            current_role = request.headers.get("x-user-role") or role
        if not current_username:
            current_username = request.headers.get("x-username") or username

        # Determine filter query
        query = {}
        # If user is NOT an admin (e.g. advt_editor or standard user)
        if current_role not in ["super_admin", "advt_admin"]:
            if current_username:
                safe_name = re.escape(current_username)
                query = {
                    "$or": [
                        {"username": {"$regex": f"^{safe_name}$", "$options": "i"}},
                        {"created_by": {"$regex": f"^{safe_name}$", "$options": "i"}}
                    ]
                }
            else:
                # If role is advt_editor but no username passed, don't leak other ads
                query = {"_id": None}

        # Apply search filter by filename, username, created_by
        if search and search.strip():
            safe_search = re.escape(search.strip())
            search_cond = {
                "$or": [
                    {"filename": {"$regex": safe_search, "$options": "i"}},
                    {"username": {"$regex": safe_search, "$options": "i"}},
                    {"created_by": {"$regex": safe_search, "$options": "i"}}
                ]
            }
            if query:
                query = {"$and": [query, search_cond]}
            else:
                query = search_cond

        cursor = db["advt"].find(query).sort("created_at", -1)
        advts = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            advts.append(doc)
        return advts
    except Exception as e:
        print(f"[ERROR] Failed to fetch advts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{id}", response_model=dict)
async def get_advt_by_id(id: str, request: Request):
    """Retrieve single advertisement by ID"""
    try:
        db = get_db()
        doc = await db["advt"].find_one({"_id": ObjectId(id)})
        if not doc:
            raise HTTPException(status_code=404, detail="Advertisement not found")
        doc["_id"] = str(doc["_id"])
        return doc
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to fetch advt {id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{id}", response_model=dict)
async def update_advt(id: str, payload: dict):
    """Update translated text for an advertisement"""
    try:
        db = get_db()
        translated_text = payload.get("translated_text")
        if not translated_text:
            raise HTTPException(status_code=400, detail="Translated text is required")
            
        res = await db["advt"].update_one(
            {"_id": ObjectId(id)},
            {"$set": {"translated_text": translated_text}}
        )
        
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail="Advertisement not found")
            
        return {"message": "Advertisement updated successfully"}
    except Exception as e:
        print(f"[ERROR] Failed to update advt: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{id}", response_model=dict)
async def delete_advt(id: str, request: Request):
    """Delete an advertisement record (admin can delete any, editor only their own)"""
    try:
        db = get_db()
        current_username = None
        current_role = None

        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                sub = payload.get("sub")
                if sub:
                    current_username = sub
                    user_doc = await db["users"].find_one({"username": sub})
                    if user_doc:
                        current_role = user_doc.get("role")
            except Exception:
                pass

        if not current_role:
            current_role = request.headers.get("x-user-role")
        if not current_username:
            current_username = request.headers.get("x-username")

        delete_filter = {"_id": ObjectId(id)}
        if current_role and current_role not in ["super_admin", "advt_admin"] and current_username:
            safe_name = re.escape(current_username)
            delete_filter["$or"] = [
                {"username": {"$regex": f"^{safe_name}$", "$options": "i"}},
                {"created_by": {"$regex": f"^{safe_name}$", "$options": "i"}}
            ]

        res = await db["advt"].delete_one(delete_filter)
        
        if res.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Advertisement not found or unauthorized")
            
        return {"message": "Advertisement deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to delete advt: {e}")
        raise HTTPException(status_code=500, detail=str(e))
