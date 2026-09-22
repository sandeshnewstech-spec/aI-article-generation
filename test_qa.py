import asyncio
import json
import os
import sys
from app.services.advt_service import AdvtService

sys.stdout.reconfigure(encoding='utf-8')

class TestAdvtService(AdvtService):
    async def _call_openrouter(self, messages):
        res = await super()._call_openrouter(messages)
        print("====== RAW OPENROUTER RESPONSE ======")
        print(res)
        print("=====================================")
        return res

async def main():
    print('Testing AdvtService...')
    svc = TestAdvtService()
    original = r'd:\C Data\Documents\GitHub\aI-article-generation\Ad materials\ENGLISH CREATIVE.jpeg'
    blank_relative = 'Ad materials/ENGLISH CREATIVE.jpeg'
    
    result = await svc.process_image(
        file_path=original,
        mime_type='image/jpeg',
        advt_type='Social Media Post',
        height=1000,
        width=1000,
        unit='px',
        blank_url=blank_relative,
        eng_to_guj=True,
        add_keypoints=False,
        legal_notice=False
    )
    print("Result parsed.")

asyncio.run(main())
