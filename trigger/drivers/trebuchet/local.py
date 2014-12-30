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
import trigger.drivers as drivers

import redis

from datetime import datetime
from trigger.drivers import SyncDriverError
from trigger.drivers import LockDriverError
from trigger.drivers import ServiceDriverError
from trigger.drivers import ReportDriverError

LOG = config.LOG


class SyncDriver(drivers.SyncDriver):

    def __init__(self, conf):
        self.conf = conf
        self._deploy_dir = os.path.join(self.conf.repo.git_dir,
                                        'deploy')
        self._deploy_file = os.path.join(self._deploy_dir, 'deploy')
        self._report_driver = conf.drivers['report-driver']

    def get_config(self):
        return {
            'deploy.checkout-submodules': {
                'required': False,
                'default': False
            }
        }

    def _write_deploy_file(self, tag):
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        tag_info = {
            'tag': tag.name,
            'sync-time': timestamp,
            'time': timestamp,
            'user': self.conf.config['user.name'],
        }
        try:
            f = open(self._deploy_file, 'w+')
            f.write(json.dumps(tag_info))
            f.close()
        except OSError:
            raise SyncDriverError('Failed to write deploy file', 1)

    def _update_server_info(self, tag):
        # TODO (ryan-lane): Use GitPython for this function if possible
        # TODO (ryan-lane): Check return values from these commands
        p = subprocess.Popen(['git','update-server-info'],
                             cwd=self._deploy_dir,
                             stderr=subprocess.PIPE)
        p.communicate()
        # Also update server info for all submodules
        if self.conf.config['deploy.checkout-submodules']:
            # The same tag used in the parent needs to exist in the submodule
            p = subprocess.Popen(['git','submodule','foreach','--recursive',
                                  'git','tag',tag.name],
                                 cwd=self.conf.repo.working_dir,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
            p.communicate()
            p = subprocess.Popen(['git','submodule','foreach','--recursive',
                                  'trigger-submodule-update'],
                                 cwd=self.conf.repo.working_dir,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
            p.communicate()

    def _fetch(self, args):
        # TODO (ryan-lane): Check return values from these commands
        repo_name = self.conf.config['deploy.repo-name']
        p = subprocess.Popen(['sudo','salt-call','-l','quiet','publish.runner',
                              'deploy.fetch', repo_name],
                             stdout=subprocess.PIPE)
        p.communicate()

    def _checkout(self, args):
        # TODO (ryan-lane): Check return values from these commands
        repo_name = self.conf.config['deploy.repo-name']
        p = subprocess.Popen(['sudo','salt-call','-l','quiet','publish.runner',
                              'deploy.checkout', repo_name+','+str(args.force)],
                             stdout=subprocess.PIPE)
        p.communicate()

    def _ask(self, stage, args, tag):
        self._report_driver.report_sync(tag,
                                        report_type=stage)
        while True:
            answer = raw_input("Continue? ([d]etailed/[C]oncise report,"
                               "[y]es,[n]o,[r]etry): ")
            if not answer or answer == "c" or answer == "C":
                self._report_driver.report_sync(tag,
                                                report_type=stage)
            elif answer == "d" or answer == "D":
                self._report_driver.report_sync(tag,
                                                report_type=stage,
                                                detailed=True)
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
        # TODO (ryan-lane): Break sync up into two stages and move this
        #                   logic out of the driver
        self._write_deploy_file(tag)
        self._update_server_info(tag)
        self._fetch(args)
        # TODO (ryan-lane): Add repo dependencies here
        if not self._ask('fetch', args, tag.name):
            msg = ('Not continuing to checkout phase. A deployment is still'
                   ' underway, please finish, sync, or abort.')
            raise SyncDriverError(msg, 2)
        self._checkout(args)
        if not self._ask('checkout', args, tag.name):
            msg = ('Not continuing to finish phase. A checkout has already'
                   ' occurred. Please finish, sync or revert. Aborting'
                   ' at this phase is not recommended.')
            raise SyncDriverError(msg, 3)

    def get_deploy_info(self):
        try:
            f = open(self._deploy_file, 'r')
            deploy_info = json.loads(f.read())
            f.close()
            return deploy_info
        except OSError:
            raise SyncDriverError('Failed to load deploy file', 3)


class LockDriver(drivers.LockDriver):

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


class ServiceDriver(drivers.ServiceDriver):

    def __init__(self, conf):
        self.conf = conf

    def restart(self, args):
        repo_name = self.conf.config['deploy.repo-name']
        p = subprocess.Popen(['sudo','salt-call','-l','quiet','--out=json',
                              'publish.runner','deploy.restart',
                              repo_name+','+str(args.batch)],
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


class ReportDriver(drivers.ReportDriver):

    def __init__(self, conf):
        self.conf = conf

    def _get_redis_serv(self):
        # TODO (ryan-lane): Load this info from config
        return redis.Redis(host='localhost', port=6379, db=0)

    def _mins_ago(self, now, timestamp):
        if timestamp:
            time = datetime.fromtimestamp(float(timestamp))
            delta = now - time
            mins = delta.seconds / 60
        else:
            mins = None
        return mins

    def _get_minion_data(self, serv, repo, minion):
        # TODO (ryan-lane): use hgetall, this is absurd
        data = {}
        now = datetime.now()
        minion_key = 'deploy:{0}:minions:{1}'.format(repo, minion)
        data['fetch_status'] = serv.hget(minion_key, 'fetch_status')
        fetch_checkin_timestamp = serv.hget(minion_key,
                                            'fetch_checkin_timestamp')
        data['fetch_checkin_mins'] = self._mins_ago(now,
                                                    fetch_checkin_timestamp)
        fetch_timestamp = serv.hget(minion_key, 'fetch_timestamp')
        data['fetch_mins'] = self._mins_ago(now, fetch_timestamp)
        data['checkout_status'] = serv.hget(minion_key, 'checkout_status')
        checkout_checkin_timestamp = serv.hget(minion_key,
                                               'checkout_checkin_timestamp')
        _c_checkin_t = self._mins_ago(now, checkout_checkin_timestamp)
        data['checkout_checkin_mins'] = _c_checkin_t
        checkout_timestamp = serv.hget(minion_key, 'checkout_timestamp')
        data['checkout_mins'] = self._mins_ago(now, checkout_timestamp)
        data['tag'] = serv.hget(minion_key, 'tag')
        data['fetch_tag'] = serv.hget(minion_key, 'fetch_tag')
        restart_checkin_timestamp = serv.hget(minion_key,
                                              'restart_checkin_timestamp')
        _r_c_t = self._mins_ago(now, restart_checkin_timestamp)
        data['restart_checkin_mins'] = _r_c_t
        data['restart_status'] = serv.hget(minion_key, 'restart_status')
        restart_timestamp = serv.hget(minion_key, 'restart_timestamp')
        data['restart_mins'] = self._mins_ago(now, restart_timestamp)
        return data

    def report_sync(self, tag, report_type='full', detailed=False):
        serv = self._get_redis_serv()
        repo_name = self.conf.config['deploy.repo-name']
        LOG.info('Repo: {}'.format(repo_name))
        LOG.info('Tag: {}'.format(tag))
        minions = serv.smembers('deploy:{0}:minions'.format(repo_name))
        _fetch_info = self._get_fetch_info(serv, repo_name, minions, tag)
        _checkout_info = self._get_checkout_info(serv, repo_name, minions, tag)
        min_len = len(minions)
        fetch_len = len(_fetch_info['complete'])
        checkout_len = len(_checkout_info['complete'])
        fetch_report = "{0}/{1} minions completed fetch"
        fetch_report = fetch_report.format(fetch_len, min_len)
        checkout_report = "{0}/{1} minions completed checkout"
        checkout_report = checkout_report.format(checkout_len, min_len)
        if report_type == 'fetch':
            msgs = fetch_report
        elif report_type == 'checkout':
            msgs = checkout_report
        else:
            msgs = '{0}; {1}'.format(fetch_report, checkout_report)
        LOG.info("")
        LOG.info(msgs)
        if detailed:
            LOG.info("")
            LOG.info("Details:")
            LOG.info("")
            msg = ("{0} status: {1} [started: {2} mins ago,"
                   " last-return: {3} mins ago]")
            for minion in minions:
                try:
                    data = _fetch_info['pending'][minion]
                except KeyError:
                    if report_type == 'fetch':
                        continue
                    data = _fetch_info['complete'][minion]
                fetch_msg = msg.format('fetch',
                                       data['fetch_status'],
                                       data['fetch_checkin_mins'],
                                       data['fetch_mins'])
                try:
                    data = _checkout_info['pending'][minion]
                except KeyError:
                    if report_type == 'checkout':
                        continue
                    data = _checkout_info['complete'][minion]
                checkout_msg = msg.format('checkout',
                                          data['checkout_status'],
                                          data['checkout_checkin_mins'],
                                          data['checkout_mins'])
                if report_type == 'fetch':
                    msgs = '\n\t{}'.format(fetch_msg)
                elif report_type == 'checkout':
                    msgs = '\n\t{}'.format(checkout_msg)
                else:
                    msgs = '\n\t{0}\n\t{1}'.format(fetch_msg, checkout_msg)
                msgs = "{0}: {1}".format(minion, msgs)
                LOG.info(msgs)

    def _get_fetch_info(self, serv, repo_name, minions, tag):
        ret = {'complete': {}, 'pending': {}}
        for minion in minions:
            data = self._get_minion_data(serv, repo_name, minion)
            if data['fetch_tag'] == tag:
                ret['complete'][minion] = data
            else:
                ret['pending'][minion] = data
        return ret

    def _get_checkout_info(self, serv, repo_name, minions, tag):
        ret = {'complete': {}, 'pending': {}}
        for minion in minions:
            data = self._get_minion_data(serv, repo_name, minion)
            if data['tag'] == tag:
                ret['complete'][minion] = data
            else:
                ret['pending'][minion] = data
        return ret
