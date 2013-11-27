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
            'repo_name': ('deploy', 'repo_name', None),
            'user.name': ('user', 'name', None),
            'user.email': ('user', 'email', None),
        }
        self._register_config(config)

    def _register_drivers(self):
        driver_config = {
            'sync_driver': ('deploy', 'sync_driver',
                            'trebuchet.local.SyncManager'),
            'file_driver': ('deploy', 'file_driver',
                            'trebuchet.local.FileManager'),
        }
        self._register_config(driver_config)
        for driver in driver_config:
            driver = self.config[driver]
            mod, _, cls = driver.rpartition('.')
            mod = 'driver.' + mod
            try:
                __import__(mod)
                driver_class = getattr(sys.modules[mod], cls)
                self.drivers[key] = driver_class()
                self._register_config(self.drivers[key].get_config())
            except (ValueError, AttributeError):
                # TODO: set an error condition and exit after all
                # config has been parsed
                LOG.error('Failed to import driver: {0}'.format(mod))
                sys.exit(2)

    def _register_config(self, config):
        for key, val in config.items():
            try:
                self.config[key] = self.repo_config.get_value(val[0], val[1])
            except ConfigParser.NoOptionError:
                if val[2]:
                    self.config[key] = val[2]
                else:
                    msg = ('Missing the following configuration item in the'
                           ' git config: {0}.{1}').format(val[1], val[2])
                    LOG.error(msg)
                    sys.exit(2)

    def register_cli_options(self, options):
        raise NotImplementedError


CONF = Configuration()
