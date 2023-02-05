#!/bin/bash

LOG_FILE="{{ log_directory }}/run_experiment.log"
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

chmod -R 777 /vagrant | tail -n +1 | WriteLog

{% if gui %}

{% for setting in settings %}
su -c "DISPLAY=:0 {{ setting }}" vagrant | tail -n +1 | WriteLog
{% endfor %}

su -c "DISPLAY=:0 xrandr -s {{ resolution }}" vagrant | tail -n +1 | WriteLog
echo "set resolution to {{ resolution }} done" | tail -n +1 | WriteLog
sleep 30

su -c "pip3 install /vagrant/scripts/GUIAutomation/" vagrant | tail -n +1 | WriteLog
su -c "DISPLAY=:0 /home/vagrant/.local/bin/guiautomation --logfile {{ log_directory }}/gui.log run '{{ gui_scenario }}'" vagrant | tail -n +1 | WriteLog
echo "automation for scenario {{ gui_scenario }} done" | tail -n +1| WriteLog

mkdir -p /vagrant/result/ | tail -n +1 | WriteLog

sleep 30
su -c "pip3 install /vagrant/scripts/ParseAndTest/" vagrant | tail -n +1 | WriteLog
su -c "DISPLAY=:0 /home/vagrant/.local/bin/parseandtest {{ inputfile }} {{ outputfile }} --logfile {{ log_directory }}/parseandtest.log" vagrant | tail -n +1 | WriteLog

{% else %}

{% for setting in settings %}
su -c "{{ setting }}" vagrant | tail -n +1 | WriteLog
{% endfor %}

su -c "pip3 install /vagrant/scripts/GUIAutomation/" vagrant | tail -n +1 | WriteLog
su -c "/home/vagrant/.local/bin/guiautomation --logfile {{ log_directory }}/gui.log run '{{ gui_scenario }}'" vagrant | tail -n +1 | WriteLog
echo "automation for scenario {{ gui_scenario }} done" | tail -n +1| WriteLog

mkdir -p /vagrant/result/ | tail -n +1 | WriteLog

sleep 30
su -c "pip3 install /vagrant/scripts/ParseAndTest/" vagrant | tail -n +1 | WriteLog
su -c "DISPLAY=:0 /home/vagrant/.local/bin/parseandtest {{ inputfile }} {{ outputfile }} --logfile {{ log_directory }}/parseandtest.log" vagrant | tail -n +1 | WriteLog

{% endif %}

