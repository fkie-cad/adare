# ADARE Development Roadmap

This document tracks ongoing development tasks, planned features, quality of life improvements, known bugs, and testing initiatives for ADARE.

## Current Development Tasks

- [x] built windows vm new from fresh installation -> done; test it
- [ ] built remote platform to store VMs and test/improve download to not be done manually
- [x] built furhter testfunction; and filters/variables 
- [ ] built tests/test experiments for new testfunctions
- [ ] check if we can easily add new testfunctionsets? 
- [ ] test if we can still run adare if we delete cloned repo
- [ ] test if we can run dev experiments that allow for easy change of experiments for testing -> we then need to make the experiment.yml not write-protected?!

## Planned Features
- [ ] test and enable ydotool to make it work on wayland linux distros as well
- [ ] implement interactive experiment development
    - [ ] use nicegui to interactively test and create playbook and tests -> e.g. crop images extract icons ... 
- [ ] built a way to better validate playbooks (e.g. two variables with saame name through variables or save_timestamp ..., check that used variables are defined before, check if filters are correct)
- [ ] make all output available as csv/json/yaml

## Quality of Life Improvements
- [ ] update documentation
  - [ ] add sections about timezones -> since vm syncs with local time do not interfer -> when tool uses utc all good when tool uses localtime use | localtime filter!
- [ ] screenshot not via websockets but via shared files (to make faster?)
- [ ] add easier way to updated/test new testfunctions
- [ ] improve code quality in general
  - [ ] we use the username/password dummy when we with virtualbox do not need the commands ... -> find a better solution!
  - [ ] variable resolving uses regex to track resolved - can we do this without regex?
- [ ] improve logging at the moment too much is going on reduce and make log level clearer define what to store at which level
- [ ] built in the testfunction methods variables info what variable tyes are allwoed 
- [ ] split windows and unix test methods and separate testfunction modules with their own requirements (clenaer+test more functionality ;)
- [ ] let a user run multiple exepriments -> requires more advanced snapshot handling -> so vm needs to uploaded 
- [ ] rethink testfunction result -> at the moment lists -> how is it saved in databse plain json? (then dicts would be better?)

## Known Bugs
- [ ] on ctrl-c we see temporary two lines of the top line / relict from old implementation (-> remove); on interrupt top level total time stays there
- [ ] vm files are not write protected in project directory
- [ ] requirements of testfunction are not installed within adarevm
- [ ] real testunfction error (so no failed test) are not displayed properly in flowconsole but markes as failed test
- [ ] by default on run no specific log is saved to adare run log dir if not --logfile is set as well?!
