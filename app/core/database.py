import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DB_NAME", "ai_newsroom")

from app.core.security import get_password_hash
from app.models.user import UserRole

client: AsyncIOMotorClient = None
db = None


async def connect_db():
    global client, db
    try:
        # Set a short timeout for initial contact
        client = AsyncIOMotorClient(MONGODB_URL, serverSelectionTimeoutMS=10000)
        db = client[DB_NAME]
        
        # Verify connection by pinging the server
        await client.admin.command('ping')
        print(f"[OK] MongoDB connected: {MONGODB_URL} / {DB_NAME}")
        
        # Seed default data if collections are empty
        await seed_defaults()
        await seed_users()
    except Exception as e:
        print(f"❌ [CRITICAL] Could not connect to MongoDB at {MONGODB_URL}")
        print(f"   Please ensure MongoDB service is running (e.g., 'net start MongoDB' or 'brew services start mongodb-community')")
        print(f"   Error: {e}")
        # In a real app, you might want to exit here, but for now we'll let it raise so the user sees it.
        raise e


async def close_db():
    global client
    if client:
        client.close()
        print("[INFO] MongoDB disconnected")


def get_db():
    return db


async def seed_defaults():
    """Seed default categories+sources and slots if collections are empty."""
    cat_count = await db["categories"].count_documents({})
    if cat_count == 0:
        default_categories = [
            {
                "name": "National",
                "slug": "national",
                "sources": [
                    "ndtv.com", "timesofindia.indiatimes.com", "thehindu.com",
                    "scroll.in", "theprint.in", "thewire.in", "aajtak.in",
                    "abplive.com", "zeenews.india.com", "indianexpress.com",
                    "indiatoday.in", "republicbharat.com", "bhaskar.com",
                    "navbharattimes.indiatimes.com", "news18.com", "jagran.com",
                    "hindustantimes.com", "tribuneindia.com", "telegraphindia.com"
                ],
                "is_active": True
            },
            {
                "name": "Business",
                "slug": "business",
                "sources": [
                    "moneycontrol.com", "economictimes.indiatimes.com",
                    "business-standard.com", "livemint.com",
                    "financialexpress.com", "thehindubusinessline.com",
                    "businesstoday.in", "cnbctv18.com", "ndtvprofit.com",
                    "zeebiz.com", "outlookbusiness.com", "bloomberg.com"
                ],
                "is_active": True
            },
            {
                "name": "International",
                "slug": "international",
                "sources": [
                    "bbc.com", "reuters.com", "nytimes.com",
                    "washingtonpost.com", "aljazeera.com", "theguardian.com",
                    "cnn.com", "foxnews.com", "dailymail.co.uk"
                ],
                "is_active": True
            },
            {
                "name": "Local",
                "slug": "local",
                "sources": [
                    "tv9gujarati.com", "gstv.in", "divyabhaskar.co.in",
                    "gujarati.news18.com", "abpasmita.abplive.in",
                    "zee24kalak.in", "ddnewsgujarati.com"
                ],
                "is_active": True
            },
            {
                "name": "Agency",
                "slug": "agency",
                "sources": [
                    "aninews.in", "ptinews.com", "pib.gov.in",
                    "newsonair.gov.in", "nseindia.com", "bseindia.com"
                ],
                "is_active": True
            }
        ]
        await db["categories"].insert_many(default_categories)
        print("[OK] Seeded default categories")

    slot_count = await db["slots"].count_documents({})
    if slot_count == 0:
        default_slots = []
        for c in range(1, 9):  # 1 to 8 columns
            for s in range(1, 5):  # 1 to 4 slots
                size_factor = c / s
                
                wc_h = 8 + (c // 2)
                if wc_h > 15: wc_h = 15
                
                wc_i = int(35 + (size_factor * 25))
                if wc_i > 200: wc_i = 200
                
                wc_b = int(70 + (size_factor * 80))
                if wc_b > 500: wc_b = 500

                wc_k = int(30 + (size_factor * 15))
                if wc_k > 100: wc_k = 100

                default_slots.append({
                    "name": f"{c} Col | {s} Slot",
                    "column_span": c,
                    "slot_count": s,
                    "description": f"Layout for {c} columns width divided into {s} vertical segments.",
                    "is_active": True,
                    "wc_headline": wc_h,
                    "wc_intro": wc_i,
                    "wc_body": wc_b,
                    "wc_infobox": wc_k
                })
        await db["slots"].insert_many(default_slots)
        print("[OK] Seeded 32 default slot combinations")

async def seed_users():
    """Seed a default super admin user if no users exist."""
    user_count = await db["users"].count_documents({})
    if user_count == 0:
        admin_user = {
            "username": "admin",
            "hashed_password": get_password_hash("admin123"), # Default password
            "role": UserRole.SUPER_ADMIN,
            "is_active": True
        }
        await db["users"].insert_one(admin_user)
        print("[OK] Seeded default super admin: admin / admin123")
