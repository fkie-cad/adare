# ADARE Development Roadmap

This document tracks ongoing development tasks, planned features, quality of life improvements, known bugs for ADARE.

## Current Development Tasks
- [ ] check/build testfunctions
  - [ ] doe we have file_contains test method to test if file contains a certain string?
  - [ ] does filecontentequals works with pure regex? -> test
- [ ] update docs to acceptable amount!
- [ ] built remote platform to store VMs and test/improve download to not be done manually
- [ ] test if we can still run adare if we delete cloned repo
- [ ] add xml testfunctions in separate xml module
- [ ] support yaml with same logic/function as for json!

## Planned Features
- [ ] test and enable ydotool to make it work on wayland linux distros as well
- [ ] implement interactive experiment development
    - [ ] use nicegui to interactively test and create playbook and tests -> e.g. crop images extract icons ... 
- [ ] built a way to better validate playbooks (e.g. two variables with saame name through variables or save_timestamp ..., check that used variables are defined before, check if filters are correct)
- [ ] make all output available as csv/json/yaml
- [ ] enhance `adare vm test` with automatic platform detection and desktop environmadaent detection for platform-specific tests -> complexer than thought since we need database indendent experiment run with own stages and own flow console
- [ ] use proper directory for installation; maybe convert instllation from ps1,sh to python script to use platformdirs to get installation location; also use for database then later!
- [ ] build conditionlogic , wait until we find, retry logic for playbook
- [x] autocomplete for commands / abbreviations like env/exp
 
## Quality of Life Improvements
- [ ] update documentation
  - [ ] add sections about timezones -> since vm syncs with local time do not interfer -> when tool uses utc all good when tool uses localtime use | localtime filter!
  - [ ] add some info about the testfunctions in the different set and what variables are allowed in the different fields
  - [ ] keypress with special keys
  - [ ] expect_to_fail for tests
  - [ ] option to not stop on test failure
  - [ ] add automatic variables to docs
  - [ ] add info about default cores and ram for vm and how to set this 
  - [ ] svg are not supported for icons at the moment!
  - [ ] in installation add: eval "$(_ADARE_COMPLETE=zsh_source adare)" and tutorial how to enable autocomplete
- [ ] improve code quality in general
  - [ ] we use the username/password dummy when we with virtualbox do not need the commands ... -> find a better solution!
  - [ ] variable resolving uses regex to track resolved - can we do this without regex?
- [ ] improve logging at the moment too much is going on reduce and make log level clearer define what to store at which level
  - [ ] thereby replace claude logging details with different levels and be less noicy and clearer to see what went wrong? 
- [x] split windows and unix test methods and separate testfunction modules with their own requirements (clenaer+test more functionality ;)
- [ ] rethink testfunction result -> at the moment lists -> how is it saved in databse plain json? (then dicts would be better?)
- [x] add some automatic variables -> e.g. adare_user_home als automatische Variable, die im Playbook verwendet werden kann und zum entsprechenden Home-Verzeichnis auflöst 
- [ ] improve adare-mcp-server code quality; maybe tweak functionality
- [ ] reconsider if fake runs are deleted from database or kept until we wipe them manually

## Known Bugs
- [ ] on ctrl-c we see temporary two lines of the top line / relict from old implementation (-> remove); on interrupt top level total time stays there
- [ ] interrupt on verify does not work!
- [ ] somehow it does not work if test execution error is displayed same as test error this should not happen!
- [ ] adding/removing a pull does not trigger reload of experiment?! -> this means run do not work -> try to load on every run?!