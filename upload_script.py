import os
import asyncio
from pyrogram import Client

# Fetching the secrets we just added to GitHub
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))

async def main():
    # Logging in using the Session String
    async with Client("my_account", session_string=SESSION_STRING, api_id=API_ID, api_hash=API_HASH) as app:
        print("Log in successful!")
        
        # Finding the file downloaded by the GitHub Action
        # We will look for any .mp4 or .mkv file in the folder
        files = [f for f in os.listdir('.') if f.endswith(('.mp4', '.mkv', '.zip'))]
        
        if not files:
            print("No movie file found to upload!")
            return

        movie = files[0]
        print(f"Uploading {movie} to Telegram...")
        
        # Uploading the file
        msg = await app.send_document(
            chat_id=CHANNEL_ID,
            document=movie,
            caption=f"🎥 **New Upload:** `{movie}`\n🚀 Status: Beastly Complete"
        )
        print(f"Done! Message ID: {msg.id}")

if __name__ == "__main__":
    asyncio.run(main())
