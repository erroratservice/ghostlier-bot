import signal
import pickle
import os
from os import path, remove
from pyrogram import Client, idle
from pyrogram import enums
from bot import (
    BOT_TOKEN,
    DOWNLOAD_DIR,
    LOGGER,
    TELEGRAM_API,
    TELEGRAM_HASH
)
from bot.helper.ext_utils import fs_utils

BOT_USERNAME = None

def main():
    fs_utils.start_cleanup()
    # Check if the bot is restarting
    if path.exists('restart.pickle'):
        with open('restart.pickle', 'rb') as status:
            restart_message = pickle.load(status)
        restart_message.edit_text("Restarted Successfully!")
        remove('restart.pickle')

    plugins = dict(
        root="bot/modules"
    )
    app = Client(
        ":memory:",
        api_id=TELEGRAM_API,
        api_hash=TELEGRAM_HASH,
        plugins=plugins,
        bot_token=BOT_TOKEN,
        workdir=DOWNLOAD_DIR
    )

    app.set_parse_mode(enums.ParseMode.HTML)

    LOGGER.info("Bot Started!")

    os.mkdir(DOWNLOAD_DIR)
    
    app.start()

    idle() 

    # app.send_message(chat_id="-1001271941524", text="Bot Session Started #booted")

    try:
        signal.signal(signal.SIGINT, fs_utils.exit_clean_up)
    except Exception as e:
        print(e)   

if __name__ == "__main__":
    main()    