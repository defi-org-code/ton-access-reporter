#!/usr/bin/python3 -u
import os
import json

REPORTER_DIR = f'/var/reporter'
REPORTER_PARAMS_FILE = f'{REPORTER_DIR}/params.json'


def load_params_from_file():
	if os.path.isfile(REPORTER_PARAMS_FILE):
		with open(REPORTER_PARAMS_FILE, 'r') as f:
			return json.load(f)


def write_params_to_file(params, key, value):
	params[key] = value

	print(f'writing {key} with value {value} to params file at {REPORTER_PARAMS_FILE}')

	with open(REPORTER_PARAMS_FILE, 'w') as f:
		json.dump(params, f)
		print(f'{REPORTER_PARAMS_FILE} was updated')


print('Reset Params script started')
print('Reset all params are you sure? [y/n]')
res = input()
if res.lower() != 'y':
	print('exit script without any action')
	exit()
else:

	with open(REPORTER_PARAMS_FILE, 'w') as f:
		json.dump({}, f)
		print(f'{REPORTER_PARAMS_FILE} was reset')

	print(f'restarting reporter service')
	res = os.system('sudo systemctl restart reporter')

	if res != 0:
		print('[ERROR] failed to restart reporter service')
	else:
		print('reporter service restarted successfully')

	print('all done')
