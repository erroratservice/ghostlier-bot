from pyrogram import (
    Client,
    filters
)
from pyrogram.types import Message
from bot import (
    AUTHORIZED_CHATS
)
from bot.helper.mirror_utils.upload_utils.gdriveTools import GoogleDriveHelper
from bot.helper.mirror_utils.download_utils.gdrive_download import GDdownload
from bot.helper.telegram_helper.message_utils import *
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.ext_utils.bot_utils import new_thread
from bot.helper.ext_utils.bot_utils import *

@Client.on_message(
    filters.command(BotCommands.CloneCommand) &
    filters.chat(AUTHORIZED_CHATS)
)
def cloneNode(client: Client, message: Message):
    args = message.text.split(" ",maxsplit=1)
    if args:
        try:
            link = args[1]
        except IndexError:
            link = ''
        try:
            reply_to = message.reply_to_message
            print(reply_to)
            #if reply_to.text:
                #link = reply_to.text
        finally:
            gd = GoogleDriveHelper()
            try:
                file_id = gd.getIdFromUrl(link)
                meta = gd.getFileMetadata(file_id)
                msg = sendMessage(f"Cloning: <code>{meta.get('name')}</code>",client, message)
            except:
                msg = sendMessage(f"Cloning: <code>{link}</code>",client, message)    
            result, button = gd.clone(link, message)
            deleteMessage(msg)
            if button == "":
                sendMessage(result,client, message)
            else:
                sendMarkup(result,client, message,button)
            if not link:
                sendMessage("Provide G-Drive Shareable Link to Clone.",client, message)
    else:
        sendMessage("Provide G-Drive Shareable Link to Clone.",client, message)

@Client.on_message(
    filters.command(BotCommands.GetSizeCommand) &
    filters.chat(AUTHORIZED_CHATS)
)
def getsize(client: Client, message: Message):
    args = message.text.split(" ",maxsplit=1)
    if len(args) > 1:
        link = args[1]
        gd = GDdownload()
        gd.getsizehandle(client, message, link)
    else:
        sendMessage("Provide G-Drive Shareable Link Which You Want me To Get Size Of.",client, message)
