import os
import asyncio
from pyrogram.errors import FloodWait, RPCError, BadRequest

class TelegramUploader:
    def __init__(self, client, chat_id, listener, path, as_document=True, thumbnail=None):
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
        self.as_document = as_document
        self.thumbnail = thumbnail  # Should be file_id or file path

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
            sent_msg = None
            # Decide file type by extension if not forced as document
            ext = os.path.splitext(self.path)[1].lower()
            is_video = ext in [".mp4", ".mkv", ".webm"]
            is_audio = ext in [".mp3", ".wav", ".ogg", ".flac"]
            is_image = ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]

            # Handle thumbnail (it can be file_id or a file path)
            thumb_arg = None
            if self.thumbnail:
                # If it's a file_id, pass directly. If it's a local file, download/open it.
                thumb_arg = self.thumbnail

            if not self.as_document and is_video:
                sent_msg = await self.client.send_video(
                    chat_id=self.chat_id,
                    video=self.path,
                    caption=self.name,
                    thumb=thumb_arg,
                    progress=self._upload_progress,
                )
            elif not self.as_document and is_audio:
                sent_msg = await self.client.send_audio(
                    chat_id=self.chat_id,
                    audio=self.path,
                    caption=self.name,
                    thumb=thumb_arg if thumb_arg else None,
                    progress=self._upload_progress,
                )
            elif not self.as_document and is_image:
                sent_msg = await self.client.send_photo(
                    chat_id=self.chat_id,
                    photo=self.path,
                    caption=self.name,
                    progress=self._upload_progress,
                )
            else:
                # Default: send as document
                sent_msg = await self.client.send_document(
                    chat_id=self.chat_id,
                    document=self.path,
                    caption=self.name,
                    thumb=thumb_arg if thumb_arg else None,
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
