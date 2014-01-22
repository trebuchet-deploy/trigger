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
import json
import subprocess
import trigger.config as config
import trigger.driver as driver

from datetime import datetime
from driver import SyncDriverError
from driver import LockDriverError
from driver import ServiceDriverError

LOG = config.LOG


class SyncDriver(driver.SyncDriver):

    def __init__(self, conf):
        self.conf = conf
        self._deploy_dir = os.path.join(self.conf.repo.git_dir,
                                        'deploy')

    def get_config(self):
        return {
            'checkout-submodules': ('deploy', 'checkout-submodules', False)
        }

    def _write_deploy_file(self, tag):
        deploy_file = os.path.join(self._deploy_dir, 'deploy')
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        tag_info = {
            'tag': tag.name,
            'sync-time': timestamp,
            'time': timestamp,
            'user': self.conf.config['user.name'],
        }
        try:
            f = open(deploy_file, 'w+')
            f.write(json.dumps(tag_info))
            f.close()
        except OSError:
            raise SyncDriverError('Failed to write deploy file', 1)

    def _update_server_info(self, tag):
        # TODO (ryan-lane): Use GitPython for this function if possible
        # TODO (ryan-lane): Check return values from these commands
        p = subprocess.Popen('git update-server-info',
                             cwd=self._deploy_dir, shell=True,
                             stderr=subprocess.PIPE)
        p.communicate()
        # Also update server info for all submodules
        if self.conf.config['checkout-submodules']:
            # The same tag used in the parent needs to exist in the submodule
            cmd = 'git submodule foreach --recursive "git tag {0}"'
            cmd = cmd.format(tag.name)
            p = subprocess.Popen(cmd, cwd=self.conf.repo.working_dir,
                                 shell=True, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
            p.communicate()
            # TODO (ryan-lane): Find a way to do this without a separate
            #                   bash script.
            p = subprocess.Popen('git submodule foreach --recursive '
                                 '"submodule-update-server-info"',
                                 cwd=self.conf.repo.working_dir, shell=True,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
            p.communicate()

    def _fetch(self, args):
        # TODO (ryan-lane): Check return values from these commands
        repo_name = self.conf.config['repo-name']
        cmd = "sudo salt-call -l quiet publish.runner deploy.fetch '{0}'"
        cmd = cmd.format(repo_name)
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        p.communicate()

    def _checkout(self, args):
        # TODO (ryan-lane): Check return values from these commands
        repo_name = self.conf.config['repo-name']
        cmd = ("sudo salt-call -l quiet publish.runner"
               " deploy.checkout '{0},{1}'")
        cmd = cmd.format(repo_name, args.force)
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        p.communicate()

    def _ask(self, stage, args):
        # TODO (ryan-lane): Use deploy-info as a library, rather
        #                   than shelling out
        repo_name = self.conf.config['repo-name']
        if stage == "fetch":
            check = "deploy-info --repo=%s --fetch"
        elif stage == "checkout":
            check = "deploy-info --repo=%s"
        p = subprocess.Popen(check % (repo_name), shell=True,
                             stdout=subprocess.PIPE)
        out = p.communicate()[0]
        LOG.info(out)
        while True:
            answer = raw_input("Continue? ([d]etailed/[C]oncise report,"
                               "[y]es,[n]o,[r]etry): ")
            if not answer or answer == "c" or answer == "C":
                p = subprocess.Popen(check % (repo_name), shell=True,
                                     stdout=subprocess.PIPE)
                out = p.communicate()[0]
                LOG.info(out)
            elif answer == "d" or answer == "D":
                p = subprocess.Popen(check % (repo_name) + " --detailed",
                                     shell=True, stdout=subprocess.PIPE)
                out = p.communicate()[0]
                LOG.info(out)
            elif answer == "Y" or answer == "y":
                return True
            elif answer == "N" or answer == "n":
                return False
            elif answer == "R" or answer == "r":
                if stage == "fetch":
                    self._fetch(args)
                if stage == "checkout":
                    self._checkout(args)

    def sync(self, tag, args):
        self._write_deploy_file(tag)
        self._update_server_info(tag)
        self._fetch(args)
        # TODO (ryan-lane): Add repo dependencies here
        if not self._ask('fetch', args):
            msg = ('Not continuing to checkout phase. A deployment is still'
                   ' underway, please finish, sync, or abort.')
            raise SyncDriverError(msg, 2)
        self._checkout(args)
        if not self._ask('checkout', args):
            msg = ('Not continuing to finish phase. A checkout has already'
                   ' occurred. Please finish, sync or revert. Aborting'
                   ' at this phase is not recommended.')
            raise SyncDriverError(msg, 3)


class LockDriver(driver.LockDriver):

    def __init__(self, conf):
        self.conf = conf
        self._deploy_dir = os.path.join(self.conf.repo.git_dir,
                                        'deploy')
        self._lock_file = os.path.join(self._deploy_dir, 'lock')
        self._create_deploy_dir()

    def _create_deploy_dir(self):
        if os.path.isdir(self._deploy_dir):
            return
        try:
            os.mkdir(self._deploy_dir)
        except OSError:
            raise LockDriverError('Failed to create deploy directory', 1)

    def add_lock(self, args):
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        lock_info = {
            'time': timestamp,
            'user': self.conf.config['user.name'],
        }
        try:
            f = open(self._lock_file, 'w+')
            f.write(json.dumps(lock_info))
            f.close()
        except (OSError, IOError):
            raise LockDriverError('Failed to write lock file', 1)

    def remove_lock(self, args):
        try:
            os.remove(self._lock_file)
        except OSError:
            raise LockDriverError('Failed to remove lock file', 3)

    def check_lock(self, args):
        try:
            f = open(self._lock_file, 'r')
            lock_info = f.read()
            lock_info = json.loads(lock_info)
            f.close()
            return lock_info
        except (OSError, IOError):
            return {}
        except (KeyError, ValueError):
            return {'user': None, 'time': None}


class ServiceDriver(driver.ServiceDriver):

    def __init__(self, conf):
        self.conf = conf

    def restart(self, args):
        repo = self.conf.config['repo-name']
        cmd = ("sudo salt-call -l quiet --out=json publish.runner "
               "deploy.restart '{0}','{1}'")
        p = subprocess.Popen(cmd.format(repo, args.batch),
                             shell=True,
                             stdout=subprocess.PIPE)
        out = p.communicate()[0]
        ## Disabled until salt bug is fixed:
        ##   https://github.com/saltstack/salt/issues/9146
        #LOG.info('Service restart sent to salt. Check the status using:'
        #         ' deploy-info --repo={0} --restart'.format(repo))
        ## Display the data directly from the runner return until bug is fixed.
        try:
            minion_data = json.loads(out)
        except (ValueError, AttributeError):
            msg = 'Could not parse salt return; raw output:\n\n{0}'
            raise ServiceDriverError(msg.format(out), 1)
        minion_data = minion_data['local']
        if isinstance(minion_data, basestring):
            msg = 'Error received from salt; raw output:\n\n{0}'
            raise ServiceDriverError(msg.format(minion_data), 2)
        for i in minion_data:
            try:
                for minion, data in i.items():
                    try:
                        LOG.info('{0}: {1}'.format(minion, data['status']))
                    except KeyError:
                        LOG.info('{0}: No status available'.format(minion))
            except AttributeError:
                LOG.error('Got bad return from salt. Here is the raw data:')
                LOG.error('{}'.format(i))
