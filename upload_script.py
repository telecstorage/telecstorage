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
        print("Log in successful!")

        # Resolve channel
        try:
            await app.get_chat(CHANNEL_ID)
        except:
            async for dialog in app.get_dialogs():
                if dialog.chat.id == CHANNEL_ID: break

        files = [f for f in os.listdir('.') if f.endswith(('.mp4', '.mkv'))]
        if not files: return

        movie_file = files[0]
        print(f"Uploading {movie_file} with Streaming Support...")
        
        # CHANGED: send_video instead of send_document for instant playback
        msg = await app.send_video(
            chat_id=CHANNEL_ID,
            video=movie_file,
            supports_streaming=True, # This is the "Golden Ticket" for streaming
            caption=f"🎥 **New Upload:** `{movie_file}`\n🚀 Status: Beastly Complete"
        )
        print(f"Upload Done! Message ID: {msg.id}")

        # Update database.json
        new_entry = {
            "title": movie_file.replace(".mp4", "").replace(".mkv", ""),
            "msg_id": msg.id,
            "file_name": movie_file
        }

        db_file = "database.json"
        db = []
        if os.path.exists(db_file):
            try:
                with open(db_file, "r") as f: db = json.load(f)
            except: pass

        db.append(new_entry)
        with open(db_file, "w") as f: json.dump(db, f, indent=4)
        print("Database updated!")

if __name__ == "__main__":
    asyncio.run(main())
