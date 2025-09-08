<img src="docsrc/source/logo.png" alt="Logo" width="150">

# ADARE

All relevant information can be found in the documentation. (`docs/html/index.html`)


### Todos
- [ ] built windows vm new from fresh installation -> done; test it
- [ ] built remote platform to store VMs and test/improve download to not be done manually
- [x] built furhter testfunction; and filters/variables 
- [ ] built tests/test experiments for new testfunctions
- [ ] check if we can easily add new testfunctionsets? 
- [x] clear distinction between failed test and exception/error -> find a way to propagate to the client!
- [ ] test if we can still run adare if we delete cloned repo
- [ ] vm is copied to project or? then we can also make it write protected?

#### Features
- [ ] test and enable ydotool to make it work on wayland as well -> also would make machine setup easier as not X11 specific stuff needs to happen 
- [ ] implement interactive experiment development
    - [ ] use nicegui to interactively test and create playbook and tests -> e.g. crop images extract icons ... 
- [x] add filter to variables as timestamp to define timezone/format and tolerance
- [ ] install requirements of testfunctions if given into poetry somehow!
- [x] make in experiment run total time at top in a row!
- [ ] built a way to better validate playbooks (e.g. two variables with saame name through variables or save_timestamp ..., check that used variables are defined before, check if filters are correct)


#### QOL
- [ ] update documentation
- [ ] make all output available as csv/json/yaml
- [ ] screenshot not via websockets but via shared files (to make faster?)
- [ ] add easier way to updated/test new testfunctions
- [ ] improve code quality in general
  - [x] split virtualbox api into multiple files
- [ ] improve logging at the moment too much is going on reduce and make log level clearer define what to store at which level
- [x] Final short experiment finished message with overall result (exception/error vs none) and test result (if all tests succeded)and ULID
- [ ] we use the username/password dummy when we with virtualbox do not need the commands ... -> find a better solution!
- [ ] vm file integrity takes a long time -> any better ideas? -> maybe exchange for filesize -> maybe keep due to snapshot we only do it once!

#### Bugs
- [x] fix shared directory handling with snapshots; so what happens if we remove project and then create again with same vms .... At the moment we get an error.
- [x] fix port forwarding if already there check if identical and if yes then do nothing! -> at the moment logs shows an error
- [x] we can easily load testfunction and change while we already run an experiment -> fix that to be not possible to preserve integrity; general workflow for update those seems a little broken
- [x] we copy adarevm into project dir?! but we use it from appdata so we may not do this?!
- [ ] on ctrl-c we see temporary two lines of the top line / relict from old implementation (-> remove); on interrupt top level total time stays there
- [ ] if over 1m we have two opening brackets ((2m ... 
- [ ] vm file integrity does not seem to work!

#### Test
- [ ] built more unit tests / integration tests / ... (maybe with claude)


### Issue when checking filecontent with two resolved timestamps/other vars after another!
  Case 1 - Normal delimiters:
  Template: "User {{ USERNAME }} logged at {{ TIMESTAMP }}"
  Parts: ["User ", " logged at ", ""]
  ✅ Clear delimiters: " logged at "

  Case 2 - Empty delimiter:
  Template: "{{ USERNAME }}{{ TIMESTAMP }}"
  Parts: ["", "", ""]
  ❌ No delimiters to separate the placeholders!
