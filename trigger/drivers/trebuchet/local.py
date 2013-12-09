import trigger.config as config
from trigger.driver import SyncDriver, FileDriver

CONF = config.CONF
LOG = config.LOG


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
