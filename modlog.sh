#!/bin/bash
# run as cronjob like so:
#1 0 0 * * * /path/to/modlog.sh

yesterday="$(date -d @$(($(date -d "$(date +%F)" +%s) - 3605)) +%F)"
cd "$HOME/modlog/"
echo "$yesterday"
python modlog.py "$yesterday" > "public/$yesterday.xhtml"
