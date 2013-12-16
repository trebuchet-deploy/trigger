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

CONF = config.CONF
LOG = config.LOG


class SyncDriver(driver.SyncDriver):

    def __init__(self):
        self._deploy_dir = os.path.join(CONF.repo.working_dir, '.git/deploy')

    def _write_deploy_file(self, tag):
        deploy_file = os.path.join(self._deploy_dir, 'deploy')
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        tag_info = {
            'tag': tag.name,
            'sync-time': timestamp,
            'user': CONF.config['user.name'],
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
        if checkout_submodules:
            # The same tag used in the parent needs to exist in the submodule
            cmd = 'git submodule foreach --recursive "git tag {0}"'
            cmd = cmd.format(tag.name)
            p = subprocess.Popen(cmd, cwd=CONF.repo.working_dir, shell=True,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
            p.communicate()
            # TODO (ryan-lane): Find a way to do this without a separate
            #                   bash script.
            p = subprocess.Popen('git submodule foreach --recursive '
                                 '"submodule-update-server-info"',
                                 cwd=CONF.repo.working_dir, shell=True,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
            p.communicate()

    def _fetch(self, args):
        # TODO (ryan-lane): Check return values from these commands
        repo_name = CONF.config['repo-name']
        cmd = "sudo salt-call -l quiet publish.runner deploy.fetch '{0}'"
        cmd = cmd.format(repo_name)
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        p.communicate()

    def _checkout(self, args):
        # TODO (ryan-lane): Check return values from these commands
        repo_name = CONF.config['repo-name']
        cmd = ("sudo salt-call -l quiet publish.runner"
              " deploy.checkout '{0},{1}'")
        cmd = cmd.format(repo_name, args.force)
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        p.communicate()

    def _ask(self, stage, args):
        # TODO (ryan-lane): Use deploy-info as a library, rather
        #                   than shelling out
        repo_name = CONF.config['repo-name']
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
            raise SyncDriverError('Error during fetch phase', 2)
        self._checkout(args)
        if not self._ask('checkout', args):
            raise SyncDriverError('Error during checkout phase', 3)


class LockDriver(driver.LockDriver):

    def __init__(self):
        self._deploy_dir = os.path.join(CONF.repo.working_dir, '.git/deploy')
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
        try:
            open(self._lock_file, 'a').close()
        except IOError:
            raise LockDriverError('Failed to create lock file', 2)

    def remove_lock(self, args):
        try:
            os.remove(self._lock_file)
        except OSError:
            raise LockDriverError('Failed to remove lock file', 3)

    def check_lock(self, args):
        return os.path.isfile(self._lock_file)


class ServiceDriver(driver.ServiceDriver):

    def stop(self, args):
        raise NotImplementedError

    def start(self, args):
        raise NotImplementedError

    def restart(self, args):
        raise NotImplementedError

    def reload(self, args):
        raise NotImplementedError
