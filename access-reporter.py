#!/usr/bin/python3 -u
from mytoncore import GetMemoryInfo
from mypylib.mypylib import *
import mytonctrl
import os
from pathlib import Path
import sys
import socket
import json
import time
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import traceback
from logging import Formatter, getLogger, StreamHandler
import copy
import math
import requests
import subprocess

sys.path.append('/usr/src/mytonctrl')


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
    VALIDATOR_WALLET_NAME = 'validator_wallet_001'
    WALLET_PATH = f'{HOME}/.local/share/mytoncore/wallets/'
    WALLET_PK_PATH = f'{WALLET_PATH}/{VALIDATOR_WALLET_NAME}.pk'
    WALLET_ADDR_PATH = f'{WALLET_PATH}/{VALIDATOR_WALLET_NAME}.addr'
    MYTONCORE_FILE_PATH = f'{HOME}/.local/share/mytoncore/mytoncore.db'
    REPORTER_DIR = f'/var/reporter'
    METRICS_FILE = f'{REPORTER_DIR}/metrics.json'
    CONST_FILE = f'{REPORTER_DIR}/constants.json'
    EMERGENCY_FLAGS_FILE = f'{REPORTER_DIR}/emergency_flags.json'
    DB_FILE = f'{REPORTER_DIR}/db.json'
    LOG_FILENAME = f'/var/log/reporter/reporter.log'

    SECONDS_IN_YEAR = 365 * 24 * 3600
    SLEEP_INTERVAL = 1 * 60

    MIN_PROB_NULL = 100

    def __init__(self):
        super(Reporter, self).__init__()

        self.log = self.init_logger()
        self.log.info(
            f'validator reporter init started at {datetime.utcnow()}')

        self.metrics = self.load_json_from_file(self.METRICS_FILE)
        self.const = self.load_json_from_file(self.CONST_FILE)
        self.reporter_db = self.load_json_from_file(self.DB_FILE)

        self.prev_offers = []

        self.apy = -1
        self.balance_at_elector = self.reporter_db.get('balance_at_elector', 0)
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

    def update_start_work_time(self, participate_in_next_validation, start_work_time):

        if 'start_work_time' not in self.reporter_db.keys() and participate_in_next_validation:
            self.reporter_db['start_work_time'] = start_work_time
            self.save_json_to_file(self.reporter_db, self.DB_FILE)

    def systemctl_status_validator(self):
        return os.system('systemctl status validator')

    def systemctl_status_validator_ok(self):
        return int(self.systemctl_status_validator() == 0)

    def validator_wallet_exists(self):
        return int(os.path.exists(self.WALLET_PK_PATH) and os.path.exists(self.WALLET_ADDR_PATH))

    def validator_addr_changed(self, wallet_addr):
        return int(wallet_addr != self.const['validator_wallet_addr'])

    def validator_index(self):
        return self.mtc.GetValidatorIndex()

    def validator_name_ok(self, wallet_id):
        return int(socket.gethostname() == f'validator-{wallet_id}')

    def get_sub_wallet_id(self, wallet):
        res = self.mtc.liteClient.Run(f'runmethod {wallet.addrB64} wallet_id')
        res = self.mtc.GetVarFromWorkerOutput(res, "result")
        self.log.info('res: ', res)

        if not res:
            return -1

        try:
            return int((res.replace('[', '').replace(']', '').split())[0])
        except Exception as e:
            self.log.info(f'error: unable to extract wallet_id: {e}')
            return -1

    def single_nominator(self):
        pools = self.mtc.GetPools()
        assert len(
            pools) == 1, f'expected exactly 1 single nominator but detected {len(pools)} pools'
        account = self.mtc.GetAccount(pools[0].addrB64)
        setattr(pools[0], 'account', account)
        return pools[0]

    def validator_wallet(self):
        return self.mtc.GetValidatorWallet()

    def validator_account(self, validator_wallet):
        return self.mtc.GetAccount(validator_wallet.addrB64)

    def free_nominator_balance(self, nominator_account):
        return nominator_account.account.balance

    def free_validator_balance(self, validator_account):
        return validator_account.balance

    def get_elector_total_stake(self, elector_addr):
        cmd = "runmethodfull {fullElectorAddr} past_elections".format(
            fullElectorAddr=elector_addr)
        result = self.mtc.liteClient.Run(cmd)
        result = self.mtc.Result2List(result)
        return result[0][0][5]

    def get_stake_in_election(self, elector_addr, adnl_addr):
        cmd = "runmethodfull {fullElectorAddr} participant_list_extended".format(
            fullElectorAddr=elector_addr)
        result = self.mtc.liteClient.Run(cmd)
        # self.log.info(f'get_stake_in_election: result={result}')
        rawElectionEntries = self.mtc.Result2List(result)
        # self.log.info(f'rawElectionEntries={rawElectionEntries}')

        electionEntries = rawElectionEntries[4]
        for entry in electionEntries:
            if len(entry) == 0:
                continue

            # Create dict
            adnlAddr = mytonctrl.Dec2HexAddr(entry[1][3])
            # self.log.info(f'adnl={adnlAddr}, adnl_Addr={adnl_addr}')
            if adnlAddr == adnl_addr:
                stake = mytonctrl.ng2g(entry[1][0])
                self.log.info(f'get_stake_in_election: stake: {stake}')
                return stake

        return 0

    def get_stake_in_validation(self, adnl_addr, config34, elector_addr):
        # self.log.info(f'config34: {config34}')

        res = next((item for item in config34['validators'] if item['adnlAddr'] == adnl_addr), {
                   'weight': 0})
        # self.log.info(f'get_stake_in_validation: {res}')

        elector_total_stake = self.get_elector_total_stake(elector_addr)

        # self.log.info(f'get_stake_in_validation: elector_total_stake={elector_total_stake}')

        return (elector_total_stake * res['weight'] / config34['totalWeight']) / 1e9

    def get_freeze_stake(self, mytoncore_db, adnl_addr):
        # TODO: need to parse past_elections frozen dict in python (not implemented) currently reading from mytoncore_db
        election_id = self.const['validators_elected_for'] * math.floor(
            self.start_run_time / self.const['validators_elected_for'])
        return self.get_stake_from_mytoncore_db(mytoncore_db, election_id, adnl_addr)

        # cmd = "runmethodfull {fullElectorAddr} past_elections".format(fullElectorAddr=elector_addr)
        # result = self.mtc.liteClient.Run(cmd)
        # self.log.info(f'get_freeze_stake: result: {result}')
        #
        # res = self.mtc.Result2List(result)
        # self.log.info(f'get_freeze_stake: res: {res}')
        # return 0

    def get_unfreeze_stake(self, elector_addr, single_nominator):
        # compute_returned_stake
        cmd = "runmethodfull {fullElectorAddr} compute_returned_stake 0x{single_nominator_addr}".format(
            fullElectorAddr=elector_addr, single_nominator_addr=single_nominator.addr)
        result = self.mtc.liteClient.Run(cmd)
        res = self.mtc.Result2List(result)
        self.log.info(f'get_unfreeze_stake: res: {res}')
        return res[0]

    def calc_balance_at_elector(self, elector_addr, adnl_addr, single_nominator, config34):
        # currently we are sampling right after elections begins so we are not expected to have frozen stake
        return self.get_stake_in_election(elector_addr, adnl_addr) + \
            self.get_stake_in_validation(adnl_addr, config34, elector_addr) + \
            self.get_unfreeze_stake(elector_addr, single_nominator)
        # + self.get_freeze_stake(mytoncore_db, adnl_addr)

    def get_balance_at_elector(self, adnl_addr, single_nominator, config34):

        next_update = self.const['validators_elected_for'] * math.ceil(
            self.start_run_time / self.const['validators_elected_for']) + self.const['stake_held_for'] + 630

        if self.start_run_time > next_update:
            elector_addr = self.const['elector_addr']
            self.balance_at_elector = \
                self.get_stake_in_election(elector_addr, adnl_addr) + \
                self.get_stake_in_validation(adnl_addr, config34, elector_addr) + \
                self.get_unfreeze_stake(elector_addr, single_nominator)
            # + self.get_freeze_stake(mytoncore_db, adnl_addr)
            # self.log.info(f'balance_at_elector: {self.balance_at_elector}')

            self.reporter_db['balance_at_elector'] = self.balance_at_elector
            self.save_json_to_file(self.reporter_db, self.DB_FILE)

        return self.balance_at_elector

    def get_local_stake(self):
        stake = self.mtc.GetSettings("stake")

        if stake is None:
            return -1

        return float(self.mtc.GetSettings("stake"))

    def get_local_stake_percent(self):
        stake_percent = self.mtc.GetSettings("stakePercent")

        if stake_percent is None:
            return -1

        return float(self.mtc.GetSettings("stakePercent"))

    def get_stats(self):
        return self.mtc.GetValidatorStatus()

    def past_election_ids(self, mytoncore_db):
        # cmd = f"runmethodfull {self.metrics.get('elector_addr')} past_election_ids"
        #
        # result = self.mtc.liteClient.Run(cmd)
        # activeElectionId = self.mtc.GetVarFromWorkerOutput(result, "result")
        # return sorted([int(s) for s in activeElectionId.replace('(', '').replace(')', '').split() if s.isdigit()], reverse=True)
        return sorted(mytoncore_db['saveElections'].keys(), reverse=True)

    def participate_in_next_validation(self, mytoncore_db, past_election_ids, adnl_addr):
        return int(float(past_election_ids[0]) > self.start_run_time and self.participates_in_election_id(mytoncore_db, str(past_election_ids[0]), adnl_addr))

    def participate_in_curr_validation(self, mytoncore_db, past_election_ids, adnl_addr, validator_index):

        if validator_index == -1:
            return 0

        if float(past_election_ids[0]) < self.start_run_time:
            return self.participates_in_election_id(mytoncore_db, str(past_election_ids[0]), adnl_addr)
        else:
            return self.participates_in_election_id(mytoncore_db, str(past_election_ids[1]), adnl_addr)

    def active_election_id(self):
        return self.mtc.GetActiveElectionId(self.const['elector_addr'])

    def elections_ends_in(self, past_election_ids):

        if float(past_election_ids[0]) < self.start_run_time:
            return -1

        return max(int((int(past_election_ids[0]) - int(self.const['elections_end_before']) - self.start_run_time) / 60), 0)

    def validation_ends_in(self):
        return int(self.const['validators_elected_for'] * math.ceil(self.start_run_time / self.const['validators_elected_for']) - self.start_run_time)

    def elections_starts_in(self):
        return int(
            self.const['validators_elected_for'] * math.floor((self.start_run_time + self.const['validators_elected_for'] - self.const['elections_start_before']) / self.const['validators_elected_for']) + self.const[
                'validators_elected_for'] - self.const['elections_start_before'] - self.start_run_time)

    def held_period_ends_in(self):
        # return int(self.const['validators_elected_for'] + self.const['stake_held_for'] - (self.start_run_time % (self.const['validators_elected_for'] + self.const['stake_held_for'])))
        return int(self.const['validators_elected_for'] * math.floor((self.start_run_time + self.const['stake_held_for']) / self.const['validators_elected_for']) + self.const['stake_held_for'] - self.start_run_time)

    def validation_started_at(self, past_election_ids):

        if float(past_election_ids[0]) > self.start_run_time:
            assert float(
                past_election_ids[1]) < self.start_run_time, f'election_id {past_election_ids[1]} is expected to less than current time {self.start_run_time}'
            return past_election_ids[1]
        else:
            return past_election_ids[0]

    def get_mytoncore_db(self):

        with open(self.MYTONCORE_FILE_PATH, 'r') as f:
            return json.load(f)

    def participates_in_election_id(self, mytoncore_db, election_id, adnl_addr):

        if 'saveElections' not in mytoncore_db or election_id not in mytoncore_db['saveElections']:
            return 0

        return int(mytoncore_db['saveElections'][election_id].get(adnl_addr) is not None)

    def get_stake_from_mytoncore_db(self, mytoncore_db, election_id, adnl_addr):

        if 'saveElections' not in mytoncore_db or election_id not in mytoncore_db['saveElections'] or adnl_addr not in mytoncore_db['saveElections'][election_id]:
            return 0

        return int(mytoncore_db['saveElections'][election_id][adnl_addr]['stake'])

    def calc_roi(self, total_balance):

        if total_balance < 1:
            return 0

        if 'wallet_init_balance' not in self.reporter_db:
            self.reporter_db['wallet_init_balance'] = total_balance
            return 0

        return round(100 * (total_balance / self.reporter_db['wallet_init_balance'] - 1), 2)

    def calc_apy(self, roi):

        if roi <= 0 or not self.reporter_db.get('start_work_time'):
            return 0

        apy = round(
            roi * self.SECONDS_IN_YEAR / (
                self.const['validators_elected_for'] * math.floor(
                    self.start_run_time / self.const['validators_elected_for']) - int(self.reporter_db['start_work_time'])
            ), 2)

        next_update = self.const['validators_elected_for'] * math.ceil(
            self.start_run_time / self.const['validators_elected_for']) + self.const['stake_held_for'] + 630
        self.log.info(
            f"roi={roi}, next_update={next_update}, apy={apy}, x={self.const['validators_elected_for'] * math.floor(self.start_run_time / self.const['validators_elected_for'])}")

        if self.start_run_time > next_update or self.apy == -1:
            self.apy = max(round(
                roi * self.SECONDS_IN_YEAR / (
                    self.const['validators_elected_for'] * math.floor(
                        self.start_run_time / self.const['validators_elected_for']) - int(self.reporter_db['start_work_time'])
                ), 2), 0)

        return self.apy

    def get_validator_load(self, validator_id, election_id):
        # get validator load at index validator_id returns -1 if validator id not found
        # o.w returns the expected and actual blocks created for the last 2000 seconds
        # mr and wr are blocks_created/blocks_expected
        start_time = int(election_id)
        end_time = int(self.start_run_time) - 15

        if end_time - start_time > 65536:
            self.log.error(
                f'unexpected time diff between end_time = {end_time} and start_time = {start_time}')
            start_time = end_time - 3 * 3600  # last 3 hours

        validators_load = self.get_validators_load(start_time, end_time)

        if validator_id not in validators_load.keys():
            return 0, {
                'mc_blocks_created': -1,
                'mc_blocks_expected': -1,
                'mc_prob': -1,
                'wc_blocks_created': -1,
                'wc_blocks_expected': -1,
                'wc_prob': -1,
                'mr': -1,
                'wr': -1,
            }

        return 1, {
            'mc_blocks_created': validators_load[validator_id]['masterBlocksCreated'],
            'mc_blocks_expected': validators_load[validator_id]['masterBlocksExpected'],
            'mc_prob': validators_load[validator_id]['masterProb'],
            'wc_blocks_created': validators_load[validator_id]['workBlocksCreated'],
            'wc_blocks_expected': validators_load[validator_id]['workBlocksExpected'],
            'wc_prob': validators_load[validator_id]['workchainProb'],
            'mr': validators_load[validator_id]['mr'],
            'wr': validators_load[validator_id]['wr'],
        }

    def min_prob(self, active_validator, validator_load):
        # probability to close <= blocks_created blocks given th expected blocks to close are blocks_expected
        if not active_validator:
            return self.MIN_PROB_NULL

        return min(validator_load['mc_prob'], validator_load['wc_prob'])

    def check_fine_changes(self, mytoncore_db):

        if 'saveComplaints' not in mytoncore_db:
            return 0

        complaints_hash = []
        last_reported_election = sorted(
            mytoncore_db['saveComplaints'].keys(), reverse=True)[0]
        for complaint_hash, complaints_values in mytoncore_db['saveComplaints'][last_reported_election].items():
            if complaints_values['suggestedFine'] != self.const['suggested_fine'] or complaints_values['suggestedFinePart'] != self.const['suggested_fine_part']:
                complaints_hash.append(complaint_hash)

        return complaints_hash or 0

    def get_load_stats(self, mytoncore_db):

        # TODO fix hack
        return 0, 0, 0
        net_load_avg = mytoncore_db['statistics']['netLoadAvg'][1]
        sda_load_avg_pct = mytoncore_db['statistics']['disksLoadPercentAvg']['sda'][1]
        sdb_load_avg_pct = mytoncore_db['statistics']['disksLoadPercentAvg']['sdb'][1]
        disk_load_pct_avg = max(sda_load_avg_pct, sdb_load_avg_pct)

        mem_info = GetMemoryInfo()
        mem_load_avg = mem_info['usagePercent']

        return net_load_avg, disk_load_pct_avg, mem_load_avg

    def elector_addr_changed(self):

        elector_addr = self.mtc.GetFullElectorAddr()

        if elector_addr != self.const['elector_addr']:
            return 1

        return 0

    def config_addr_changed(self):

        config_addr = self.mtc.GetFullConfigAddr()

        if config_addr != self.const['config_addr']:
            return 1

        return 0

    def single_nominator_code_changed(self, single_nominator):

        if single_nominator.account.codeHash != self.const['single_nominator_hash']:
            return 1

        return 0

    def elector_code_changed(self):

        elector_account = self.mtc.GetAccount(self.const['elector_addr'])
        assert elector_account, 'failed to get elector account'

        if elector_account.codeHash != self.const['elector_code_hash']:
            return 1

        return 0

    def config_code_changed(self):

        config_account = self.mtc.GetAccount(self.const['config_addr'])
        assert config_account, 'failed to get config account'

        if config_account.codeHash != self.const['config_code_hash']:
            return 1

        return 0

    def _get_total_stake(self, mytoncore_db):

        prev_election_id = sorted(
            mytoncore_db['saveElections'].keys(), reverse=True)[1]
        total_stake = 0
        for values in mytoncore_db['saveElections'][prev_election_id].values():
            total_stake += values['stake']

        return total_stake

    def total_stake_reduced(self, total_stake):

        if not self.reporter_db.get('prev_cycle_total_stake') or total_stake > self.reporter_db['prev_cycle_total_stake']:
            self.reporter_db['prev_cycle_total_stake'] = total_stake
            self.save_json_to_file(self.reporter_db, self.DB_FILE)
            return 0

        return int(total_stake / self.reporter_db['prev_cycle_total_stake'] < 0.8)

    def get_num_validators(self, config34):
        return config34['totalValidators']

    def get_total_network_stake(self, config34):
        return config34['totalWeight']

    def num_validators_reduced(self, num_validators):

        if not self.reporter_db.get('prev_cycle_num_validators') or num_validators > self.reporter_db['prev_cycle_num_validators']:
            self.reporter_db['prev_cycle_num_validators'] = num_validators
            self.save_json_to_file(self.reporter_db, self.DB_FILE)
            return 0

        return int(num_validators / self.reporter_db['prev_cycle_num_validators'] < 0.8)

    def new_offers(self):

        offers = self.mtc.GetOffers()

        if not offers:
            return 0

        if not self.prev_offers:
            self.prev_offers = offers
            return 0

        if offers[-1].get('hash') != self.prev_offers[-1].get('hash'):
            self.prev_offers = offers
            self.log.info(
                f'new offers: {offers}, prev offers: {self.prev_offers}')
            return 1

        return 0

    def detect_complaint(self, mytoncore_db, past_election_ids, adnl_addr):

        election_id = past_election_ids[0] if float(
            past_election_ids[0]) < self.start_run_time else past_election_ids[1]
        if 'saveComplaints' not in mytoncore_db or election_id not in mytoncore_db['saveComplaints']:
            return -1

        return int(adnl_addr in mytoncore_db['saveComplaints'][election_id].keys())

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

    def global_version_changed(self, version, capabilities):

        if version != self.const['version'] or capabilities != self.const['capabilities']:
            return 1

        return 0

    def reporter_pid_changed(self, pid):

        if not self.metrics.get('reporter_pid'):
            self.write_metrics_to_file('reporter_pid', pid)
            return 0

        if pid != self.metrics.get('reporter_pid'):
            return 1

        return 0

    def get_pid(self):
        return os.getpid()

    def compounding(self, total_balance):
        self.mtc.SetSettings("stake", total_balance)

    def exit_next_elections(self):

        self.mtc.SetSettings("stake", 0)
        self.mtc.SetSettings("stakePercent", 0)

        stake = self.get_local_stake()
        stake_pct = self.get_local_stake_percent()

        if stake != 0 or stake_pct != 0:
            self.log.error(
                f'Failed to set stake and stake_percent to 0 (stake={stake}, stake_percent={stake_pct})')
        else:
            self.log.info(f'Successfully set stake and stake_percent to 0')

    def emergency_update(self, emergency_flags_filler):

        emergency_flags = {'exit_flags': dict(
        ), 'recovery_flags': dict(), 'warning_flags': dict()}

        #################################
        # Exit Only
        #################################
        for key, value in emergency_flags_filler['exit_flags'].items():
            if value != 0:
                emergency_flags['exit_flags'][key] = 1

        #################################
        # Warning Only
        #################################
        for key, value in emergency_flags_filler['warning_flags'].items():
            if value != 0:
                emergency_flags['warning_flags'][key] = 1

        #################################
        # Recovery Only
        #################################
        for key, value in emergency_flags_filler['recovery_flags'].items():
            if value != 0:
                emergency_flags['recovery_flags'][key] = 1

        emergency_flags['exit'] = int(
            len(emergency_flags['exit_flags'].keys()) != 0)
        emergency_flags['recovery'] = int(
            len(emergency_flags['recovery_flags'].keys()) != 0)
        emergency_flags['warning'] = int(
            len(emergency_flags['warning_flags'].keys()) != 0)
        emergency_flags['message'] = f"exit_flags: {list(emergency_flags['exit_flags'].keys())}, recovery_flags: {list(emergency_flags['recovery_flags'].keys())}, " \
                                     f"warning_flags: {list(emergency_flags['warning_flags'].keys())}"

        self.save_json_to_file(emergency_flags, self.EMERGENCY_FLAGS_FILE)

        if emergency_flags['exit']:
            self.exit_next_elections()

    def report(self):

        with open(self.METRICS_FILE, 'w') as f:
            json.dump(self.metrics, f)
            self.log.info(f'{self.METRICS_FILE} was updated')
            self.sendToElastic()
            self.log.info(f'{self.METRICS_FILE} posted to elastic')

    def sendToElastic(self):
        self.log.info("Sending elastic")
        url = 'http://3.141.233.132:3001/putes/sn-reporter'
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

                single_nominator = self.single_nominator()
                validator_index = self.validator_index()
                validator_wallet = self.validator_wallet()
                validator_account = self.validator_account(validator_wallet)
                adnl_addr = self.mtc.GetAdnlAddr()
                free_nominator_balance = self.free_nominator_balance(
                    single_nominator)
                free_validator_balance = self.free_validator_balance(
                    validator_account)
                stats = self.get_stats()
                config15 = self.mtc.GetConfig15()
                config34 = self.mtc.GetConfig34()
                validation_started_at = str(config34['startWorkTime'])
                validation_end_at = str(config34['endWorkTime'])
                past_election_ids = self.past_election_ids(mytoncore_db)
                # total_stake = self.get_total_stake(mytoncore_db)
                balance_at_elector = self.get_balance_at_elector(
                    adnl_addr, single_nominator, config34)
                total_stake = self.get_total_network_stake(config34)
                num_validators = self.get_num_validators(config34)
                pid = self.get_pid()
                version, capabilities = self.get_global_version()
                # validation_started_at = self.validation_started_at(past_election_ids)
                active_validator, validator_load = self.get_validator_load(
                    validator_index, str(validation_started_at))
                participate_in_curr_validation = self.participate_in_curr_validation(
                    mytoncore_db, past_election_ids, adnl_addr, validator_index)
                participate_in_next_validation = self.participate_in_next_validation(
                    mytoncore_db, past_election_ids, adnl_addr)
                min_prob = self.min_prob(active_validator, validator_load)
                validator_load_not_updated = participate_in_curr_validation and not active_validator and float(
                    validation_started_at) - self.start_run_time > 15

                self.update_start_work_time(
                    participate_in_next_validation, past_election_ids[0])

                ###############################################################
                # metrics
                # general validator metrics
                ###############################################################

                self.metrics['validator_index'] = validator_index
                self.metrics['adnl_addr'] = adnl_addr
                self.metrics['free_validator_balance'] = free_validator_balance
                self.metrics['free_nominator_balance'] = free_nominator_balance
                self.metrics['local_stake'] = self.get_local_stake()
                self.metrics['local_stake_percent'] = self.get_local_stake_percent()
                self.metrics['out_of_sync'] = stats['outOfSync']
                self.metrics['is_working'] = int(stats['isWorking'])
                self.metrics['participate_in_next_validation'] = participate_in_next_validation
                self.metrics['participate_in_curr_validation'] = participate_in_curr_validation
                self.metrics['active_election_id'] = self.active_election_id()
                self.metrics['elections_ends_in'] = self.elections_ends_in(
                    past_election_ids)
                self.metrics['validations_ends_in'] = self.validation_ends_in()
                self.metrics['validation_started_at'] = validation_started_at
                self.metrics['validation_end_at'] = validation_end_at
                self.metrics['elections_starts_in'] = self.elections_starts_in()
                self.metrics['held_period_ends_in'] = self.held_period_ends_in()
                self.metrics['total_validator_balance'] = balance_at_elector + \
                    free_validator_balance + free_nominator_balance
                self.metrics['roi'] = self.calc_roi(
                    self.metrics['total_validator_balance'])
                self.metrics['apy'] = self.calc_apy(self.metrics['roi'])
                self.metrics['validator_load'] = validator_load
                self.metrics['min_prob'] = min_prob
                self.metrics['net_load_avg'], self.metrics['disk_load_pct_avg'], self.metrics['mem_load_avg'] = self.get_load_stats(
                    mytoncore_db)
                self.metrics['total_network_stake'] = total_stake
                self.metrics['version'], self.metrics['capabilities'] = version, capabilities
                self.metrics['num_validators'] = num_validators
                self.metrics['reporter_pid'] = pid
                self.metrics['validator_wallet_addr'] = validator_wallet.addrB64
                self.metrics['single_nominator_hash'] = single_nominator.account.codeHash
                self.metrics['update_time'] = self.start_run_time
                self.metrics['hostname'] = socket.gethostname()
                self.metrics['mytonctrl_version'] = self.getMytonctrlVersion()
                self.metrics['ton_version'] = self.getTonVersion()

                emergency_flags = {'exit_flags': dict(
                ), 'recovery_flags': dict(), 'warning_flags': dict()}

                ###############################################################
                # exit flags
                # when set should trigger immediate exit from the next validation cycle
                # reporter will initiate set stake 0 (and set stakePercent 0)
                ###############################################################

                # verify validator wallet exists
                emergency_flags['exit_flags']['validator_wallet_not_exists'] = int(
                    self.validator_wallet_exists() != 1)
                # verify validation cycle was not changed
                emergency_flags['exit_flags']['validators_elected_for_changed'] = int(
                    config15['validatorsElectedFor'] != self.const['validators_elected_for'])
                # verify start of election cycle before next validation was not changed
                emergency_flags['exit_flags']['elections_start_before_changed'] = int(
                    config15['electionsStartBefore'] != self.const['elections_start_before'])
                # verify end of election cycle before next validation was not changed
                emergency_flags['exit_flags']['elections_end_before_changed'] = int(
                    config15['electionsEndBefore'] != self.const['elections_end_before'])
                # verify freeze period was not changed
                emergency_flags['exit_flags']['stake_held_for_changed'] = int(
                    config15['stakeHeldFor'] != self.const['stake_held_for'])
                # verify network fine was not changed
                emergency_flags['exit_flags']['fine_changed'] = self.check_fine_changes(
                    mytoncore_db)
                # verify single nominator code hash was not changed
                emergency_flags['exit_flags']['single_nominator_code_changed'] = self.single_nominator_code_changed(
                    single_nominator)
                # verify elector address was not changed
                emergency_flags['exit_flags']['elector_addr_changed'] = self.elector_addr_changed(
                )
                # verify config address was not changed
                emergency_flags['exit_flags']['config_addr_changed'] = self.config_addr_changed(
                )
                # verify elector code hash address was not changed
                emergency_flags['exit_flags']['elector_code_changed'] = self.elector_code_changed(
                )
                # verify config code hash address was not changed
                emergency_flags['exit_flags']['config_code_changed'] = self.config_code_changed(
                )
                # verify total network stake was not reduced by more than 20% (relative to previous cycle)
                emergency_flags['exit_flags']['total_stake_reduced'] = self.total_stake_reduced(
                    total_stake)
                # verify total number of valudators in the network was not reduced by more than 20% (relative to previous cycle)
                emergency_flags['exit_flags']['num_validators_reduced'] = self.num_validators_reduced(
                    num_validators)
                # verify global version and network capabilities were not changed
                emergency_flags['exit_flags']['global_version_changed'] = self.global_version_changed(
                    version, capabilities)
                # verify no one complaints about this validator
                emergency_flags['exit_flags']['complaint_detected'] = int(
                    self.detect_complaint(mytoncore_db, past_election_ids, adnl_addr) == 1)
                # TODO: need to check this flag
                # verify no new offers were submitted, new offers might influence and change some important network params
                emergency_flags['exit_flags']['new_offers'] = self.new_offers()
                # verify validator load is accessible. validator load reflects the load from validator work (e.g.: how many blocks were closed)
                emergency_flags['exit_flags']['validator_load'] = validator_load_not_updated
                # verify validator is closing blocks with high probability (> 0.1)
                # min_prob is the probability the validator didn't close block for the given period (since the start of the validation cycle)
                emergency_flags['exit_flags']['min_prob'] = min_prob < .1

                ###############################################################
                # recovery flags
                # when set should trigger manual/automatic operation by the devops group operating the validator
                # the operation might include for example restarting a process or checking that network connectivity is ok
                # however it will not trigger exit from the next validating cycle
                ###############################################################

                # validator process is running
                emergency_flags['recovery_flags']['systemctl_status_validator'] = int(
                    self.systemctl_status_validator_ok() != 1)
                # validator is not out of sunc (validator epoch relative to the network)
                emergency_flags['recovery_flags']['out_of_sync_err'] = int(
                    self.metrics['out_of_sync'] > 120)
                # validator RAM should be < 85%
                emergency_flags['recovery_flags']['mem_load_avg_err'] = int(
                    self.metrics['mem_load_avg'] > 85)
                # validator disk should be < 85%
                emergency_flags['recovery_flags']['disk_load_pct_avg_err'] = int(
                    self.metrics['mem_load_avg'] > 85)
                # validator network load average should be < 400 MB/sec
                emergency_flags['recovery_flags']['net_load_avg_err'] = int(
                    self.metrics['mem_load_avg'] > 400)

                ###############################################################
                # warning flags
                # general warnings that should be noticed and might require some actions from R&D team
                # for example low validator balance should trigger sending funds to the validtor wallet
                ###############################################################

                # validator balance should be > 100 TON
                emergency_flags['warning_flags']['low_validator_balance'] = free_validator_balance < 100
                # validator should continuously participate in every validation cycle
                emergency_flags['warning_flags']['participate_in_curr_validation'] = bool(
                    not participate_in_curr_validation)

                self.emergency_update(emergency_flags)

                self.report()

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
