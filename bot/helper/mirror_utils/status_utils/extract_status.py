from .status import Status
from bot.helper.ext_utils.bot_utils import get_readable_file_size, MirrorStatus


class ExtractStatus(Status):
    def __init__(self, name, path, size, gid, source):
        self.__name = name
        self.__path = path
        self.__size = size
        self.__gid = gid
        self.message = source

    # The progress of extract function cannot be tracked. So we just return dummy values.
    # If this is possible in future,we should implement it

    def progress(self):
        return '0'

    def speed(self):
        return '0'

    def speed_raw(self):
        return '0'   

    def isgdfolder(self):
        return None     

    def name(self):
        return self.__name

    def path(self):
        return self.__path

    def size(self):
        return get_readable_file_size(self.__size)

    def eta(self):
        return '0s'

    def status(self):
        return MirrorStatus.STATUS_EXTRACTING

    def processed_bytes(self):
        return 0

    def completed(self):
        return None    

    def gid(self):
        return self.__gid  
          
    def genid(self):
        return None  

    #another sasta hack for source to work we return the source message
    def sourceobj(self):
        return self.message      

    def which_client(self):
        return None

    def seeds(self):
        return None

    def leechers(self):
        return None