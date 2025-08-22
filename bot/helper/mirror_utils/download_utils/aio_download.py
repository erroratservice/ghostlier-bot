import aiohttp
import asyncio
from aiohttp import ClientResponseError
import cgi
import os
import io
import time
import asyncio
from json import dumps
import urllib.parse
import shutil
import random
import string
import re
import json
import requests
import logging
from httplib2 import Http
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from bot.helper.ext_utils.exceptions import ProcessCanceled
from bot.helper.telegram_helper.message_utils import *
from bot.helper.telegram_helper import button_build

from tenacity import *
from bot.helper.ext_utils.bot_utils import *

from bot import parent_id, DOWNLOAD_DIR, IS_TEAM_DRIVE, INDEX_URL, \
    USE_SERVICE_ACCOUNTS, download_dict, download_dict_lock, Interval
from bot.helper.ext_utils.bot_utils import *
from bot.helper.ext_utils.fs_utils import get_mime_type
from bot.helper.mirror_utils.upload_utils import gdriveTools
from bot.helper.mirror_utils.status_utils.aio_download_status import AioDownloadStatus
from bot.helper.telegram_helper.bot_commands import BotCommands


global_lock = threading.Lock()
GLOBAL_GID = set()


LOGGER = logging.getLogger(__name__)
logging.getLogger('googleapiclient.discovery').setLevel(logging.ERROR)


class AioHttpDownload:
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
        self.status = None
        self.isfolder = False
        self.completed_bytes = 0
        self.gdfoldersize = 0
        self.sfile = 0
        self.sfolder = 0
        self.session = None
        self.mimeType = None
        self.resumableuri = None
        self.downloaded_chunk = 0
        self.done_chunk = 0
        self.link = None
        self.gdrivelink = None

    @property
    def gid(self):
        with self.__resource_lock:
            return self.__gid    

    def _cancel(self) -> None:
        self._is_canceled = True
        self._is_finished = False

    def _finish(self) -> None:
        self._is_finished = True

    async def clean(self):
        try:
            Interval[0].cancel()
            del Interval[0]
            await delete_all_messages_async()
        except IndexError:
            pass

    def speed(self):
        """
        It calculates the average upload speed and returns it in bytes/seconds unit
        :return: Upload speed in bytes/second
        """
        try:
            return self.downloaded_chunk / self.total_time
        except ZeroDivisionError:
            return 0    

    def __onDownloadStart(self, name, size, listener):
        gid = ''.join(random.SystemRandom().choices(string.ascii_letters + string.digits, k=4))
        with download_dict_lock:
            download_dict[listener.uid] = AioDownloadStatus(self, listener)
        with global_lock:
            GLOBAL_GID.add(gid)
        with self.__resource_lock:
            self.name = name
            self.__gid = gid
        listener.onDownloadStarted()


    async def add_download(self, link: str, path, listener):
        self.__listener = listener
        async with aiohttp.ClientSession(raise_for_status = True) as self.session:
            try:
                async with self.session.get(link, allow_redirects=True) as response:    
                    #link = str(response.url)
                    LOGGER.info(f"url is {link}")
                    try:
                        content_disposition = cgi.parse_header(
                            response.headers['Content-Disposition'])
                        filename = content_disposition[1]['filename']
                        filename = urllib.parse.unquote_plus(filename)
                    except KeyError:
                        filename = response._real_url.name
                    try:
                        size = int(response.headers['Content-Length'])
                    except KeyError:
                        size = 0
                    self.size = size    
                    self.__listener = listener
                    self.mimeType = response.headers['content-type']
                    LOGGER.info(f"mimetype is {self.mimeType}")     
                    try: 
                        self.updater = setInterval(self.update_interval, self._on_download_progress)     
                        self.__onDownloadStart(filename, size, listener) 
                        self.getsessionuri()
                        self.link = link
                        await self._download(link)
                    except HttpError as err:
                        LOGGER.info(f"Http error {err}")  
            except ClientResponseError as cerr:
                    await self.onClientError(cerr.message)
                    return None


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

    async def _download(self, link) -> None:
        try:
            async with self.session.get(link) as response:
                while True:
                    if self._is_canceled == True:
                        await self.onClientError("<b>Cancelled Due To User Request</b>")
                        break
                    try:
                        chunk = await response.content.readexactly(10485760) #5mb chunk recommended is 50mb for best performace
                        self.downloaded_chunk += len(chunk)
                        await self.upload_file(chunk)
                        self.done_chunk += len(chunk)
                        if response.content.at_eof():
                            LOGGER.info("Ya and i'm done with the chunks")
                            LOGGER.info(get_readable_file_size(self.downloaded_chunk))
                            break  
                    except asyncio.IncompleteReadError as err:
                        eofchunk = err.partial
                        self.downloaded_chunk += len(eofchunk)
                        await self.upload_file(eofchunk)
                        self.done_chunk += len(eofchunk)
                        if response.content.at_eof():
                            LOGGER.info("Ya and i'm done with the chunks")
                            LOGGER.info(get_readable_file_size(self.downloaded_chunk))
                            break                           
        except ClientResponseError as cerr:   
            await self.onClientError(cerr.message)
            return None
            
        except Exception as e:
            LOGGER.info(f"{e}") 

    def __onDownloadError(self, error):
        with global_lock:
            try:
                GLOBAL_GID.remove(self.gid)
            except KeyError:
                pass
        self.__listener.onDownloadError(error)

    async def onClientError(self, error):
        uname = f'<a href="tg://user?id={self.__listener.message.from_user.id}">{self.__listener.message.from_user.first_name}</a>'
        clienterrormsg = f"{uname} Stopped cuz: {error}"
        await sendMessage(clienterrormsg, self.__listener.bot, self.__listener.update)
        with download_dict_lock:
            del download_dict[self.__listener.uid]
            count = len(download_dict)
        if count == 0:
            await self.clean()
        else:
            update_all_messages()        

    async def __onUploadComplete(self):
        uname = f'<a href="tg://user?id={self.__listener.message.from_user.id}">{self.__listener.message.from_user.first_name}</a>'
        with download_dict_lock:
            try:
                msgid = self.__listener.source.id
                chat_id = str(self.__listener.source.chat.id)
            except:    
                chat_id = str(6969) #pass random values for watch upload complete to work
            url = None    
            if chat_id.startswith('-100'):
                url = f'<a href="https://t.me/c/{chat_id[4::]}/{msgid}">Source Message 👈🏻</a>'
            if url:    
                msg = f'<b>Filename</b>: <code>{self.name}</code>\n\n<b>Size</b>: <code>{get_readable_file_size(self.size)}</code>\n\n<b>cc</b>: {uname}\n\n{url}\n<i>Join TD to Access Gdrive Links🤘🏻\nDont Share Links In Public</i>\n#Uploads❤️'
            else:
                msg = f'<b>Filename</b>: <code>{self.name}</code>\n\n<b>Size</b>: <code>{get_readable_file_size(self.size)}</code>\n\n<b>cc</b>: {uname}\n\n<i>Join TD to Access Gdrive Links🤘🏻\nDont Share Links In Public</i>\n#Uploads❤️'
            buttons = button_build.ButtonMaker()
            buttons.buildbutton("⚡GDrive Link⚡", self.gdrivelink)
            LOGGER.info(f'Done Uploading {self.name}')
            if INDEX_URL is not None:
                share_url = requests.utils.requote_uri(f'{INDEX_URL}/{self.name}')
                buttons.buildbutton("🔥Index Link🔥", share_url)
                buttons.buildbutton("❣️Join TeamDrive❣️", 'https://t.me/c/1271941524/361972')    
            del download_dict[self.__listener.uid]
            count = len(download_dict)
        await sendMarkup(msg, self.__listener.bot, self.__listener.update, InlineKeyboardMarkup(buttons.build_menu(2)))
        if count == 0:
            await self.clean()
        else:
            update_all_messages()  


    def _on_download_progress(self):
            self.total_time += self.update_interval

    @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(5),
        retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
    def __set_permission(self, drive_id):
        permissions = {
            'role': 'reader',
            'type': 'anyone',
            'value': None,
            'withLink': True
        }
        return self.__service.permissions().create(supportsTeamDrives=True, fileId=drive_id,
                                                   body=permissions).execute()


    def getsessionuri(self, **kwargs) -> None:
        try:
            file_metadata = {
            'name': self.name,
            'description': 'mirror',
            'mimeType': self.mimeType
        }
            if parent_id is not None:
                file_metadata['parents'] = [self._parent_id]

            headers = {"Authorization": "Bearer "+gdriveTools.GoogleDriveHelper().get_credentials(), "Content-Type": "application/json; charset=UTF-8"}
            r = requests.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&supportsTeamDrives=True",
            data=json.dumps(file_metadata),
            headers = headers
            )
            self.resumableuri = r.headers['Location']
            LOGGER.info(f"resumable uri is {self.resumableuri}")
        except HttpError as err:
            error = (f"<b>HttpError {err.resp.status}</b>\n{err._get_reason()}")
            LOGGER.info(error)
            self.__onDownloadError(str(error)) 

    @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(5),
           retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
    async def upload_file(self, chunk, **kwargs) -> None:
        try:
            headers = {"Content-Length": str(len(chunk)), "Content-Range": f"bytes {str(self.done_chunk)}-" + str(self.downloaded_chunk - 1) + "/" + str(self.size)}
            r = requests.put(
                self.resumableuri,
                headers=headers,
                data=chunk
            )
            if r.text:
                LOGGER.info(f"r.text is {r.text}")
                self.gdrivelink = self.__G_DRIVE_BASE_DOWNLOAD_URL.format(r.json()['id'])
                await self.__onUploadComplete()
                return r.text
            #info = json.loads(r.text.decode("utf-8"))
            #LOGGER.info(f"id is {info}")
            #self.gdrivelink = self.__G_DRIVE_BASE_DOWNLOAD_URL.format(r.json()['id'])
            #LOGGER.info(r.text)
            #LOGGER.info(f"{r.json()['id']}")
            #self.__set_permission(r.json()['id'])
        except HttpError as err:
            if "416" in str(err):
                f = open(f"{os.path.join(path, name)}", "w").close
            else:
                error = (f"<b>HttpError {err.resp.status}</b>\n{err._get_reason()}")
                LOGGER.info(f"http error is {error}")
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
            size_wrapper = f"uri added ⚡️\nYou May Want to Check Out /{BotCommands.StatusCommand}\n\n<code>{meta.get('name')}</code>\n<b>Folders/Files</b>: {self.sfolder} / {self.sfile}\n<b>Size:</b> {get_readable_file_size(self.gdfoldersize)}"
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

    def getsizehandle(self, update, context, link):
        fileId = self.getIdFromUrl(link)
        meta = self.getFileMetadata(fileId)
        showaf = f"<b>Calculating Google Drive Folder/File Size</b>\n<i>Please Wait...... :3</i>"
        sizemsg = sendMessage(showaf,context.bot,update)
        size = self.gdrivesizeforhandler(meta)
        deleteMessage(context.bot, sizemsg)
        sizemsg = sendMessage(size,context.bot,update)

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
              

#deprceated                        

# import aiohttp
# import asyncio
# from aiohttp import ClientResponseError
# import cgi
# from bot import Interval, INDEX_URL

# import os
# import io
# import time
# import math
# import pickle
# import asyncio
# from json import dumps
# from functools import wraps
# from datetime import datetime
# from mimetypes import guess_type
# import urllib.parse
# import shutil
# import random
# import string
# from time import sleep
# import re
# import json
# import requests
# import logging
# from telegram.ext import CommandHandler
# from httplib2 import Http
# from pySmartDL import SmartDL
# from googleapiclient.discovery import build
# from googleapiclient.errors import HttpError
# from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
# from google.oauth2 import service_account
# from google_auth_oauthlib.flow import InstalledAppFlow
# from google.auth.transport.requests import Request
# from bot.helper.ext_utils.exceptions import ProcessCanceled
# from bot.helper.telegram_helper.message_utils import *
# from bot.helper.telegram_helper import button_build
# from bot.helper.ext_utils.bot_utils import new_thread

# from tenacity import *
# from bot.helper.ext_utils.bot_utils import *

# from bot import parent_id, DOWNLOAD_DIR, IS_TEAM_DRIVE, INDEX_URL, \
#     USE_SERVICE_ACCOUNTS, download_dict ,TD_OLD1, TD_OLD2, download_dict_lock, Interval
# from bot.helper.ext_utils.bot_utils import *
# from bot.helper.ext_utils.fs_utils import get_mime_type
# from bot.helper.mirror_utils.upload_utils import gdriveTools
# from bot.helper.mirror_utils.status_utils.aio_download_status import AioDownloadStatus
# from bot.helper.telegram_helper.bot_commands import BotCommands


# global_lock = threading.Lock()
# GLOBAL_GID = set()


# LOGGER = logging.getLogger(__name__)
# logging.getLogger('googleapiclient.discovery').setLevel(logging.ERROR)


# class AioHttpDownload:
#     def __init__(self, name=None, listener=None):
#         super().__init__()
#         self.__G_DRIVE_TOKEN_FILE = "token.pickle"
#         # Check https://developers.google.com/drive/scopes for all available scopes
#         self.__OAUTH_SCOPE = ["https://www.googleapis.com/auth/drive",
#                               "https://www.googleapis.com/auth/drive.file",
#                               "https://www.googleapis.com/auth/drive.metadata"]
#         # Redirect URI for installed apps, can be left as is
#         self.__REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"
#         self.__G_DRIVE_DIR_MIME_TYPE = "application/vnd.google-apps.folder"
#         self.__G_DRIVE_BASE_DOWNLOAD_URL = "https://drive.google.com/uc?id={}&export=download"
#         self.__G_DRIVE_DIR_BASE_DOWNLOAD_URL = "https://drive.google.com/drive/folders/{}"
#         self.__listener = None
#         self.__service = gdriveTools.GoogleDriveHelper().authorize()
#         self._parent_id = parent_id
#         self.completed = 0
#         self.list = 1
#         self._progress = None
#         self._output = None
#         self._is_canceled = False
#         self._is_finished = False
#         self._file_downloaded_bytes = 0
#         self.uploaded_bytes = 0
#         self.UPDATE_INTERVAL = 5
#         self.start_time = 0
#         self.total_time = 0
#         self.size = 0
#         self.updater = None
#         self.eta = None
#         self.update_interval = 3
#         self.__resource_lock = threading.RLock()
#         self.name = None
#         self.currentname = None
#         self.__gid = ''
#         self._should_update = True
#         self.status = None
#         self.isfolder = False
#         self.completed_bytes = 0
#         self.gdfoldersize = 0
#         self.sfile = 0
#         self.sfolder = 0
#         self.session = None
#         self.mimeType = None
#         self.resumableuri = None
#         self.downloaded_chunk = 0
#         self.done_chunk = 0
#         self.link = None
#         self.gdrivelink = None

#     @property
#     def gid(self):
#         with self.__resource_lock:
#             return self.__gid    

#     def _cancel(self) -> None:
#         self._is_canceled = True
#         self._is_finished = False

#     def _finish(self) -> None:
#         self._is_finished = True

#     async def clean(self):
#         try:
#             Interval[0].cancel()
#             del Interval[0]
#             await delete_all_messages_async()
#         except IndexError:
#             pass

#     def speed(self):
#         """
#         It calculates the average upload speed and returns it in bytes/seconds unit
#         :return: Upload speed in bytes/second
#         """
#         try:
#             return self.downloaded_chunk / self.total_time
#         except ZeroDivisionError:
#             return 0    

#     def __onDownloadStart(self, name, size, listener):
#         gid = ''.join(random.SystemRandom().choices(string.ascii_letters + string.digits, k=4))
#         with download_dict_lock:
#             download_dict[listener.uid] = AioDownloadStatus(self, listener)
#         with global_lock:
#             GLOBAL_GID.add(gid)
#         with self.__resource_lock:
#             self.name = name
#             self.__gid = gid
#         listener.onDownloadStarted()


#     async def add_download(self, link: str, path, listener):
#         self.__listener = listener
#         async with aiohttp.ClientSession(raise_for_status = True) as self.session:
#             try:
#                 async with self.session.get(link, allow_redirects=True) as response:    
#                     #link = str(response.url)
#                     LOGGER.info(f"url is {link}")
#                     try:
#                         content_disposition = cgi.parse_header(
#                             response.headers['Content-Disposition'])
#                         filename = content_disposition[1]['filename']
#                         filename = urllib.parse.unquote_plus(filename)
#                     except KeyError:
#                         filename = response._real_url.name
#                     try:
#                         size = int(response.headers['Content-Length'])
#                     except KeyError:
#                         size = 0
#                     self.size = size    
#                     self.__listener = listener
#                     self.mimeType = response.headers['content-type']
#                     LOGGER.info(f"mimetype is {self.mimeType}")     
#                     try: 
#                         self.updater = setInterval(self.update_interval, self._on_download_progress)     
#                         self.__onDownloadStart(filename, size, listener) 
#                         self.getsessionuri()
#                         self.link = link
#                         await self._download(link)
#                     except HttpError as err:
#                         LOGGER.info(f"Http error {err}")  
#             except ClientResponseError as cerr:
#                     await self.onClientError(cerr.message)
#                     return None


#     def cancel_download(self):
#         LOGGER.info(f'Cancelling download on user request')
#         self._is_canceled = True                

#     @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(5),
#            retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
#     def getFileMetadata(self,file_id):
#         try:
#             return self.__service.files().get(supportsAllDrives=True, fileId=file_id,
#                                               fields="name,id,mimeType,size").execute()      
#         except HttpError as err:
#             LOGGER.info(f"err is {err.resp.status} and {err._get_reason()}")
#             error = (f"<b>HttpError {err.resp.status}</b>\n{err._get_reason()}")
#             self.__onDownloadError(str(error))                                                                   

#     async def _download(self, link) -> None:
#         try:
#             async with self.session.get(link) as response:
#                 while True:
#                     if self._is_canceled == True:
#                         await self.onClientError("<b>Cancelled Due To User Request</b>")
#                         break
#                     try:
#                         chunk = await response.content.readexactly(10485760) #5mb chunk recommended is 50mb for best performace
#                         self.downloaded_chunk += len(chunk)
#                         await self.upload_file(chunk)
#                         self.done_chunk += len(chunk)
#                         if response.content.at_eof():
#                             LOGGER.info("Ya and i'm done with the chunks")
#                             LOGGER.info(get_readable_file_size(self.downloaded_chunk))
#                             break  
#                     except asyncio.IncompleteReadError as err:
#                         eofchunk = err.partial
#                         self.downloaded_chunk += len(eofchunk)
#                         await self.upload_file(eofchunk)
#                         self.done_chunk += len(eofchunk)
#                         if response.content.at_eof():
#                             LOGGER.info("Ya and i'm done with the chunks")
#                             LOGGER.info(get_readable_file_size(self.downloaded_chunk))
#                             break                           
#         except ClientResponseError as cerr:   
#             await self.onClientError(cerr.message)
#             return None
            
#         except Exception as e:
#             LOGGER.info(f"{e}") 

#     def __onDownloadError(self, error):
#         with global_lock:
#             try:
#                 GLOBAL_GID.remove(self.gid)
#             except KeyError:
#                 pass
#         self.__listener.onDownloadError(error)

#     async def onClientError(self, error):
#         uname = f'<a href="tg://user?id={self.__listener.message.from_user.id}">{self.__listener.message.from_user.first_name}</a>'
#         clienterrormsg = f"{uname} Stopped cuz: {error}"
#         await sendMessage(clienterrormsg, self.__listener.bot, self.__listener.update)
#         with download_dict_lock:
#             del download_dict[self.__listener.uid]
#             count = len(download_dict)
#         if count == 0:
#             await self.clean()
#         else:
#             update_all_messages()        

#     async def __onUploadComplete(self):
#         uname = f'<a href="tg://user?id={self.__listener.message.from_user.id}">{self.__listener.message.from_user.first_name}</a>'
#         with download_dict_lock:
#             try:
#                 msgid = self.__listener.source.message_id
#                 chat_id = str(self.__listener.source.chat.id)
#             except:    
#                 chat_id = str(6969) #pass random values for watch upload complete to work
#             url = None    
#             if chat_id.startswith('-100'):
#                 url = f'<a href="https://t.me/c/{chat_id[4::]}/{msgid}">Source Message 👈🏻</a>'
#             if url:    
#                 msg = f'<b>Filename</b>: <code>{self.name}</code>\n\n<b>Size</b>: <code>{get_readable_file_size(self.size)}</code>\n\n<b>cc</b>: {uname}\n\n{url}\n<i>Join TD to Access Gdrive Links🤘🏻\nDont Share Links In Public</i>\n#Uploads❤️'
#             else:
#                 msg = f'<b>Filename</b>: <code>{self.name}</code>\n\n<b>Size</b>: <code>{get_readable_file_size(self.size)}</code>\n\n<b>cc</b>: {uname}\n\n<i>Join TD to Access Gdrive Links🤘🏻\nDont Share Links In Public</i>\n#Uploads❤️'
#             buttons = button_build.ButtonMaker()
#             buttons.buildbutton("⚡GDrive Link⚡", self.gdrivelink)
#             LOGGER.info(f'Done Uploading {self.name}')
#             if INDEX_URL is not None:
#                 share_url = requests.utils.requote_uri(f'{INDEX_URL}/{self.name}')
#                 buttons.buildbutton("🔥Index Link🔥", share_url)
#                 buttons.buildbutton("❣️Join TeamDrive❣️", 'https://t.me/c/1271941524/361972')    
#             del download_dict[self.__listener.uid]
#             count = len(download_dict)
#         await sendMarkup(msg, self.__listener.bot, self.__listener.update, InlineKeyboardMarkup(buttons.build_menu(2)))
#         if count == 0:
#             await self.clean()
#         else:
#             update_all_messages()  


#     def _on_download_progress(self):
#             self.total_time += self.update_interval

#     @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(5),
#         retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
#     def __set_permission(self, drive_id):
#         permissions = {
#             'role': 'reader',
#             'type': 'anyone',
#             'value': None,
#             'withLink': True
#         }
#         return self.__service.permissions().create(supportsTeamDrives=True, fileId=drive_id,
#                                                    body=permissions).execute()


#     def getsessionuri(self, **kwargs) -> None:
#         try:
#             file_metadata = {
#             'name': self.name,
#             'description': 'mirror',
#             'mimeType': self.mimeType
#         }
#             if parent_id is not None:
#                 file_metadata['parents'] = [self._parent_id]

#             headers = {"Authorization": "Bearer "+gdriveTools.GoogleDriveHelper().get_credentials(), "Content-Type": "application/json; charset=UTF-8"}
#             r = requests.post(
#             "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&supportsTeamDrives=True",
#             data=json.dumps(file_metadata),
#             headers = headers
#             )
#             self.resumableuri = r.headers['Location']
#             LOGGER.info(f"resumable uri is {self.resumableuri}")
#         except HttpError as err:
#             error = (f"<b>HttpError {err.resp.status}</b>\n{err._get_reason()}")
#             LOGGER.info(error)
#             self.__onDownloadError(str(error)) 

#     @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(5),
#            retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
#     async def upload_file(self, chunk, **kwargs) -> None:
#         try:
#             headers = {"Content-Length": str(len(chunk)), "Content-Range": f"bytes {str(self.done_chunk)}-" + str(self.downloaded_chunk - 1) + "/" + str(self.size)}
#             r = requests.put(
#                 self.resumableuri,
#                 headers=headers,
#                 data=chunk
#             )
#             if r.text:
#                 LOGGER.info(f"r.text is {r.text}")
#                 self.gdrivelink = self.__G_DRIVE_BASE_DOWNLOAD_URL.format(r.json()['id'])
#                 await self.__onUploadComplete()
#                 return r.text
#             #info = json.loads(r.text.decode("utf-8"))
#             #LOGGER.info(f"id is {info}")
#             #self.gdrivelink = self.__G_DRIVE_BASE_DOWNLOAD_URL.format(r.json()['id'])
#             #LOGGER.info(r.text)
#             #LOGGER.info(f"{r.json()['id']}")
#             #self.__set_permission(r.json()['id'])
#         except HttpError as err:
#             if "416" in str(err):
#                 f = open(f"{os.path.join(path, name)}", "w").close
#             else:
#                 error = (f"<b>HttpError {err.resp.status}</b>\n{err._get_reason()}")
#                 LOGGER.info(f"http error is {error}")
#                 self.__onDownloadError(str(error))     


#     @staticmethod
#     def getIdFromUrl(link: str):
#         if "folders" in link or "file" in link:
#             regex = r"https://drive\.google\.com/(drive)?/?u?/?\d?/?(mobile)?/?(file)?(folders)?/?d?/([-\w]+)[?+]?/?(w+)?"
#             res = re.search(regex,link)
#             if res is None:
#                 raise IndexError("GDrive ID not found.")
#             return res.group(5)
#         parsed = urlparse.urlparse(link)
#         return parse_qs(parsed.query)['id'][0]   


#     @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(5),
#            retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
#     def getFilesByFolderId(self,folder_id):
#         page_token = None
#         q = f"'{folder_id}' in parents"
#         files = []
#         while True:
#             response = self.__service.files().list(supportsTeamDrives=True,
#                                                    includeTeamDriveItems=True,
#                                                    q=q,
#                                                    spaces='drive',
#                                                    pageSize=200,
#                                                    fields='nextPageToken, files(id, name, mimeType,size)',
#                                                    pageToken=page_token).execute()
#             for file in response.get('files', []):
#                 files.append(file)
#             page_token = response.get('nextPageToken', None)
#             if page_token is None:
#                 break
#         return files     
            
#     @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(5),
#            retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
#     def gdrivesize(self, meta) -> str:
#         self.computed_size = 0
#         try:
#             if meta.get("mimeType") == self.__G_DRIVE_DIR_MIME_TYPE:
#                 size = self.foldersize(meta.get('id'))
#                 self.sfolder += 1
#             else:
#                 self.computed_size = int(meta.get('size'))
#                 self.sfile += 1
#             self.gdfoldersize = self.computed_size
#             size_wrapper = f"uri added ⚡️\nYou May Want to Check Out /{BotCommands.StatusCommand}\n\n<code>{meta.get('name')}</code>\n<b>Folders/Files</b>: {self.sfolder} / {self.sfile}\n<b>Size:</b> {get_readable_file_size(self.gdfoldersize)}"
#             return size_wrapper
#         except HttpError as err:
#             LOGGER.info(f"Error {err}")

#     @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(5),
#            retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
#     def foldersize(self, folder_id):
#         files = self.getFilesByFolderId(folder_id)
#         if len(files) == 0:
#             return 0
#         for file in files:
#             if file.get('mimeType') == self.__G_DRIVE_DIR_MIME_TYPE:
#                 size = self.foldersize(file.get('id'))
#                 self.sfolder += 1
#             else:
#                 try:
#                     self.computed_size += int(file.get('size'))
#                     self.sfile += 1
#                 except TypeError:
#                     pass       
#         return self.computed_size    

#     def getsizehandle(self, update, context, link):
#         fileId = self.getIdFromUrl(link)
#         meta = self.getFileMetadata(fileId)
#         showaf = f"<b>Calculating Google Drive Folder/File Size</b>\n<i>Please Wait...... :3</i>"
#         sizemsg = sendMessage(showaf,context.bot,update)
#         size = self.gdrivesizeforhandler(meta)
#         deleteMessage(context.bot, sizemsg)
#         sizemsg = sendMessage(size,context.bot,update)

#     @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(5),
#         retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
#     def gdrivesizeforhandler(self, meta) -> str:
#         self.computed_size = 0
#         try:
#             if meta.get("mimeType") == self.__G_DRIVE_DIR_MIME_TYPE:
#                 size = self.foldersize(meta.get('id'))
#                 self.sfolder += 1
#             else:
#                 self.computed_size = int(meta.get('size'))
#                 self.sfile += 1
#             size_wrapper = f"<code>{meta.get('name')}</code>\n<b>Folders/Files</b>: {self.sfolder} / {self.sfile}\n<b>Size</b> {get_readable_file_size(self.computed_size)}"
#             return size_wrapper
#         except HttpError as err:
#             LOGGER.info(f"Error {err}")
              

                        
