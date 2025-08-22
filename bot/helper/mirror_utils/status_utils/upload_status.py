from .status import Status
from bot.helper.ext_utils.bot_utils import MirrorStatus, get_readable_file_size, get_readable_time
from bot import DOWNLOAD_DIR

class UploadStatus(Status):
    def __init__(self, obj, size, listener):
        self.obj = obj
        self.__size = size
        self.uid = listener.uid
        self.message = listener.message
        self.upload_type = getattr(obj, "upload_type", "gdrive")

    def path(self):
        return f"{DOWNLOAD_DIR}{self.uid}"

    def processed_bytes(self):
        return getattr(self.obj, "uploaded_bytes", 0)

    def size_raw(self):
        return self.__size

    def size(self):
        return get_readable_file_size(self.__size)

    def status(self):
        if self.upload_type == "telegram":
            return "TGUPLOADING"
        return MirrorStatus.STATUS_UPLOADING

    def name(self):
        return getattr(self.obj, "name", "unknown")

    def progress_raw(self):
        try:
            return self.processed_bytes() / self.__size * 100
        except ZeroDivisionError:
            return 0

    def progress(self):
        return f'{round(self.progress_raw())}%'

    def speed_raw(self):
        return getattr(self.obj, "speed", lambda: 0)()

    def speed(self):
        return f'{get_readable_file_size(self.speed_raw())}ps'

    def eta(self):
        try:
            seconds = (self.__size - self.processed_bytes()) / (self.speed_raw() or 1)
            return f'{get_readable_time(seconds)}'
        except ZeroDivisionError:
            return '-'

    def completed(self):
        return None        

    def isgdfolder(self):
        return None

    def genid(self):
        return None      

    def which_client(self):
        if self.upload_type == "telegram":
            return "TGUP"
        return "GDRIVEUP"

    def seeds(self):
        return None

    def leechers(self):
        return None