#!/bin/bash -eux

{% for user in configuration.users %}
id -u {{ user.name }} &>/dev/null || adduser --disabled-password --gecos "" {{ user.name }}
echo "{{ user.name }}:{{ user.password }}" | chpasswd
yes {{ user.password }} | head -n 2 | smbpasswd -a -s {{ user.name }}
{% endfor %}

{% for s in configuration.shares %}
{% if s.remote_path %}mkdir -p {{ s.remote_path }}{% endif %}
chown -R {{ s.user.name }}:{{ s.user.name }} {{ s.remote_path }}
{% endfor %}

cp /home/vagrant/config/smb.conf /etc/samba/smb.conf
systemctl restart smbd



