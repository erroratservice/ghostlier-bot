import logging
import os
import threading
import time

import aria2p
from dotenv import load_dotenv
import socket
from pyrogram import Client

socket.setdefaulttimeout(600)

botStartTime = time.time()
if os.path.exists('log.txt'):
    with open('log.txt', 'r+') as f:
        f.truncate(0)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('log.txt'), logging.StreamHandler()],
                    level=logging.INFO)

logging.getLogger("pyrogram").setLevel(logging.WARNING)

load_dotenv('config.env')

Interval = []


def getConfig(name: str):
    return os.environ[name]


LOGGER = logging.getLogger(__name__)

try:
    if bool(getConfig('_____REMOVE_THIS_LINE_____')):
        logging.error('The README.md file there to be read! Exiting now!')
        exit()
except KeyError:
    pass

aria2 = aria2p.API(
    aria2p.Client(
        host="http://localhost",
        port=6800,
        secret="",
    )
)

OWNER_ID = int(getConfig('OWNER_ID'))

DOWNLOAD_DIR = None
BOT_TOKEN = None

download_dict_lock = threading.Lock()
status_reply_dict_lock = threading.Lock()
# Key: update.effective_chat.id
# Value: telegram.Message
status_reply_dict = {}
# Key: update.message.id
# Value: An object of Status
download_dict = {}
# Stores list of users and chats the bot is authorized to use in       
AUTHORIZED_CHATS = set()
if os.path.exists('authorized_chats.txt'):
    with open('authorized_chats.txt', 'r+') as f:
        lines = f.readlines()
        for line in lines:
            #    LOGGER.info(line.split())
            AUTHORIZED_CHATS.add(int(line.split()[0]))
AUTHORIZED_CHATS = list(AUTHORIZED_CHATS)
AUTHORIZED_CHATS.append(OWNER_ID)
AUTHORIZED_CHATS = list(set(AUTHORIZED_CHATS)) 

try:
    BOT_TOKEN = getConfig('BOT_TOKEN')
    parent_id = getConfig('GDRIVE_FOLDER_ID')
    DOWNLOAD_DIR = getConfig('DOWNLOAD_DIR')
    if DOWNLOAD_DIR[-1] != '/' or DOWNLOAD_DIR[-1] != '\\':
        DOWNLOAD_DIR = DOWNLOAD_DIR + '/'
    DOWNLOAD_STATUS_UPDATE_INTERVAL = int(getConfig('DOWNLOAD_STATUS_UPDATE_INTERVAL'))
    AUTO_DELETE_MESSAGE_DURATION = int(getConfig('AUTO_DELETE_MESSAGE_DURATION'))
    TELEGRAM_API = getConfig('TELEGRAM_API')
    TELEGRAM_HASH = getConfig('TELEGRAM_HASH')
    BOT_USERNAME = getConfig('BOT_USERNAME')
    MAX_TORRENT_SIZE = getConfig('MAX_TORRENT_SIZE')
    TELEGRAPH_TOKEN = getConfig('TELEGRAPH_TOKEN')
    MAX_SIMULTANEOUS_DOWNLOADS = getConfig('MAX_SIMULTANEOUS_DOWNLOADS')
except KeyError as e:
    LOGGER.error("One or more env variables missing! Exiting now")
    exit(1)
LOGGER.info("Generating USER_SESSION_STRING")
with Client(':memory:', api_id=int(TELEGRAM_API), api_hash=TELEGRAM_HASH, bot_token=BOT_TOKEN) as app:
    USER_SESSION_STRING = app.export_session_string()
try:
    INDEX_URL = getConfig('INDEX_URL')
    if len(INDEX_URL) == 0:
        INDEX_URL = None
except KeyError:
    INDEX_URL = None
try:
    IS_TEAM_DRIVE = getConfig('IS_TEAM_DRIVE')
    if IS_TEAM_DRIVE.lower() == 'true':
        IS_TEAM_DRIVE = True
    else:
        IS_TEAM_DRIVE = False
except KeyError:
    IS_TEAM_DRIVE = False

try:
    USE_SERVICE_ACCOUNTS = getConfig('USE_SERVICE_ACCOUNTS')
    if USE_SERVICE_ACCOUNTS.lower() == 'true':
        USE_SERVICE_ACCOUNTS = True
    else:
        USE_SERVICE_ACCOUNTS = False
except KeyError:
    USE_SERVICE_ACCOUNTS = False

try:
    ENABLE_DRIVE_SEARCH = getConfig('ENABLE_DRIVE_SEARCH')
    if ENABLE_DRIVE_SEARCH.lower() == 'true':
        ENABLE_DRIVE_SEARCH = True
    else:
        ENABLE_DRIVE_SEARCH = False
except KeyError:
    ENABLE_DRIVE_SEARCH = False
