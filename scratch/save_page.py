import requests

def save_page():
    try:
        resp = requests.get("http://127.0.0.1:8000", timeout=10)
        with open("scratch/output.html", "w", encoding="utf-8") as f:
            f.write(resp.text)
        print(f"Successfully saved page. Status: {resp.status_code}, Length: {len(resp.text)}")
    except Exception as e:
        print(f"FAILED to get page: {e}")

if __name__ == "__main__":
    save_page()
