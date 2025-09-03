Create Your Custom ADARE VM
***************************

Setting up a VirtualBox VM compatible with ADARE can be done in just a few steps. 
You can either create a new VM from scratch or adapt an existing one, as long as the 
minimal requirements are met. Once configured, export the VM as an ``.ova`` or ``.ovf`` 
file in **OVF 1.0 format**.

Minimal VM Setup for ADARE
==========================

Inside the VM, ensure the following configuration:

- Create a user account with:

  - **Username:** ``adare``
  - **Password:** ``adare``

- Enable **autologin** so the VM boots directly into the ``adare`` user’s desktop.

  - For Linux: autologin must start an **X11 session** (not Wayland).

- Install:

  - Python 3.10 or newer
  - `Poetry <https://python-poetry.org/docs/#installing-with-the-official-installer>`_
  - VirtualBox Guest Additions
  - ``python3-tk``, ``python3-dev``
  - ``gnome-screenshot`` (if using GNOME)

- Disable the system keyring or configure it to allow empty passwords.

Optional Additions
==================

You may install additional software or dependencies you frequently use in experiments. 
This prevents long setup times every time an experiment is executed.

Notes for Existing VMs
======================

If you’re building the ADARE VM from an existing Linux VM:

- Remove the ``/adare`` path (ADARE uses this path la