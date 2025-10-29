#!/bin/sh
export CHROMEDRIVER_PATH=$(which chromedriver)
echo "--- Starting Application ---"
echo "Found chromedriver at: $CHROMEDRIVER_PATH"
echo "--------------------------"
python moodle_checker.py
