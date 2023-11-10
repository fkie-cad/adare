statusfile="{{ log_directory }}/status.csv"

source "{{ script }}"
echo "RUN_{{ name }},$?" >> $statusfile