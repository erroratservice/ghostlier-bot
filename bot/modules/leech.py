import requests
from pyrogram import Client, filters
from pyrogram.types import Message
from bot import Interval, DOWNLOAD_DIR, DOWNLOAD_STATUS_UPDATE_INTERVAL, download_dict, download_dict_lock, AUTHORIZED_CHATS
from bot.helper.ext_utils import fs_utils, bot_utils
from bot.helper.ext_utils.bot_utils import setInterval
from bot.helper.ext_utils.exceptions import DirectDownloadLinkException, NotSupportedExtractionArchive
from bot.helper.mirror_utils.download_utils.aria2_download import AriaDownloadHelper
from bot.helper.mirror_utils.download_utils.direct_link_generator import direct_link_generator
from bot.helper.mirror_utils.download_utils.telegram_downloader import TelegramDownloadHelper
from bot.helper.mirror_utils.download_utils.gdrive_download import GDdownload
from bot.helper.mirror_utils.download_utils.aio_download import AioHttpDownload
from bot.helper.mirror_utils.download_utils.qbit_download import QbitWrap
from bot.helper.mirror_utils.status_utils import listeners
from bot.helper.mirror_utils.status_utils.leech_listeners import LeechListeners
from bot.helper.mirror_utils.status_utils.extract_status import ExtractStatus
from bot.helper.mirror_utils.status_utils.tar_status import TarStatus
from bot.helper.mirror_utils.status_utils.zip_status import ZipStatus
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.message_utils import *
import pathlib
import os
import threading
import shutil
import random
import string
import asyncio

from bot.helper.mirror_utils.upload_utils.telegramUploader import TelegramUploader
from bot.helper.mirror_utils.status_utils.upload_status import UploadStatus

ariaDlManager = AriaDownloadHelper()
ariaDlManager.start_listener()
qbit = QbitWrap()
qbitclient = qbit.get_client()

class LeechListener(LeechListeners):
    def __init__(self, bot, update, isTar=False, tag=None, extract=False, isZip=False, source=None, genid=None, password=None):
        super().__init__(bot, update)
        self.isTar = isTar
        self.tag = tag
        self.extract = extract
        self.isZip = isZip
        self.source = source
        self.genid = genid
        self.password = password

    def onDownloadStarted(self):
        sendMessage("Download started!", self.bot, self.message)

    def onDownloadProgress(self, current=None, total=None):
        # Optional: update status messages here
        pass

    def onDownloadComplete(self):
        with download_dict_lock:
            download = download_dict[self.uid]
            name = download.name()
            size = download.size_raw()
            m_path = download.upload_path()
        path = m_path
        if self.isTar:
            path = fs_utils.tar(m_path, self) or m_path
        elif self.isZip:
            path = fs_utils.zip(m_path, f"{DOWNLOAD_DIR}{self.uid}/", self) or m_path
        elif self.extract:
            path = fs_utils.get_base_name(m_path)
        up_name = os.path.basename(path)
        uploader = TelegramUploader(self.bot, self.message.chat.id, self, path)
        upload_status = UploadStatus(uploader, os.path.getsize(path), self)
        with download_dict_lock:
            download_dict[self.uid] = upload_status
        asyncio.run(uploader.upload())

    def onDownloadError(self, error: str):
        sendMessage(f"Download error: {error}", self.bot, self.message)

    def onUploadStarted(self):
        sendMessage("Upload started!", self.bot, self.message)

    def onUploadProgress(self, current=None, total=None):
        # Optional: update status messages here
        pass

    def onUploadComplete(self, msg):
        sendMessage(f"{msg}", self.bot, self.message)

    def onUploadError(self, error):
        sendMessage(f"Telegram upload error: {error}", self.bot, self.message)

def _leech(bot: Client, message: Message, isTar=False, extract=False, isZip=False):
    args = message.text.split(" ", maxsplit=1)
    reply_to = message.reply_to_message
    istorrentfile = False
    genid = ''.join(random.SystemRandom().choices(string.ascii_letters + string.digits, k=4))
    if len(args) > 1 or reply_to:
        uname = f'<a href="tg://user?id={message.from_user.id}">{message.from_user.first_name}</a>'
        cc = f"@{message.from_user.username}" if message.from_user.username else uname
        message_args = message.text.split(' ', maxsplit=1)
        try:
            source = sendMessage(f"{uname} has sent:\n\n<i>{message_args[0]}</i> <code>{message_args[1]}</code>\n\ncc: {cc}", bot, message)
        except:
            if reply_to and reply_to.text:
                source = sendMessage(f"{uname} has sent:\n\n<i>{message_args[0]}</i> <code>{reply_to.text}</code>\n\ncc: {cc}", bot, message)
        try:
            link = message_args[1]
        except IndexError:
            link = ''
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
                if file is not None and file.mime_type != "application/x-bittorrent":
                    source = sendMessage(f"{uname} has sent:\n\n<i>{message_args[0]}</i> <code>A Telegram Media File</code>\n\ncc: {cc}", bot, message)
                    listener = LeechListener(bot, message, isTar, tag, extract, isZip, source)
                    tg_downloader = TelegramDownloadHelper(listener)
                    tg_downloader.add_download(reply_to, f'{DOWNLOAD_DIR}{listener.uid}/')
                    uriadded = sendUriAdded(message, bot)
                    sendMessage(f"{uriadded}", bot, message)
                    if len(Interval) == 0:
                        Interval.append(setInterval(DOWNLOAD_STATUS_UPDATE_INTERVAL, update_all_messages))
                    return
                elif file and file.mime_type == "application/x-bittorrent":
                    source = sendMessage(f"{uname} has sent:\n\n<i>{message_args[0]}</i> <code>A Torrent File</code>\n\ncc: {cc}", bot, message)
                    istorrentfile = True
                    link = reply_to.download()
        else:
            tag = None
        if not bot_utils.is_url(link) and not bot_utils.is_magnet(link) and not bot_utils.is_torrent(link):
            sendMessage('No download source provided', bot, message)
            return
        try:
            link = direct_link_generator(link)
        except DirectDownloadLinkException:
            pass
        isitgdrive = "drive.google.com" in link
        isitmagnet = "magnet" in link
        if isitgdrive:
            listener = LeechListener(bot, message, isTar, tag, extract, isZip, source)
            gd = GDdownload()
            if len(Interval) == 0:
                Interval.append(setInterval(DOWNLOAD_STATUS_UPDATE_INTERVAL, update_all_messages))
            gd.add_download(link, f'{DOWNLOAD_DIR}{listener.uid}', listener)
        elif istorrentfile:
            listener = LeechListener(bot, message, isTar, tag, extract, isZip, source, None, None)
            if len(Interval) == 0:
                Interval.append(setInterval(DOWNLOAD_STATUS_UPDATE_INTERVAL, update_all_messages))
            uriadded = sendUriAdded(message, bot)
            sendMessage(f"{uriadded}", bot, message)
            qo = QbitWrap()
            qo.register_torrent(bot, message, link, listener, file=True)
        elif isitmagnet:
            listener = LeechListener(bot, message, isTar, tag, extract, isZip, source, None, None)
            if len(Interval) == 0:
                Interval.append(setInterval(DOWNLOAD_STATUS_UPDATE_INTERVAL, update_all_messages))
            uriadded = sendUriAdded(message, bot)
            sendMessage(f"{uriadded}", bot, message)
            qo = QbitWrap()
            qo.register_torrent(bot, message, link, listener, magnet=True)
        else:
            listener = LeechListener(bot, message, isTar, tag, extract, isZip, source, genid)
            ariaDlManager.add_download(link, f'{DOWNLOAD_DIR}/{listener.uid}/', listener)
            uriadded = sendUriAdded(message, bot)
            sendMessage(f"{uriadded}", bot, message)
            if len(Interval) == 0:
                Interval.append(setInterval(DOWNLOAD_STATUS_UPDATE_INTERVAL, update_all_messages))
    else:
        sendMessage(f"No Download Source Provided", bot, message)

@Client.on_message(
    filters.command("leech") &
    filters.chat(AUTHORIZED_CHATS)
)
def leech(client: Client, message: Message):
    _leech(client, message)

@Client.on_message(
    filters.command("tarleech") &
    filters.chat(AUTHORIZED_CHATS)
)
def tar_leech(client: Client, message: Message):
    _leech(client, message, isTar=True)

@Client.on_message(
    filters.command("zipleech") &
    filters.chat(AUTHORIZED_CHATS)
)
def zip_leech(client: Client, message: Message):
    _leech(client, message, isZip=True)

@Client.on_message(
    filters.command("unzipleech") &
    filters.chat(AUTHORIZED_CHATS)
)
def unzip_leech(client: Client, message: Message):
    _leech(client, message, extract=True)
