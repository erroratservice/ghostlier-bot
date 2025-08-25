from aiofiles.os import remove, path as aiopath
from asyncio import sleep, TimeoutError
from bencoding import bencode, bdecode
from hashlib import sha1
from re import search as re_search
from bot import (
    task_dict,
    task_dict_lock,
    qbittorrent_client,
    LOGGER,
    config_dict,
)
from ...ext_utils.bot_utils import bt_selection_buttons, sync_to_async
from ...ext_utils.task_manager import check_running_tasks
from ...listeners.qbit_listener import on_download_start
from ...mirror_leech_utils.status_utils.qbit_status import QbittorrentStatus
from ...telegram_helper.message_utils import (
    send_message,
    delete_message,
    send_status_message,
)

def _get_hash_magnet(mgt: str):
    hash_ = re_search(r'(?<=xt=urn:btih:)[a-zA-Z0-9]+', mgt).group(0)
    if len(hash_) == 32:
        hash_ = hash_.upper().decode('hex')
    return hash_

def _get_hash_file(fpath):
    with open(fpath, "rb") as f:
        decodedDict = bdecode(f.read())
        return sha1(bencode(decodedDict[b'info'])).hexdigest()

async def add_qb_torrent(listener, path, ratio, seed_time):
    try:
        url = listener.link
        tpath = None
        if await aiopath.exists(listener.link):
            url = None
            tpath = listener.link
            ext_hash = _get_hash_file(tpath)
        else:
            ext_hash = _get_hash_magnet(listener.link)

        add_to_queue, event = await check_running_tasks(listener)
        
        LOGGER.info(f"Adding torrent to qBittorrent...")
        op = await sync_to_async(
            qbittorrent_client.torrents_add,
            urls=url,
            torrent_files=tpath,
            save_path=path,
            is_paused=add_to_queue,
            # We explicitly remove the 'tags' parameter here because it's not
            # supported in this qBittorrent version's API.
            ratio_limit=ratio,
            seeding_time_limit=seed_time,
        )
        LOGGER.info(f"torrents_add response: {op}")

        if op.lower() != "ok.":
            await listener.on_download_error(
                "This Torrent already added or unsupported/invalid link/file.",
            )
            return

        # The crucial fix: Wait until the torrent is fully processed and exists
        while True:
            try:
                torrents_info = await sync_to_async(qbittorrent_client.torrents_info, torrent_hashes=ext_hash)
                if torrents_info:
                    tor_info = torrents_info[0]
                    break
            except Exception as e:
                LOGGER.error(f"Error during torrent info lookup: {e}")
            await sleep(1)

        # Now that we have the torrent by its permanent hash, we can apply the tag reliably.
        LOGGER.info(f"Found torrent info. Hash: {ext_hash}. Attempting to set tag: {listener.mid}")
        await sync_to_async(
            qbittorrent_client.torrents_set_tags, 
            torrent_hashes=ext_hash, 
            tags=f"{listener.mid}"
        )
        LOGGER.info("Tag set successfully. Now proceeding with download.")
        
        listener.name = tor_info.name
        
        async with task_dict_lock:
            task_dict[listener.mid] = QbittorrentStatus(listener, queued=add_to_queue)
        await on_download_start(f"{listener.mid}")

        if add_to_queue:
            LOGGER.info(f"Added to Queue/Download: {tor_info.name} - Hash: {ext_hash}")
        else:
            LOGGER.info(f"QbitDownload started: {tor_info.name} - Hash: {ext_hash}")

        await listener.on_download_start()

        if config_dict.get("BASE_URL") and listener.select:
            if listener.link.startswith("magnet:"):
                metamsg = "Downloading Metadata, wait then you can select files. Use torrent file to avoid this wait."
                meta = await send_message(listener.message, metamsg)
                while True:
                    tor_info = await sync_to_async(
                        qbittorrent_client.torrents_info, tag=f"{listener.mid}"
                    )
                    if len(tor_info) == 0:
                        await delete_message(meta)
                        return
                    try:
                        tor_info = tor_info[0]
                        if tor_info.state not in [
                            "metaDL",
                            "checkingResumeData",
                            "pausedDL",
                        ]:
                            await delete_message(meta)
                            break
                    except:
                        await delete_message(meta)
                        return

            if not add_to_queue:
                await sync_to_async(
                    qbittorrent_client.torrents_pause, torrent_hashes=ext_hash
                )
            SBUTTONS = bt_selection_buttons(ext_hash)
            msg = "Your download paused. Choose files then press Done Selecting button to start downloading."
            await send_message(listener.message, msg, SBUTTONS)
        elif listener.multi <= 1:
            await send_status_message(listener.message)

        if event is not None:
            if not event.is_set():
                await event.wait()
                if listener.is_cancelled:
                    return
                async with task_dict_lock:
                    task_dict[listener.mid].queued = False
                LOGGER.info(
                    f"Start Queued Download from Qbittorrent: {tor_info.name} - Hash: {ext_hash}"
                )
            await on_download_start(f"{listener.mid}")
            await sync_to_async(qbittorrent_client.torrents_resume, torrent_hashes=ext_hash)
            
    except Exception as e:
        await listener.on_download_error(f"{e}")
    finally:
        if tpath and await aiopath.exists(tpath):
            await remove(tpath)
