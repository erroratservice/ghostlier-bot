from pyrogram import (
    Client,
    filters
)
from bot import TELEGRAPH_TOKEN
from pyrogram.types import Message
from bot.helper.mirror_utils.upload_utils.gdriveTools import GoogleDriveHelper
from bot import LOGGER, AUTHORIZED_CHATS
from bot.helper.telegram_helper.message_utils import auto_delete_message, sendMessage, SendDocument
import threading
from bot.helper.telegram_helper.bot_commands import BotCommands
from telegraph import Telegraph
import random
import string
import os

@Client.on_message(
    filters.command(BotCommands.ListCommand) &
    filters.chat(AUTHORIZED_CHATS)
)
def list_drive(client: Client, message: Message):
    search = message.text.split(' ', maxsplit=1)[1]
    LOGGER.info(f"Searching: {search}")
    searchmsg = sendMessage(f"Searching <code>{search}</code>",client,message)
    gdrive = GoogleDriveHelper(None)
    msg = gdrive.drive_list(search)
    response = Telegraph(access_token=TELEGRAPH_TOKEN).create_page(
                                                    title = 'ShiNobi Drive',
                                                    author_name='ShiNobi-Ghost',
                                                    html_content=msg
                                                    )['path']
    telegraph = f"Search Results for {search}👇\nhttps://telegra.ph/{response}"
    if telegraph:
        reply_message = sendMessage(telegraph, client, message)
    else:
        reply_message = sendMessage('No result found', client, message)
    
    threading.Thread(target=auto_delete_message, args=(client, message, searchmsg)).start()

