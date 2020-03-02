#!/bin/bash
# Wrapper script by yuvipanda
# Submits job to the grid

# Replaces disabled  script by Snowolf that run the bot on the current host
# and was disabled by yuvipanda for this reason on April 30th (2015?)

jstop stewardbot

if [ $? -eq 0 ]; then
	echo "Waiting for bot to stop so it can be restarted"
	qstat -j stewardbot 2>&1 > /dev/null
	while [ $? -eq 0 ]; do
		sleep 1
		echo -n '.'
		qstat -j stewardbot  2>&1 > /dev/null
	done
fi

jstart -N stewardbot -mem 2G /data/project/stewardbots/venv-py3/bin/python3 /data/project/stewardbots/stewardbots/StewardBot/StewardBot.py

#EOF
