from bot import aria2, DOWNLOAD_DIR, LOGGER
from bot.helper.ext_utils.bot_utils import MirrorStatus, get_readable_file_size, get_readable_time, get_readable_time_status
from .status import Status


def get_download(gid):
    return aria2.get_download(gid)


class AriaDownloadStatus(Status):

    def __init__(self, gid, listener):
        super().__init__()
        self.upload_name = None
        self.is_archiving = False
        self.__gid = gid
        self.__genid = listener.genid
        self.__download = get_download(self.__gid)
        self.__uid = listener.uid
        self.__listener = listener
        self.message = listener.message
        self.last = None
        self.is_waiting = False
        self.is_extracting = False
        self.source = listener.source

    def __update(self):
        self.__download = get_download(self.__gid)

    def sourcemsg(self):
        return self.source

    def progress(self):
        """
        Calculates the progress of the mirror (upload or download)
        :return: returns progress in percentage
        """
        self.__update()
        return self.__download.progress_string(0)

    def size_raw(self):
        """
        Gets total size of the mirror file/folder
        :return: total size of mirror
        """
        return self.aria_download().total_length

    def processed_bytes(self):
        return self.aria_download().completed_length

    def speed(self):
        return f'{get_readable_file_size(self.aria_download().download_speed)}ps'

    def speed_raw(self):
        return self.aria_download().download_speed

    def name(self):
        return self.aria_download().name

    def path(self):
        return f"{DOWNLOAD_DIR}{self.__uid}"

    def size(self):
        return f'{get_readable_file_size(self.aria_download().total_length)}'

    def eta(self):
        return f'{get_readable_time_status(self.aria_download().total_length, self.aria_download().completed_length, self.aria_download().download_speed)}'


    def status(self):
        download = self.aria_download()
        if download.is_waiting:
            status = MirrorStatus.STATUS_WAITING
        elif download.is_paused:
            status = MirrorStatus.STATUS_CANCELLED
        elif download.has_failed:
            status = MirrorStatus.STATUS_FAILED
        else:
            status = MirrorStatus.STATUS_DOWNLOADING
        return status

    def aria_download(self):
        self.__update()
        return self.__download

    def download(self):
        return self

    def updateName(self,name):
        self.__name = name

    def updateGid(self,gid):
        self.__gid = gid

    def getListener(self):
        return self.__listener
    
    def uid(self):
        return self.__uid

    def gid(self):
        self.__update()
        return self.__genid

    def genid(self):
        self.__update()
        return self.__gid


    def completed(self):
        return None      

    def isgdfolder(self):
        return None

    def seeds(self):
        return None

    def leechers(self):
        return None

    def cancel_download(self):
        LOGGER.info(f"Cancelling Download: {self.name()}")
        download = self.aria_download()
        if download.is_waiting:
            aria2.remove([download])
            self.__listener.onDownloadError("Cancelled by user")
            return
        if len(download.followed_by_ids) != 0:
            downloads = aria2.get_downloads(download.followed_by_ids)
            aria2.pause(downloads)
        aria2.pause([download])

    def which_client(self):
        return "ARIA2"  

    def upload_path(self):
        return f'{DOWNLOAD_DIR}{self.__uid}/{self.name()}'


