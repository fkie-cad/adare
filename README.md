<img src="docsrc/source/logo.png" alt="Logo" width="150">

# ADARE

All relevant information can be found in the documentation. (`docs/html/index.html`)


### Todos
- [ ] built windows vm new from fresh installation
- [ ] built remote platform to store VMs and test/improve download to not be done manually

#### Features
- [ ] test and enable ydotool to make it work on wayland as well -> also would make machine setup easier as not X11 specific stuff needs to happen 
- [ ] make interactive experiment development
    - [ ] use nicegui to interactively test and create playbook and tests -> e.g. crop images extract icons ... 
- [ ] add filter to variables as timestamp to define timezone/format and tolerance


#### QOL
- [ ] update documentation
- [ ] make all output available as csv/json/yaml
- [ ] screenshot not via websockets but via shared files (to make faster?)
- [ ] add easier way to test updated/new testfunctions
- [ ] improve code quality in general
- [ ] improve logging at the moment too much is going on reduce and make log level clearer define what to store at which level

#### Bugs
- [ ] fix shared directory handling with snapshots; so what happens if we remove project and then create again with same vms .... At the moment we get an error.
- [ ] we can easily load testfunction and change while we already run an experiment -> fix that to be not possible to preserve integrity; general workflow for update those seems a little broken


#### Test
- [ ] built more and working unit tests (maybe with claude)
