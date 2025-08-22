# -*- coding: utf-8 -*-
# (c) YashDK [yash-dk@github]
import shutil
import qbittorrentapi as qba
import asyncio as aio
import os,logging,traceback,time
from datetime import datetime,timedelta
from bot.helper.ext_utils import Hash_Fetch
from bot.helper.mirror_utils.status_utils.qbit_download_status import QBTask
from bot.helper.telegram_helper.message_utils import *
from bot.helper.ext_utils.exceptions import ProcessCanceled
from bot.helper.mirror_utils.upload_utils.gdriveTools import GoogleDriveHelper
import random
import string
from bot import parent_id, DOWNLOAD_DIR, IS_TEAM_DRIVE, INDEX_URL, \
    USE_SERVICE_ACCOUNTS, ENABLE_DRIVE_SEARCH,  download_dict, download_dict_lock, DOWNLOAD_STATUS_UPDATE_INTERVAL, MAX_TORRENT_SIZE, TELEGRAPH_TOKEN, MAX_SIMULTANEOUS_DOWNLOADS
from telegraph import Telegraph
from bot.helper.ext_utils.bot_utils import setInterval
import subprocess

global_lock = threading.Lock()
GLOBAL_GID = set()

#logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)
# logging.getLogger('qbittorrentapi').setLevel(logging.ERROR)
# logging.getLogger('requests').setLevel(logging.ERROR)
# logging.getLogger('urllib3').setLevel(logging.ERROR)

class QbitWrap:
    def __init__(self):
        super().__init__()
        self.__listener = None
        self.updater = None
        self.update_interval = 5
        self._torrent = None
        self.gid = None
        self._client = None
        self.message = None
        self.task = None
        self._is_canceled = False
        self.is_active = True
        self.meta_time = None
        self.stalled_time = None
        self.checkindrive = True
        self.sizeavail = True
        self.gl_enabled = True

    def get_client(self, host=None,port=None,uname=None,passw=None,retry=2) -> qba.TorrentsAPIMixIn:
        """Creats and returns a client to communicate with qBittorrent server. Max Retries 2
        """
        #getting the conn 
        host = host if host is not None else "localhost"
        port = port if port is not None else "8090"
        uname = uname if uname is not None else "admin"
        passw = passw if passw is not None else "adminadmin"
        LOGGER.info(f"Trying to login in qBittorrent using creds {host} {port} {uname} {passw}")

        client = qba.Client(host=host,port=port,username=uname,password=passw)
        
        #try to connect to the server :)
        try:
            client.auth_log_in()
            LOGGER.info("Client connected successfully to the torrent server. :)")
            client.application.set_preferences({"disk_cache":20,"incomplete_files_ext":True,"max_connec":3000,"max_connec_per_torrent":300,"async_io_threads":6,"max_active_torrents":MAX_SIMULTANEOUS_DOWNLOADS,"max_active_downloads":MAX_SIMULTANEOUS_DOWNLOADS,"max_active_uploads":MAX_SIMULTANEOUS_DOWNLOADS})
            LOGGER.debug("Setting the cache size to 20 incomplete_files_ext:True,max_connec:3000,max_connec_per_torrent:300,async_io_threads:6")
            return client
        except qba.LoginFailed as e:
            LOGGER.error("An errot occured invalid creds detected\n{}\n{}".format(e,traceback.format_exc()))
            return None
        except qba.APIConnectionError:
            if retry == 0:
                LOGGER.error("Tried to get the client 3 times no luck")
                return None
            
            LOGGER.info("Oddly enough the qbittorrent server is not running.... Attempting to start at port {}".format(port))
            cmd = f"qbittorrent-nox -d --webui-port={port}"
            cmd = cmd.split(" ")

            result = subprocess.run(["qbittorrent-nox", "-d", f"--webui-port={port}"])
            # subpr = subprocess.Popen(*cmd, stdout=subprocess.PIPE)
            # #subpr = aio.create_subprocess_exec(*cmd,stderr=aio.subprocess.PIPE,stdout=aio.subprocess.PIPE)
            # subpr.communicate()
            return self.get_client(host,port,uname,passw,retry=retry-1)


    def add_torrent_magnet(self, magnet,message):
        print("""Adds a torrent by its magnet link.
        """)
        client = self.get_client()
        try:
            ctor = len(client.torrents_info())
            
            ext_hash = Hash_Fetch.get_hash_magnet(magnet)
            ext_res = client.torrents_info(torrent_hashes=ext_hash)
            if len(ext_res) > 0:
                LOGGER.info(f"This torrent is in list {ext_res} {magnet} {ext_hash}")
                sendMessage(f"This torrent is alreaded in the leech list.", self.__listener.bot, self.__listener.message) 
                return False
            # hot fix for the below issue
            savepath = os.path.join(DOWNLOAD_DIR, str(self.__listener.uid))
            LOGGER.info(f"Path is {savepath}")
            op = client.torrents_add(magnet, save_path=savepath)

            LOGGER.info(f"op is {op}")
            
            
            # TODO uncomment the below line and remove the above fix when fixed https://github.com/qbittorrent/qBittorrent/issues/13572
            # op = client.torrents_add(magnet)

            # torrents_add method dosent return anything so have to work around
            if op.lower() == "ok.":
                st = datetime.now()
                
                ext_res = client.torrents_info(torrent_hashes=ext_hash)
                if len(ext_res) > 0:
                    #LOGGER.info(f"Yayayay! Got torrent info from ext hash. {ext_res[0]}")
                    return ext_res[0]
                while True:
                    if (datetime.now() - st).seconds >= 10:
                        LOGGER.warning("The provided torrent was not added and it was timed out. magnet was:- {}".format(magnet))
                        LOGGER.error(ext_hash)
                        sendMessage(f"The torrent was not added due to an error.", self.__listener.bot, self.__listener.message) 
                        return False
                    # commenting in favour of wrong torrent getting returned
                    # ctor_new = client.torrents_info()
                    #if len(ctor_new) > ctor:
                    #    # https://t.me/c/1439207386/2977 below line is for this
                    #    LOGGER.info(ctor_new)
                    #    LOGGER.info(magnet)
                    #    return ctor_new[0]
                    ext_res = client.torrents_info(torrent_hashes=ext_hash)
                    if len(ext_res) > 0:
                        LOGGER.info("Got torrent info from ext hash.")
                        return ext_res[0]
            else:
                sendMessage(f"This is an unsupported/invalid link.", self.__listener.bot, self.__listener.message) 
        except qba.UnsupportedMediaType415Error as e:
            #will not be used ever ;)
            LOGGER.error("Unsupported file was detected in the magnet here")
            sendMessage(f"This is an unsupported/invalid link.", self.__listener.bot, self.__listener.message) 
            return False
        except Exception as e:
            LOGGER.error("{}\n{}".format(e,traceback.format_exc()))
            sendMessage(f"Error occured check logs.", self.__listener.bot, self.__listener.message) 
            return False

    def add_torrent_file(self, path,message):
        if not os.path.exists(path):
            LOGGER.error("The path supplied to the torrent file was invalid.\n path:-{}".format(path))
            return False

        client = self.get_client()
        try:
            ctor = len(client.torrents_info())

            ext_hash = Hash_Fetch.get_hash_file(path)
            ext_res = client.torrents_info(torrent_hashes=ext_hash)
            if len(ext_res) > 0:
                LOGGER.info(f"This torrent is in list {ext_res} {path} {ext_hash}")
                sendMessage(f"This torrent is alreaded in the leech list.", self.__listener.bot, self.__listener.message) 
                return False
            
            # hot fix for the below issue
            savepath = os.path.join(DOWNLOAD_DIR, str(self.__listener.uid))

            op = client.torrents_add(torrent_files=[path], save_path=savepath)
            
            # TODO uncomment the below line and remove the above fix when fixed https://github.com/qbittorrent/qBittorrent/issues/13572
            # op = client.torrents_add(torrent_files=[path])
            #this method dosent return anything so have to work around
            
            if op.lower() == "ok.":
                st = datetime.now()
                
                ext_res = client.torrents_info(torrent_hashes=ext_hash)
                if len(ext_res) > 0:
                    LOGGER.info("Got torrent info from ext hash.")
                    return ext_res[0]

                while True:
                    if (datetime.now() - st).seconds >= 20:
                        LOGGER.warning("The provided torrent was not added and it was timed out. file path was:- {}".format(path))
                        LOGGER.error(ext_hash)
                        sendMessage(f"The torrent was not added due to an error.", self.__listener.bot, self.__listener.message) 
                        return False
                    #ctor_new = client.torrents_info()
                    #if len(ctor_new) > ctor:
                    #    return ctor_new[0]
                    ext_res = client.torrents_info(torrent_hashes=ext_hash)
                    if len(ext_res) > 0:
                        LOGGER.info("Got torrent info from ext hash.")
                        return ext_res[0]

            else:
                sendMessage(f"This is an unsupported/invalid link.", self.__listener.bot, self.__listener.message) 
        except qba.UnsupportedMediaType415Error as e:
            #will not be used ever ;)
            LOGGER.error("Unsupported file was detected in the magnet here")
            sendMessage(f"This is an unsupported/invalid link.", self.__listener.bot, self.__listener.message) 
            return False
        except Exception as e:
            LOGGER.error("{}\n{}".format(e,traceback.format_exc()))
            sendMessage(f"Error occured check logs.", self.__listener.bot, self.__listener.message) 
            return False

    def cancel_download(self):
        LOGGER.info(f'Cancelling download on user request')
        self._is_canceled = True   

    def update_progress(self, client=None,message=None,torrent=None,task=None,except_retry=0,sleepsec=None):
        #task = QBTask(torrent, message, client)
        try:
            client = self._client
            message = self.message
            task = self.task
            torrent = self._torrent
            sleepsec = int(DOWNLOAD_STATUS_UPDATE_INTERVAL)
            #switch to iteration from recursion as python dosent have tailing optimization :O
            #RecursionError: maximum recursion depth exceeded
            is_meta = False
            is_stalled = False
            tor_info = client.torrents_info(torrent_hashes=torrent.hash)
            #update cancellation

            #LOGGER.info(f"hash is {tor_info.hash}")
            if self._is_canceled:
                self.updater.cancel()
                raise ProcessCanceled

            if len(tor_info) > 0:
                tor_info = tor_info[0]
            else:
                task.cancel = True
                task.set_inactive()
                message.edit("Torrent canceled ```{}``` ".format(torrent.name),buttons=None)
            
            if int(tor_info.size) > (int(MAX_TORRENT_SIZE) * 1024 * 1024 * 1024):
                self.__onDownloadError(f"<b>Torrent Max Size Allowed is {MAX_TORRENT_SIZE}GB. Thus Download Stopped!.</b>")
                client.torrents_delete(torrent_hashes=tor_info.hash,delete_files=True)
                self.updater.cancel()
            try:
                task.refresh_info(tor_info)

                if  tor_info.state == "metaDL":
                    is_meta = True
                else:
                    self.meta_time = time.time()
                    is_meta = False

                if (is_meta and (time.time() - self.meta_time) > 360):
                    self.__onDownloadError(f"<b>Getting MetaData of {tor_info.name} Failed</b>. <i>Thus Download Stopped!.</i>")
                    client.torrents_delete(torrent_hashes=tor_info.hash,delete_files=True)
                    self.updater.cancel()
                
                if  tor_info.state == "stalledDL":
                    is_stalled = True
                else:
                    self.stalled_time = time.time()
                    is_stalled = False

                if (is_stalled and (time.time() - self.stalled_time) > 360):
                    self.__onDownloadError(f"<b>{tor_info.name} was Stalled and Thus Failed</b>. <i>Thus Download Stopped!.</i>\n#deadtorrent")
                    client.torrents_delete(torrent_hashes=tor_info.hash,delete_files=True)
                    self.updater.cancel()

                if tor_info.state != "metaDL":
                    if self.checkindrive:
                        self.checkindrive = False
                        if ENABLE_DRIVE_SEARCH:
                            gdrive = GoogleDriveHelper(None)
                            msg = gdrive.search_drives(tor_info.name)
                            if msg:   
                                response = Telegraph(access_token=TELEGRAPH_TOKEN).create_page(
                                                    title = 'ShiNobi Drive',
                                                    author_name='ShiNobi-GhostLeech',
                                                    html_content=msg
                                                    )['path']
                                telegraph = f"Search Results for {tor_info.name}👇\nhttps://telegra.ph/{response}"
                                self.__listener.onDownloadAlreadyComplete(f"{telegraph}")
                                client.torrents_delete(torrent_hashes=tor_info.hash,delete_files=True)
                                self.cancel_download()    

                if tor_info.state == "error":

                    self.__onDownloadError(f"<b>Torrent {tor_info.name} Errored Out!. Thus Download Stopped!.</b>")
                    client.torrents_delete(torrent_hashes=tor_info.hash,delete_files=True)
                    self.updater.cancel()
                
                #aio timeout have to switch to global something
                # time.sleep(sleepsec)
                if self.is_active:
                    #stop the download when download complete
                    if tor_info.state == "uploading" or tor_info.state.lower().endswith("up"):
                        # this is to address the situations where the name would cahnge abdruptly
                        client.torrents_pause(tor_info.hash)

                        # TODO uncomment the below line when fixed https://github.com/qbittorrent/qBittorrent/issues/13572
                        # savepath = os.path.join(tor_info.save_path,tor_info.name)
                        # hot fix
                        try:
                            savepath = os.path.join(tor_info.save_path, os.listdir(tor_info.save_path)[-1])
                            print(savepath)
                            print(tor_info.save_path)
                        except:
                            #self.__onDownloadError(f"<b>Torrent Download of {tor_info.name} Failed!. Thus Download Stopped!.</b>")
                            client.torrents_delete(torrent_hashes=tor_info.hash,delete_files=True)
                            self.updater.cancel()

                        task.set_path(savepath)
                        self.isactive = False
                        print("torrent Downloaded!!!!!")
                        self.__onDownloadComplete()
                        self.updater.cancel()
                    else:
                        #return update_progress(client,message,torrent)
                        pass
                    
            except Exception as e:
                LOGGER.error("{}\n\n{}\n\nn{}".format(e,traceback.format_exc(),tor_info))
                try:
                    message.edit("Error occure {}".format(e),buttons=None)
                except:pass
                return False
        except ProcessCanceled:
            self.__onDownloadError("<b>QbitTorrent Download Stopped.</b>")

    def __onDownloadError(self, error):
        with global_lock:
            try:
                GLOBAL_GID.remove(self.gid)
            except KeyError:
                pass
        self.__listener.onDownloadError(error)

    def pause_all(self, message):
        client = get_client()
        client.torrents_pause(torrent_hashes='all')
        aio.sleep(1)
        msg = ""
        tors = client.torrents_info(status_filter="paused|stalled")
        msg += "⏸️ Paused total <b>{}</b> torrents ⏸️\n".format(len(tors))

        for i in tors:
            if i.progress == 1:
                continue
            msg += "➡️<code>{}</code> - <b>{}%</b>\n".format(i.name,round(i.progress*100,2))

        message.reply(msg,parse_mode="html")
        message.delete()

    def resume_all(self, message):
        client = get_client()
        client.torrents_resume(torrent_hashes='all')

        aio.sleep(1)
        msg = ""
        tors = client.torrents_info(status_filter="stalled|downloading|stalled_downloading")
        
        msg += "▶️Resumed {} torrents check the status for more...▶️".format(len(tors))

        for i in tors:
            if i.progress == 1:
                continue
            msg += "➡️<code>{}</code> - <b>{}%</b>\n".format(i.name,round(i.progress*100,2))

        message.reply(msg,parse_mode="html")
        message.delete()

    def delete_all(self, message):
        client = get_client()
        tors = client.torrents_info()
        msg = "☠️ Deleted <b>{}</b> torrents.☠️".format(len(tors))
        client.torrents_delete(delete_files=True,torrent_hashes="all")

        message.reply(msg,parse_mode="html")
        message.delete()
        
    def delete_this(self, ext_hash):
        client = get_client()
        client.torrents_delete(delete_files=True,torrent_hashes=ext_hash)
        return True

    def get_status(self, message,all=False):
        client = get_client()
        tors = client.torrents_info()
        olen = 0

        if len(tors) > 0:
            msg = ""
            for i in tors:
                if i.progress == 1 and not all:
                    continue
                else:
                    olen += 1
                    msg += "📥 <b>{} | {}% | {}/{}({}) | {} | {} | S:{} | L:{} | {}</b>\n\n".format(
                        i.name,
                        round(i.progress*100,2),
                        human_readable_bytes(i.completed),
                        human_readable_bytes(i.size),
                        human_readable_bytes(i.total_size),
                        human_readable_bytes(i.dlspeed,postfix="/s"),
                        human_readable_timedelta(i.eta),
                        i.num_seeds,
                        i.num_leechs,
                        i.state
                    )
            if msg.strip() == "":
                return "No torrents running currently...." 
            return msg
        else:
            msg = "No torrents running currently...."
            return msg
        
        if olen == 0:
            msg = "No torrents running currently...."
            return msg



    def progress_bar(self, percentage):
        """Returns a progress bar for download
        """
        #percentage is on the scale of 0-1
        comp = get_val("COMPLETED_STR")
        ncomp = get_val("REMAINING_STR")
        pr = ""

        for i in range(1,11):
            if i <= int(percentage*10):
                pr += comp
            else:
                pr += ncomp
        return pr

    def deregister_torrent(self, hashid):
        client = self.get_client()
        client.torrents_delete(torrent_hashes=hashid,delete_files=True)

    def ghostleech(self):
        rmmsg = f"<b>Removed These Trackers</b>\n"
        isdone = False
        while True:
            trackers = self._client.torrents_trackers(torrent_hash=self._torrent.hash)
            trackers = trackers[3:]
            print(trackers)
            for x in trackers:
                if x.status == 2 or x.status == 3 or isdone:
                    print(f"Removing {x.url} with status {x.status}")
                    rmmsg += f"<code>{x.url}</code>\n"
                    self._client.torrents_remove_trackers(torrent_hash=self._torrent.hash,urls=x.url)
                    isdone = True
            time.sleep(0.5)
            if isdone:
                break
        sendMessage(rmmsg, self.__listener.bot, self.__listener.message) 


    def register_torrent(self, bot,message,link,listener,magnet=False,file=False):
        # try:
        client = self.get_client()
        self.__listener = listener
        if magnet:
            LOGGER.info(f"magnet :- {link}")
            torrent = self.add_torrent_magnet(link,message)
            if isinstance(torrent,bool):
                return False
            LOGGER.info(torrent)
            if torrent.progress == 1 and torrent.completion_on > 1:
                sendMessage(f"The provided torrent was already completly downloaded.", self.__listener.bot, self.__listener.message) 
                return True
            else:
                self.__onDownloadStart(listener, torrent, message, client)
                self.meta_time = time.time()
                self.stalled_time = time.time()
                self._client = client
                self._torrent = torrent
                self.message = message
                if self.gl_enabled:
                    self.ghostleech()
                self.updater = setInterval(self.update_interval, self.update_progress) 
                update_all_messages()
        if file:
            torrent = self.add_torrent_file(link,message)
            if isinstance(torrent,bool):
                return False
            LOGGER.info(torrent)
            
            if torrent.progress == 1:
                sendMessage(f"The provided torrent was already completly downloaded.", self.__listener.bot, self.__listener.message) 
                return True
            else:
                self.__onDownloadStart(listener, torrent, message, client)
                self.meta_time = time.time()
                self.stalled_time = time.time()
                self._client = client
                self._torrent = torrent
                self.message = message
                if self.gl_enabled:
                    self.ghostleech()
                self.updater = setInterval(self.update_interval, self.update_progress) 
                update_all_messages()
        # except ProcessCanceled:
        #         self.__onDownloadError("<b>QbitTorrent Download Stopped.</b>")
        # finally:
        #     self.updater.cancel()
        #     self.__onDownloadComplete()

    def __onDownloadComplete(self):
        self.__listener.onDownloadComplete() 

    def __onDownloadStart(self, listener, torrent, message, client):
        self.gid = ''.join(random.SystemRandom().choices(string.ascii_letters + string.digits, k=4)) 
        with download_dict_lock:
            task = QBTask(self, listener, torrent, message, client)
            download_dict[listener.uid] = task
            self.task = task
            #self.update_progress(client,message,torrent, task)
        with global_lock:
            GLOBAL_GID.add(self.gid)
        listener.onDownloadStarted()
