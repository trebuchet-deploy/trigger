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
from trigger.driver import LockDriverError
from trigger.driver import SyncDriverError
from trigger.driver import ServiceDriverError
from datetime import datetime
from git import GitCommandError
from git.repo import Repo

CONF = config.CONF
CONF.register_drivers()
LOG = config.LOG


class TriggerError(Exception):

    def __init__(self, message, errorno):
        Exception.__init__(self, message)
        self.errorno = errorno

    def __str__(self):
        return self.message


class Trigger(object):

    def __init__(self):
        self._lock_driver = CONF.drivers['lock-driver']
        self._sync_driver = CONF.drivers['sync-driver']
        self._service_driver = CONF.drivers['service-driver']

    def do_start(self, args):
        if self._lock_driver.check_lock(args):
            message = 'A deployment has already been started for this repo.'
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
    def do_abort(self, args):
        if not self._lock_driver.check_lock(args):
            message = 'There is no deployment to abort.'
            raise TriggerError(message, 130)
        if not args.noreset:
            try:
                start_tag = self._get_latest_tag('start')
                if start_tag:
                    CONF.repo.head.reset(commit=start_tag.commit, index=True,
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

    def do_sync(self, args):
        if not self._lock_driver.check_lock(args):
            message = 'A deployment has not been started.'
            raise TriggerError(message, 160)
        if CONF.repo.is_dirty():
            message = ('The repository is dirty. Please commit or revert any'
                       ' uncommitted changes.')
            raise TriggerError(message, 161)
        tag = self._write_tag('sync')
        try:
            # TODO (ryan-lane): Add logging call here
            self._sync_driver.sync(tag, args)
        except SyncDriverError as e:
            raise TriggerError(e.message, 163)

    def _write_tag(self, tag_type):
        #TODO: use a tag driver
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        try:
            tag_format = '{0}-{1}-{2}'.format(CONF.config['repo-name'],
                                              tag_type,
                                              timestamp)
            return CONF.repo.create_tag(tag_format)
        except GitCommandError:
            message = 'Failed to write the {0} tag.'.format(tag_type)
            raise TriggerError(message, 190)

    def _get_latest_tag(self, tag_type):
        tag_filter = '-{0}-'.format(tag_type)
        tags = filter(lambda k: tag_filter in k.name, CONF.repo.tags)
        if len(tags) > 0:
            return tags[-1]
        else:
            return None

    @utils.arg('action',
               metavar='<action>',
               help='Service action to take: stop|start|restart|reload')
    @utils.arg('--batch',
               dest='batch',
               help='Number or percentage of targets to target for'
                    ' batch processing.')
    def do_service(self, args):
        """
        Manage the service associated with this repository.
        """
        try:
            getattr(self.service_driver, args.action)(args)
        except AttributeError, NotImplementedError:
            msg = '{0} is not an action implemented by this service driver.'
            msg = msg.format(args.action)
            raise TriggerError(msg, 200)

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
                raise exc.CommandError("'%s' is not a valid subcommand" %
                                       args.command)
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
        parser = argparse.ArgumentParser(
            prog="trigger",
            description=__doc__.strip(),
            epilog='See "trigger help COMMAND" '
                   'for help on a specific command.',
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
                add_help=False
            )
            subparser.add_argument('-h', '--help',
                action='help',
                help=argparse.SUPPRESS,
            )
            self.subcommands[command] = subparser
            for (args, kwargs) in arguments:
                subparser.add_argument(*args, **kwargs)
            subparser.set_defaults(func=callback)

    def main(self, argv):
        # TODO (ryan-lane): Add novaclient's model for hooks
        self.extensions = self._discover_extensions()
        self.parser = self._get_subcommand_parser()
        args = self.parser.parse_args(argv)

        if args.func == self.do_help:
            self.do_help(args)
            return 0

        try:
            args.func(args)
        except TriggerError as e:
            LOG.error(e.message)
            raise SystemExit(e.errorno)


def main():
    trigger = Trigger()
    trigger.main(sys.argv[1:])

if __name__ == "__main__":
    main()
