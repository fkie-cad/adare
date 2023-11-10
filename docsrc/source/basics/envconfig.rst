Environment Configuration File
*******************************

This file contains the configuration for the environment.
It contains the name of the vagrant box, information about the guest OS as well as potentially additional information such as installations to be performed on the guest OS, before the experiment.
A minimal configuration file just needs to contain the vagrant box name as well as the platform of the guest OS as shown below:

.. code-block:: yaml

    vagrantbox: "win10vagrantbox"
    os_platform: "windows"
    os: "Windows 10"
    os_distribution: "Home"

Additionally, the configuration file can contain the following fields:

.. csv-table::
    :file: /_static/tables/environment_configuration_fields.csv
    :delim: |
    :widths: 30, 70
    :header-rows: 1

Examples
########
Below you can find further examples of environment configuration files.

An extended configuration file for a Windows 10 guest OS with a custom vagrant box:

.. code-block:: yaml

    name: "testenv"
    vagrantbox: "win10home21H1_english"
    resolution: "1920x1080"
    os_platform: "windows"
    os: "Windows 10"
    os_distribution: "Home"
    os_version: "21H1"
    os_language: "English"
    postsetupinstallations:
      - name: "jinja2"
        command: "pip3 install jinja2"
        description: "tool to use templating in python"
      - name: "datefinder"
        command: "pip3 install datefinder"
      - name: "guibot"
        command: "pip3 install guibot"
      - name: "pyautogui"
        command: "pip3 install pyautogui"
        description: "tool to change resolution"
      - name: "opencv"
        command: "pip3 install opencv-python"
      - name: "tesseract"
        command: "choco install --no-progress -y tesseract"
      - name: "tesseract python"
        command: "pip3 install pytesseract"

An example for an Ubuntu 20.04 guest OS:

.. code-block:: yaml

    name: "testenv"
    vagrantbox: "ubuntu20043_gnome"
    resolution: "1920x1080"
    os: "linux"
    postsetupinstallations:
      - name: "jinja2"
        command: "pip3 install jinja2"
        description: "tool to use templating in python"
      - name: "datefinder"
        command: "pip3 install datefinder"
      - name: "update"
        command: "apt-get update"
        description: ''
      - name: "nfs client"
        command: "apt-get install nfs-common"
      - name: "smb"
        command: "apt-get install cifs-utils"
        description: ''
    settings:
      - "gsettings set org.gnome.desktop.lockdown disable-lock-screen 'true'"
    usbdevices:
      - name: "testusb"
        scenarios:
          - "deletefileUSB"
        VendorId: "0x0781"
        ProductId: "0x5567"
        Manufacturer: "SanDisk"
        Product: "Cruzer Blade"
        SerialNumber: "4C530000171114113444"
    networkdrives:
      - name: "testdrive"
        scenarios:
          - "deletefileSMB"
        type: "smb"
        user: "test"
        password: "123"



