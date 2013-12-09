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
        self._args = args
        self._file_driver = CONF.drivers['file_driver']
        self._sync_driver = CONF.drivers['sync_driver']
        self._repo = Repo(".")

    def start(self):
        if self._file_driver.check_lock():
            message = 'A deployment has already been started for this repo.'
            raise TriggerError(message, 100)
        try:
            self._file_driver.add_lock()
        except FileDriverError as e:
            raise TriggerError(e.message, 101)
        try:
            self._write_tag('start')
        except TriggerError as e:
            LOG.error(e.message)
            self.abort(reset=False)
        LOG.info('Deployment started.')

    def abort(self, reset=True):
        if not self._file_driver.check_lock():
            message = 'There is no deployment to abort.'
            raise TriggerError(message, 130)
        if reset:
            try:
                start_tag = self._get_latest_tag('start')
                self._repo.reset(commit=start_tag.commit, index=True,
                                 working_tree=True)
            except GitCommandError:
                LOG.error('Failed to reset to the start tag.')
                pass
        try:
            self._file_driver.remove_lock()
        except FileDriverError as e:
            raise TriggerError(e.message, 131)
        LOG.info('Deployment aborted.')

    def sync(self):
        if not self._file_driver.check_lock():
            message = 'A deployment has not been started.'
            raise TriggerError(message, 160)
        if self._repo.is_dirty():
            message = ('The repository is dirty. Please commit or revert any'
                       ' uncommitted changes.')
            raise TriggerError(message, 161)
        tag = self._write_tag('sync')
        try:
            self._file_driver.write_deploy_file(tag)
        except FileDriverError as e:
            raise TriggerError(e.message, 162)
        try:
            self._sync_driver.sync(tag)
        except SyncDriverError as e:
            raise TriggerError(e.message, 163)

    def _write_tag(self, tag_type):
        #TODO: use a tag driver
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        try:
            tag_format = '{0}-{1}-{2}'.format(CONF.config['repo_name'],
                                              tag_type,
                                              timestamp)
            return self._repo.create_tag(tag_format)
        except GitCommandError:
            message = 'Failed to write the {0} tag.'.format(tag_type)
            raise TriggerError(message, 190)

    def _get_latest_tag(tag_type):
        tag_filter = '-{0}-'.format(tag_type)
        tags = filter(lambda k: tag_filter in k.name, self._repo.tags)
        return tags[-1]
