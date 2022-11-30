#!/bin/bash

LOG_FILE="{{logfolder}}/postsetup_installations.log"
TIMESTAMP=`date --rfc-3339=seconds`

exec 1> >(tee -a $LOG_FILE) 2>&1

#Set the field separator to new line
IFS=$'\n'

WriteLog(){
  local in=$1;
  if [ -z "$in" ]; then
    in=`cat`;
  fi
  for item in $in
  do
    echo "[$(date --rfc-3339=seconds)]: $item"
  done
}

{% for installationline in installations %}
# {{ installationline.0 }}: {{ installationline.1 }}
{{ installationline.2 }} | tail -n +1 | WriteLog
{% endfor %}