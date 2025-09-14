import os
import json
from config import PROCESSED_DB_PATH

def load_processed_db():
    if not os.path.exists("data"):
        os.makedirs("data")
    if os.path.exists(PROCESSED_DB_PATH):
        try:
            if os.path.getsize(PROCESSED_DB_PATH) == 0:
                return {}
            with open(PROCESSED_DB_PATH, "r") as f:
                return json.load(f)
        except Exception as e:
            print("Error loading processed_data.json:", e)
            return {}
    return {}

def update_processed_db(junction_id, record):
    db = load_processed_db()
    db[junction_id] = record
    try:
        with open(PROCESSED_DB_PATH, "w") as f:
            json.dump(db, f, indent=4)
    except Exception as e:
        print("Error writing to processed_data.json:", e)
