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

        # Step 1: Meet the channel
        try:
            await app.get_chat(CHANNEL_ID)
        except:
            async for dialog in app.get_dialogs():
                if dialog.chat.id == CHANNEL_ID: break

        # Step 2: Find all video files in the downloads folder
        download_path = "./downloads"
        files = []
        for root, dirs, filenames in os.walk(download_path):
            for f in filenames:
                if f.endswith((".mp4", ".mkv")):
                    files.append(os.path.join(root, f))

        if not files:
            print("No videos found in torrent!")
            return

        db_file = "database.json"
        db = []
        if os.path.exists(db_file):
            with open(db_file, "r") as f: db = json.load(f)

        # Step 3: Upload each file one by one
        for movie_path in files:
            name = os.path.basename(movie_path)
            print(f"Uploading {name}...")
            
            msg = await app.send_video(
                chat_id=CHANNEL_ID,
                video=movie_path,
                supports_streaming=True,
                caption=f"🎥 **Episode:** `{name}`"
            )

            db.append({
                "title": name,
                "msg_id": msg.id,
                "file_name": name
            })

        # Step 4: Save database
        with open(db_file, "w") as f:
            json.dump(db, f, indent=4)
        print("All episodes uploaded and database updated!")

if __name__ == "__main__":
    asyncio.run(main())
