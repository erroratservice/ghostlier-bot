from aiofiles.os import remove, path as aiopath
from asyncio import sleep

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

# Uncommented for hash computation
from hashlib import sha1
from base64 import b16encode, b32decode
from bencoding import bencode, bdecode
from re import search as re_search

def _get_hash_magnet(mgt: str):
    hash_ = re_search(r'(?<=xt=urn:btih:)[a-zA-Z0-9]+', mgt).group(0)
    if len(hash_) == 32:
        hash_ = b16encode(b32decode(hash_.upper())).decode()
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

        # Compute hash beforehand for older API versions
        if url and url.startswith("magnet:"):
            ext_hash = _get_hash_magnet(url)
        elif tpath:
            ext_hash = _get_hash_file(tpath)
        else:
            # Fallback if unable to compute hash (shouldn't happen for valid inputs)
            ext_hash = None

        # Check WebAPI version
        api_version = await sync_to_async(qbittorrent_client.app_web_api_version)
        supports_tags_in_add = api_version >= '2.6.2'  # Compare as string or parse if needed

        add_to_queue, event = await check_running_tasks(listener)

        # Prepare add kwargs
        add_kwargs = {
            "savepath": path,
            "is_paused": add_to_queue,
            "ratio_limit": ratio,
            "seeding_time_limit": seed_time,
        }
        if supports_tags_in_add:
            add_kwargs["tags"] = f"{listener.mid}"

        if url:
            op = await sync_to_async(qbittorrent_client.torrents_add, url, **add_kwargs)
        else:
            op = await sync_to_async(qbittorrent_client.torrents_add, torrent_files=[tpath], **add_kwargs)

        if op.lower() == "ok.":
            if supports_tags_in_add:
                # Use tag for lookup
                tor_info = await sync_to_async(
                    qbittorrent_client.torrents_info, tag=f"{listener.mid}"
                )
                if len(tor_info) == 0:
                    while True:
                        if add_to_queue and event.is_set():
                            add_to_queue = False
                        tor_info = await sync_to_async(
                            qbittorrent_client.torrents_info, tag=f"{listener.mid}"
                        )
                        if len(tor_info) > 0:
                            break
                        await sleep(1)
                tor_info = tor_info[0]
                ext_hash = tor_info.hash  # Update if needed
            else:
                # For older versions, use hash for lookup (fallback to polling all if hash not computed)
                if ext_hash:
                    lookup_kwargs = {"torrent_hashes": ext_hash}
                else:
                    lookup_kwargs = {}  # Poll all, but risky if many torrents; improve if possible
                tor_info = await sync_to_async(
                    qbittorrent_client.torrents_info, **lookup_kwargs
                )
                if len(tor_info) == 0:
                    while True:
                        if add_to_queue and event.is_set():
                            add_to_queue = False
                        tor_info = await sync_to_async(
                            qbittorrent_client.torrents_info, **lookup_kwargs
                        )
                        if len(tor_info) > 0:
                            break
                        await sleep(1)
                # Assuming the first/newest match; refine if multiple
                tor_info = tor_info[0]
                ext_hash = tor_info.hash

                # Now add the tag separately
                await sync_to_async(
                    qbittorrent_client.torrents_add_tags,
                    torrent_hashes=ext_hash,
                    tags=f"{listener.mid}"
                )

            listener.name = tor_info.name
        else:
            await listener.on_download_error(
                "This Torrent already added or unsupported/invalid link/file.",
            )
            return

        async with task_dict_lock:
            task_dict[listener.mid] = QbittorrentStatus(listener, queued=add_to_queue)
        await on_download_start(f"{listener.mid}")

        if add_to_queue:
            LOGGER.info(f"Added to Queue/Download: {tor_info.name} - Hash: {ext_hash}")
        else:
            LOGGER.info(f"QbitDownload started: {tor_info.name} - Hash: {ext_hash}")

        await listener.on_download_start()

        if config_dict["BASE_URL"] and listener.select:
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

            ext_hash = tor_info.hash
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
            await sync_to_async(
                qbittorrent_client.torrents_resume, torrent_hashes=ext_hash
            )

    except Exception as e:
        await listener.on_download_error(f"{e}")
    finally:
        if tpath and await aiopath.exists(tpath):
            await remove(tpath)
