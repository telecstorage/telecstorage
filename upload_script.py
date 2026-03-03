import os
import asyncio
import json
from pyrogram import Client

# Fetching the secrets
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))

async def main():
    async with Client("my_account", session_string=SESSION_STRING, api_id=API_ID, api_hash=API_HASH) as app:
        print("Log in successful!")

        # --- THE CONNECTION FIX ---
        # We force the app to "see" the channel first
        try:
            chat = await app.get_chat(CHANNEL_ID)
            print(f"Connected to Channel: {chat.title}")
        except Exception as e:
            print(f"Resolving channel via dialogs...")
            async for dialog in app.get_dialogs():
                if dialog.chat.id == CHANNEL_ID:
                    print(f"Found: {dialog.chat.title}")
                    break

        # Finding the downloaded movie
        files = [f for f in os.listdir('.') if f.endswith(('.mp4', '.mkv', '.zip'))]
        if not files:
            print("No movie file found!")
            return

        movie_file = files[0]
        print(f"Uploading {movie_file}...")
        
        # Uploading to Telegram
        msg = await app.send_document(
            chat_id=CHANNEL_ID,
            document=movie_file,
            caption=f"🎥 **New Upload:** `{movie_file}`\n🚀 Status: Beastly Complete"
        )
        print(f"Upload Done! Message ID: {msg.id}")

        # --- DATABASE LOGIC ---
        new_entry = {
            "title": movie_file.replace(".mp4", "").replace(".mkv", ""),
            "msg_id": msg.id,
            "file_name": movie_file
        }

        db_file = "database.json"
        if os.path.exists(db_file):
            with open(db_file, "r") as f:
                try:
                    db = json.load(f)
                except:
                    db = []
        else:
            db = []

        db.append(new_entry)
        with open(db_file, "w") as f:
            json.dump(db, f, indent=4)
        print("Database updated!")

if __name__ == "__main__":
    asyncio.run(main())
