<img src="docsrc/source/logo.png" alt="Logo" width="150">

# ADARE

All relevant information can be found in the documentation. (`docs/html/index.html`)


### Todos

#### Features
- [x] load from existing vm / only create new snapshot to save time and space! 
- [x] add command line option to not remove snapshot after run
- [x] add command line option/command to clean up certain VMs still there (either all or by environment)
- [ ] for adare show run implement a filter mechanism to search for at least environments, experiments (and combo with donotation?)
- [x] recover file from playbook
- [ ] make interactive test development
    - [ ] some way to skip after installation; and then do something? 
    - [ ] replay? so let user click and we create playbook
- [ ] add way to delete all vms at once? make with additonal requestto user to agree

#### Output
- [x] Show experiment run flow in show run display (maybe extendable)
- [x] make duration dynamic for run. Store the durations in database as before and display for the classic run display
- [ ] improve stages (at the moment to unclear / maybe to many?! -> combine typical short ones)
- [ ] restructure command like args maybe do not have show but instead incooporate it smoothly? 

#### QOL
- [ ] make general output for filterable/specificable (e.g. delete all snapshots for one vm with one command)

#### Bugs
- [ ] always run on base snapshot and create one after the experiment run not before (if specific option is set)
- [ ] adare show run shows pending for interrupted run
- [ ] ligntning does not show for interrupted run?!
- [ ] ctrl-c during loading results in vm potentially created later (track vm names -> check on next start and remove old ones)
- [ ] unclear if flow shows fails -> test
- [ ] with preserve snapshot we do snapshot before the run not after (also for run do it after even after fail!)
- [ ] update tui