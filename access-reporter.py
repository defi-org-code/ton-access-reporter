#!/usr/bin/python3 -u
from pathlib import Path
import subprocess
import requests
from logging import Formatter, getLogger, StreamHandler
import traceback
from logging.handlers import RotatingFileHandler
import logging
from datetime import datetime
import time
import json
import socket
import sys

import os

sys.path.append('/usr/src/mytonctrl')

from mypylib.mypylib import *
import mytonctrl


local = MyPyClass(__file__)


class MTC(object):

    def __init__(self):
        self.mtc = mytonctrl.MyTonCore()
        self.mtc.ton = mytonctrl.MyTonCore()

    def get_validators_load(self, start, end):

        assert start < end, 'start time should be less than end time'

        cmd = "checkloadall {start} {end}".format(end=end, start=start)
        result = self.mtc.liteClient.Run(cmd, timeout=30)
        lines = result.split('\n')
        data = dict()
        for line in lines:
            if "val" in line and "pubkey" in line:
                buff = line.split(' ')
                vid = buff[1]
                vid = vid.replace('#', '')
                vid = vid.replace(':', '')
                vid = int(vid)
                pubkey = buff[3]
                pubkey = pubkey.replace(',', '')
                blocksCreated_buff = buff[6]
                blocksCreated_buff = blocksCreated_buff.replace('(', '')
                blocksCreated_buff = blocksCreated_buff.replace(')', '')
                blocksCreated_buff = blocksCreated_buff.split(',')
                masterBlocksCreated = float(blocksCreated_buff[0])
                workBlocksCreated = float(blocksCreated_buff[1])
                blocksExpected_buff = buff[8]
                blocksExpected_buff = blocksExpected_buff.replace('(', '')
                blocksExpected_buff = blocksExpected_buff.replace(')', '')
                blocksExpected_buff = blocksExpected_buff.split(',')
                masterBlocksExpected = float(blocksExpected_buff[0])
                workBlocksExpected = float(blocksExpected_buff[1])

                masterProb = float(buff[10])
                workchainProb = float(buff[12])

                if masterBlocksExpected == 0:
                    mr = 0
                else:
                    mr = masterBlocksCreated / masterBlocksExpected
                if workBlocksExpected == 0:
                    wr = 0
                else:
                    wr = workBlocksCreated / workBlocksExpected
                r = (mr + wr) / 2
                efficiency = round(r * 100, 2)
                if efficiency > 10:
                    online = True
                else:
                    online = False
                item = dict()
                item["id"] = vid
                item["pubkey"] = pubkey
                item["masterBlocksCreated"] = masterBlocksCreated
                item["workBlocksCreated"] = workBlocksCreated
                item["masterBlocksExpected"] = masterBlocksExpected
                item["workBlocksExpected"] = workBlocksExpected
                item["mr"] = mr
                item["wr"] = wr
                item["efficiency"] = efficiency
                item["online"] = online
                item["masterProb"] = masterProb
                item["workchainProb"] = workchainProb

                # Get complaint file
                index = lines.index(line)
                nextIndex = index + 2
                if nextIndex < len(lines):
                    nextLine = lines[nextIndex]
                    if "COMPLAINT_SAVED" in nextLine:
                        buff = nextLine.split('\t')
                        item["var1"] = buff[1]
                        item["var2"] = buff[2]
                        item["fileName"] = buff[3]
                data[vid] = item

        return data


class Reporter(MTC):
    HOME = Path.home()

    MYTONCORE_FILE_PATH = f'{HOME}/.local/share/mytoncore/mytoncore.db'
    REPORTER_DIR = f'/var/access-reporter'
    METRICS_FILE = f'{REPORTER_DIR}/metrics.json'
    EMERGENCY_FLAGS_FILE = f'{REPORTER_DIR}/emergency_flags.json'
    DB_FILE = f'{REPORTER_DIR}/db.json'
    LOG_FILENAME = f'/var/log/access-reporter/access-reporter.log'

    SECONDS_IN_YEAR = 365 * 24 * 3600
    SLEEP_INTERVAL = 1 * 60

    MIN_PROB_NULL = 100

    def __init__(self):
        super(Reporter, self).__init__()

        self.log = self.init_logger()
        self.log.info(
            f'validator reporter init started at {datetime.utcnow()}')

        self.metrics = self.load_json_from_file(self.METRICS_FILE)
        self.reporter_db = self.load_json_from_file(self.DB_FILE)

        self.prev_offers = []
        self.start_run_time = 0

    def init_logger(self):

        formatter = Formatter(
            fmt='[%(asctime)s] %(filename)s:%(lineno)s - %(message)s', datefmt='%Y-%m-%d,%H:%M:%S')
        stream_handler = StreamHandler()
        stream_handler.setFormatter(formatter)

        file_handler = RotatingFileHandler(
            self.LOG_FILENAME, maxBytes=3 * 1024 * 1024, backupCount=5, mode='a')
        file_handler.setFormatter(formatter)

        logger = getLogger('reporter')
        logger.addHandler(stream_handler)
        logger.addHandler(file_handler)
        logger.setLevel(logging.DEBUG)

        return logger

    def load_json_from_file(self, file_name):

        if os.path.isfile(file_name):
            with open(file_name, 'r') as f:
                return json.load(f)

        return {}

    def save_json_to_file(self, json_dict, file_name):

        with open(file_name, 'w') as f:
            json.dump(json_dict, f)
            self.log.info(f'{file_name} was updated')

    def write_metrics_to_file(self, key, value):
        self.metrics[key] = value
        self.log.info(
            f'writing {key} with value {value} to metrics file at {self.METRICS_FILE}')

        with open(self.METRICS_FILE, 'w') as f:
            json.dump(self.metrics, f)
            self.log.info(f'{self.METRICS_FILE} was updated')

    def get_stats(self):
        return self.mtc.GetValidatorStatus()

    def get_mytoncore_db(self):

        with open(self.MYTONCORE_FILE_PATH, 'r') as f:
            return json.load(f)

    def get_num_validators(self, config34):
        return config34['totalValidators']

    def get_total_network_stake(self, config34):
        return config34['totalWeight']

    def get_global_version(self):

        config8 = self.mtc.GetConfig(8)
        try:
            version = config8['_']['version']
            capabilities = config8['_']['capabilities']
            return version, capabilities

        except Exception as e:
            self.log.error(
                'could not extract version and capabilities from config8={}, e={}'.format(config8, e))
            return -1, -1

    def get_pid(self):
        return os.getpid()

    def report(self):
        with open(self.METRICS_FILE, 'w') as f:
            json.dump(self.metrics, f)
            self.log.info(f'{self.METRICS_FILE} was updated')
            self.sendToElastic()
            self.log.info(f'{self.METRICS_FILE} posted to elastic')

    def sendToElastic(self):
        self.log.info("Sending elastic")
        url = 'http://3.141.233.132:3001/putes/access-node-reporter'
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, headers=headers,
                                 data=json.dumps(self.metrics))
        self.log.info(response)

    def getTonVersion(self):
        directory = "/usr/src/ton"
        command = ["git", "rev-parse", "HEAD"]
        result = subprocess.run(command, cwd=directory, stdout=subprocess.PIPE)
        commit_hash = result.stdout.decode().strip()
        branch = self.get_git_branch(directory)
        return commit_hash+"-"+branch

    def getMytonctrlVersion(self):
        directory = "/usr/src/mytonctrl"
        command = ["git", "rev-parse", "HEAD"]
        result = subprocess.run(command, cwd=directory, stdout=subprocess.PIPE)
        commit_hash = result.stdout.decode().strip()
        branch = self.get_git_branch(directory)
        return commit_hash+"-"+branch

    def get_git_branch(self, path):
        if path is None:
            path = os.path.curdir
        command = 'git rev-parse --abbrev-ref HEAD'.split()
        branch = subprocess.Popen(
            command, stdout=subprocess.PIPE, cwd=path).stdout.read()
        return branch.strip().decode('utf-8')

    def run(self):
        retry = 0

        while True:

            self.start_run_time = time.time()
            success = True

            try:
                self.log.info(
                    f'validator reporter started at {datetime.utcnow()} (retry {retry})')
                mytoncore_db = self.get_mytoncore_db()

                adnl_addr = self.mtc.GetAdnlAddr()
                stats = self.get_stats()
                config34 = self.mtc.GetConfig34()

                total_stake = self.get_total_network_stake(config34)
                num_validators = self.get_num_validators(config34)
                pid = self.get_pid()
                version, capabilities = self.get_global_version()

                ###############################################################
                # metrics
                # general validator metrics
                ###############################################################

                self.metrics['adnl_addr'] = adnl_addr
                self.metrics['out_of_sync'] = stats['outOfSync']
                self.metrics['is_working'] = int(stats['isWorking'])
                self.metrics['total_network_stake'] = total_stake
                self.metrics['version'], self.metrics['capabilities'] = version, capabilities
                self.metrics['num_validators'] = num_validators
                self.metrics['reporter_pid'] = pid
                self.metrics['update_time'] = self.start_run_time
                self.metrics['hostname'] = socket.gethostname()
                self.metrics['mytonctrl_version'] = self.getMytonctrlVersion()
                self.metrics['ton_version'] = self.getTonVersion()

                emergency_flags = {'recovery_flags': dict(), 'exit_flags': dict(
                ), 'git statusvery_flags': dict(), 'warning_flags': dict()}

                ###############################################################
                # recovery flags
                # when set should trigger manual/automatic operation by the devops group operating the validator
                # the operation might include for example restarting a process or checking that network connectivity is ok
                # however it will not trigger exit from the next validating cycle
                ###############################################################

                # validator is not out of sunc (validator epoch relative to the network)
                emergency_flags['recovery_flags']['out_of_sync_err'] = int(
                    self.metrics['out_of_sync'] > 120)
                # validator RAM should be < 85%
                # emergency_flags['recovery_flags']['mem_load_avg_err'] = int(
                #     self.metrics['mem_load_avg'] > 85)
                # # validator disk should be < 85%
                # emergency_flags['recovery_flags']['disk_load_pct_avg_err'] = int(
                #     self.metrics['mem_load_avg'] > 85)
                # # # validator network load average should be < 400 MB/sec
                # emergency_flags['recovery_flags']['net_load_avg_err'] = int(
                #     self.metrics['mem_load_avg'] > 400)

                self.report()

                # emergency flags
                emergency_flags['exit'] = int(len(emergency_flags['exit_flags'].keys()) != 0)
                emergency_flags['recovery'] = int(len(emergency_flags['recovery_flags'].keys()) != 0)
                emergency_flags['warning'] = int(len(emergency_flags['warning_flags'].keys()) != 0)
                emergency_flags['message'] = f"exit_flags: {list(emergency_flags['exit_flags'].keys())}, recovery_flags: {list(emergency_flags['recovery_flags'].keys())}, " \
                                             f"warning_flags: {list(emergency_flags['warning_flags'].keys())}"

                self.save_json_to_file(emergency_flags, self.EMERGENCY_FLAGS_FILE)


                self.log.info(self.metrics)

            except Exception as e:
                retry += 1
                success = False
                self.log.info(self.metrics)
                self.log.info(f'unexpected error: {e}')
                self.log.info(traceback.format_exc())
                time.sleep(1)

            if success or retry >= 5:
                retry = 0
                sleep_sec = self.SLEEP_INTERVAL - time.time() % self.SLEEP_INTERVAL
                self.log.info(
                    f'executed in {round(time.time() - self.start_run_time, 2)} seconds')
                self.log.info(f'sleep for {round(sleep_sec)} seconds')
                time.sleep(sleep_sec)


if __name__ == '__main__':
    reporter = Reporter()
    reporter.run()
