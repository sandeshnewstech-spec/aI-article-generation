import sys
import os
import asyncio

# Set up event loop for Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.core.database import get_db

async def main():
    try:
        db = get_db()
        # Find the latest document in advt collection
        cursor = db['advt'].find().sort('created_at', -1).limit(1)
        advts = await cursor.to_list(1)
        if advts:
            print("LATEST ADVT TEXT:")
            print(advts[0].get('translated_text', 'No translated_text field')[:1000])
        else:
            print('No advts')
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(main())
