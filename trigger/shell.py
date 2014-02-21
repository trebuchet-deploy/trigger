#!/usr/bin/python
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

"""
Git command-line interface for trebuchet
"""

import os
import imp
import sys
import glob
import argparse

from trigger import utils
from trigger import config
from trigger import extension
from trigger.drivers import LockDriverError
from trigger.drivers import SyncDriverError
from trigger.drivers import ServiceDriverError
from trigger.drivers import ReportDriverError
from trigger.config import ConfigurationError
from datetime import datetime
from git import GitCommandError

LOG = config.LOG


class TriggerError(Exception):

    def __init__(self, message, errorno):
        Exception.__init__(self, message)
        self.errorno = errorno

    def __str__(self):
        return self.message


class Trigger(object):

    def __init__(self, conf):
        self.conf = conf
        self._lock_driver = self.conf.drivers['lock-driver']
        self._sync_driver = self.conf.drivers['sync-driver']
        self._service_driver = self.conf.drivers['service-driver']
        self._report_driver = self.conf.drivers['report-driver']

    def do_start(self, args):
        """
        Start a deployment for this repository and hold the deployment lock.
        """
        lock_info = self._lock_driver.check_lock(args)
        if lock_info:
            if lock_info['user']:
                message = ('A deployment has already been started for this'
                           ' repo by {0}.').format(lock_info['user'])
            else:
                message = ('A deployment has already been started for this'
                           ' repo.')
            raise TriggerError(message, 100)
        try:
            self._lock_driver.add_lock(args)
        except LockDriverError as e:
            LOG.error(e.message)
            raise TriggerError('Failed to start deployment', 101)
        try:
            self._write_tag('start')
            # TODO (ryan-lane): Add logging call here
        except TriggerError as e:
            LOG.error(e.message)
            if self._lock_driver.check_lock(args):
                try:
                    self._lock_driver.remove_lock(args)
                except LockDriverError as e:
                    LOG.error(e.message)
            raise TriggerError('Deployment failed to start', 131)
        LOG.info('Deployment started.')

    @utils.arg('--noreset',
               dest='noreset',
               action='store_true',
               default=False,
               help='Do not reset the working tree to the start tag.')
    @utils.arg('--force',
               dest='force',
               action='store_true',
               default=False,
               help='Abort even if another user started this deployment.')
    def do_abort(self, args):
        """
        Abort this deployment, resetting the local repository back to the
        start tag.
        """
        lock_info = self._lock_driver.check_lock(args)
        if not lock_info:
            message = 'There is no deployment to abort.'
            raise TriggerError(message, 130)
        if lock_info['user'] != self.conf.config['user.name']:
            if not args.force:
                message = ('{0} started this deployment, use --force to'
                           ' abort that deployment.').format(lock_info['user'])
                raise TriggerError(message, 132)
        if not args.noreset:
            try:
                start_tag = self._get_latest_tag('start')
                if start_tag:
                    self.conf.repo.head.reset(commit=start_tag.commit,
                                              index=True,
                                              working_tree=True)
                else:
                    LOG.warning('Could not find a start tag to reset to.')
            except GitCommandError:
                LOG.error('Failed to reset to the start tag.')
                pass
        try:
            self._lock_driver.remove_lock(args)
        except LockDriverError as e:
            raise TriggerError(e.message, 131)
        LOG.info('Deployment aborted.')

    @utils.arg('--force',
               dest='force',
               action='store_true',
               default=False,
               help='Force a sync even if nothing changed locally.')
    def do_sync(self, args):
        """
        Synchronize the current state of the local repository to all
        deployment targets.
        """
        if not self._lock_driver.check_lock(args):
            message = 'A deployment has not been started.'
            raise TriggerError(message, 160)
        if self.conf.repo.is_dirty():
            message = ('The repository is dirty. Please commit or revert any'
                       ' uncommitted changes.')
            raise TriggerError(message, 161)
        tag = self._write_tag('sync')
        try:
            # TODO (ryan-lane): Add logging call here
            self._sync_driver.sync(tag, args)
        except SyncDriverError as e:
            raise TriggerError(e.message, 163)
        try:
            self._lock_driver.remove_lock(args)
        except LockDriverError as e:
            raise TriggerError(e.message, 131)
        # TODO (ryan-lane): display amount of time of deployment
        LOG.info('Deployment finished.')

    def do_finish(self, args):
        """
        Finish the deployment and release the deloyment lock. This is called
        automatically when sync successfully exits.
        """
        if not self._lock_driver.check_lock(args):
            message = 'A deployment has not been started.'
            raise TriggerError(message, 160)
        try:
            self._lock_driver.remove_lock(args)
        except LockDriverError as e:
            raise TriggerError(e.message, 131)
        # TODO (ryan-lane): display amount of time of deployment
        LOG.info('Deployment finished.')

    def _write_tag(self, tag_type):
        #TODO: use a tag driver
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        try:
            repo_name = self.conf.config['deploy.repo-name']
            tag_format = '{0}-{1}-{2}'.format(repo_name,
                                              tag_type,
                                              timestamp)
            return self.conf.repo.create_tag(tag_format)
        except GitCommandError:
            if tag_type == 'start':
                try:
                    self.conf.repo.head.object
                except ValueError:
                    msg = ('There is no initial commit, so no start tag can be'
                           ' written. Please add at least one commit before'
                           ' attempting to start a deployment.')
                    raise TriggerError(msg, 191)
            msg = 'Failed to write the {0} tag.'.format(tag_type)
            raise TriggerError(msg, 190)

    def _get_latest_tag(self, tag_type):
        tag_filter = '-{0}-'.format(tag_type)
        tags = filter(lambda k: tag_filter in k.name, self.conf.repo.tags)
        if len(tags) > 0:
            return tags[-1]
        else:
            return None

    @utils.arg('action',
               metavar='<action>',
               help='Service action to take: stop|start|restart|reload')
    @utils.arg('--batch',
               dest='batch',
               default='10%',
               help='Number or percentage of targets to target for'
                    ' batch processing.')
    def do_service(self, args):
        """
        Manage the service associated with this repository.
        """
        # TODO (ryan-lane): Make this more extendable and have the help
        #                   report implemented functions.
        try:
            getattr(self._service_driver, args.action)(args)
        except (AttributeError, NotImplementedError):
            msg = '{0} is not an action implemented by this service driver.'
            msg = msg.format(args.action)
            raise TriggerError(msg, 200)
        except ServiceDriverError as e:
            raise TriggerError(e.message, 201)

    @utils.arg('action',
               metavar='<action>',
               help='Service action to take: sync|service')
    @utils.arg('--detailed',
               dest='detailed',
               action='store_true',
               default=False,
               help='Show report for all minions rather than a summary')
    def do_report(self, args):
        """
        Report information about this repository's deployments.
        """
        try:
            deploy_info = self._sync_driver.get_deploy_info()
            tag = deploy_info['tag']
        except SyncDriverError as e:
            LOG.error(e.message)
            raise TriggerError('Failed to read deployment file. Has an initial'
                               ' deploment occurred?.', 211)
        except KeyError:
            LOG.error(e.message)
            raise TriggerError('Tag not in deployment file. Has an initial'
                               ' deploment occurred?.', 212)
        try:
            if args.action == 'sync':
                self._report_driver.report_sync(tag, detailed=args.detailed)
        except ReportDriverError as e:
            LOG.error(e.message)
            raise TriggerError('The reporter failed.', 210)

    @utils.arg('command', metavar='<subcommand>', nargs='?',
               help='Display help for <subcommand>.')
    def do_help(self, args):
        """
        Display help about this program or one of its subcommands.
        """
        if args.command:
            if args.command in self.subcommands:
                self.subcommands[args.command].print_help()
            else:
                msg = "'{0}' is not a valid subcommand".format(args.command)
                raise TriggerError(msg, 1)
        else:
            self.parser.print_help()

    def _discover_extensions(self):
        extensions = []
        for name, module in self._discover_via_extension_path():
            ext = extension.Extension(name, module)
            extensions.append(ext)

        return extensions

    def _discover_via_extension_path(self):
        module_path = os.path.dirname(os.path.abspath(__file__))
        ext_path = os.path.join(module_path, 'extensions')
        ext_glob = os.path.join(ext_path, "*.py")

        for ext_path in glob.iglob(ext_glob):
            name = os.path.basename(ext_path)[:-3]

            if name == "__init__":
                continue

            module = imp.load_source(name, ext_path)
            yield name, module

    def _get_base_parser(self):
        epilog = ('See "{0} help COMMAND" '
                  'for help on a specific command.')
        epilog = epilog.format(self.command_name)
        parser = argparse.ArgumentParser(
            prog=self.command_name,
            description=__doc__.strip(),
            epilog=epilog,
            add_help=False
        )

        return parser

    def _get_subcommand_parser(self):
        parser = self._get_base_parser()

        self.subcommands = {}
        subparsers = parser.add_subparsers(metavar='<subcommand>')

        self._find_actions(subparsers, self)

        for ext in self.extensions:
            self._find_actions(subparsers, ext.module)

        return parser

    def _find_actions(self, subparsers, actions_module):
        for attr in (a for a in dir(actions_module) if a.startswith('do_')):
            # I prefer to be hyphen-separated instead of underscores.
            command = attr[3:].replace('_', '-')
            callback = getattr(actions_module, attr)
            desc = callback.__doc__ or ''
            action_help = desc.strip()
            arguments = getattr(callback, 'arguments', [])

            subparser = subparsers.add_parser(command,
                                              help=action_help,
                                              description=desc,
                                              add_help=False)
            subparser.add_argument('-h', '--help',
                                   action='help',
                                   help=argparse.SUPPRESS)
            self.subcommands[command] = subparser
            for (args, kwargs) in arguments:
                subparser.add_argument(*args, **kwargs)
            subparser.set_defaults(func=callback)

    def main(self, name, argv):
        # TODO (ryan-lane): Add novaclient's model for hooks
        name = os.path.basename(name)
        self.command_name = name[4:]
        self.extensions = self._discover_extensions()
        self.parser = self._get_subcommand_parser()
        if len(argv) == 0:
            self.parser.print_help()
            raise SystemExit(2)
        args = self.parser.parse_args(argv)
        if args.func == self.do_help:
            self.do_help(args)
            raise SystemExit(0)
        try:
            self.conf.check_config()
        except ConfigurationError as e:
            LOG.error(e.message)
            raise SystemExit(e.errorno)
        umask = self.conf.config['deploy.required-umask']
        if umask:
            # When the config is set, it'll be in octal, but users may or may
            # not set it as a string. If it isn't a string, GitPython will read
            # it in as an int, so we need to convert that properly to a string,
            # then to int by treating the string as octal.
            if isinstance(umask, str):
                _umask = int(umask, 8)
            else:
                _umask = int(str(umask), 8)
            # os.umask annoyingly is the only way to get the current umask and
            # it sets the umask. Get the umask and return it to the original.
            current_umask = os.umask(_umask)
            os.umask(current_umask)
            if current_umask != _umask:
                msg = ('Required umask is {0:03d}. Please set your umask and'
                       ' try again.')
                LOG.error(msg.format(umask))
                raise SystemExit(220)
        try:
            args.func(args)
        except TriggerError as e:
            LOG.error(e.message)
            raise SystemExit(e.errorno)


def main():
    conf = config.Configuration()
    trigger = Trigger(conf)
    trigger.main(sys.argv[0], sys.argv[1:])

if __name__ == "__main__":
    main()
