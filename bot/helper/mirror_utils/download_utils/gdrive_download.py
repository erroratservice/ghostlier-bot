import os
import io
import time
import pickle
import urllib.parse as urlparse
from urllib.parse import parse_qs
import shutil
import random
import string
import re
import logging
from httplib2 import Http
from pySmartDL import SmartDL
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from google.auth.transport.requests import Request
from bot.helper.ext_utils.exceptions import ProcessCanceled
from bot.helper.telegram_helper.message_utils import *

from tenacity import *
from bot.helper.ext_utils.bot_utils import *

from bot import parent_id, DOWNLOAD_DIR, IS_TEAM_DRIVE, INDEX_URL, \
    USE_SERVICE_ACCOUNTS, download_dict, download_dict_lock, MAX_TORRENT_SIZE
from bot.helper.mirror_utils.upload_utils import gdriveTools
from bot.helper.mirror_utils.status_utils.gdrivedownload_status import GDDownloadStatus
from bot.helper.telegram_helper.bot_commands import BotCommands


global_lock = threading.Lock()
GLOBAL_GID = set()


LOGGER = logging.getLogger(__name__)
logging.getLogger('googleapiclient.discovery').setLevel(logging.ERROR)


class GDdownload:
    def __init__(self, name=None, listener=None):
        super().__init__()
        self.__G_DRIVE_TOKEN_FILE = "token.pickle"
        # Check https://developers.google.com/drive/scopes for all available scopes
        self.__OAUTH_SCOPE = ["https://www.googleapis.com/auth/drive",
                              "https://www.googleapis.com/auth/drive.file",
                              "https://www.googleapis.com/auth/drive.metadata"]
        # Redirect URI for installed apps, can be left as is
        self.__REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"
        self.__G_DRIVE_DIR_MIME_TYPE = "application/vnd.google-apps.folder"
        self.__G_DRIVE_BASE_DOWNLOAD_URL = "https://drive.google.com/uc?id={}&export=download"
        self.__G_DRIVE_DIR_BASE_DOWNLOAD_URL = "https://drive.google.com/drive/folders/{}"
        self.__listener = None
        self.__service = gdriveTools.GoogleDriveHelper().authorize()
        self._parent_id = parent_id
        self.completed = 0
        self.list = 1
        self._progress = None
        self._output = None
        self._is_canceled = False
        self._is_finished = False
        self._file_downloaded_bytes = 0
        self.uploaded_bytes = 0
        self.UPDATE_INTERVAL = 5
        self.start_time = 0
        self.total_time = 0
        self.size = 0
        self.updater = None
        self.eta = None
        self.update_interval = 3
        self.__resource_lock = threading.RLock()
        self.name = None
        self.currentname = None
        self.__gid = ''
        self._should_update = True
        self.__listener = listener
        self.status = None
        self.isfolder = False
        self.completed_bytes = 0
        self.gdfoldersize = 0
        self.sfile = 0
        self.sfolder = 0

    @property
    def gid(self):
        with self.__resource_lock:
            return self.__gid    

    def _cancel(self) -> None:
        self._is_canceled = True
        self._is_finished = False

    def _finish(self) -> None:
        self._is_finished = True


    def speed(self):
        """
        It calculates the average upload speed and returns it in bytes/seconds unit
        :return: Upload speed in bytes/second
        """
        try:
            return self.uploaded_bytes / self.total_time
        except ZeroDivisionError:
            return 0    

    def __onDownloadStart(self, name, file_id, listener):
        if name.find("/"):
            name = name.replace("/", "~")
        gid = ''.join(random.SystemRandom().choices(string.ascii_letters + string.digits, k=4))
        with download_dict_lock:
            download_dict[listener.uid] = GDDownloadStatus(self, listener)
        with global_lock:
            GLOBAL_GID.add(file_id)
        with self.__resource_lock:
            self.name = name
            self.__gid = gid
        listener.onDownloadStarted()


    def add_download(self, link: str, path, listener):
        if (listener.isZip or listener.isTar or listener.extract):
            try:
                total, used, free = shutil.disk_usage('.')
                fileId = self.getIdFromUrl(link)
                self.__listener = listener
                meta = self.getFileMetadata(fileId)
                if meta:
                    showaf = f"<b>Calculating Google Drive Folder/File Size</b>\n<i>Please Wait...... :3</i>"
                    sizemsg = sendMessage(showaf,listener.bot,listener.update)
                    msg = self.gdrivesize(meta)
                    deleteMessage(sizemsg)
                    sizemsg = sendMessage(msg,listener.bot,listener.update)
                    allowed_size = int(MAX_TORRENT_SIZE) * 1024 * 1024 * 1024
                    if meta.get('mimeType') == self.__G_DRIVE_DIR_MIME_TYPE and listener.extract:
                        maxsize = f"<b>Folders cannot be extracted.</b>\n<b>Thus Downlaod Stopped</b>"
                        sendMessage(maxsize, listener.bot, listener.update)
                        return
                    elif meta.get('mimeType') != self.__G_DRIVE_DIR_MIME_TYPE and listener.isZip:
                        maxsize = f"<b>Single Files won't be Zipped.</b>\n<b>Thus Downlaod Stopped</b>"
                        sendMessage(maxsize, listener.bot, listener.update)
                        return
                    elif meta.get('mimeType') != self.__G_DRIVE_DIR_MIME_TYPE and listener.isTar:
                        maxsize = f"<b>Single Files won't be Zipped.</b>\n<b>Thus Downlaod Stopped</b>"
                        sendMessage(maxsize, listener.bot, listener.update)
                        return
                    if self.gdfoldersize > allowed_size:
                        maxsize = f"Max Size Currently Allowed is <b>{get_readable_file_size(allowed_size)}</b> and Your Download Size is <b>{get_readable_file_size(self.gdfoldersize)}</b>.\n<b>Thus Downlaod Stopped</b>"
                        sendMessage(maxsize, listener.bot, listener.update)
                        return
                    elif self.gdfoldersize > free:
                        sendMessage(f"<b>Not Enough Free Space on device</b>\n#gddiskfull",listener.bot,listener.update)
                        return
                    else:
                        self.__onDownloadStart(meta.get('name'), fileId, listener)
                        self._download(fileId, path)
                        update_all_messages()
            except HttpError as err:
                error = (f"<b>HttpError {err.resp.status}</b>\n{err._get_reason()}")
                self.__onDownloadError(str(error)) 
        else:
            #clone them!
            msg = sendMessage(f"Cloning: <code>{link}</code>",listener.bot,listener.update)    
            gd = gdriveTools.GoogleDriveHelper()
            result, button = gd.clone(link, listener.update)
            deleteMessage(msg)
            if button == "":
                sendMessage(result,listener.bot,listener.update)
            else:
                sendMarkup(result,listener.bot,listener.update,button)   

    def cancel_download(self):
        LOGGER.info(f'Cancelling download on user request')
        self._is_canceled = True                

    @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(5),
           retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
    def getFileMetadata(self,file_id):
        try:
            return self.__service.files().get(supportsAllDrives=True, fileId=file_id,
                                              fields="name,id,mimeType,size").execute()      
        except HttpError as err:
            LOGGER.info(f"err is {err.resp.status} and {err._get_reason()}")
            error = (f"<b>HttpError {err.resp.status}</b>\n{err._get_reason()}")
            self.__onDownloadError(str(error))                                                                   

    @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(5),
           retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
    def _download(self, file_id: str, localpath) -> None:
        try:
            drive_file = self.__service.files().get(fileId=file_id, fields="id, name, mimeType",
                                                supportsTeamDrives=True).execute()
            self.start_time = time.time()
            self.updater = setInterval(self.update_interval, self._on_download_progress)                                    
            if drive_file['mimeType'] == self.__G_DRIVE_DIR_MIME_TYPE:
                self.isfolder = True
                if not os.path.exists(localpath):
                    os.mkdir(localpath)
                path = self._create_server_dir(localpath, drive_file['name'])
                self._download_dir(path, **drive_file)
            else:
                if not os.path.exists(localpath):
                    os.mkdir(localpath)
                self._download_file(localpath, **drive_file)
            self._output = os.path.join(localpath, drive_file['name'])
        except HttpError as err:
            error = (f"<b>HttpError {err.resp.status}</b>\n{err._get_reason()}")
            self.__onDownloadError(str(error)) 
        except ProcessCanceled:
            self.__onDownloadError("<b>GDrive Download Stopped.</b>")
        finally:
                self.updater.cancel()
                self.__onDownloadComplete()

    def __onDownloadError(self, error):
        with global_lock:
            try:
                GLOBAL_GID.remove(self.gid)
            except KeyError:
                pass
        self.__listener.onDownloadError(error)

    def __onDownloadComplete(self):
        self.__listener.onDownloadComplete()    


    def _download_dir(self, path: str, **kwargs) -> None:
        if self._is_canceled:
            raise ProcessCanceled
        files = self._list_drive_dir(kwargs['id'])
        if len(files) == 0:
            return
        self.list += len(files)
        for file_ in files:
            if file_['mimeType'] == self.__G_DRIVE_DIR_MIME_TYPE:
                path_ = self._create_server_dir(path, file_['name'])
                self._download_dir(path_, **file_)
            else:
                self._download_file(path, **file_)
                

    def _create_server_dir(self, current_path: str, folder_name: str) -> str:
        folder_name = folder_name.replace("/" , "~")
        path = str(os.path.join(current_path, folder_name))
        if not os.path.exists(path):
            os.mkdir(path)
        LOGGER.info("Created Folder => Name: %s", folder_name)
        self.completed += 1
        return path


    def _on_download_progress(self):
        if self.status is not None:
            self.size = self.status.total_size
            chunk_size = self.status.total_size * self.status.progress() - self._file_downloaded_bytes
            self._file_downloaded_bytes = self.status.total_size * self.status.progress()
            LOGGER.debug(f'Downloading {self.name}, chunk size: {get_readable_file_size(chunk_size)}')
            self.uploaded_bytes += chunk_size
            self.total_time += self.update_interval


    def _list_drive_dir(self, file_id: str) -> list:
        query = f"'{file_id}' in parents and (name contains '*')"
        fields = 'nextPageToken, files(id, name, mimeType)'
        page_token = None
        page_size = 100
        files = []
        while True:
            response = self.__service.files().list(supportsTeamDrives=True,
                                                includeTeamDriveItems=True,
                                                q=query, spaces='drive',
                                                fields=fields, pageToken=page_token,
                                                pageSize=page_size, corpora='allDrives',
                                                orderBy='folder, name').execute()
            files.extend(response.get('files', []))
            page_token = response.get('nextPageToken', None)
            if page_token is None:
                break
            if self._is_canceled:
                self.__onDownloadError("Download Has Been Cancelled Wew!")
        return files


    def _download_file(self, path: str, name: str, **kwargs) -> None:
        try:
            total, used, free = shutil.disk_usage('.')
            #free = get_readable_file_size(free)
            request = self.__service.files().get_media(fileId=kwargs['id'], supportsTeamDrives=True)
            with io.FileIO(os.path.join(path, name), 'wb') as d_f:
                d_file_obj = MediaIoBaseDownload(d_f, request, chunksize=50*1024*1024)
                self.c_time = time.time()
                self.currentname = name
                done = False
                while done is False:
                    self.status, done = d_file_obj.next_chunk(num_retries=5)
                    if self.status is not None:
                        if self.status.total_size > free:
                            raise ProcessCanceled
                    if self._is_canceled:
                        raise ProcessCanceled   
            self.completed += 1
            self.completed_bytes += self.status.total_size
        except HttpError as err:
            if "416" in str(err):
                f = open(f"{os.path.join(path, name)}", "w").close
            else:
                error = (f"<b>HttpError {err.resp.status}</b>\n{err._get_reason()}")
                self.__onDownloadError(str(error))           

    def _download_file_quota(self, path: str, name: str, file_id) -> None:
        try:
            total, used, free = shutil.disk_usage('.')
            #free = get_readable_file_size(free)
            request = self.__service.files().get_media(fileId=file_id, supportsTeamDrives=True)
            with io.FileIO(os.path.join(path, name), 'wb') as d_f:
                d_file_obj = MediaIoBaseDownload(d_f, request, chunksize=50*1024)
                self.c_time = time.time()
                self.currentname = name
                done = False
                while done is False:
                    self.status, done = d_file_obj.next_chunk(num_retries=5)
                    if self.status is not None:
                        return False 
        except HttpError as err:
            if "download quota" in str(err._get_reason()):
                LOGGER.info(f"CAlled Download Quota! True")
                return True
            else:
                error = (f"<b>HttpError {err.resp.status}</b>\n{err._get_reason()}")
                LOGGER.info(f"error in else block {error}")
                return False
                self.__onDownloadError(str(error))  

    @staticmethod
    def getIdFromUrl(link: str):
        if "folders" in link or "file" in link:
            regex = r"https://drive\.google\.com/(drive)?/?u?/?\d?/?(mobile)?/?(file)?(folders)?/?d?/([-\w]+)[?+]?/?(w+)?"
            res = re.search(regex,link)
            if res is None:
                raise IndexError("GDrive ID not found.")
            return res.group(5)
        parsed = urlparse.urlparse(link)
        return parse_qs(parsed.query)['id'][0]   


    @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(5),
           retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
    def getFilesByFolderId(self,folder_id):
        page_token = None
        q = f"'{folder_id}' in parents"
        files = []
        while True:
            response = self.__service.files().list(supportsTeamDrives=True,
                                                   includeTeamDriveItems=True,
                                                   q=q,
                                                   spaces='drive',
                                                   pageSize=200,
                                                   fields='nextPageToken, files(id, name, mimeType,size)',
                                                   pageToken=page_token).execute()
            for file in response.get('files', []):
                files.append(file)
            page_token = response.get('nextPageToken', None)
            if page_token is None:
                break
        return files     
            
    @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(5),
           retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
    def gdrivesize(self, meta) -> str:
        self.computed_size = 0
        try:
            if meta.get("mimeType") == self.__G_DRIVE_DIR_MIME_TYPE:
                size = self.foldersize(meta.get('id'))
                self.sfolder += 1
            else:
                self.computed_size = int(meta.get('size'))
                self.sfile += 1
            self.gdfoldersize = self.computed_size
            size_wrapper = f"uri added ⚡️\nYou May Want to Check Out /{BotCommands.StatusCommand[0]}\n\n<code>{meta.get('name')}</code>\n<b>Folders/Files</b>: {self.sfolder} / {self.sfile}\n<b>Size:</b> {get_readable_file_size(self.gdfoldersize)}"
            return size_wrapper
        except HttpError as err:
            LOGGER.info(f"Error {err}")

    @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(5),
           retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
    def foldersize(self, folder_id):
        files = self.getFilesByFolderId(folder_id)
        if len(files) == 0:
            return 0
        for file in files:
            if file.get('mimeType') == self.__G_DRIVE_DIR_MIME_TYPE:
                size = self.foldersize(file.get('id'))
                self.sfolder += 1
            else:
                try:
                    self.computed_size += int(file.get('size'))
                    self.sfile += 1
                except TypeError:
                    pass       
        return self.computed_size    

    def getsizehandle(self, client, message, link):
        try:
            fileId = self.getIdFromUrl(link)
            meta = self.__service.files().get(supportsAllDrives=True, fileId=fileId,
                                              fields="name,id,mimeType,size").execute() 
            showaf = f"<b>Calculating Google Drive Folder/File Size</b>\n<i>Please Wait...... :3</i>"
            sizemsg = sendMessage(showaf,client, message)
            size = self.gdrivesizeforhandler(meta)
            deleteMessage(sizemsg)
            sizemsg = sendMessage(size,client, message)
        except HttpError as err:
            error = (f"<b>HttpError {err.resp.status}</b>\n{err._get_reason()}")
            sendMessage(error , client, message)


    @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(5),
        retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
    def gdrivesizeforhandler(self, meta) -> str:
        self.computed_size = 0
        try:
            if meta.get("mimeType") == self.__G_DRIVE_DIR_MIME_TYPE:
                size = self.foldersize(meta.get('id'))
                self.sfolder += 1
            else:
                self.computed_size = int(meta.get('size'))
                self.sfile += 1
            size_wrapper = f"<code>{meta.get('name')}</code>\n<b>Folders/Files</b>: {self.sfolder} / {self.sfile}\n<b>Size</b> {get_readable_file_size(self.computed_size)}"
            return size_wrapper
        except HttpError as err:
            LOGGER.info(f"Error {err}")
 
              

                        