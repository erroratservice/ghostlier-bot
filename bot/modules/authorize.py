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
from bot.helper.telegram_helper.message_utils import sendMessage
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands


@Client.on_message(
    filters.command(BotCommands.AuthorizeCommand) &
    filters.chat(OWNER_ID)
)
def authorize(client: Client, message: Message):
    reply_message = message.reply_to_message
    msg = ''
    with open('authorized_chats.txt', 'a') as file:
        if reply_message is None:
            # Trying to authorize a chat
            chat_id = message.effective_chat.id
            if chat_id not in AUTHORIZED_CHATS:
                file.write(f'{chat_id}\n')
                AUTHORIZED_CHATS.add(chat_id)
                msg = 'Chat authorized'
            else:
                msg = 'Already authorized chat'
        else:
            # Trying to authorize someone in specific
            user_id = reply_message.from_user.id
            if user_id not in AUTHORIZED_CHATS:
                file.write(f'{user_id}\n')
                AUTHORIZED_CHATS.add(user_id)
                msg = 'Person Authorized to use the bot!'
            else:
                msg = 'Person already authorized'
        sendMessage(msg, client, message)


@Client.on_message(
    filters.command(BotCommands.UnAuthorizeCommand) &
    filters.chat(OWNER_ID)
)
def unauthorize(client: Client, message: Message):
    reply_message = message.reply_to_message
    if reply_message is None:
        # Trying to unauthorize a chat
        chat_id = message.effective_chat.id
        if chat_id in AUTHORIZED_CHATS:
            AUTHORIZED_CHATS.remove(chat_id)
            msg = 'Chat unauthorized'
        else:
            msg = 'Already unauthorized chat'
    else:
        # Trying to authorize someone in specific
        user_id = reply_message.from_user.id
        if user_id in AUTHORIZED_CHATS:
            AUTHORIZED_CHATS.remove(user_id)
            msg = 'Person unauthorized to use the bot!'
        else:
            msg = 'Person already unauthorized!'
    with open('authorized_chats.txt', 'a') as file:
        file.truncate(0)
        for i in AUTHORIZED_CHATS:
            file.write(f'{i}\n')
    sendMessage(msg, client, message)
