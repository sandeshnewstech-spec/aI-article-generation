import os
import tempfile
import asyncio
import base64
from fastapi import APIRouter, HTTPException, UploadFile, File
from app.core.config import settings

router = APIRouter(prefix="/extract", tags=["extract"])

async def _extract_image_text(file_path: str, mime_type: str) -> str:
    import requests
    def _encode_image():
        with open(file_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
            
    base64_image = await asyncio.to_thread(_encode_image)
    
    prompt = (
        "Extract all the text from this image accurately. "
        "Output ONLY the extracted text, in its original language, without any additional explanations."
    )
    
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": prompt
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{base64_image}"
                    }
                }
            ]
        }
    ]
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "AI Newsroom Pro"
    }
    payload = {
        "model": settings.OPENROUTER_MODEL,
        "messages": messages,
        "temperature": 0.1
    }
    
    def _request():
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        if not response.ok:
            try:
                err = response.json()
                raise Exception(err.get("error", {}).get("message", response.text))
            except Exception:
                response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
        
    return await asyncio.to_thread(_request)


@router.post("/", response_model=dict)
async def extract_text_from_file(file: UploadFile = File(...)):
    """Upload a file (PDF, Image, Word, TXT) and extract text"""
    import shutil
    try:
        suffix = os.path.splitext(file.filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name

        extracted_text = ""
        file_type = file.content_type.lower()
        suffix_lower = suffix.lower()

        try:
            if "text/plain" in file_type or suffix_lower == '.txt':
                def _read_txt():
                    with open(tmp_path, 'r', encoding='utf-8', errors='ignore') as f:
                        return f.read()
                extracted_text = await asyncio.to_thread(_read_txt)
                
            elif "wordprocessingml.document" in file_type or suffix_lower == '.docx':
                import docx
                def _extract_docx():
                    doc = docx.Document(tmp_path)
                    fullText = [para.text for para in doc.paragraphs if para.text.strip()]
                    return '\n'.join(fullText)
                extracted_text = await asyncio.to_thread(_extract_docx)
                
            elif "pdf" in file_type or suffix_lower == '.pdf':
                import pypdf
                def _extract_pdf():
                    text = ""
                    with open(tmp_path, "rb") as f:
                        reader = pypdf.PdfReader(f)
                        for page in reader.pages:
                            ext = page.extract_text()
                            if ext:
                                text += ext + "\n"
                    return text
                extracted_text = await asyncio.to_thread(_extract_pdf)
                
            elif "image" in file_type or suffix_lower in ['.png', '.jpg', '.jpeg', '.webp']:
                extracted_text = await _extract_image_text(tmp_path, file_type)
            else:
                raise HTTPException(status_code=400, detail="Unsupported file format. Please upload PDF, Word (.docx), TXT, or an Image.")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        return {"text": extracted_text}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Text extraction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
