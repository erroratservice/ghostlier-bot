import logging
import os
import re
import threading
import time
import requests
import shutil, psutil
from bot import download_dict, download_dict_lock
import random
import urllib.parse as urlparse
from urllib.parse import parse_qs
from bot.helper.telegram_helper.bot_commands import BotCommands

LOGGER = logging.getLogger(__name__)

MAGNET_REGEX = r"magnet:\?xt=urn:btih:[a-zA-Z0-9]*"

URL_REGEX = r"(?:(?:https?|ftp):\/\/)?[\w/\-?=%.]+\.[\w/\-?=%.]+"


class MirrorStatus:
    STATUS_UPLOADING = "Uploading"
    STATUS_DOWNLOADING = "Filename"
    STATUS_WAITING = "Queued"
    STATUS_FAILED = "Failed. Cleaning download"
    STATUS_CANCELLED = "Cancelled"
    STATUS_ARCHIVING = "Archiving"
    STATUS_EXTRACTING = "Extracting"
    STATUS_DOWNLOADINGANDUPLOADING = "Filename"
    STATUS_STALLED = "Stalled"
    STATUS_FETCHING_METADATA = "Getting MetaData"
    STATUS_UNKNOWN = "Unknown"
    STATUS_ALLOCATING = "Allocating"
    STATUS_CHECKING = "Checking"
    STATUS_FORCED = "Forced"
    STATUS_PAUSED = "Paused"
    STATUS_SEEDING = "Seeding"


PROGRESS_MAX_SIZE = 100 // 8
PROGRESS_INCOMPLETE = ['▏', '▎', '▍', '▌', '▋', '▊', '▉']

SIZE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']


class setInterval:
    def __init__(self, interval, action):
        self.interval = interval
        self.action = action
        self.stopEvent = threading.Event()
        thread = threading.Thread(target=self.__setInterval)
        thread.start()

    def __setInterval(self):
        nextTime = time.time() + self.interval
        while not self.stopEvent.wait(nextTime - time.time()):
            nextTime += self.interval
            self.action()

    def cancel(self):
        self.stopEvent.set()


def get_readable_file_size(size_in_bytes) -> str:
    if size_in_bytes is None:
        return '0B'
    index = 0
    while size_in_bytes >= 1024:
        size_in_bytes /= 1024
        index += 1
    try:
        return f'{round(size_in_bytes, 2)}{SIZE_UNITS[index]}'
    except IndexError:
        return 'File too large'


def getDownloadByGid(gid):
    with download_dict_lock:
        for dl in download_dict.values():
            status = dl.status()
            if status != MirrorStatus.STATUS_UPLOADING:
                if dl.gid() == gid:
                    return dl     
    return None

def getDownloadByaria2Gid(gid):
    with download_dict_lock:
        for dl in download_dict.values():
            status = dl.status()
            if status != MirrorStatus.STATUS_UPLOADING:
                if dl.genid() == gid:
                    return dl     
    return None

def get_progress_bar_string(status):
    completed = status.processed_bytes() / 8
    total = status.size_raw() / 8
    if total == 0:
        p = 0
    else:
        p = round(completed * 100 / total)
    p = min(max(p, 0), 100)
    cFull = p // 8
    cPart = p % 8 - 1
    p_str = '█' * cFull
    if cPart >= 0:
        p_str += PROGRESS_INCOMPLETE[cPart]
    p_str += ' ' * (PROGRESS_MAX_SIZE - cFull)
    p_str = f"[{p_str}]"
    return p_str

def get_progress_bar_string_forgd(status):
    completed = status.processed_bytes() / 8
    total = status.size_raw_progress() / 8
    if total == 0:
        p = 0
    else:
        p = round(completed * 100 / total)
    p = min(max(p, 0), 100)
    cFull = p // 8
    cPart = p % 8 - 1
    p_str = '█' * cFull
    if cPart >= 0:
        p_str += PROGRESS_INCOMPLETE[cPart]
    p_str += ' ' * (PROGRESS_MAX_SIZE - cFull)
    p_str = f"[{p_str}]"
    return p_str

#name though lol
def generate_spin(status):
    different = ['◑', '◐', '◒', '◓']
    random_symbol = random.choice(different)
    p_str = f"{random_symbol}"
    return p_str    


def get_readable_message():
    cpuUsage = psutil.cpu_percent(interval=0.5)
    total, used, free, diskpercent = psutil.disk_usage('.')
    memory = psutil.virtual_memory().percent
    dl = 0
    ul = 0
    with download_dict_lock:
        msg = ""
        for download in list(download_dict.values()):
            if download.isgdfolder() is not None and download.isgdfolder() is True:
                msg += f"<b>{download.status()}</b>: <code>{download.name()}</code>" \
                    f"\n<b>Status</b>: <code>Downloading From GDRIVE ▼ </code>"
                if download.downloaded_bytes() != '0B':
                    msg += f"\n<b>Downloaded</b>: <code>{download.downloaded_bytes()} / {download.totalsize()}</code>"
                msg += f"\n<b>Completed</b>: <code>{download.completed()}</code>" \
                       f"\n<i>{download.downloadingname()} | {download.currentsize()}</i>" \
                       f"\n<b>Progress</b>: <code>{get_progress_bar_string_forgd(download)} {download.progress()}</code>" \
                       f"\n<b>Speed</b>: <code>{download.speed()}</code>" \
                       f"\n<b>ETA</b>: <code>{download.eta()}</code>" \
                       f"\n<b>To Stop</b>: <code>/{BotCommands.CancelMirror[0]} {download.gid()}</code>"
                if download.status() == MirrorStatus.STATUS_DOWNLOADING:
                    dl += download.speed_raw()
                msg += "\n\n"    
            elif download.status() == MirrorStatus.STATUS_ARCHIVING or download.status() == MirrorStatus.STATUS_EXTRACTING:
                msg += f"{generate_spin(download)}<i> {download.status()} </i>{generate_spin(download)}: <code>{download.name()}</code>"  \
                       f"\n<b>Source</b>: <code>/{BotCommands.SourceCommand[0]} {download.gid()}</code>" \
                       f"\n<b>Size</b>: <code>{download.size()}</code>" \
                       f"\n\n"     
            elif download.status() == MirrorStatus.STATUS_WAITING:
                msg += f"{generate_spin(download)}<i> {download.status()} </i>{generate_spin(download)}: <code>{download.name()}</code>"  \
                       f"\n<b>Source</b>: <code>/{BotCommands.SourceCommand[0]} {download.gid()}</code>" \
                       f"\n\n"    
            elif download.status() == MirrorStatus.STATUS_ARCHIVING or download.status() == MirrorStatus.STATUS_EXTRACTING or download.status() == MirrorStatus.STATUS_ALLOCATING or download.status() == MirrorStatus.STATUS_WAITING or download.status() == MirrorStatus.STATUS_CHECKING or download.status() == MirrorStatus.STATUS_FORCED or download.status() == MirrorStatus.STATUS_PAUSED or download.status() == MirrorStatus.STATUS_SEEDING:
                msg += f"{generate_spin(download)}<i> {download.status()} </i>{generate_spin(download)}: <code>{download.name()}</code>"  \
                       f"\n<b>Source</b>: <code>/{BotCommands.SourceCommand[0]} {download.gid()}</code>" \
                       f"\n\n"
            elif download.status() == MirrorStatus.STATUS_STALLED or download.status() == MirrorStatus.STATUS_FETCHING_METADATA:
                msg += f"{generate_spin(download)}<i> {download.status()} </i>{generate_spin(download)}: <code>{download.name()}</code>"  \
                       f"\n<b>Cancel</b>: <code>/{BotCommands.CancelMirror[0]} {download.gid()}</code>" \
                       f"\n\n"          
            else:
                msg += f"<b>{download.status()}</b>: <code>{download.name()}</code>"
                if download.completed() is not None:
                    msg += f"\n<b>Status</b>: <code>Downloading From GDRIVE ▼ </code>" \
                        f"\n<b>Completed</b>: <code>{download.completed()}</code>" 
                if download.status() != MirrorStatus.STATUS_ARCHIVING or download.status() != MirrorStatus.STATUS_EXTRACTING or download.status() != MirrorStatus.STATUS_ALLOCATING or download.status() != MirrorStatus.STATUS_WAITING or download.status() != MirrorStatus.STATUS_CHECKING or download.status() != MirrorStatus.STATUS_FORCED or download.status() != MirrorStatus.STATUS_PAUSED or download.status() != MirrorStatus.STATUS_SEEDING:
                    msg += f"\n<b>Size</b>: <code>{download.size()}</code>" \
                        f"\n<b>Progress</b>: <code>{get_progress_bar_string(download)} {download.progress()}</code>" \
                        f"\n<b>Speed</b>: <code>{download.speed()}</code>" \
                        f"\n<b>ETA</b>: <code>{download.eta()}</code>"
                if download.status() == MirrorStatus.STATUS_DOWNLOADING:
                    dl += download.speed_raw()                             
                    if download.seeds() is not None:
                        msg += f"\n<b>Seeders</b>: <code>{download.seeds()}</code>" \
                            f"\t\t\t<b>Peers</b>: <code>{download.leechers()}</code>"
                    msg += f"\n<b>To Stop</b>: <code>/{BotCommands.CancelMirror[0]} {download.gid()}</code>"
                if download.status() == MirrorStatus.STATUS_UPLOADING:
                    ul += download.speed_raw()   
                msg += "\n\n" 
        msg += f"<b>CPU</b>: {cpuUsage}%\t\t<b>DISK</b>: {diskpercent}%\t\t<b>RAM</b>: {memory}%\n" \
               f"<b>DL</b>: <code>{get_readable_file_size(dl)}ps</code> ▼\t<b>UL</b>: <code>{get_readable_file_size(ul)}ps</code> ▲"    
        return msg

def get_readable_time(seconds: int) -> str:
    result = ''
    (days, remainder) = divmod(seconds, 86400)
    days = int(days)
    if days != 0:
        result += f'{days}d'
    (hours, remainder) = divmod(remainder, 3600)
    hours = int(hours)
    if hours != 0:
        result += f'{hours}h'
    (minutes, seconds) = divmod(remainder, 60)
    minutes = int(minutes)
    if minutes != 0:
        result += f'{minutes}m'
    seconds = int(seconds)
    result += f'{seconds}s'
    return result

def get_readable_time_status(totalLength: int, completedLength: int, speed: int) -> str:
    try:
        seconds = (totalLength - completedLength) / speed
        result = ''
        (days, remainder) = divmod(seconds, 86400)
        days = int(days)
        if days != 0:
            result += f'{days}d'
        (hours, remainder) = divmod(remainder, 3600)
        hours = int(hours)
        if hours != 0:
            result += f'\t{hours}h'
        (minutes, seconds) = divmod(remainder, 60)
        minutes = int(minutes)
        if minutes != 0:
            result += f'\t{minutes}m'
        seconds = int(seconds)
        result += f'\t{seconds}s'
        return result
    except ZeroDivisionError:
            return '-'   


def is_url(url: str):
    url = re.findall(URL_REGEX, url)
    if url:
        return True
    return False


def is_magnet(url: str):
    magnet = re.findall(MAGNET_REGEX, url)
    if magnet:
        return True
    return False

def new_thread(fn):
    """To use as decorator to make a function call threaded.
    Needs import
    from threading import Thread"""

    def wrapper(*args, **kwargs):
        thread = threading.Thread(target=fn, args=args, kwargs=kwargs)
        thread.start()
        return thread

    return wrapper

def isgdriveurl(link: str):
    fileId = ''
    if "folders" in link or "file" in link:
        regex = r"https://drive\.google\.com/(drive)?/?u?/?\d?/?(mobile)?/?(file)?(folders)?/?d?/([-\w]+)[?+]?/?(w+)?"
        res = re.search(regex,link)
        if res is None:
            return False
        fileId = res.group(5)
    parsed = urlparse.urlparse(link)
    fileId = parse_qs(parsed.query)['id'][0]   
    if fileId is not None:
        return True
    return False    

def isitwebpage(link: str):
    r = requests.head(link, allow_redirects=True)
    if "text/html" in r.headers["content-type"]:
        html = requests.get(link).text
        return True
    else:
        return False
        
def is_torrent(file_name: str):
    if os.path.exists(file_name) and file_name.lower().endswith(".torrent"):
        return True
    return False

        
