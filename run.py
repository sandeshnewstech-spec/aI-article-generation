import sys
import asyncio


if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*50)
    print("🚀 STARTING NEWSROOM ENGINE")
    print("📍 URL: http://localhost:8000")
    print("="*50 + "\n")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
 
 
 
 
