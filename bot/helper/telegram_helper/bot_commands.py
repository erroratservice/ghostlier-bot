from bot import (BOT_USERNAME)

class _BotCommands:
    def __init__(self):
        self.StartCommand = ['start',f"start@{BOT_USERNAME}"]
        self.MirrorCommand = ['mirror',f"mirror@{BOT_USERNAME}"]
        self.UnzipMirrorCommand = ['extract',f"extract@{BOT_USERNAME}"]
        self.TarMirrorCommand = ['tar',f"tar@{BOT_USERNAME}"]
        self.ZipMirrorCommand = ['zip',f"zip@{BOT_USERNAME}"]
        self.CancelMirror = ['cancel',f"cancel@{BOT_USERNAME}"]
        self.CancelAllCommand = ['cancelall',f"cancelall@{BOT_USERNAME}"]
        self.ListCommand = ['find',f"find@{BOT_USERNAME}"]
        self.StatusCommand = ['status',f"status@{BOT_USERNAME}"]
        self.AuthorizeCommand = ['authorize',f"authorize@{BOT_USERNAME}"]
        self.UnAuthorizeCommand = ['unauthorize',f"unauthorize@{BOT_USERNAME}"]
        self.PingCommand = ['ping',f"ping@{BOT_USERNAME}"]
        self.RestartCommand = ['restart',f"restart@{BOT_USERNAME}"]
        self.StatsCommand = ['stats',f"stats@{BOT_USERNAME}"]
        self.LogCommand = ['log',f"log@{BOT_USERNAME}"]
        self.CloneCommand = ['clone',f"clone@{BOT_USERNAME}"]
        self.WatchCommand = ['watch',f"watc3@{BOT_USERNAME}"]
        self.TarWatchCommand = ['tarwatch',f"tarwatch@{BOT_USERNAME}"]
        self.ZipWatchCommand = ['zipwatch',f"zipwatch@{BOT_USERNAME}"]
        self.SourceCommand = ['source',f"source@{BOT_USERNAME}"]
        self.GetSizeCommand = ['getsize',f"getsize@{BOT_USERNAME}"]
        self.deleteCommand = ['delete',f"delete@{BOT_USERNAME}"]
        self.wgetCommand = ['wget',f"wget@{BOT_USERNAME}"]

BotCommands = _BotCommands()
