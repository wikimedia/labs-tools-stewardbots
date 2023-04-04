#!/usr/bin/env bash
# Management script for <del>stashbot</del> StewardBot kubernetes processes
# https://github.com/wikimedia/stashbot/blob/master/bin/stashbot.sh

set -e

TOOL_DIR=/data/project/stewardbots/stewardbots/StewardBot
JOB_NAME=stewardbot
JOB_FILE="${TOOL_DIR}/jobs.yaml"
LOG_FILE="/data/project/stewardbots/logs/stewardbot.log"
VENV=/data/project/stewardbots/venv-k8s-py39

case "$1" in
    start)
        echo "Starting StewardBot k8s deployment..."
        toolforge-jobs load "${JOB_FILE}" --job "${JOB_NAME}"
        ;;
    run)
        date +%Y-%m-%dT%H:%M:%S
        echo "Starting StewardBot..."
        source ${VENV}/bin/activate
        cd ${TOOL_DIR}
        exec python StewardBot.py
        ;;
    stop)
        echo "Stopping StewardBot k8s deployment..."
        toolforge-jobs delete "${JOB_NAME}"
        # FIXME: wait for the pods to stop
        ;;
    restart)
        echo "Restarting StewardBot pod..."
        toolforge-jobs restart "${JOB_NAME}"
        ;;
    status)
        toolforge-jobs show "${JOB_NAME}"
        ;;
    tail)
        exec tail -f "${LOG_FILE}"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|tail}"
        exit 1
        ;;
esac

exit 0
# vim:ft=sh:sw=4:ts=4:sts=4:et:
