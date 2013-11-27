class Driver(object):

    def get_config(self):
        return {}


class SyncDriver(Driver):

    def sync(self):
        raise NotImplementedError


class LockDriver(Driver):

    def add_lock(self):
        raise NotImplementedError

    def remove_lock(self):
        raise NotImplementedError

    def write_deploy_file(self):
        raise NotImplementedError
