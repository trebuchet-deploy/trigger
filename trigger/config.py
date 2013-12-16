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

import sys
import logging
import ConfigParser
from git.repo import Repo

try:
    NullHandler = logging.NullHandler
except AttributeError:
    class NullHandler(logging.Handler):
        def emit(self, record):
            pass

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)


class ConfigurationError(Exception):

    def __init__(self, message, errorno):
        self.message = message
        self.errorno = errorno

    def __str__(self):
        return message


class Configuration(object):

    config = {}
    drivers = {}

    def __init__(self):
        try:
            self.repo = Repo('.')
            self.repo_config = self.repo.config_reader()
        except InvalidGitRepositoryError:
            LOG.error('Not in a git repository')
            sys.exit(1)
        config = {
            'repo-name': ('deploy', 'repo-name', None),
            'user.name': ('user', 'name', None),
            'user.email': ('user', 'email', None),
        }
        self._register_config(config)

    def register_drivers(self):
        driver_config = {
            'sync-driver': ('deploy', 'sync-driver',
                            'trebuchet.local.SyncDriver'),
            'lock-driver': ('deploy', 'lock-driver',
                            'trebuchet.local.LockDriver'),
            'service-driver': ('deploy', 'service-driver',
                               'trebuchet.local.ServiceDriver'),
        }
        self._register_config(driver_config)
        for driver in driver_config:
            LOG.debug('Getting config for driver: {}'.format(driver))
            driver_config = self.config[driver]
            mod, _, cls = driver_config.rpartition('.')
            mod = 'trigger.drivers.' + mod
            try:
                LOG.debug('Importing {}'.format(mod))
                __import__(mod)
                driver_class = getattr(sys.modules[mod], cls)
                self.drivers[driver] = driver_class()
                self._register_config(self.drivers[driver].get_config())
            except (ValueError, AttributeError):
                # TODO (ryan-lane): set an error condition and exit after all
                #                   config has been parsed
                msg = 'Failed to import driver: {0}'.format(mod)
                LOG.error(msg)
                raise ConfigurationError(msg, 1)

    def _register_config(self, config):
        for key, val in config.items():
            try:
                self.config[key] = self.repo_config.get_value(val[0], val[1])
            except (ConfigParser.NoOptionError, ConfigParser.NoSectionError):
                if val[2]:
                    self.config[key] = val[2]
                else:
                    msg = ('Missing the following configuration item in the'
                           ' git config: {0}.{1}').format(val[0], val[1])
                    LOG.error(msg)
                    raise ConfigurationError(msg, 2)

    def register_cli_options(self, options):
        raise NotImplementedError


CONF = Configuration()
