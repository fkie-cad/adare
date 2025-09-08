Create Your Custom ADARE VM
***************************

Setting up a VirtualBox VM compatible with ADARE can be done in just a few steps.
It make sense to create a new VM in one of two cases: 1. None of the provided VMs has the operating system/distribution you need, or 2. You need specific software that takes a while to installing-with-the-official-installer
You therefore can either create a new VM from scratch or adapt an existing one, as long as the requirements below are met. 
Once configured, export the VM as an ``.ova`` or ``.ovf`` file in **OVF 1.0 format**.

Windows Setup
=============

User Account Configuration
--------------------------

- Create a user account with:

  - **Username:** ``adare``
  - **Password:** ``adare``

- Enable **autologin** so the VM boots directly into the ``adare`` user's desktop.

Security Configuration
----------------------

1. **Disable User Account Control (UAC):**

   - Go to Control Panel → ``User Accounts`` → ``User Accounts`` → ``Change User Account Control settings``
   - Set the slider to the bottom (``Never notify``)

2. **Enable Developer Mode:**

   - In Windows Settings, search for ``For Developers``
   - Toggle the switch to enable Developer Mode
   - This is required to set up shared directories properly

3. **Configure Windows Defender Firewall:**

   a. Press ``Win + R``, type ``wf.msc``, and press Enter
   
   b. In the left panel, right-click **Windows Defender Firewall with Advanced Security on Local Computer** → **Properties**
   
   c. For each profile tab (**Domain Profile**, **Private Profile**, and **Public Profile**), configure:
   
      - **Inbound connections:** Allow
      - **Outbound connections:** Allow (default)
   
   d. Click **OK**

4. **Apply Changes:**

   - Perform a clean shutdown to apply all security changes

Required Software Installation
-----------------------------

Install the following software:

- **Python 3.10 or newer**
- **Poetry** (`Installation Guide <https://python-poetry.org/docs/#installing-with-the-official-installer>`_)
- **VirtualBox Guest Additions**
  

Linux Setup
===========

Base Configuration (all environments)
-------------------------------------

- Create a user account with:

  - **Username:** ``adare``
  - **Password:** ``adare``

- Enable **autologin** so the VM boots directly into the ``adare`` user’s desktop.

  - **Important:** autologin must start an **X11 session** (not Wayland).

- Install:

  - Python 3.10 or newer
  - `Poetry <https://python-poetry.org/docs/#installing-with-the-official-installer>`_
  - VirtualBox Guest Additions
  - ``python3-tk``
  - ``python3-dev``


Desktop Environment–Specific Setup
----------------------------------

GNOME
~~~~~

- Install:

  - ``gnome-screenshot``

- Configure Seahorse (keyring) to unlock automatically on login by setting an empty password.


Other Desktop Environments
~~~~~~~~~~~~~~~~~~~~~~~~~~

- Not tested so far. Confirm PyAutoGUI can make screenshots and control the mouse and keyboard.

