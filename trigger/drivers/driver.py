class Driver(object):

    def get_config(self):
        return {}


class SyncDriverError(Exception):

    def __init__(self, message):
        Exception.__init__(self, message)

    def __str__(self):
        return self.message


class SyncDriver(Driver):

    def sync(self, args):
        raise NotImplementedError


class FileDriverError(Exception):

    def __init__(self, message):
        Exception.__init__(self, message)

    def __str__(self):
        return self.message


class FileDriver(Driver):

    def check_lock(self):
        raise NotImplementedError

    def add_lock(self):
        raise NotImplementedError

    def remove_lock(self):
        raise NotImplementedError

    def write_deploy_file(self, tag):
        raise NotImplementedError
