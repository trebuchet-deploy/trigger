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

import os
import sys
import yaml
import logging
import ConfigParser

from git import InvalidGitRepositoryError
from git.repo import Repo

try:
    NullHandler = logging.NullHandler
except AttributeError:
    class NullHandler(logging.Handler):
        def emit(self, record):
            pass

logging.basicConfig(format='%(message)s', level=logging.INFO)
LOG = logging.getLogger(__name__)


class ConfigurationError(Exception):

    def __init__(self, message, errorno):
        self.message = message
        self.errorno = errorno

    def __str__(self):
        return self.message


class Configuration(object):

    config = {}
    drivers = {}
    _config_levels = ['system', 'global', 'trigger', 'repository']

    def __init__(self):
        try:
            self.repo = Repo('.')
        except InvalidGitRepositoryError:
            msg = 'Not in a git repository'
            raise ConfigurationError(msg, 1)
        self._load_config()
        self._missing_config = {}
        config = {
            'repo-name': ('deploy', 'repo-name', None),
            'user.name': ('user', 'name', None),
            'user.email': ('user', 'email', None),
        }
        self._register_config(config)
        self.register_drivers()
        self._check_config()

    def _load_config(self):
        self._repo_config = {}
        self._repo_config['system'] = self.repo.config_reader('system')
        self._repo_config['global'] = self.repo.config_reader('global')
        try:
            f = open(os.path.join(self.repo.working_dir, '.trigger'), 'r')
            trigger_config = f.read()
            f.close()
            self._repo_config['trigger'] = yaml.safe_load(trigger_config)
        except (IOError, OSError):
            self._repo_config['trigger'] = {}
        except (ValueError, KeyError):
            LOG.warning('Found a .trigger config file, but could not parse'
                        ' it. Unable to load repo specific config.')
        self._repo_config['repository'] = self.repo.config_reader('repository')

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
                self.drivers[driver] = driver_class(self)
                self._register_config(self.drivers[driver].get_config())
            except (ValueError, AttributeError):
                msg = 'Failed to import driver: {0}'.format(mod)
                raise ConfigurationError(msg, 1)

    def _register_config(self, config):
        for level in self._config_levels:
            repo_config = self._repo_config[level]
            for key, val in config.items():
                try:
                    if level == 'trigger':
                        _key = '{0}.{1}'.format(val[0], val[1])
                        self.config[key] = repo_config[_key]
                    else:
                        self.config[key] = repo_config.get_value(val[0],
                                                                 val[1])
                except (KeyError,
                        ConfigParser.NoOptionError,
                        ConfigParser.NoSectionError):
                    if val[2] is not None:
                        self.config[key] = val[2]
        for key, val in config.items():
            if key not in self.config:
                self._missing_config[key] = val

    def _check_config(self):
        if self._missing_config:
            for key, val in self._missing_config.items():
                msg = ('Missing the following configuration item:'
                       ' {0}.{1}').format(val[0], val[1])
                LOG.error(msg)
            raise ConfigurationError('Please add the missing configuration'
                                     ' items via git config or in the'
                                     ' .trigger file', 1)

    def register_cli_options(self, options):
        raise NotImplementedError
