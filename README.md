<img src="docsrc/source/logo.png" alt="Logo" width="150">

# ADARE

All relevant information can be found in the documentation. (`docs/html/index.html`)


### Todos

#### Features
- [ ] load from existing vm / only create new snapshot to save time and space!
- [ ] recover file from 
- [ ] make interactive test development
    - [ ] some way to skip after installation; and then do something? 
    - [ ] replay? so let user click and we create playbook

#### Output
- [ ] Show experimen run flow in show run display (maybe extendable)
- [ ] make duration dynamic for run. Store the durations in database as before and display for the classic run display


#### Bugs
- [ ] ctrl-c during loading results in vm potentially created later (track vm names -> check on next start and remove old ones)
- [ ] crtl-c locks at the moment
- [ ] unclear if flow shows fails -> test