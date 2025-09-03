<img src="docsrc/source/logo.png" alt="Logo" width="150">

# ADARE

All relevant information can be found in the documentation. (`docs/html/index.html`)


### Todos
- [ ] built windows vm new from fresh installation

#### Features
- [ ] test and enable ydotool to make it work on wayland as well -> also would make machine setup easier as not X11 specific stuff needs to happen 

#### Output
- [x] Show experiment run flow in show run display (maybe extendable)
- [x] make duration dynamic for run. Store the durations in database as before and display for the classic run display
- [x] improve stages (at the moment to unclear / maybe to many?! -> combine typical short ones)
- [x] restructure command like args maybe do not have show but instead incooporate it smoothly? 
- [ ] make interactive experiment development
    - [ ] use nicegui to interactively test and create playbook and tests -> e.g. crop images extract icons ... 

#### QOL
- [ ] update documentation drastically
- [ ] add all output available as json or csv? 
- [ ] screenshot not via websockets but via shared files (to improve speed)

#### Bugs
- [x] always run on base snapshot and create one after the experiment run not before (if specific option is set) -> test -> no snapshot saved?!
- [x] adare show run shows pending for interrupted run
- [x] ligntning does not show for interrupted run?!
- [x] if one tests fails and not all tests are run we see wrong result for adare run list and tests panel for adare run info
- [ ] unclear if flow shows fails -> test
- [ ] somehow environment got deleted after adare manage reset-vm -> test more
- [ ] allow .yml and .yaml for input files (playbook, testset, ...)
- [ ] fix shared directory handling with snapshots

#### Test
- [ ] all frontend terminal commands
- [ ] download of ova! -> find location where to upload machines? 
- [ ] built test suite to test if vm is ready and can be used to avoid errors!