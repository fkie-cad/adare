statusfile="{{ log_directory }}/status.csv"

. "{{ script }}"
echo "RUN_{{ name }},$?" >> $statusfile