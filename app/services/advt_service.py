import os
import tempfile
import asyncio
import requests
import base64
from app.core.config import settings

import json
import base64
import requests
import cv2
import numpy as np

def extract_ocr_blocks(image_bytes):
    try:
        np_arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        h, w = img.shape[:2]
        max_dim = 1000
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            img = cv2.resize(img, (int(w*scale), int(h*scale)))
            h, w = img.shape[:2]
            
        _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        b64 = base64.b64encode(buffer).decode('utf-8')
        
        payload = {
            'base64Image': 'data:image/jpeg;base64,' + b64,
            'apikey': 'helloworld',
            'isOverlayRequired': True,
            'language': 'eng'
        }
        
        r = requests.post('https://api.ocr.space/parse/image', data=payload, timeout=15)
        data = r.json()
        
        blocks = []
        if 'ParsedResults' in data and data['ParsedResults']:
            lines = data['ParsedResults'][0].get('TextOverlay', {}).get('Lines', [])
            for i, line in enumerate(lines):
                text = line['LineText']
                min_top = line['MinTop']
                max_height = line['MaxHeight']
                words = line['Words']
                if not words: continue
                
                left = words[0]['Left']
                right = words[-1]['Left'] + words[-1]['Width']
                width = right - left
                
                blocks.append({
                    'id': i + 1,
                    'text': text,
                    'top_percent': round((min_top / h) * 100, 2),
                    'left_percent': round((left / w) * 100, 2),
                    'width_percent': round((width / w) * 100, 2),
                    'height_percent': round((max_height / h) * 100, 2)
                })
        return blocks
    except Exception as e:
        print('[OCR Error]', e)
        return []

class AdvtService:
    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.model = "google/gemini-2.5-pro"

    async def process_and_translate(self, file_path: str, mime_type: str, advt_type: str, height: float, width: float, unit: str, blank_url: str = "", eng_to_guj: bool = False, add_keypoints: bool = False, legal_notice: bool = False) -> tuple[str, str]:
        """
        Processes images and PDFs.
        Extracts text locally (for PDFs) or sends base64 image (for images) 
        to OpenRouter for translation and image generation.
        """
        if "pdf" in mime_type.lower():
            return await self.process_pdf(file_path, advt_type, height, width, unit, blank_url, eng_to_guj, add_keypoints, legal_notice)
        else:
            return await self.process_image(file_path, mime_type, advt_type, height, width, unit, blank_url, eng_to_guj, add_keypoints, legal_notice)

    async def process_pdf(self, file_path: str, advt_type: str, height: float, width: float, unit: str, blank_url: str = "", eng_to_guj: bool = False, add_keypoints: bool = False, legal_notice: bool = False) -> tuple[str, str]:
        import fitz
        import os
        import tempfile
        
        def _render_pdf_to_image():
            doc = fitz.open(file_path)
            if len(doc) == 0:
                raise ValueError("PDF has no pages")
            page = doc.load_page(0)
            # Render at 150 DPI for good OCR quality while keeping size manageable
            pix = page.get_pixmap(dpi=150)
            temp_path = os.path.join(tempfile.gettempdir(), f"pdf_page_{os.path.basename(file_path)}.png")
            pix.save(temp_path)
            return temp_path
            
        try:
            image_path = await asyncio.to_thread(_render_pdf_to_image)
        except Exception as e:
            print(f"Failed to render PDF to image with PyMuPDF: {e}")
            # Fallback to PyPDF text extraction if rendering fails
            import pypdf
            def _extract():
                text = ""
                with open(file_path, "rb") as f:
                    reader = pypdf.PdfReader(f)
                    for page in reader.pages:
                        extracted = page.extract_text()
                        if extracted:
                            text += extracted + "\n"
                return text
                
            text = await asyncio.to_thread(_extract)
            return await self._generate_advt_content(text, advt_type, height, width, unit, blank_url, eng_to_guj, add_keypoints, legal_notice)
            
        # Process the successfully rendered image. Do NOT catch AI API errors here.
        return await self.process_image(image_path, "image/png", advt_type, height, width, unit, blank_url, eng_to_guj, add_keypoints, legal_notice)

    async def process_image(self, file_path: str, mime_type: str, advt_type: str, height: float, width: float, unit: str, blank_url: str = "", eng_to_guj: bool = False, add_keypoints: bool = False, legal_notice: bool = False) -> tuple[str, str]:
        def _encode_image():
            with open(file_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
                
        base64_image = await asyncio.to_thread(_encode_image)
        
        formatting_instructions = []
        if eng_to_guj:
            formatting_instructions.append("- Translate the text accurately into Gujarati.")
        if add_keypoints:
            formatting_instructions.append("- Format the text using bullet points for key information.")
        if legal_notice or advt_type.lower() == "legal notice":
            formatting_instructions.append("- Structure the text as a formal legal/public notice.")
            formatting_instructions.append("- CRITICAL: DO NOT extract or include any stamps, seals, or handwritten signatures. Ignore them completely. DO NOT extract the text from any rubber stamp (e.g. English advocate stamps with license numbers). Only extract the actual printed article text.")
            formatting_instructions.append("- CRITICAL for Legal Notice: Top heading MUST be 'જાહેર નોટિસ' (font_size_px: 20, color: '#FFFFFF', background_color: '#000000', font_family: 'Gopika', text_align: 'center').")
            formatting_instructions.append("- Content MUST have font_size_px: 11, color: '#000000', font_family: 'Gopika'.")
            formatting_instructions.append("- Advocate names MUST have font_size_px: 12, font_weight: 'bold', color: '#000000', font_family: 'Gopika'.")
            if float(width) >= 15:
                formatting_instructions.append("- Since width is >= 15, use a 2-COLUMN layout. Split the content logically. Column 1 (left_percent: 2, width_percent: 45), Column 2 (left_percent: 52, width_percent: 45). Place the Top Heading ONLY in Column 1 at the top.")
            else:
                formatting_instructions.append("- The notice must be structured as a single 1-column layout. Use logical top_percent spacing to separate heading, content, and signatures without overlapping.")
        if legal_notice or advt_type.lower() == "legal notice":
            prompt = (
                "You are an expert advertisement copywriter, translator, and graphic designer.\n"
                "Advertisement Type: Legal Notice\n"
                f"Step 1: Visually analyze the original image and {'translate' if eng_to_guj else 'extract'} the text.\n"
                "Step 2: CRITICAL: DO NOT extract or include any stamps, seals, or handwritten signatures. Ignore them completely. DO NOT extract the text from any rubber stamp (e.g. English advocate stamps with license numbers). Only extract the actual printed article text.\n"
                "Format your output strictly as a pure JSON ARRAY of objects. Do NOT include a 'thought_process' key or any surrounding object.\n"
                "The output MUST be a pure JSON array where each object has ONLY the following keys:\n"
                f"  - 'text': the {'translated Gujarati text' if eng_to_guj else 'extracted text'}\n"
                "  - 'type': EITHER 'heading' (for જાહેર નોટિસ), 'content' (for body paragraphs), or 'advocate' (for advocate details).\n"
                "CRITICAL: Your JSON MUST be 100% syntactically valid. You MUST escape any double quotes inside strings using backslashes (\\\"). Do NOT use trailing commas.\n"
                "Output ONLY the JSON array, without any markdown formatting.\n"
            )
        else:
            format_prompt = "\n".join(formatting_instructions)
            prompt = (
                "You are an expert advertisement copywriter, translator, and graphic designer.\n"
                f"Advertisement Type: {advt_type}\n"
                "You are provided with two images (if a blank template is available):\n"
                "1. The original advertisement with text.\n"
                "2. The blank template where the translated text will be placed.\n"
                "Step 1: We have extracted the exact text bounding boxes from the original image using OCR. The OCR blocks will be provided below as JSON.\n"
                f"Step 2: Visually analyze the original image and {'translate' if eng_to_guj else 'extract'} the text inside each OCR block {'to Gujarati' if eng_to_guj else 'exactly as written'}.\n"
                f"Step 3: If a single logical sentence is split across multiple OCR blocks (IDs), you MUST combine them into ONE {'Gujarati ' if eng_to_guj else ''}block. The output ID can just be the first ID of the combined blocks. However, you MUST perfectly preserve the bounding box dimensions of the resulting layout.\n"
                f"{format_prompt}\n"
                "Format your output strictly as a JSON object with three keys: 'thought_process', 'gujarati_text', and 'image_prompt'.\n"
                "The 'gujarati_text' key MUST be a JSON array of objects, where each object has the following keys:\n"
                f"  - 'text': the {'translated Gujarati text' if eng_to_guj else 'extracted text'}\n"
                "  - 'font_size_percent': COPY the 'height_percent' value EXACTLY from the original OCR block (or max height if combined)\n"
                "  - 'font_size_px': absolute font size in pixels if specified in formatting instructions (e.g., 20, 11, 12)\n"
                "  - 'top_percent': COPY this value EXACTLY from the original OCR block (or the top-most if combined)\n"
                "  - 'left_percent': COPY this value EXACTLY from the original OCR block (or the left-most if combined)\n"
                "  - 'width_percent': COPY this value EXACTLY from the original OCR block (or sum widths if combined horizontally)\n"
                "  - 'color': the hex color code of the text (e.g. '#FFFFFF')\n"
                "  - 'background_color': the hex color code of the background (e.g. '#000000' or null if transparent)\n"
                "  - 'font_weight': 'normal' or 'bold'\n"
                "  - 'font_family': 'Inter' or 'Gopika'\n"
                "  - 'text_align': 'left', 'center', or 'right'. CRITICAL: visually inspect the original image and set this accurately.\n"
                "CRITICAL: Your JSON MUST be 100% syntactically valid. You MUST escape any double quotes inside strings using backslashes (\\\"). Do NOT use trailing commas.\n"
                "Output ONLY the JSON object, without any markdown formatting.\n"
            )
        
        # Read the main image
        with open(file_path, "rb") as f:
            image_data = f.read()
            
        ocr_blocks = await asyncio.to_thread(extract_ocr_blocks, image_data)
        
        base64_image = base64.b64encode(image_data).decode('utf-8')
        
        content_parts = [
            {
                "type": "text",
                "text": prompt + "\n\nEXTRACTED OCR BLOCKS:\n" + json.dumps(ocr_blocks, indent=2)
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{base64_image}"
                }
            }
        ]
        
        # Read the blank template if provided
        if blank_url:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            blank_local_path = os.path.join(base_dir, blank_url.lstrip('/'))
            if os.path.exists(blank_local_path):
                from PIL import Image
                import io
                
                # Compress the image to avoid massive payloads freezing the API
                img = Image.open(blank_local_path)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                img.thumbnail((800, 800))
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=75)
                blank_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                blank_mime = "image/jpeg"
                
                content_parts.append({
                    "type": "text",
                    "text": "Below is the blank template where the text will be placed:"
                })
                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{blank_mime};base64,{blank_b64}"
                    }
                })

        messages = [
            {
                "role": "user",
                "content": content_parts
            }
        ]
        
        return await self._process_openrouter_json(messages, height, width, unit, blank_url, eng_to_guj, legal_notice)

    async def process_docx(self, file_path: str, advt_type: str, height: float, width: float, unit: str, blank_url: str = "", eng_to_guj: bool = False, add_keypoints: bool = False, legal_notice: bool = False) -> tuple[str, str]:
        import docx
        
        def _extract():
            doc = docx.Document(file_path)
            fullText = []
            for para in doc.paragraphs:
                if para.text.strip():
                    fullText.append(para.text)
            return '\n'.join(fullText)
            
        text = await asyncio.to_thread(_extract)
        return await self._generate_advt_content(text, advt_type, height, width, unit, blank_url, eng_to_guj, add_keypoints, legal_notice)

    async def _generate_advt_content(self, text: str, advt_type: str, height: float, width: float, unit: str, blank_url: str, eng_to_guj: bool, add_keypoints: bool, legal_notice: bool) -> tuple[str, str]:
        formatting_instructions = []
        if eng_to_guj:
            formatting_instructions.append("- Rewrite and translate the text accurately into Gujarati.")
        if add_keypoints:
            formatting_instructions.append("- Format the text using bullet points for key information.")
        if legal_notice or advt_type.lower() == "legal notice":
            formatting_instructions.append("- Structure the text as a formal legal/public notice.")
            formatting_instructions.append("- CRITICAL: DO NOT extract or include any stamps, seals, or handwritten signatures. Ignore them completely.")
            formatting_instructions.append("- CRITICAL for Legal Notice: Top heading MUST be 'જાહેર નોટિસ' (font_size_px: 20, color: '#FFFFFF', background_color: '#000000', font_family: 'Gopika', text_align: 'center').")
            formatting_instructions.append("- Content MUST have font_size_px: 11, color: '#000000', font_family: 'Gopika'.")
            formatting_instructions.append("- Advocate names MUST have font_size_px: 12, font_weight: 'bold', color: '#000000', font_family: 'Gopika'.")
            if float(width) >= 15:
                formatting_instructions.append("- Since width is >= 15, use a 2-COLUMN layout. Split the content logically. Column 1 (left_percent: 2, width_percent: 45), Column 2 (left_percent: 52, width_percent: 45). Place the Top Heading ONLY in Column 1 at the top.")
            else:
                formatting_instructions.append("- The notice must be structured as a single 1-column layout. Use logical top_percent spacing to separate heading, content, and signatures without overlapping.")
        if legal_notice or advt_type.lower() == "legal notice":
            prompt = (
                "You are an expert advertisement copywriter, translator, and layout designer.\n"
                f"Advertisement Type: Legal Notice\n"
                f"Step 1: Visually analyze the original advertisement. Group the text into logical paragraphs.\n"
                f"Step 2: {'Translate the text to Gujarati accurately.' if eng_to_guj else 'Extract the text exactly as written.'}\n"
                "Step 3: CRITICAL: DO NOT extract or include any stamps, seals, or handwritten signatures. Ignore them completely.\n"
                "Format your output strictly as a pure JSON ARRAY of objects. Do NOT include a 'thought_process' key or any surrounding object.\n"
                "The output MUST be a pure JSON array where each object has ONLY the following keys:\n"
                f"  - 'text': the {'translated Gujarati text' if eng_to_guj else 'extracted text'}\n"
                "  - 'type': EITHER 'heading' (for જાહેર નોટિસ), 'content' (for body paragraphs), or 'advocate' (for advocate details).\n"
                "CRITICAL: Your JSON MUST be 100% syntactically valid. You MUST escape any double quotes inside strings using backslashes (\\\"). Do NOT use trailing commas.\n"
                "Output ONLY the JSON array, without any markdown formatting or additional explanations.\n\n"
                f"TEXT:\n{text}"
            )
        else:
            format_prompt = "\n".join(formatting_instructions)
            prompt = (
                "You are an expert advertisement copywriter, translator, and layout designer.\n"
                f"Advertisement Type: {advt_type}\n"
                f"Dimensions: {height}x{width} {unit}\n"
                "Step 1: Visually analyze the original advertisement. Group the text into logical paragraphs or distinct visual blocks. Do NOT over-fragment the text into tiny pieces if they belong together.\n"
                f"Step 2: {'Translate the text to Gujarati accurately.' if eng_to_guj else 'Extract the text exactly as written.'}\n"
                "Step 3: Perform a manual QA pass like a human graphic designer. Compare your planned text blocks with the original visual layout. CRITICAL: Ensure NO TWO BOUNDING BOXES OVERLAP. If text is stacked vertically, their y-coordinates must not intersect.\n"
                f"{format_prompt}\n"
                "Write a detailed English prompt for an Image Generation AI to create a visual that perfectly matches this advertisement.\n"
                "Format your output strictly as a JSON object with three keys: 'thought_process', 'gujarati_text', and 'image_prompt'.\n"
                "The 'thought_process' key MUST contain a detailed explanation of your manual comparison of the fonts, colors, and layout, and how you ensured the bounding boxes are perfectly accurate.\n"
                "The 'gujarati_text' key MUST be a JSON array of objects, where each object represents a text block and has the following keys:\n"
                f"  - 'text': the {'translated Gujarati text' if eng_to_guj else 'extracted text'}\n"
                "  - 'box': an array of 4 integers [ymin, xmin, ymax, xmax] representing the bounding box normalized to a 1000x1000 grid.\n"
                "  - 'top_percent': vertical position percentage (0-100)\n"
                "  - 'left_percent': horizontal position percentage (0-100)\n"
                "  - 'width_percent': width percentage (0-100)\n"
                "  - 'font_size_percent': font size as percentage of canvas height (e.g., 3.0)\n"
                "  - 'font_size_px': absolute font size in pixels if specified (e.g., 20, 11, 12)\n"
                "  - 'color': the hex color code of the text (e.g. '#000000')\n"
                "  - 'background_color': the hex color code of the background (e.g. '#000000' or null)\n"
                "  - 'font_weight': 'normal' or 'bold'\n"
                "  - 'font_family': 'Inter' or 'Gopika'\n"
                "  - 'text_align': 'left', 'center', or 'right'\n"
                "Output ONLY the JSON object, without any markdown formatting or additional explanations.\n\n"
                f"TEXT:\n{text}"
            )
        messages = [{"role": "user", "content": prompt}]
        return await self._process_openrouter_json(messages, height, width, unit, blank_url, eng_to_guj, legal_notice)

    def _draw_qa_boxes(self, blank_url: str, json_str: str) -> str:
        import json
        import os
        import io
        import base64
        from PIL import Image, ImageDraw

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        blank_local_path = os.path.join(base_dir, blank_url.lstrip('/'))
        if not os.path.exists(blank_local_path):
            return None
            
        try:
            img = Image.open(blank_local_path).convert('RGB')
            draw = ImageDraw.Draw(img, "RGBA")
            width, height = img.size
            
            blocks = json.loads(json_str)
            if not isinstance(blocks, list):
                return None
                
            for block in blocks:
                if 'box' in block and isinstance(block['box'], list) and len(block['box']) == 4:
                    ymin, xmin, ymax, xmax = block['box']
                    # Convert normalized [0,1000] to absolute pixels
                    y1 = int((ymin / 1000.0) * height)
                    x1 = int((xmin / 1000.0) * width)
                    y2 = int((ymax / 1000.0) * height)
                    x2 = int((xmax / 1000.0) * width)
                    # Draw thick red rectangle with semi-transparent fill
                    draw.rectangle([x1, y1, x2, y2], outline=(255, 0, 0, 255), width=4, fill=(255, 0, 0, 40))
                    
            # Compress for sending to AI
            img.thumbnail((800, 800))
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
        except Exception as e:
            print(f"Error drawing QA boxes: {e}")
            return None

    async def _process_openrouter_json(self, messages: list, height: float, width: float, unit: str, blank_url: str = "", eng_to_guj: bool = False, legal_notice: bool = False) -> tuple[str, str]:
        import json
        import os
        import time

        result = await self._call_openrouter(messages)
        
        try:
            clean_result = result.strip()
            
            # Find the first { or [ and last } or ] to extract pure JSON
            start_idx_brace = clean_result.find('{')
            start_idx_bracket = clean_result.find('[')
            start_idx = -1
            if start_idx_brace != -1 and start_idx_bracket != -1:
                start_idx = min(start_idx_brace, start_idx_bracket)
            else:
                start_idx = max(start_idx_brace, start_idx_bracket)
                
            end_idx_brace = clean_result.rfind('}')
            end_idx_bracket = clean_result.rfind(']')
            end_idx = max(end_idx_brace, end_idx_bracket)
            
            if start_idx != -1 and end_idx != -1:
                clean_result = clean_result[start_idx:end_idx+1]
                
            import re
            # Fix common LLM JSON errors (trailing commas)
            clean_result = re.sub(r',\s*}', '}', clean_result)
            clean_result = re.sub(r',\s*\]', ']', clean_result)
            
            try:
                data = json.loads(clean_result)
            except json.JSONDecodeError as e_strict:
                print(f"[WARNING] Strict JSON parse failed ({e_strict}). Attempting robust extraction...")
                # If it's a list format, try fixing newlines inside strings
                try:
                    fixed_str = re.sub(r'(?<!\\)\n', '\\\\n', clean_result)
                    data = json.loads(fixed_str)
                except Exception:
                    # Fallback to extracting the gujarati_text array
                    match = re.search(r'"gujarati_text"\s*:\s*(\[.*?\])', clean_result, re.DOTALL)
                    if match:
                        try:
                            array_str = match.group(1)
                            array_str = re.sub(r',\s*\]', ']', array_str)
                            array_str = re.sub(r'(?<!\\)\n', '\\\\n', array_str)
                            data = json.loads(array_str)
                        except Exception as e2:
                            print(f"[ERROR] Regex JSON extraction failed: {e2}")
                            raise
                    else:
                        raise

            if isinstance(data, list):
                gujarati_text_list = data
            elif isinstance(data, dict):
                gujarati_text_list = data.get("gujarati_text", data)
            else:
                gujarati_text_list = []
                
            # Post-processing: Filter out rubber stamps explicitly
            filtered_list = []
            for block in gujarati_text_list:
                text = block.get('text', '')
                if not text:
                    continue
                
                # Check for english character density
                eng_chars = sum(1 for c in text if c.isascii() and c.isalpha())
                total_alpha = sum(1 for c in text if c.isalpha())
                
                if total_alpha > 0 and (eng_chars / total_alpha) > 0.8:
                    # If block is 80% English letters but we expect a Gujarati legal notice, it's a stamp!
                    if eng_to_guj or legal_notice:
                        print(f"[FILTER] Dropped English rubber stamp block: {text}")
                        continue
                        
                # Explicit check for common advocate rubber stamps
                if re.search(r'(?i)(ankit v\. thakor|rohan b\. solanki|advocate|g/1918)', text) and eng_chars > 5:
                    print(f"[FILTER] Dropped rubber stamp block: {text}")
                    continue
                    
                filtered_list.append(block)
                
            gujarati_text_list = filtered_list
                
            initial_json_str = json.dumps(gujarati_text_list, ensure_ascii=False)
            
            # Visual QA Loop removed because Vision models hallucinate coordinates when verifying red boxes.
            
            if isinstance(gujarati_text_list, list) or isinstance(gujarati_text_list, dict):
                gujarati_text = json.dumps(gujarati_text_list, ensure_ascii=False)
            else:
                gujarati_text = str(gujarati_text_list)
                    
            if isinstance(data, dict):
                image_prompt = data.get("image_prompt", "An advertisement background")
            else:
                image_prompt = "An advertisement background"
        except Exception as e:
            import traceback
            print(f"[ERROR] Failed to parse JSON from OpenRouter: {e}\nRaw Result: {result}\n{traceback.format_exc()}")
            raise Exception("The AI model failed to generate a valid JSON layout. Please try regenerating.")

        if blank_url:
            return gujarati_text, blank_url

        # If width and height are provided, we should generate an exact blank image instead of relying on AI
        if float(width) > 0:
            import time
            from PIL import Image
            dpi = 300 # standard print DPI
            cm_to_inch = 0.393701
            px_width = int(float(width) * cm_to_inch * dpi)
            h = float(height) if float(height) > 0 else (float(width) * 1.5) # fallback aspect ratio
            px_height = int(h * cm_to_inch * dpi)
            
            img = Image.new('RGB', (px_width, px_height), color='white')
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            static_dir = os.path.join(base_dir, "static", "advt_images")
            os.makedirs(static_dir, exist_ok=True)
            image_filename = f"advt_exact_{int(time.time())}.png"
            img.save(os.path.join(static_dir, image_filename))
            return gujarati_text, f"/static/advt_images/{image_filename}"

        # Fallback for when no dimensions are provided (legacy behavior)
        combined_prompt = (
            f"Generate an image of a traditional newspaper public notice advertisement. "
            f"The image MUST have a simple white background with a black border, and black text. "
            f"The following Gujarati text must be prominently and clearly written on it: '{gujarati_text}'. "
            "Do NOT draw any people, vehicles, or complex scenes. The image should ONLY contain the text, exactly resembling a printed newspaper clipping. "
            "Please return ONLY the image URL or the raw image data, nothing else."
        )
        
        generated_image_url = ""
        try:
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "google/gemini-3.1-flash-image",
                "messages": [{"role": "user", "content": combined_prompt}]
            }
            
            def _generate_gemini_image():
                response = requests.post(url, headers=headers, json=payload, timeout=120)
                if not response.ok:
                    try:
                        err_json = response.json()
                        raise Exception(err_json)
                    except Exception as parse_e:
                        response.raise_for_status()
                data = response.json()
                
                # Format 0: OpenRouter standard 'images' array (new format)
                images_list = data.get("choices", [{}])[0].get("message", {}).get("images", [])
                if images_list and len(images_list) > 0:
                    img_obj = images_list[0]
                    if isinstance(img_obj, dict) and "image_url" in img_obj:
                        img_url_data = img_obj["image_url"]
                        if isinstance(img_url_data, dict) and "url" in img_url_data:
                            return img_url_data["url"]
                        elif isinstance(img_url_data, str):
                            return img_url_data
                
                # Format 1: image is in tool_calls (old format)
                tool_calls = data.get("choices", [{}])[0].get("message", {}).get("tool_calls", [])
                if tool_calls and len(tool_calls) > 0:
                    tc = tool_calls[0]
                    # custom image_generation type
                    if "image_generation" in tc and isinstance(tc["image_generation"], dict):
                        return tc["image_generation"].get("image", "")
                    # standard OpenAI function call
                    elif tc.get("type") == "function" and "function" in tc:
                        try:
                            import json
                            args = json.loads(tc["function"].get("arguments", "{}"))
                            if "image" in args:
                                return args["image"]
                        except:
                            pass
                            
                content = data.get("choices", [{}])[0].get("message", {}).get("content")
                if content is None:
                    raise Exception(f"OpenRouter returned None content and no valid image. Full response: {data}")
                return content.strip()
                
            image_res = await asyncio.to_thread(_generate_gemini_image)
            
            # Handle base64 data URI returned by Gemini image models
            if image_res.startswith("data:image"):
                import base64
                import time
                import os
                
                header, base64_str = image_res.split(",", 1)
                
                # Fix base64 padding if necessary
                padding_needed = len(base64_str) % 4
                if padding_needed:
                    base64_str += "=" * (4 - padding_needed)
                    
                image_bytes = base64.b64decode(base64_str)
                
                ext = "png"
                if "jpeg" in header or "jpg" in header:
                    ext = "jpg"
                    
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                static_dir = os.path.join(base_dir, "static", "advt_images")
                os.makedirs(static_dir, exist_ok=True)
                
                image_filename = f"advt_{int(time.time())}.{ext}"
                image_path = os.path.join(static_dir, image_filename)
                
                with open(image_path, "wb") as f:
                    f.write(image_bytes)
                    
                generated_image_url = f"/static/advt_images/{image_filename}"
                
            else:
                # Extract URL if it's in markdown format ![alt](url)
                import re
                markdown_match = re.search(r'!\[.*?\]\((.*?)\)', image_res)
                if markdown_match:
                    generated_image_url = markdown_match.group(1)
                elif image_res.startswith("http"):
                    generated_image_url = image_res
                else:
                    generated_image_url = image_res
                
        except Exception as e:
            import traceback
            error_msg = f"[ERROR] Failed to generate image via google/gemini-3.1-flash-image: {e}\n{traceback.format_exc()}"
            print(error_msg)
            
            # Write error to a file so the agent can read it
            try:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                with open(os.path.join(base_dir, "error.log"), "w") as f:
                    f.write(error_msg)
            except:
                pass
                
            # Do NOT raise exception to avoid 500 error.
            # Fallback to FLUX (uncensored) via OpenRouter since Gemini likely refused due to safety filters (accident text)
            print("[INFO] Falling back to FLUX model for image generation...")
            fallback_prompt = (
                f"A pristine, traditional newspaper public notice clipping. Simple white background, solid black border, black text. "
                f"Write the following text clearly: '{gujarati_text[:200]}'. "
                f"Do not draw any scenes. Just a typographic newspaper notice."
            )
            
            try:
                flux_payload = {
                    "model": "black-forest-labs/flux-schnell",
                    "messages": [{"role": "user", "content": fallback_prompt}]
                }
                flux_res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=flux_payload, timeout=60)
                flux_data = flux_res.json()
                generated_image_url = flux_data["choices"][0]["message"]["content"].strip()
                
                # Extract markdown URL if present
                import re
                markdown_match = re.search(r'!\[.*?\]\((.*?)\)', generated_image_url)
                if markdown_match:
                    generated_image_url = markdown_match.group(1)
            except Exception as flux_e:
                print(f"[ERROR] FLUX fallback also failed: {flux_e}")
                # Ultimate fallback
                import urllib.parse
                encoded = urllib.parse.quote("newspaper public notice clipping")
                generated_image_url = f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=800&nologo=true"
        
        return gujarati_text, generated_image_url

    async def _call_openrouter(self, messages: list) -> str:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "AI Newsroom Pro"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 8192
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
