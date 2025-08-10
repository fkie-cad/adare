<img src="docsrc/source/logo.png" alt="Logo" width="150">

# ADARE

All relevant information can be found in the documentation. (`docs/html/index.html`)


### Todos

#### Features
- [x] load from existing vm / only create new snapshot to save time and space! 
- [x] add command line option to not remove snapshot after run
- [x] add command line option/command to clean up certain VMs still there (either all or by environment)
- [x] for adare show run implement a filter mechanism to search for at least environments, experiments (and combo with donotation?)
- [x] recover file from playbook
- [ ] make interactive test development
    - [ ] some way to skip after installation; and then do something? 
    - [ ] replay? so let user click and we create playbook
- [x] add way to delete all vms at once? make with additonal requestto user to agree
- [x] add way to download ova/ovf directly on first use!
- [ ] built tests

#### Output
- [x] Show experiment run flow in show run display (maybe extendable)
- [x] make duration dynamic for run. Store the durations in database as before and display for the classic run display
- [x] improve stages (at the moment to unclear / maybe to many?! -> combine typical short ones)
- [x] restructure command like args maybe do not have show but instead incooporate it smoothly? 

#### QOL
- [ ] update documentation drastically
    - [x] update Installation guide
    - [x] update About Adare
    - [ ] the rest
- [ ] look for dead/deprecated code and remove

#### Bugs
- [x] always run on base snapshot and create one after the experiment run not before (if specific option is set) -> test -> no snapshot saved?!
- [x] adare show run shows pending for interrupted run
- [x] ligntning does not show for interrupted run?!
- [ ] unclear if flow shows fails -> test
- [ ] somehow environment got deleted after adare manage reset-vm -> test more
- [ ] remove vm_type or change to auto to auto detect


#### Test
- [ ] all frontend terminal commands
- [ ] download of ova! -> find location where to upload machines? 