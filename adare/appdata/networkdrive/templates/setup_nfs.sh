#!/bin/sh -eux
# need to be run with sudo

{% for share in configuration.shares %}
mkdir -p {{ share.remote_path }}
chown -R vagrant:vagrant {{ share.remote_path }}
{% endfor %}

{% for share in configuration.shares %}
# insecure needs to be added to allow access from ports > 1024 (https://security.stackexchange.com/questions/246527/what-is-insecure-about-the-insecure-option-of-nfs-exports)
echo "{{ share.remote_path }} {{ share.allowed_hosts }}{% if share.get_mount_option_string %}({{ share.get_mount_option_string() }}){% endif %}" >> /etc/exports
{% endfor %}

sudo systemctl restart nfs-kernel-server
echo "nfs activated successfully"
