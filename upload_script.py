import os
import asyncio
from pyrogram import Client

# Fetching the secrets
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))

async def main():
    async with Client("my_account", session_string=SESSION_STRING, api_id=API_ID, api_hash=API_HASH) as app:
        print("Log in successful!")

        # --- THE FIX STARTS HERE ---
        # We search for the channel by ID to "cache" it in the session
        print("Resolving channel ID...")
        try:
            chat = await app.get_chat(CHANNEL_ID)
            print(f"Connected to: {chat.title}")
        except Exception as e:
            print(f"Error finding channel: {e}")
            # Alternative: If it still fails, we list all chats to find it
            async for dialog in app.get_dialogs():
                if dialog.chat.id == CHANNEL_ID:
                    print(f"Found channel in dialogs: {dialog.chat.title}")
                    break
        # --- THE FIX ENDS HERE ---
        
        # Finding the file downloaded by the GitHub Action
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
