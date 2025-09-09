<img src="docsrc/source/logo.png" alt="Logo" width="150">

# ADARE

All relevant information can be found in the documentation. (`docs/html/index.html`)


### Todos
- [x] built windows vm new from fresh installation -> done; test it
- [ ] built remote platform to store VMs and test/improve download to not be done manually
- [x] built furhter testfunction; and filters/variables 
- [ ] built tests/test experiments for new testfunctions
- [ ] check if we can easily add new testfunctionsets? 
- [ ] test if we can still run adare if we delete cloned repo

#### Features
- [ ] test and enable ydotool to make it work on wayland as well -> also would make machine setup easier as not X11 specific stuff needs to happen 
- [ ] implement interactive experiment development
    - [ ] use nicegui to interactively test and create playbook and tests -> e.g. crop images extract icons ... 
- [ ] install requirements of testfunctions if given into poetry somehow!
- [ ] built a way to better validate playbooks (e.g. two variables with saame name through variables or save_timestamp ..., check that used variables are defined before, check if filters are correct)


#### QOL
- [ ] update documentation
- [ ] make all output available as csv/json/yaml
- [ ] screenshot not via websockets but via shared files (to make faster?)
- [ ] add easier way to updated/test new testfunctions
- [ ] improve code quality in general
  - [x] split virtualbox api into multiple files
  - [ ] we use the username/password dummy when we with virtualbox do not need the commands ... -> find a better solution!
  - [ ] split resolving variables logic from playbook controller!
- [ ] improve logging at the moment too much is going on reduce and make log level clearer define what to store at which level
- [ ] built in the testfunction methods variables info what variable tyes are allwoed 
- [ ] split windows and unix test methods and separate testfunction modules with their own requirements (clenaer+test more functionality ;))
- [ ] add option like --runlog that saves a runlog in the logs directory! 
- [ ] let a user run multiple exepriments -> requires more advanced snapshot handling -> so vm needs to uploaded 

#### Bugs
- [ ] on ctrl-c we see temporary two lines of the top line / relict from old implementation (-> remove); on interrupt top level total time stays there
- [ ] vm files are not write protected in project directory
- [x] no new vm create when we create new project still reuse the old one!

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
