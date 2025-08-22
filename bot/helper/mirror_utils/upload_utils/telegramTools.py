from pyrogram import Client
import os
import asyncio
class TelegramUploadHelper:
    def __init__(self, client: Client, chat_id: int, listener=None):
        self.client = client
        self.chat_id = chat_id
        self.listener = listener

    async def upload_file(self, file_path: str, caption: str = None):
        if self.listener:
            self.listener.onUploadStarted()
        try:
            await self.client.send_document(
                chat_id=self.chat_id,
                document=file_path,
                caption=caption or os.path.basename(file_path)
            )
            if self.listener:
                self.listener.onUploadComplete(f"Sent to Telegram: {file_path}")
        except Exception as e:
            if self.listener:
                self.listener.onUploadError(str(e))