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
        self._missing_config = []
        config = {
            'deploy.repo-name': {
                'required': True,
            },
            'deploy.required-umask': {
                'required': False,
                'default': None,
            },
            'user.name': {
                'required': True,
            },
            'user.email': {
                'required': True,
            },
        }
        self._register_config(config)
        self.register_drivers()

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
            'deploy.sync-driver': {
                'required': True,
                'default': 'trebuchet.local.SyncDriver'
            },
            'deploy.lock-driver': {
                'required': True,
                'default': 'trebuchet.local.LockDriver'
            },
            'deploy.service-driver': {
                'required': True,
                'default': 'trebuchet.local.ServiceDriver'
            },
            'deploy.report-driver': {
                'required': True,
                'default': 'trebuchet.local.ReportDriver'
            },
        }
        self._register_config(driver_config)
        for driver in driver_config:
            driver_config = self.config[driver]
            driver_name = driver.split('.')[1]
            LOG.debug('Getting config for driver: {}'.format(driver_name))
            mod, _, cls = driver_config.rpartition('.')
            mod = 'trigger.drivers.' + mod
            try:
                LOG.debug('Importing {}'.format(mod))
                __import__(mod)
                driver_class = getattr(sys.modules[mod], cls)
                self.drivers[driver_name] = driver_class(self)
                self._register_config(self.drivers[driver_name].get_config())
            except (ValueError, AttributeError):
                msg = 'Failed to import driver: {0}'.format(mod)
                raise ConfigurationError(msg, 1)

    def _register_config(self, config):
        for level in self._config_levels:
            repo_config = self._repo_config[level]
            for key, item in config.items():
                try:
                    section, name = key.split('.')
                    if level == 'trigger':
                        self.config[key] = repo_config[key]
                    else:
                        self.config[key] = repo_config.get_value(section,
                                                                 name)
                except (KeyError,
                        ConfigParser.NoOptionError,
                        ConfigParser.NoSectionError):
                    if 'default' in item:
                        self.config[key] = item['default']
        for key, item in config.items():
            if item['required'] and key not in self.config:
                self._missing_config.append(key)

    def check_config(self):
        if self._missing_config:
            for item in self._missing_config:
                msg = ('Missing the following configuration item:'
                       ' {0}').format(item)
                LOG.error(msg)
            raise ConfigurationError('Please add the missing configuration'
                                     ' items via git config or in the'
                                     ' .trigger file', 1)

    def register_cli_options(self, options):
        raise NotImplementedError
