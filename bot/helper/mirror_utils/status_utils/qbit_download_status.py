from bot import aria2, DOWNLOAD_DIR, LOGGER
from bot.helper.ext_utils.bot_utils import MirrorStatus, get_readable_file_size, get_readable_time, get_readable_time_status
from .status import Status
from datetime import datetime

class QBTask(Status):
    def __init__(self, obj, listener, torrent, message, client):
        self.uid = listener.uid
        self.listener = listener
        self.obj = obj
        self.message = listener.message
        self.source = listener.source
        self.hash = torrent.hash
        self._torrent = torrent
        self._message = message
        self._client = client
        self._active = True
        self._path = torrent.save_path
        self._error = ""
        self._done = False
        self.cancel = False
        self._omess = None
        self._prevmsg = ""
    
    def set_path(self, path):
        self._path = path

    def gid(self):
        return self.obj.gid

    def sourcemsg(self):
        return self.source

    def path(self):
        return self._path

    def name(self):
        return self._torrent.name

    def processed_bytes(self):
        return self._torrent.downloaded

    def size_raw(self):
        return self._torrent.total_size

    def size_raw_progress(self):
        return self.obj.size

    def getListener(self):
        return self.listener

    def size(self):
        return get_readable_file_size(self._torrent.total_size)

    def totalsize(self):
        return get_readable_file_size(self._torrent.total_size) 

    def currentsize(self):
        return get_readable_file_size(self.obj.size)


    def status(self):
        if self._torrent.state == "stalledDL" or self._torrent.state == "stalledUP":
            return MirrorStatus.STATUS_STALLED
        #meta stage
        elif self._torrent.state == "metaDL":
            return MirrorStatus.STATUS_FETCHING_METADATA
        elif self._torrent.state == "queuedDL" or self._torrent.state == "queuedUP":
            return MirrorStatus.STATUS_WAITING
        elif self._torrent.state == "downloading":
            return MirrorStatus.STATUS_DOWNLOADING
        elif self._torrent.state == "allocating":
            return MirrorStatus.STATUS_ALLOCATING
        elif self._torrent.state == "checkingDL" or self._torrent.state == "checkingUP" or self._torrent.state == "checkingResumeData":
            return MirrorStatus.STATUS_CHECKING
        elif self._torrent.state == "forcedDL" or self._torrent.state == "forcedUP" or self._torrent.state == "forcedMetaDL":
            return MirrorStatus.STATUS_FORCED
        elif self._torrent.state == "pausedDL" or self._torrent.state == "pausedUP":
            return MirrorStatus.STATUS_PAUSED
        elif self._torrent.state == "uploading":
            return MirrorStatus.STATUS_SEEDING
        else:
            return MirrorStatus.STATUS_UNKNOWN

    def progress_raw(self):
        try:
            return self._torrent.downloaded / self._torrent.total_size * 100
        except ZeroDivisionError:
            return 0

    def downloaded_bytes(self):
        return get_readable_file_size(self._torrent.downloaded)                    

    def downloadingname(self):
        return self.obj.currentname          

    def progress(self):
        return f'{round(self.progress_raw())}%'

    def speed_raw(self):
        """
        :return: Upload speed in Bytes/Seconds
        """
        return self._torrent.dlspeed

    def isgdfolder(self):
        return None  

    def speed(self):
        return f'{get_readable_file_size(self.speed_raw())}ps'

    def download(self):
        return self    

    def eta(self):
        try:
            seconds = (self._torrent.total_size - self._torrent.downloaded) / self.speed_raw()
            return f'{get_readable_time(seconds)}'
        except ZeroDivisionError:
            return '-'

    def completed(self):
        return None       

    def cancel_download(self):
        LOGGER.info(f'Cancelling Qbitdownload on user request')
        self._client.torrents_delete(torrent_hashes=self._torrent.hash,delete_files=True)
        self.obj.cancel_download()

    def genid(self):
        return None  

    def seeds(self):
        return self._torrent.num_seeds

    def leechers(self):
        return self._torrent.num_leechs

    def refresh_info(self, torrent = None):
        if torrent is None:
            self._torrent = self._client.torrents_info(torrent_hashes=self._torrent.hash)
            LOGGER.info(self._torrent)
        else:
            self._torrent = torrent

    async def set_inactive(self, error=None):
        self._active = False
        if error is not None:
            self._error = error

    async def is_active(self):
        return self._active

    def get_state(self):
        #stalled
        if self._torrent.state == "stalledDL":
            return"Torrent <code>{}</code> is stalled(waiting for connection) temporarily.".format(self._torrent.name)
        #meta stage
        elif self._torrent.state == "metaDL":
            return  "Getting metadata for {} - {}".format(self._torrent.name,datetime.now().strftime("%H:%M:%S"))
        elif self._torrent.state == "downloading" or self._torrent.state.lower().endswith("dl"):
            # kept for past ref
            return None

    def which_client(self):
        return "Qbit"

    def upload_path(self):
        return self._path