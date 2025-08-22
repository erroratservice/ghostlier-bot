from bot import aria2, MAX_TORRENT_SIZE
from bot.helper.ext_utils.bot_utils import *
from .download_helper import DownloadHelper
from bot.helper.mirror_utils.status_utils.aria_download_status import AriaDownloadStatus
from bot.helper.ext_utils.fs_utils import clean_download
from bot.helper.mirror_utils.upload_utils.gdriveTools import GoogleDriveHelper
from bot.helper.telegram_helper.message_utils import *
from bot.helper.ext_utils.bot_utils import *
import threading
from aria2p import API
from time import sleep
from telegraph import Telegraph


class AriaDownloadHelper(DownloadHelper):

    def __init__(self):
        super().__init__()

    @new_thread
    def __onDownloadStarted(self, api: API, gid):
        LOGGER.info(f"onDownloadStart: {gid}")  
        sleep(2)
        # dl = getDownloadByaria2Gid(gid)
        # download = api.get_download(gid)
        # gdrive = GoogleDriveHelper(None)
        # msg = gdrive.search_drives(download)
        # if msg:   
        #     response = Telegraph(access_token=TELEGRAPH_TOKEN).create_page(
        #                         title = 'ShiNobi Drive',
        #                         author_name='ShiNobi-Ghost',
        #                         html_content=msg
        #                         )['path']
        #     telegraph = f"Search Results for {download}👇\nhttps://telegra.ph/{response}"
        #     if dl: dl.getListener().onDownloadAlreadyComplete(f"{telegraph}")
        #     aria2.remove([download])
        #     sleep(2)        
        sleep(2)    
        LOGGER.info(f"Size is {download.total_length}") 
        allowed_size = int(MAX_TORRENT_SIZE) * 1024 * 1024 * 1024
        if download.total_length > allowed_size:
            maxsize = f"Max Size Currently Allowed is <b>{get_readable_file_size(allowed_size)}</b> and Your Download Size is <b>{get_readable_file_size(download.total_length)}</b>.\n<b>Thus Downlaod Stopped</b>"
            if dl: dl.getListener().onMaxSize(f"{maxsize}")
            aria2.remove([download]) 
        update_all_messages()

    def __onDownloadComplete(self, api: API, gid):
        LOGGER.info(f"onDownloadComplete: {gid}")
        dl = getDownloadByaria2Gid(gid)
        download = api.get_download(gid)
        if download.followed_by_ids:
            new_gid = download.followed_by_ids[0]
            new_download = api.get_download(new_gid)
            with download_dict_lock:
                download_dict[dl.uid()] = AriaDownloadStatus(new_gid, dl.getListener())
                if new_download.is_torrent:
                    download_dict[dl.uid()].is_torrent = True
            update_all_messages()
            LOGGER.info(f'Changed gid from {gid} to {new_gid}')
        else:
            if dl: threading.Thread(target=dl.getListener().onDownloadComplete).start()

    @new_thread
    def __onDownloadPause(self, api, gid):
        LOGGER.info(f"onDownloadPause: {gid}")
        dl = getDownloadByaria2Gid(gid)
        dl.getListener().onDownloadError('Download stopped by user!')

    @new_thread
    def __onDownloadStopped(self, api, gid):
        LOGGER.info(f"onDownloadStop: {gid}")
        dl = getDownloadByaria2Gid(gid)
        if dl: dl.getListener().onTorrentDeadError('<b>Your torrent have no seeders</b>. Download Stopped!\n#DeadTorrent')

    @new_thread
    def __onDownloadError(self, api, gid):
        sleep(0.5) #sleep for split second to ensure proper dl gid update from onDownloadComplete
        LOGGER.info(f"onDownloadError: {gid}")
        dl = getDownloadByaria2Gid(gid)
        download = api.get_download(gid)
        error = download.error_message
        LOGGER.info(f"Download Error: {error}")
        if dl: dl.getListener().onDownloadError(error)

    def start_listener(self):
        aria2.listen_to_notifications(threaded=True, on_download_start=self.__onDownloadStarted,
                                      on_download_error=self.__onDownloadError,
                                      on_download_pause=self.__onDownloadPause,
                                      on_download_stop=self.__onDownloadStopped,
                                      on_download_complete=self.__onDownloadComplete)


    def add_download(self, link: str, path, listener):
        if is_magnet(link):
            download = aria2.add_magnet(link, {'dir': path})
        elif is_torrent(link):
            download = aria2.add_torrent(link, options={'dir': path})
        else:
            download = aria2.add_uris([link], {'dir': path})
        if download.error_message: #no need to proceed further at this point
            listener.onDownloadError(download.error_message)
            LOGGER.info(f"Error message {download.error_message}")
            return 
        with download_dict_lock:
            download_dict[listener.uid] = AriaDownloadStatus(download.gid,listener)
            LOGGER.info(f"Started: {download.gid} DIR:{download.dir} ")


