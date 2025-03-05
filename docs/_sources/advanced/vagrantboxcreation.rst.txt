Create your own Adare Box
****************************

Creating a own vagrant box compatible with Adare can be done by first creating a vagrant box and then run provided setup scripts dependent on the OS.
The easiest way is to first find a base box on `Vagrant Cloud <https://app.vagrantup.com/boxes/search>`_ and then apply the following steps.
Alternatively a box can be created from scratch as described in the `Vagrant documentation <https://www.vagrantup.com/docs/boxes/base.html>`_.

1. Start by creating a new vagrant box with the following command:

.. code-block:: bash

	vagrant init <box-name>
	vaagrant up


2. Access the box by either the gui or ssh (`vagrant ssh`)

3. Run the setup script for the OS you are using. The setup scripts can be found in the Github.

4. Once the setup script has been run, the box can be packaged:

.. code-block:: bash

	vagrant package --output <box-name>.box

5. Now the box can be added to vagrant and is ready to be used with Adare:

.. code-block:: bash

	vagrant box add <box-name> <box-name>.box

6. If you want to share the box upload it to Vagrant Cloud. Therefore refer to the `Vagrant Cloud documentation <https://www.vagrantup.com/docs/vagrant-cloud/boxes/create.html>`_.
