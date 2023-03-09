#!/bin/bash
set -e

if [ "$(id -u)" != "0" ]; then
	echo "Please run script as root"
	exit 1
fi

SERVICE_NAME=access-reporter
REPORTER_DB=/var/${SERVICE_NAME}
SRC_DIR=/usr/src/${SERVICE_NAME}
REPORTER_LOG_DIR=/var/log/${SERVICE_NAME}
SYSTEMD_REPORTER_SERVICE=/etc/systemd/system/${SERVICE_NAME}.service

echo "stopping ${SERVICE_NAME}.service"
sudo systemctl stop ${SERVICE_NAME}

echo "stopping ${SERVICE_NAME}.service"
sudo systemctl disable ${SERVICE_NAME}

echo "rm ${SYSTEMD_REPORTER_SERVICE}"
sudo rm ${SYSTEMD_REPORTER_SERVICE}

echo "submitting changes to systemd ..."
sudo systemctl daemon-reload
sudo systemctl reset-failed

if [ -d ${SRC_DIR} ]; then
	echo "removing ${SRC_DIR}"
	rm -rf ${SRC_DIR}
fi

if [ -d ${REPORTER_DB} ]; then
	echo "removing ${REPORTER_DB}"
	rm -rf ${REPORTER_DB}
fi

if [ -d ${REPORTER_LOG_DIR} ]; then
	echo "removing ${REPORTER_LOG_DIR}"
	rm -rf ${REPORTER_LOG_DIR}
fi

echo "all done"
