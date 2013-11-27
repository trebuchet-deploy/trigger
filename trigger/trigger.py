import sys
import trebuchet.trigger.config
from trebuchet.trigger.drivers import FileManagerError, SyncManagerError
from git.repo import Repo

CONF = trigger.config.CONF
LOG = trigger.config.LOG


class TriggerError(Exception):

    def __init__(self, message, errorno):
        self.message = message
        self.errorno = errorno

    def __str__(self):
        return message


class Trigger(object):

    def __init__(self, args):
        self.args = args
        self.file_driver = CONF.drivers['file_driver']
        self.sync_driver = CONF.drivers['sync_driver']
        self.repo = Repo(".")

    def start(self):
        if self.file_driver.check_lock():
            message = 'A deployment has already been started for this repo.'
            raise TriggerError(message, 100)
        try:
            self.file_driver.add_lock()
        except FileDriverError as e:
            raise TriggerError(e.message, 101)
        try:
            self._write_tag('start')
        except TriggerError as e:
            LOG.error(e.message)
            self.abort()
        LOG.info('Deployment started.')

    def abort(self):
        if not self.file_driver.check_lock():
            message = 'There is no deployment to abort.'
            raise TriggerError(message, 130)
        try:
            self.file_driver.remove_lock()
        except FileDriverError as e:
            raise TriggerError(e.message, 131)
        LOG.info('Deployment aborted.')

    def sync(self):
        if not self.file_driver.check_lock():
            message = 'A deployment has not been started.'
            raise TriggerError(message, 160)
        if self.repo.is_dirty():
            message = ('The repository is dirty. Please commit or revert any'
                       ' uncommitted changes.')
            raise TriggerError(message, 161)
        tag = self._write_tag('sync')
        try:
            self.file_driver.write_deploy_file(tag)
        except FileDriverError as e:
            raise TriggerError(e.message, 162)
        try:
            self.sync_driver.sync(tag)
        except SyncDriverError as e:
            raise TriggerError(e.message, 163)

    def _write_tag(self, tag_type):
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        try:
            self.repo.create_tag('{0}-{1}-{2}'.format(CONF.config['repo_name'],
                                                      tag_type,
                                                      timestamp))
        except GitCommandError:
            message = 'Failed to write the {0} tag.'.format(tag_type)
            raise TriggerError(message, 190)
