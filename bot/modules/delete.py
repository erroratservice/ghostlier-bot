import os

from pyrogram import (
    Client,
    filters
)
from pyrogram.types import Message
from bot import (
    AUTHORIZED_CHATS,
    OWNER_ID,
    download_dict,
    download_dict_lock,
    DOWNLOAD_DIR
)
import threading
from bot.helper.telegram_helper.message_utils import auto_delete_message, sendMessage
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.mirror_utils.upload_utils import gdriveTools

@Client.on_message(
    filters.command(BotCommands.deleteCommand) &
    filters.chat(OWNER_ID)
)
def deletefile(client: Client, message: Message):
	args = message.text.split(" ",maxsplit=1)
	msg = ''
	try:
		link = args[1]
	except IndexError:
		msg = 'send a link along with command'

	if msg == '' : 
		drive = gdriveTools.GoogleDriveHelper()
		msg = drive.deletefile(link)
	reply_message = sendMessage(msg, client, message)

	threading.Thread(target=auto_delete_message, args=(client, message, reply_message)).start()