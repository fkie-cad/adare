# ADARE Development Roadmap

This document tracks ongoing development tasks, planned features, quality of life improvements, known bugs for ADARE.


## Current Development Tasks
- [x] check/build testfunctions -> test all tests and check if it all works
- [ ] make adare experiment run ... without env run all experiments in that env after another. Lets at the end add some summary telling what succeded which failed.
- [x] update docs to acceptable amount!
- [ ] make cli einheitlicher rm/remove instead of delete ... 
- [ ] built remote platform to store VMs and test/improve download to not be done manually
- [ ] test if we can still run adare if we delete cloned repo
- [x] add xml testfunctions in separate xml module
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
- [ ] not only expect_to_fail, but also a expect_to_fail_on: ExceptionType (-> so catch specific Exception either custom written or existing as FileNotFoundError)
- [ ] how to add an environment to an experiment after it exists?! 
- [ ] multiple runs for all environments when we call adare experiment run ... without environment specified -< print summary at the end!
- [ ] some kind of dev mode (simple first idea execute till interactive action -> we stop there an only continue on keypress)
- [ ] for all things where we need ulid lets find by unique combo already!
- [ ] add metadata to testfunction sets to let a user add description
- [ ] make own stage for dependency installation of testfunctions this can take a while!
 
## Quality of Life Improvements
- [ ] update documentation
  - [ ] add sections about timezones -> since vm syncs with local time do not interfer -> when tool uses utc all good when tool uses localtime use | localtime filter!
  - [ ] add some tutorial how to develop an experiment or some tipps:
    - [ ] pause; idles; ...
  - [ ] add info about default cores and ram for vm and how to set this 
  - [ ] svg are not supported for icons at the moment!
  - [ ] in installation add: eval "$(_ADARE_COMPLETE=zsh_source adare)" and tutorial how to enable autocomplete
- [ ] improve code quality in general
  - [ ] we at many places catch generic Exception - lets not do it but catch more specific exceptions
  - [ ] improve detect_xession to use exsiting commands command -> to avoid recusrsion sey via parameter if command is done in user x11 session
- [ ] improve logging at the moment too much is going on reduce and make log level clearer define what to store at which level
  - [ ] thereby replace claude logging details with different levels and be less noicy and clearer to see what went wrong? 
- [x] split windows and unix test methods and separate testfunction modules with their own requirements (clenaer+test more functionality ;)
- [ ] rethink testfunction result -> at the moment lists -> how is it saved in databse plain json? (then dicts would be better?)
- [x] add some automatic variables -> e.g. adare_user_home als automatische Variable, die im Playbook verwendet werden kann und zum entsprechenden Home-Verzeichnis auflöst 
- [x] improve adare-cv-server code quality; maybe tweak functionality
- [x] reconsider if fake runs are deleted from database or kept until we wipe them manually -> no do not delete them only if we all adare experiment clean "name" -> delete all fake runs

## Known Bugs
- [ ] on ctrl-c we see temporary two lines of the top line / relict from old implementation (-> remove); on interrupt top level total time stays there
- [ ] interrupt on verify does not work!
- [ ] adding/removing a pull does not trigger reload of experiment?! -> this means run do not work -> try to load on every run
- [ ] visual bug on flow console for last stages where Stopping computer vision server spinner occurs for very vers short and text and spinnger dissapera and then it apperas when its done with green dot?! why does it disappear in the middle?! does not make much sense? -> most likely weird timing issues?!