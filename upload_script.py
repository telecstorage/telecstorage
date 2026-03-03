import os
import asyncio
import json
from pyrogram import Client

API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))

async def main():
    async with Client("my_account", session_string=SESSION_STRING, api_id=API_ID, api_hash=API_HASH) as app:
        files = [f for f in os.listdir('.') if f.endswith(('.mp4', '.mkv'))]
        if not files: return

        movie_name = files[0]
        print(f"Uploading {movie_name}...")
        
        # Upload
        msg = await app.send_document(chat_id=CHANNEL_ID, document=movie_name)
        
        # --- NEW: SAVE DATA FOR THE UI ---
        movie_data = {
            "title": movie_name.replace(".mp4", "").replace(".mkv", ""),
            "msg_id": msg.id,
            "size": os.path.getsize(movie_name)
        }

        # Load existing database or create new
        db_file = "database.json"
        if os.path.exists(db_file):
            with open(db_file, "r") as f:
                db = json.load(f)
        else:
            db = []

        db.append(movie_data)
        with open(db_file, "w") as f:
            json.dump(db, f, indent=4)
        
        print(f"Successfully added {movie_name} to database.json")

if __name__ == "__main__":
    asyncio.run(main())
