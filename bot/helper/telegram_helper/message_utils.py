from pyrogram import Client
from pyrogram.types import Message
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import time
from bot import AUTO_DELETE_MESSAGE_DURATION, LOGGER, \
    status_reply_dict, status_reply_dict_lock
from bot.helper.ext_utils.bot_utils import get_readable_message
from bot.helper.telegram_helper.bot_commands import BotCommands
import threading
import os

def sendMessage(text: str, bot: Client, message: Message):
    try:
        return bot.send_message(chat_id=message.chat.id,
                            reply_to_message_id=message.id,
                            text=text)
    except Exception as e:
        LOGGER.error(str(e))

def sendMarkup(text: str, bot: Client, message: Message, reply_markup: InlineKeyboardMarkup):
    try:
        return bot.send_message(chat_id = message.chat.id,
                             reply_to_message_id=message.id,
                             text=text, reply_markup=reply_markup)
    except Exception as e:
        LOGGER.error(str(e))        


def editMessage(text: str, message: Message):
    try:
        message.edit_text(text)
    except Exception as e:
        LOGGER.error(str(e))


def deleteMessage(message: Message):
    try:
        message.delete()
    except Exception as e:
        LOGGER.error(str(e))


async def deleteMessageasync(message: Message):
    try:
        await message.delete()
    except Exception as e:
        LOGGER.error(str(e))

def sendLogFile(bot: Client, message: Message):
    f = 'log.txt'
    bot.send_document(
        document=f,
        reply_to_message_id=message.id,
        chat_id=message.chat.id
    )


def auto_delete_message(bot, cmd_message: Message, bot_message: Message):
    if AUTO_DELETE_MESSAGE_DURATION != -1:
        time.sleep(AUTO_DELETE_MESSAGE_DURATION)
        try:
            # Skip if None is passed meaning we don't want to delete bot or cmd message
            deleteMessage(cmd_message)
            deleteMessage(bot_message)
        except AttributeError:
            pass


def delete_all_messages():
    with status_reply_dict_lock:
        for message in list(status_reply_dict.values()):
            try:
                deleteMessage(message)
                del status_reply_dict[message.chat.id]
            except Exception as e:
                LOGGER.error(str(e))

async def delete_all_messages_async():
    with status_reply_dict_lock:
        for message in list(status_reply_dict.values()):
            try:
                await deleteMessageasync(message)
                del status_reply_dict[message.chat.id]
            except Exception as e:
                LOGGER.error(str(e))

def update_all_messages():
    msg = get_readable_message()
    with status_reply_dict_lock:
        for chat_id in list(status_reply_dict.keys()):
            if status_reply_dict[chat_id] and msg != status_reply_dict[chat_id].text:
                try:
                    editMessage(msg, status_reply_dict[chat_id])
                except Exception as e:
                    LOGGER.error(str(e))
                status_reply_dict[chat_id].text = msg


def sendStatusMessage(msg: Message, bot: Client):
    progress = get_readable_message()
    if len(progress) < 4096:
        with status_reply_dict_lock:
            if msg.chat.id in list(status_reply_dict.keys()):
                try:
                    message = status_reply_dict[msg.chat.id]
                    deleteMessage(message)
                    del status_reply_dict[msg.chat.id]
                except Exception as e:
                    LOGGER.error(str(e))
                    del status_reply_dict[msg.chat.id]
                    pass
            message = sendMessage(progress, bot, msg)
            status_reply_dict[msg.chat.id] = message
    else:
        progress = progress.replace('<b>', '').replace('</b>', '').replace('<code>', '').replace('</code>', '').replace('<i>', '').replace('</i>', '')
        with status_reply_dict_lock:
            if msg.chat.id in list(status_reply_dict.keys()):
                try:
                    message = status_reply_dict[msg.chat.id]
                    deleteMessage(message)
                    del status_reply_dict[msg.chat.id]
                except Exception as e:
                    LOGGER.error(str(e))
                    del status_reply_dict[msg.chat.id]
                    pass
            f = open(f"Status.txt", "w") 
            f.write(progress)
            f.close()        
            message = SendDocument(f"Status.txt", "", bot, msg)
            threading.Thread(target=os.remove, args=(f"Status.txt",)).start()     

def SendDocument(filename, caption, bot: Client, message: Message):
    with open(filename, 'rb') as f:
        bot.send_document(document=f, file_name=f.name,
                          caption=caption,
                          reply_to_message_id=message.id,
                          chat_id=message.chat.id,
                          parse_mode='html')

def sendUriAdded(msg, bot):
    if msg.from_user.username:
        uname = f"@{msg.from_user.username}"
    else:
        uname = f'<a href="tg://user?id={msg.from_user.id}">{msg.from_user.first_name}</a>'
    uriadded = f"URI Added 🔥\nYou May Want to Check Out /{BotCommands.StatusCommand[0]}"
    return uriadded  


async def handle_leech_command(e):
    tsp = time.time()
    buts = []

    # tsp is used to split the callbacks so that each download has its own callback
    # cuz at any time there are 10-20 callbacks linked for leeching XD
        
    buts.append(
            [KeyboardButtonCallback("Upload in a ZIP.[Toggle]", data=f"leechzip toggle {tsp}")]
    )
    buts.append(
            [KeyboardButtonCallback("Extract from Archive.[Toggle]", data=f"leechzipex toggleex {tsp}")]
    )
    
    conf_mes = await e.reply(f"<b>First click if you want to zip the contents or extract as an archive (only one will work at a time) then. </b>\n<b>Choose where to uploadyour files:- </b>\nThe files will be uploaded to default destination after {get_val('DEFAULT_TIMEOUT')} sec of no action by user.\n\n Supported Archives to extract .zip, 7z, tar, gzip2, iso, wim, rar, tar.gz,tar.bz2",parse_mode="html",buttons=buts)
    
    # zip check in background
    ziplist = await get_zip_choice(e,tsp)
    zipext = await get_zip_choice(e,tsp,ext=True)
    
    # blocking leech choice 
    choice = await get_leech_choice(e,tsp)
    
    # zip check in backgroud end
    await get_zip_choice(e,tsp,ziplist,start=False)
    await get_zip_choice(e,tsp,zipext,start=False,ext=True)
    is_zip = ziplist[1]
    is_ext = zipext[1]
    
    
    # Set rclone based on choice
    if choice == "drive":
        rclone = True
    else:
        rclone = False
    
    await conf_mes.delete()

    if rclone:
        if get_val("RCLONE_ENABLED"):
            await check_link(e,rclone, is_zip, is_ext)
        else:
            await e.reply("<b>DRIVE IS DISABLED BY THE ADMIN</b>",parse_mode="html")
    else:
        if get_val("LEECH_ENABLED"):
            await check_link(e,rclone, is_zip, is_ext)
        else:
            await e.reply("<b>TG LEECH IS DISABLED BY THE ADMIN</b>",parse_mode="html")