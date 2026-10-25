"""Host resources: what the machine has, what ADARE's VMs use, and how many more fit.

- :mod:`.host` -- live CPU/RAM/disk and the QEMU processes running on the host
- :mod:`.storage` -- where the disk space under the ADARE state directories goes
- :mod:`.run_monitor` -- measures one experiment run's VM while it runs
- :mod:`.history` -- periodic host samples for the usage charts
- :mod:`.capacity` -- how many more runs of each environment the host can take
"""
