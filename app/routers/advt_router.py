import os
import shutil
import tempfile
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import List, Optional
from bson import ObjectId
from datetime import datetime

from app.models.advt import AdvtModel
from app.core.database import get_db
from app.services.advt_service import AdvtService

router = APIRouter(prefix="/advt", tags=["advt"])
advt_service = AdvtService()

@router.post("/upload", response_model=dict)
async def upload_advt_file(
    file: UploadFile = File(...),
    advt_type: str = Form(""),
    height: float = Form(0.0),
    width: float = Form(0.0),
    unit: str = Form("cm"),
    blank_file: Optional[UploadFile] = File(None),
    eng_to_guj: bool = Form(False),
    add_keypoints: bool = Form(False),
    legal_notice: bool = Form(False)
):
    """Upload an advertisement file (PDF, Image, Word), extract and translate text"""
    try:
        db = get_db()
        
        # Save file to a temporary location
        suffix = os.path.splitext(file.filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name

        blank_url = ""
        if blank_file and blank_file.filename:
            import time
            blank_ext = os.path.splitext(blank_file.filename)[1].lower()
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            static_dir = os.path.join(base_dir, "static", "advt_images")
            os.makedirs(static_dir, exist_ok=True)
            
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
            "status": "Completed",
            "created_at": datetime.utcnow()
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
async def get_all_advts():
    """Retrieve all advertisement translations"""
    try:
        db = get_db()
        cursor = db["advt"].find().sort("created_at", -1)
        advts = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            advts.append(doc)
        return advts
    except Exception as e:
        print(f"[ERROR] Failed to fetch advts: {e}")
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
async def delete_advt(id: str):
    """Delete an advertisement record"""
    try:
        db = get_db()
        res = await db["advt"].delete_one({"_id": ObjectId(id)})
        
        if res.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Advertisement not found")
            
        return {"message": "Advertisement deleted successfully"}
    except Exception as e:
        print(f"[ERROR] Failed to delete advt: {e}")
        raise HTTPException(status_code=500, detail=str(e))
