# external imports
import os
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from typing import Optional

# internal imports
import adare.config as config
from adare.config.configdirectory import VAGRANTFILE_TEMPLATE
from .exceptions import VagrantFileCreationError, VagrantFileWriteError

# configure logging
import logging
log = logging.getLogger(__name__)


class VagrantMachine:
    name: str
    options: dict
    provisioners: list[dict]
    usbdevices: list[dict]
    resolution: tuple
    additional_vboxmanage: list[dict]
    networks: list[dict]
    nat_port_forwarding: list[dict]
    destination: str
    private_networks: list[dict]
    synced_folders: list[dict]

    def __init__(self, name: str):
        self.name = name
        self.options = {
            'name': name,
        }
        self.provisioners = []
        self.usbdevices = []
        self.additional_vboxmanage = []
        self.networks = []
        self.nat_port_forwarding = []
        self.private_networks = []
        self.synced_folders = []

    def get_options(self):
        self.options.update(
            {
                'provisioners': self.provisioners,
                'usbdevices': self.usbdevices,
                'additional_vboxmanage_commands': self.additional_vboxmanage,
                'virtualbox_networks': self.networks,
                'port_forwardings': self.nat_port_forwarding,
                'private_networks': self.private_networks,
                'synced_folders': self.synced_folders
            }
        )
        return self.options

    def set_memory(self, memory: int):
        """
        change used memory/ram of the vm

        :param memory: ram to be used by the vm
        """
        self.options['virtualbox_memory'] = memory

    def set_cpus(self, cpus: int):
        """
        change used cpu's of the vm

        :param cpus: number of cpus to be used
        :return:
        """
        self.options['virtualbox_cpus'] = cpus

    def set_box(self, name: str):
        """
        set the name of the vagrant box which will be used

        :param name: name of the vagrant box
        :return:
        """
        self.options['config_vm_box'] = name

    # def set_vbox_name(self, name: str):
    #     """
    #     sets a name for the newly created vm
    #
    #     :param name: name of the newly created vm
    #     :return:
    #     """
    #     self.options['virtualbox_name'] = name

    def get_vbox_name(self) -> Optional[str]:
        """
        gets the name for the newly created vm

        :return: name of the vm
        """
        if 'virtualbox_name' in self.options.keys():
            return self.options['virtualbox_name']
        else:
            return None

    def enable_gui(self):
        """
        let the vm start in interactive mode / gui mode

        :return:
        """
        self.options['virtualbox_gui'] = True

    def disable_gui(self):
        """
        let the vm start in non interactive mode

        :return:
        """
        self.options['virtualbox_gui'] = False

    def enable_virtualbox_usb(self):
        """
        enable usb in vm

        :return:
        """
        self.options['virtualbox_modifyvm_usb_on'] = True

    def disable_virtualbox_usb(self):
        """
        disable usb in vm

        :return:
        """
        self.options['virtualbox_modifyvm_usb_on'] = False

    def enable_virtualbox_usbehci(self):
        """
        enable usbehci in vm

        :return:
        """
        self.options['virtualbox_modifyvm_usbehci_on'] = True

    def disable_virtualbox_usbehci(self):
        """
        disable usbehci in vm

        :return:
        """
        self.options['virtualbox_modifyvm_usbehci_on'] = False

    def add_shell_provisioner_inline(self, code: str, privileged: bool = False, powershell_elevated_interactive: bool = False):
        """
        add a provisioner which executes inline code in the terminal of the system

        :param code: code to be executed
        :param privileged: True if executed as sudo/Administrator and False if not
        :param powershell_elevated_interactive: run a powershell script in elevated mode
        :return:
        """
        provisioner = {
            'type': "shell",
            'provisioner_option': [
                {
                    'key': "inline",
                    'value': code
                }
            ]
        }
        if privileged:
            provisioner['provisioner_option'].append({
                'key': "privileged",
                'value': "true"
            })
        if powershell_elevated_interactive:
            provisioner['provisioner_option'].append({
                'key': "powershell_elevated_interactive",
                'value': "true"
            })
        self.provisioners.append(provisioner)

    def add_shell_provisioner_path(self, path: Path, privileged: bool = False, powershell_elevated_interactive: bool = False):
        """
        add a provisioner which executes a script

        :param path: path to a script with code to be executed
        :param privileged: True if executed as sudo/Administrator and False if not
        :param powershell_elevated_interactive: run a powershell script in elevated mode
        :return:
        """
        provisioner = {
            'type': "shell",
            'provisioner_option': [
                {
                    'key': "path",
                    'value': path.as_posix()
                }
            ]
        }
        if privileged:
            provisioner['provisioner_option'].append({
                'key': "privileged",
                'value': "true"
            })
        if powershell_elevated_interactive:
            provisioner['provisioner_option'].append({
                'key': "powershell_elevated_interactive",
                'value': "true"
            })
        self.provisioners.append(provisioner)

    def add_file_provisioner(self, localpath: Path, remotepath: str):
        """
        add a provisioner to provide files to the vm

        :param localpath: path on host
        :param remotepath: path on guest (vm) where the file should be copied to
        :return:
        """
        provisioner = {
            'type': "file",
            'provisioner_option': [
                {
                    'key': "source",
                    'value': localpath.as_posix()
                },
                {
                    'key': "destination",
                    'value': remotepath
                }
            ]
        }
        self.provisioners.append(provisioner)

    def change_ssh_shell(self, shh_shell: str):
        """
        change the default shell used

        :param shh_shell: name of the shell used instead
        :return:
        """
        self.options['ssh_shell'] = shh_shell

    def set_resolution(self, x, y):
        """
        set the resolution of the vm

        :param x: x resolution
        :param y: y resolution
        :return:
        """
        self.options['resolution'] = {
            'x': x,
            'y': y
        }


    def change_communicator(self, communicator: str):
        """
        default communicator is ssh; for windows should be changed to winrm

        :param communicator: name of the communicator to be used
        :return:
        """
        self.options['communicator'] = communicator

    def add_usb_device(self, name, vendor_id=None, product_id=None, manufacturer=None, product=None, serial_number=None):
        """
        add a usb device (filter) to be forward usb device from the host system to the guest

        :param name: custom name for the usb device
        :param vendor_id:
        :param product_id:
        :param manufacturer:
        :param product:
        :param serial_number:
        :return:
        """
        self.enable_virtualbox_usb()
        self.enable_virtualbox_usbehci()

        if not [x for x in (vendor_id, product_id, manufacturer, product, serial_number) if x is not None]:
            log.error("usbfilter is missing a filter")
            return -1

        usbfilter = {}
        vboxmanage_cmdline = (
            f'["usbfilter", "add", "0", "--target", :id, "--name","{name}"'
        )
        if vendor_id:
            vboxmanage_cmdline += f', "--vendorid", "{vendor_id}"'
        if product_id:
            vboxmanage_cmdline += f', "--productid", "{product_id}"'
        if manufacturer:
            vboxmanage_cmdline += f', "--manufacturer", "{manufacturer}"'
        if product:
            vboxmanage_cmdline += f', "--product", "{product}"'
        if serial_number:
            vboxmanage_cmdline += f', "--serialnumber", "{serial_number}"'
        vboxmanage_cmdline += ']'
        usbfilter['vboxmanagecommand'] = vboxmanage_cmdline
        self.usbdevices.append(usbfilter)

    def add_network_private(self, ip=None):
        """
        add an additional private network to the vm (optional with a fixed ip)

        :param ip: fixed ip, which will be used for the vm in the private network
        :return:
        """
        details = []
        if not ip:
            details.append({
                'key': 'type',
                'value': 'dhcp'
            })
        else:
            details.append({
                'key': 'ip',
                'value': ip
            })
        network = {
            'vgname': "private_network",
            'details': details
        }
        self.networks.append(network)

    def add_network_public(self, interface: str = None, ip: str = None) -> int:
        """

        :param interface:
        :param ip:
        :return:
        """
        if not interface and not ip:
            log.error('public network can just be added if either an interface or an ip is specified')
            return -1
        details = []
        if interface:
            details.append({
                'key': "bridge",
                'value': interface
            })
        if ip:
            details.append({
                'key': 'ip',
                'value': ip
            })
        network = {
            'vgname': "public_network",
            'details': details
        }
        self.networks.append(network)
        return 0

    def add_port_forwarding(self, port_host: int, port_guest: int):
        port_forwarding = {
            'host': port_host,
            'guest': port_guest
        }
        self.nat_port_forwarding.append(port_forwarding)

    def change_ssh_port(self, port_host: int):
        port_forwarding = {
            'host': port_host,
            'id': 'ssh'
        }
        self.nat_port_forwarding.append(port_forwarding)

    def add_synced_folder(self, path_on_host: Path, path_in_guest: Path):
        self.synced_folders.append(
            {
                'source': path_on_host.as_posix(),
                'destination': path_in_guest.as_posix()
            }
        )



class VagrantFile:
    """
    This class can be used to create a Vagrantfile successively.
    Therefore, various functions are provided in order to add provisioners, change vm settings, ...
    """
    jinja2: Environment = None
    options: dict
    machines: dict

    def __init__(self, vagrantfile_template: Path = VAGRANTFILE_TEMPLATE, options: dict = None):
        if not vagrantfile_template.is_file():
            raise VagrantFileCreationError(f'parsed path ({vagrantfile_template}) for Vagrantfile isn\'t existing')

        self.jinja2 = Environment(
            loader=FileSystemLoader(vagrantfile_template.parent),
            autoescape=select_autoescape()
        )
        self.machines = {}
        self.options = options or {}


    def add_machine(self, machine: VagrantMachine, order: int = -1):
        if order < 0:
            order = 0 if len(self.machines) == 0 else max(self.machines.keys()) + 1
        self.machines[order] = machine
        if 'machines' not in self.options.keys():
            self.options['machines'] = []


    def create_vagrant_file(self, destination: Path) -> int:
        """
        creates a vagrant file with all configurations stored in the class

        :param destination: file path of the Vagrantfile, that will be created
        """
        if destination.is_file():
            os.remove(destination.as_posix())
        if not destination.parent.is_dir():
            raise VagrantFileWriteError('chosen destination for Vagrantfile isn\'t valid')

        # loop through all machines and add them to the options based on their order
        for order in sorted(self.machines.keys()):
            self.options['machines'].append(self.machines[order].get_options())

        vagrantfile_template = self.jinja2.get_template("VagrantfileMultiMachine")

        with open(destination.as_posix(), mode="w") as f:
            f.write(
                vagrantfile_template.render(
                    self.options
                )
            )
        return 0

    def disable_virtualbox_guestautoupdate(self):
        """
        disable vagrant from doing auto updates for virtualbox guest additions

        :return:
        """
        self.options['vagrant_disable_vbguestautoupdate'] = True

    def enable_virtualbox_guestautoupdate(self):
        """
        enable vagrant from doing auto updates for virtualbox guest additions

        :return:
        """
        self.options['vagrant_disable_vbguestautoupdate'] = False
