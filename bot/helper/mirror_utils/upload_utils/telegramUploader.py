import os
import asyncio
from pyrogram.errors import FloodWait, RPCError, BadRequest

class TelegramUploader:
    def __init__(self, client, chat_id, listener, path):
        self.client = client
        self.chat_id = chat_id
        self.listener = listener
        self.path = path
        self.uploaded_bytes = 0
        self._size = os.path.getsize(path)
        self.name = os.path.basename(path)
        self.upload_type = "telegram"
        self._start_time = None
        self._speed = 0

    async def _upload_progress(self, current, total):
        self.uploaded_bytes = current
        self._speed = (current / (asyncio.get_event_loop().time() - self._start_time)) if self._start_time else 0
        # Update status via listener
        if hasattr(self.listener, "onUploadProgress"):
            self.listener.onUploadProgress(current, total)

    def speed(self):
        return self._speed

    async def upload(self):
        self._start_time = asyncio.get_event_loop().time()
        try:
            await self.client.send_document(
                chat_id=self.chat_id,
                document=self.path,
                caption=self.name,
                progress=self._upload_progress,
            )

            completion_message = f"Telegram upload finished: {self.name}"
            # Use the listener's message object to reply
            await self.client.send_message(
                chat_id=self.listener.message.chat.id,
                text=completion_message,
                reply_to_message_id=self.listener.message.id
            )

            if hasattr(self.listener, "onUploadComplete"):
                self.listener.onUploadComplete()

        except FloodWait as e:
            await asyncio.sleep(e.value)
            await self.upload()
        except Exception as e:
            if hasattr(self.listener, "onUploadError"):
                self.listener.onUploadError(str(e))
