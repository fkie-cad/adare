#!/bin/bash

LOG_FILE="{{ logfolder }}/save_installed_packages.log"
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

PROGRAMLIST_FILE='{{ logfolder }}/installed_packages'

# dpkg for debian systems (like Ubuntu, Debian, Linux Mint)
if type dpkg >/dev/null; then
  dpkg-query -f '${binary:Package}=${version}\n' -W | tee "$PROGRAMLIST_FILE" | tail -n +1 | WriteLog
  exit 0
fi

# rpm for Redhat, CentOS, Fedora, ArchLinux, Scientific Linux, ...
if type rpm >/dev/null; then
  rpm -qa --qf '%{NAME}=%{VERSION}\n' | tee "$PROGRAMLIST_FILE" | tail -n +1 | WriteLog
  exit 0
fi

echo 'dpkg and rpm are not installed on the system so no file with programs version can be created'
