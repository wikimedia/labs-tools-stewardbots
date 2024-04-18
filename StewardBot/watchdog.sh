#!/bin/bash

MAX_MINUTES="65"
HEARTBEAT_FILE="/tmp/stewardbot_heartbeat"

if [[ $(find "$HEARTBEAT_FILE" -mmin "+$MAX_MINUTES" -print) ]]; then
    # Heartbeat file exists and is older than MAX_MINUTES
    ls -l --time-style=full-iso "$HEARTBEAT_FILE"
    exit 1
fi
