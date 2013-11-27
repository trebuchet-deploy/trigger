import trebuchet.trigger.config
from trebuchet.trigger.drivers.driver import SyncDriver, FileDriver
from git import *

CONF = trigger.config.CONF
LOG = trigger.config.LOG


class SyncDriver(SyncDriver):

    def sync(self):
        raise NotImplementedError


class FileDriver(FileDriver):

    def add_lock(self):
        raise NotImplementedError

    def remove_lock(self):
        raise NotImplementedError

    def check_lock(self):
        raise NotImplementedError
