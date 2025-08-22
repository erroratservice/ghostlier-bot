import requests
from pyrogram import (
    Client,
    filters
)
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.types import Message
from bot import Interval, INDEX_URL
from bot import AUTHORIZED_CHATS, DOWNLOAD_DIR, DOWNLOAD_STATUS_UPDATE_INTERVAL, download_dict, download_dict_lock, OWNER_ID, ENABLE_DRIVE_SEARCH

from bot.helper.ext_utils import fs_utils, bot_utils
from bot.helper.ext_utils.bot_utils import setInterval
from bot.helper.ext_utils.exceptions import DirectDownloadLinkException, NotSupportedExtractionArchive
from bot.helper.mirror_utils.download_utils.aria2_download import AriaDownloadHelper
from bot.helper.mirror_utils.download_utils.direct_link_generator import direct_link_generator
from bot.helper.mirror_utils.download_utils.telegram_downloader import TelegramDownloadHelper
from bot.helper.mirror_utils.download_utils.gdrive_download import GDdownload
from bot.helper.mirror_utils.download_utils.aio_download import AioHttpDownload
from bot.helper.mirror_utils.download_utils.qbit_download import QbitWrap
from bot.helper.mirror_utils.upload_utils.gdriveTools import GoogleDriveHelper
from bot.helper.mirror_utils.status_utils import listeners
from bot.helper.mirror_utils.status_utils.extract_status import ExtractStatus
from bot.helper.mirror_utils.status_utils.tar_status import TarStatus
from bot.helper.mirror_utils.status_utils.zip_status import ZipStatus
from bot.helper.mirror_utils.status_utils.upload_status import UploadStatus
from bot.helper.mirror_utils.status_utils.gdrivedownload_status import GDDownloadStatus
from bot.helper.mirror_utils.upload_utils import gdriveTools
from bot.helper.telegram_helper import button_build
from time import sleep
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import *
import pathlib
import os
import subprocess
import threading
import shutil
import random
import string
import re
import asyncio
import qbittorrentapi as qba
import asyncio as aio

ariaDlManager = AriaDownloadHelper()
ariaDlManager.start_listener()

qbit = QbitWrap()
qbitclient = qbit.get_client()

class MirrorListener(listeners.MirrorListeners):
    def __init__(self, bot, update, isTar=False,tag=None, extract=False, isZip=False, source=None, genid=None, password=None):
        super().__init__(bot, update)
        self.isTar = isTar
        self.tag = tag
        self.extract = extract
        self.isZip = isZip
        self.source = source
        self.genid = genid
        self.password = password

    def onDownloadStarted(self):
            pass

    def onDownloadProgress(self):
        # We are handling this on our own!
        pass

    def clean(self):
        try:
            Interval[0].cancel()
            del Interval[0]
            delete_all_messages()
        except IndexError:
            pass

    def onDownloadComplete(self):
        with download_dict_lock:
            total, used, free = shutil.disk_usage('.')
            LOGGER.info(f"Download completed: {download_dict[self.uid].name()}")
            download = download_dict[self.uid]
            name = download.name()
            size = download.size_raw()
            source = download.sourcemsg()
            dir_path = f"{DOWNLOAD_DIR}{self.uid}/"
            m_path = download.upload_path()
            LOGGER.info(f"After finishing Download! {download.which_client()} path is {m_path} {self.isTar} {self.isZip} {self.extract}")
            uname = f'<a href="tg://user?id={self.message.from_user.id}">{self.message.from_user.first_name}</a>'
        if self.isTar:
            download.is_archiving = True
            Isdir = os.path.isdir(m_path)
            if Isdir:
                try:
                    if size < free:
                        with download_dict_lock:
                            download_dict[self.uid] = TarStatus(name, m_path, size, download.gid(), source)
                        path = fs_utils.tar(m_path, self)
                        if path:
                            threading.Thread(target=shutil.rmtree, args=(m_path,'ignore_errors=True')).start()
                            LOGGER.info(f"Deleting Folder : {m_path}")
                        else:
                            return    
                    else:
                        sendMessage(f"{uname} <b>Not Enough Space to Archive</b>\nUploading without Zipping",self.bot,self.message)
                        #self.onDownloadError("<b>Not Enough Space to Archive</b>\n<i>Download Stopped</i>\n#archivenospace")
                        path = m_path
                except FileNotFoundError:
                    LOGGER.info('File to archive not found!')
                    self.onUploadError('Internal error occurred!!')
                    return
            else:
                sendMessage(f"{uname} <b>Single Files Won't be Zipped</b>\nUploading without Zipping",self.bot,self.message)
                path = m_path
        elif self.isZip:
            download.is_archiving = True
            Isdir = os.path.isdir(m_path)
            if Isdir:
                try:
                    if size < free:
                        with download_dict_lock:
                            download_dict[self.uid] = ZipStatus(name, m_path, size, download.gid(), source)
                        path = fs_utils.zip(m_path, dir_path, self)
                        if path:
                            threading.Thread(target=shutil.rmtree, args=(m_path,'ignore_errors=True')).start()
                            LOGGER.info(f"Deleting Folder : {m_path}")
                        else:
                            return
                    else:
                        sendMessage(f"{uname} <b>Not Enough Space to Archive</b>\nUploading without Zipping",self.bot,self.message)
                        #self.onDownloadError("<b>Not Enough Space to Archive</b>\n<i>Download Stopped</i>\n#archivenospace")
                        path = m_path               
                except FileNotFoundError:
                    LOGGER.info('File to archive not found!')
                    self.onUploadError('Internal error occurred!!')
                    return
            else:
                sendMessage(f"{uname} <b>Single Files Won't be Zipped</b>\nUploading without Zipping",self.bot,self.message)
                path = m_path
        elif self.extract:
            download.is_extracting = True
            try:
                if size < free:
                    path = fs_utils.get_base_name(m_path)
                    LOGGER.info(
                        f"Extracting : {name} "
                    )
                    sleep(2)
                    with download_dict_lock:
                        download_dict[self.uid] = ExtractStatus(name, m_path, size, download.gid(), source)
                    password = self.password
                    if password is not None:
                        archive_result = subprocess.run(["pextract", m_path, password])
                    else:
                        archive_result = subprocess.run(["extract", m_path])
                    if archive_result.returncode == 0:
                        threading.Thread(target=os.remove, args=(m_path,)).start()
                        LOGGER.info(f"Deleting archive : {m_path}")
                    else:
                        LOGGER.warning('Unable to extract archive! Canceling!')
                        fullpath = f'{DOWNLOAD_DIR}{self.uid}'
                        unableextract = f'<b>{uname} Cannot extract file, check integrity of the file</b>\n#Stopped'
                        self.onExtractError(unableextract, fullpath)
                        return
                else:
                    sendMessage(f"{uname} <b>Not Enough Space to Extract</b>\nUploading without Extracing",self.bot,self.message)
                    #self.onDownloadError("<b>Not Enough Space to Archive</b>\n<i>Download Stopped</i>\n#archivenospace")
                    path = m_path         
            except NotSupportedExtractionArchive:
                LOGGER.info("Not any valid archive, Canceling!")
                fullpath = f'{DOWNLOAD_DIR}{self.uid}'
                notsupportedarchive = f'<b>{uname} Not supported archive</b>.\n#Stopped'
                self.onExtractError(notsupportedarchive, fullpath)
                return
        else:
            path = m_path
        up_name = pathlib.PurePath(path).name
        if up_name == "None":
            up_name = "".join(os.listdir(f'{DOWNLOAD_DIR}{self.uid}/'))
        LOGGER.info(f"Upload Name : {up_name}")
        drive = gdriveTools.GoogleDriveHelper(up_name, self)
        size = fs_utils.get_path_size(path)
        upload_status = UploadStatus(drive, size, self)
        with download_dict_lock:
            download_dict[self.uid] = upload_status
        update_all_messages()
        drive.upload(up_name)

    def onTorrentDeadError(self, error):
        LOGGER.info(self.update.chat.id)
        with download_dict_lock:
            try:
                download = download_dict[self.uid]
                del download_dict[self.uid]
                LOGGER.info(f"Deleting folder: {download.path()}")
                fs_utils.clean_download(download.path())
                LOGGER.info(str(download_dict))
            except Exception as e:
                LOGGER.error(str(e))
                pass
            count = len(download_dict)
        uname = f'<a href="tg://user?id={self.message.from_user.id}">{self.message.from_user.first_name}</a>'
        msg = f"{uname} {error}"
        sendMessage(msg, self.bot, self.update)
        if count == 0:
            self.clean()
        else:
            update_all_messages()    

    def onDownloadError(self, error):
        LOGGER.info(self.update.chat.id)
        with download_dict_lock:
            try:
                download = download_dict[self.uid]
                del download_dict[self.uid]
                LOGGER.info(f"Deleting folder: {download.path()}")
                if download.which_client() == "Qbit":
                    download.cancel_download()
                fs_utils.clean_download(download.path())
                LOGGER.info(str(download_dict))
            except Exception as e:
                LOGGER.error(str(e))
                pass
            count = len(download_dict)
        uname = f'<a href="tg://user?id={self.message.from_user.id}">{self.message.from_user.first_name}</a>'
        msg = f"{uname} Stopped Cuz : {error}"
        sendMessage(msg, self.bot, self.update)
        if count == 0:
            self.clean()
        else:
            update_all_messages()


    def onDownloadAlreadyComplete(self, response):
        LOGGER.info(self.update.chat.id)
        with download_dict_lock:
            try:
                download = download_dict[self.uid]
                del download_dict[self.uid]
                LOGGER.info(f"Deleting folder: {download.path()}")
                fs_utils.clean_download(download.path())
                LOGGER.info(str(download_dict))
            except Exception as e:
                LOGGER.error(str(e))
                pass
            count = len(download_dict)
        uname = f'<a href="tg://user?id={self.message.from_user.id}">{self.message.from_user.first_name}</a>'
        msg = f"{uname} The File You Are Trying To Download is Already Downloaded: \n\n#AlreadyDownloaded\n\n{response}"
        sendMessage(msg, self.bot, self.update)
        if count == 0:
            self.clean()
        else:
            update_all_messages()

    def onMaxSize(self, response):
        LOGGER.info(self.update.chat.id)
        with download_dict_lock:
            try:
                download = download_dict[self.uid]
                del download_dict[self.uid]
                LOGGER.info(f"Deleting folder: {download.path()}")
                fs_utils.clean_download(download.path())
                LOGGER.info(str(download_dict))
            except Exception as e:
                LOGGER.error(str(e))
                pass
            count = len(download_dict)
        uname = f'<a href="tg://user?id={self.message.from_user.id}">{self.message.from_user.first_name}</a>'
        msg = f"{uname} {response}"
        sendMessage(msg, self.bot, self.update)
        if count == 0:
            self.clean()
        else:
            update_all_messages()


    def onUploadStarted(self):
        pass

    def onUploadProgress(self):
        pass

    def onUploadComplete(self, link: str):
        uname = f'<a href="tg://user?id={self.message.from_user.id}">{self.message.from_user.first_name}</a>'
        with download_dict_lock:
            try:
                msgid = self.source.id
                chat_id = str(self.source.chat.id)
            except:    
                chat_id = str(6969) #pass random values for watch upload complete to work
            url = None    
            if chat_id.startswith('-100'):
                url = f'<a href="https://t.me/c/{chat_id[4::]}/{msgid}">Source Message 👈🏻</a>'
            if url:    
                if ENABLE_DRIVE_SEARCH:
                    msg = f'<b>Filename</b>: <code>{download_dict[self.uid].name()}</code>\n\n<b>Size</b>: <code>{download_dict[self.uid].size()}</code>\n\n<b>cc</b>: {uname}\n\n{url}\n<i>Join TD to Access Gdrive Links🤘🏻\nDont Share Links In Public</i>\n#Uploads❤️'
                else:
                    msg = f'<b>Filename</b>: <code>{download_dict[self.uid].name()}</code>\n\n<b>Size</b>: <code>{download_dict[self.uid].size()}</code>\n\n<b>cc</b>: {uname}\n\n{url}\n#Uploads❤️'
            else:
                if ENABLE_DRIVE_SEARCH:
                    msg = f'<b>Filename</b>: <code>{download_dict[self.uid].name()}</code>\n\n<b>Size</b>: <code>{download_dict[self.uid].size()}</code>\n\n<b>cc</b>: {uname}\n\n<i>Join TD to Access Gdrive Links🤘🏻\nDont Share Links In Public</i>\n#Uploads❤️'
                else:
                    msg = f'<b>Filename</b>: <code>{download_dict[self.uid].name()}</code>\n\n<b>Size</b>: <code>{download_dict[self.uid].size()}</code>\n\n<b>cc</b>: {uname}\n#Uploads❤️'
            buttons = button_build.ButtonMaker()
            buttons.buildbutton("⚡GDrive Link⚡", link)
            LOGGER.info(f'Done Uploading {download_dict[self.uid].name()}')
            if INDEX_URL is not None:
                share_url = requests.utils.requote_uri(f'{INDEX_URL}/{download_dict[self.uid].name()}')
                if os.path.isdir(f'{DOWNLOAD_DIR}/{self.uid}/{download_dict[self.uid].name()}'):
                    share_url += '/'
                buttons.buildbutton("🔥Index Link🔥", share_url)
            try:
                fs_utils.clean_download(download_dict[self.uid].path())
            except FileNotFoundError:
                pass
            del download_dict[self.uid]
            count = len(download_dict)
        LOGGER.info(f"IN Here!")    
        sendMarkup(msg, self.bot, self.update, InlineKeyboardMarkup(buttons.build_menu(2)))
        if count == 0:
            self.clean()
        else:
            update_all_messages()

    def onExtractError(self, error, fullpath):
        with download_dict_lock:
            download = download_dict[self.uid]
            try:
                fs_utils.clean_download(fullpath)
            except FileNotFoundError:
                pass
            del download_dict[self.message.id]
            if download.which_client() == "Qbit":
                    download.cancel_download()
            count = len(download_dict)
        sendMessage(error, self.bot, self.update)
        if count == 0:
            self.clean()
        else:
            update_all_messages()

    def onUploadError(self, error):
        e_str = error.replace('<', '').replace('>', '')
        with download_dict_lock:
            try:
                fs_utils.clean_download(download_dict[self.uid].path())
            except FileNotFoundError:
                pass
            del download_dict[self.message.id]
            count = len(download_dict)
        sendMessage(e_str, self.bot, self.update)
        if count == 0:
            self.clean()
        else:
            update_all_messages()  

def _mirror(bot: Client, message: Message, isTar=False, extract=False, isZip=False):
    args = message.text.split(" ",maxsplit=1)
    reply_to = message.reply_to_message
    istorrentfile = False
    genid = ''.join(random.SystemRandom().choices(string.ascii_letters + string.digits, k=4))
    if len(args) > 1 or reply_to:
        uname = f'<a href="tg://user?id={message.from_user.id}">{message.from_user.first_name}</a>'
        if message.from_user.username:
            cc = f"@{message.from_user.username}"
        else:
            cc = f'<a href="tg://user?id={message.from_user.id}">{message.from_user.first_name}</a>'
        message_args = message.text.split(' ',maxsplit=1)
        try:
            source = sendMessage(f"{uname} has sent:\n\n<i>{message_args[0]}</i> <code>{message_args[1]}</code>\n\ncc: {cc}",bot,message)
        except:
            if reply_to.text:
                source = sendMessage(f"{uname} has sent:\n\n<i>{message_args[0]}</i> <code>{reply_to.text}</code>\n\ncc: {cc}",bot,message) 
        try:
            link = message_args[1]
        except IndexError:
            link = ''
        LOGGER.info(link)
        link = link.strip()
        if reply_to is not None:
            file = None
            tag = reply_to.from_user.username
            media_array = [reply_to.document, reply_to.video, reply_to.audio]
            for i in media_array:
                if i is not None:
                    file = i
                    break
            if reply_to.text:
                link = reply_to.text
            if len(link) == 0:
                if file is not None:
                    if file.mime_type != "application/x-bittorrent":
                        source = sendMessage(f"{uname} has sent:\n\n<i>{message_args[0]}</i> <code>A Telegram Media File</code>\n\ncc: {cc}",bot,message)
                        listener = MirrorListener(bot, message, isTar, tag, extract, isZip, source)
                        tg_downloader = TelegramDownloadHelper(listener)
                        tg_downloader.add_download(reply_to, f'{DOWNLOAD_DIR}{listener.uid}/')
                        uriadded = sendUriAdded(message, bot)
                        sendMessage(f"{uriadded}", bot, message)
                        if len(Interval) == 0:
                            Interval.append(setInterval(DOWNLOAD_STATUS_UPDATE_INTERVAL, update_all_messages))
                        return
                    else:
                        source = sendMessage(f"{uname} has sent:\n\n<i>{message_args[0]}</i> <code>A Torrent File</code>\n\ncc: {cc}",bot,message)
                        istorrentfile = True
                        link = reply_to.download()
        else:
            tag = None
        if not bot_utils.is_url(link) and not bot_utils.is_magnet(link) and not bot_utils.is_torrent(link):
            sendMessage('No download source provided', bot, message)
            return


        try:
            link = direct_link_generator(link)
        except DirectDownloadLinkException as e:
            LOGGER.info(f'{link}: {e}')
        isitgdrive = "drive.google.com" in link
        isitmega = "mega.nz" in link
        isitmagnet = "magnet" in link

        if (isitmega):
            uhwutmega = f"{uname} <b>We don't download that here :3</b>. Mega isn't Supported"
            sendMessage(f"{uhwutmega}", bot, message) 
            return
        
        if  bot_utils.is_url(link) and not bot_utils.is_magnet(link) and not bot_utils.is_torrent(link):
            if bot_utils.isitwebpage(link) and not isitgdrive:
                sendMessage(f"<b>{uname} It Goes To a Webpage. Please Check The Link</b>", bot, message)
                return
                
        if (isitgdrive):
            listener = MirrorListener(bot, message, isTar, tag, extract, isZip, source) 
            gd = GDdownload()
            if len(Interval) == 0:
                Interval.append(setInterval(DOWNLOAD_STATUS_UPDATE_INTERVAL, update_all_messages)) 
            gd.add_download(link, f'{DOWNLOAD_DIR}{listener.uid}',listener)   
        elif istorrentfile:
            listener = MirrorListener(bot, message, isTar, tag, extract, isZip, source, None, None)
            LOGGER.info("Meh QBittorrent Torrent") 
            if len(Interval) == 0:
                Interval.append(setInterval(DOWNLOAD_STATUS_UPDATE_INTERVAL, update_all_messages)) 
            uriadded = sendUriAdded(message, bot)    
            sendMessage(f"{uriadded}", bot, message)  
            qo = QbitWrap()  
            qo.register_torrent(bot, message,link, listener, file=True)
        elif isitmagnet:
            listener = MirrorListener(bot, message, isTar, tag, extract, isZip, source, None, None)
            LOGGER.info("Meh QBittorrent Magnet") 
            if len(Interval) == 0:
                Interval.append(setInterval(DOWNLOAD_STATUS_UPDATE_INTERVAL, update_all_messages)) 
            uriadded = sendUriAdded(message, bot)    
            sendMessage(f"{uriadded}", bot, message)  
            qo = QbitWrap()  
            qo.register_torrent(bot, message,link, listener, magnet=True)
        else:
            listener = MirrorListener(bot, message, isTar, tag, extract, isZip, source, genid)
            ariaDlManager.add_download(link, f'{DOWNLOAD_DIR}/{listener.uid}/',listener)
            uriadded = sendUriAdded(message, bot)
            sendMessage(f"{uriadded}", bot, message)
            if len(Interval) == 0:
                Interval.append(setInterval(DOWNLOAD_STATUS_UPDATE_INTERVAL, update_all_messages))
    else:
        sendMessage(f"No Download Source Provided", bot, message) 

@Client.on_message(
    filters.command(BotCommands.wgetCommand) &
    filters.chat(OWNER_ID)
)
async def wget(bot: Client, message: Message, isTar=False, extract=False, isZip=False, source = None):
    args = message.text.split(" ",maxsplit=1)
    if len(args) > 1:
        if message.from_user.username:
            cc = f"@{message.from_user.username}"
        else:
            cc = f'<a href="tg://user?id={message.from_user.id}">{message.from_user.first_name}</a>'
        uname = f'<a href="tg://user?id={message.from_user.id}">{message.from_user.first_name}</a>'
        source = sendMessage(f"{uname} has sent:\n\n<i>{args[0]}</i> <code>{args[1]}</code>\n\ncc: {cc}",bot,message)
        listener = MirrorListener(bot, message, isTar, extract, isZip, source)
        link = args[1]
        LOGGER.info("Meh aio https") 
        ao = AioHttpDownload()
        if len(Interval) == 0:
            Interval.append(setInterval(DOWNLOAD_STATUS_UPDATE_INTERVAL, update_all_messages)) 
        uriadded = sendUriAdded(message, bot)    
        sendMessage(f"{uriadded}", bot, message)    
        await ao.add_download(link, f'{DOWNLOAD_DIR}{listener.uid}',listener)
    else:
        sendMessage("Provide A Http Link to Upload.",bot, message)


@Client.on_message(
    filters.command(BotCommands.MirrorCommand) &
    filters.chat(AUTHORIZED_CHATS)
)
def mirror(client: Client, message: Message):
    _mirror(client, message)

@Client.on_message(
    filters.command(BotCommands.TarMirrorCommand) &
    filters.chat(AUTHORIZED_CHATS)
)
def tar_mirror(client: Client, message: Message):
    _mirror(client, message, isTar=True)

@Client.on_message(
    filters.command(BotCommands.ZipMirrorCommand) &
    filters.chat(AUTHORIZED_CHATS)
)
def zip_mirror(client: Client, message: Message):
    _mirror(client, message, isZip=True)

@Client.on_message(
    filters.command(BotCommands.UnzipMirrorCommand) &
    filters.chat(AUTHORIZED_CHATS)
)
def unzip_mirror(client: Client, message: Message):
    _mirror(client, message, extract=True)
