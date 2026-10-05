import httpx
import asyncio

slots_data = [
    {"col": 1, "slot": 1, "heading": 8,  "intro": 0,  "body": 111, "cap": 11, "subheading": 12},
    {"col": 2, "slot": 1, "heading": 11, "intro": 40, "body": 145, "cap": 11, "subheading": 12},
    {"col": 3, "slot": 1, "heading": 11, "intro": 45, "body": 170, "cap": 11, "subheading": 12},
    {"col": 4, "slot": 1, "heading": 11, "intro": 50, "body": 300, "cap": 14, "subheading": 16},
    {"col": 5, "slot": 1, "heading": 11, "intro": 55, "body": 360, "cap": 15, "subheading": 17},
    {"col": 6, "slot": 1, "heading": 10, "intro": 55, "body": 420, "cap": 16, "subheading": 18},
    {"col": 8, "slot": 1, "heading": 10, "intro": 60, "body": 630, "cap": 18, "subheading": 20},
    
    {"col": 3, "slot": 2, "heading": 11, "intro": 55, "body": 490, "cap": 11, "subheading": 12},
    {"col": 4, "slot": 2, "heading": 11, "intro": 55, "body": 600, "cap": 14, "subheading": 16},
    {"col": 5, "slot": 2, "heading": 11, "intro": 60, "body": 720, "cap": 15, "subheading": 17},
]

async def main():
    async with httpx.AsyncClient() as client:
        # Get existing slots
        resp = await client.get("http://127.0.0.1:8000/api/slots/")
        if resp.status_code != 200:
            print("Failed to get slots:", resp.text)
            return
            
        existing = resp.json()
        print(f"Found {len(existing)} existing slots.")
        
        for sd in slots_data:
            # Find if this combination exists
            match = next((s for s in existing if s["column_span"] == sd["col"] and s["slot_count"] == sd["slot"]), None)
            
            payload = {
                "name": f"{sd['col']} Col | {sd['slot']} Slot",
                "column_span": sd["col"],
                "slot_count": sd["slot"],
                "wc_cap_heading": sd["cap"],
                "wc_headline": sd["heading"],
                "wc_sub_heading": sd["subheading"],
                "wc_intro": sd["intro"],
                "wc_body": sd["body"]
            }
            
            if match:
                # Update
                print(f"Updating {payload['name']}")
                r = await client.put(f"http://127.0.0.1:8000/api/slots/{match['id']}", json=payload)
                if r.status_code >= 400:
                    print("Error updating:", r.text)
            else:
                # Create
                print(f"Creating {payload['name']}")
                r = await client.post("http://127.0.0.1:8000/api/slots/", json=payload)
                if r.status_code >= 400:
                    print("Error creating:", r.text)

if __name__ == "__main__":
    asyncio.run(main())
