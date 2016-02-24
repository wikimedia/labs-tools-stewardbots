#!/bin/bash
# Wrapper script by yuvipanda
# Submits job to the grid

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

jsub -N stewardbot -continuous -mem 2G -l python /data/project/stewardbots/StewardBot/StewardBot.py


#EOF
