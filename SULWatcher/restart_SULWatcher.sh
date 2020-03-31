#!/bin/bash

jstop sulwatcher

if [ $? -eq 0 ]; then
        echo "Waiting for bot to stop so it can be restarted"
        qstat -j sulwatcher 2>&1 > /dev/null
        while [ $? -eq 0 ]; do
                sleep 1
                echo -n '.'
                qstat -j sulwatcher  2>&1 > /dev/null
        done
fi

sleep 5
jstart -N sulwatcher -mem 2G -j y /data/project/stewardbots/venv-py3/bin/python3 /data/project/stewardbots/stewardbots/SULWatcher/SULWatcher.py
