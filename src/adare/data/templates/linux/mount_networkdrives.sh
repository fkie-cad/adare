#!/bin/bash

LOG_FILE="{{logfolder}}/mount_networkdrives.log"
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

{% for s in share %}
mkdir -p {{ s.local_path }} | tail -n +1 | WriteLog
echo '{{ s.fstab }}' >> /etc/fstab | tail -n +1 | WriteLog
{% endfor %}

{% if share %}
mount -a | tail -n +1 | WriteLog
{% else %}
echo "no share provided" | tail -n +1 | WriteLog
{% endif %}