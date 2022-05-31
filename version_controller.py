#!/usr/bin/python3 -u
import os
import time
import json
from urllib import request
from packaging import version
from subprocess import call
import logging

class VersionController(object):
	VERSION_DESCRIPTOR = 'https://raw.githubusercontent.com/defi-org-code/ton-validator-reporter/master/version.txt'
	INSTALLER_DESCRIPTOR = 'https://raw.githubusercontent.com/defi-org-code/ton-validator-reporter/master/installer.sh'

	REPORTER_DIR = f'/var/ton-validator-reporter'
	REPORTER_PARAMS_FILE = f'{REPORTER_DIR}/params.json'

	SECONDS_IN_YEAR = 365 * 24 * 3600
	SLEEP_INTERVAL = 5 * 60
	version = None

	LOG_FILENAME = f'/var/log/ton-validator-reporter/version_controller.log'

	def __init__(self):
		super(VersionController, self).__init__()

		logging.basicConfig(format='[%(asctime)s] %(filename)s:%(lineno)s - %(message)s', datefmt='%m-%d-%Y %H:%M:%S.%f', filename=self.LOG_FILENAME, level=logging.INFO)
		self.log = logging

		self.version = self.get_version()

	def get_version(self):

		self.log.info(f'reading version file from {self.REPORTER_PARAMS_FILE}')

		orbs_validator_params = {}
		if os.path.isfile(self.REPORTER_PARAMS_FILE):
			with open(self.REPORTER_PARAMS_FILE, 'r') as f:
				orbs_validator_params = json.load(f)

		if 'version' not in orbs_validator_params:
			orbs_validator_params['version'] = '0.0.0'
			self.log.info(f'updating {self.REPORTER_PARAMS_FILE} with version {orbs_validator_params["version"]}')
			with open(self.REPORTER_PARAMS_FILE, 'w') as f:
				json.dump(orbs_validator_params, f)

		self.log.info(f'current version is {orbs_validator_params["version"]}')
		return version.Version(orbs_validator_params['version'])

	def run(self):

		while True:

			try:
				with request.urlopen(self.VERSION_DESCRIPTOR) as url:
					data = url.read().decode().strip()
					curr_version = version.parse(data)

					if curr_version > self.version:

						if os.path.exists('installer.sh'):
							self.log.info('removing old installer.sh')
							os.remove('installer.sh')

						self.log.info('downloading new installer.sh')
						request.urlretrieve(self.INSTALLER_DESCRIPTOR, 'installer.sh')
						os.chmod('installer.sh', 777)
						call("./installer.sh")

			except Exception as e:
				self.log.info(e)

			sleep_sec = self.SLEEP_INTERVAL - time.time() % self.SLEEP_INTERVAL
			self.log.info(f'sleep for {round(sleep_sec)} seconds')
			time.sleep(sleep_sec)


if __name__ == '__main__':
	vc = VersionController()
	vc.run()
