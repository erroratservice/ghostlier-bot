import os
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

    def _upload_progress(self, current, total):
        self.uploaded_bytes = current
        # Optionally, implement speed calculation if needed
        if hasattr(self.listener, "onUploadProgress"):
            self.listener.onUploadProgress(current, total)

    def speed(self):
        return self._speed

    def upload(self):
        import time
        self._start_time = time.time()
        try:
            sent_msg = None
            ext = os.path.splitext(self.path)[1].lower()
            is_video = ext in [".mp4", ".mkv", ".webm"]
            is_audio = ext in [".mp3", ".wav", ".ogg", ".flac"]
            is_image = ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]

            thumb_arg = self.thumbnail if self.thumbnail else None
            caption = self.name

            # Debug
            print(f"[DEBUG] TelegramUploader.upload() file: {self.path}, as_document: {self.as_document}, thumb: {thumb_arg}")

            # Synchronous send methods
            if not self.as_document and is_video:
                sent_msg = self.client.send_video(
                    chat_id=self.chat_id,
                    video=self.path,
                    caption=caption,
                    thumb=thumb_arg,
                    progress=self._upload_progress,
                )
            elif not self.as_document and is_audio:
                sent_msg = self.client.send_audio(
                    chat_id=self.chat_id,
                    audio=self.path,
                    caption=caption,
                    thumb=thumb_arg,
                    progress=self._upload_progress,
                )
            elif not self.as_document and is_image:
                sent_msg = self.client.send_photo(
                    chat_id=self.chat_id,
                    photo=self.path,
                    caption=caption,
                    progress=self._upload_progress,
                )
            else:
                sent_msg = self.client.send_document(
                    chat_id=self.chat_id,
                    document=self.path,
                    caption=caption,
                    thumb=thumb_arg,
                    progress=self._upload_progress,
                )

            completion_message = f"Telegram upload finished: {self.name}"
            try:
                self.client.send_message(
                    chat_id=self.listener.message.chat.id,
                    text=completion_message,
                    reply_to_message_id=self.listener.message.id
                )
            except Exception as e:
                print(f"[DEBUG] Failed to send completion message: {e}")

            if hasattr(self.listener, "onUploadComplete"):
                self.listener.onUploadComplete()

        except FloodWait as e:
            print(f"[DEBUG] FloodWait: Sleeping for {e.value} seconds")
            import time as _time
            _time.sleep(e.value)
            self.upload()
        except Exception as e:
            print(f"[ERROR] Exception during Telegram upload: {e}")
            if hasattr(self.listener, "onUploadError"):
                self.listener.onUploadError(str(e))
