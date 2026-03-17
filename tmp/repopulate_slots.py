import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DB_NAME", "ai_newsroom")

async def repopulate():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]
    
    print(f"Connecting to {DB_NAME}...")
    
    # 1. Clear existing slots
    await db["slots"].delete_many({})
    print("Cleared existing slots.")
    
    # 2. Generate 32 combinations (8 columns * 4 slots)
    default_slots = []
    for c in range(1, 9):  # 1 to 8 columns
        for s in range(1, 5):  # 1 to 4 slots
            # Logical scaling for word counts based on article size (c/s)
            size_factor = c / s
            
            # Headline: 8 to 15 based on width
            wc_h = 8 + (c // 2)
            if wc_h > 15: wc_h = 15
            
            # Intro: Scales from 30 up to 150
            wc_i = int(35 + (size_factor * 25))
            if wc_i > 200: wc_i = 200
            
            # Body: Scales from 60 up to 400
            wc_b = int(70 + (size_factor * 80))
            if wc_b > 500: wc_b = 500

            default_slots.append({
                "name": f"{c} Col | {s} Slot",
                "column_span": c,
                "slot_count": s,
                "description": f"Layout for {c} columns width divided into {s} vertical segments.",
                "is_active": True,
                "wc_headline": wc_h,
                "wc_intro": wc_i,
                "wc_body": wc_b
            })
            
    await db["slots"].insert_many(default_slots)
    print(f"Successfully seeded {len(default_slots)} combinations (1-8 Columns, 1-4 Slots).")
    client.close()

if __name__ == "__main__":
    asyncio.run(repopulate())
