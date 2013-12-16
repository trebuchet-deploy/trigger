#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

class Driver(object):

    def get_config(self):
        return {}


class SyncDriverError(Exception):

    def __init__(self, message, errorno):
        Exception.__init__(self, message)
        self.errorno = errorno

    def __str__(self):
        return self.message


class SyncDriver(Driver):

    def sync(self, args):
        raise NotImplementedError


class LockDriverError(Exception):

    def __init__(self, message, errorno):
        Exception.__init__(self, message)
        self.errorno = errorno

    def __str__(self):
        return self.message


class LockDriver(Driver):

    def check_lock(self, args):
        raise NotImplementedError

    def add_lock(self, args):
        raise NotImplementedError

    def remove_lock(self, args):
        raise NotImplementedError


class ServiceDriverError(Exception):

    def __init__(self, message, errorno):
        Exception.__init__(self, message)
        self.errorno = errorno

    def __str__(self):
        return self.message


class ServiceDriver(Driver):

    def stop(self, args):
        raise NotImplementedError

    def start(self, args):
        raise NotImplementedError

    def restart(self, args):
        raise NotImplementedError

    def reload(self, args):
        raise NotImplementedError
