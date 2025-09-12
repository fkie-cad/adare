# ADARE Development Roadmap

This document tracks ongoing development tasks, planned features, quality of life improvements, known bugs for ADARE.

## Current Development Tasks
- [ ] built remote platform to store VMs and test/improve download to not be done manually
- [x] built tests/test experiments for new testfunctions
- [ ] test if we can still run adare if we delete cloned repo

## Planned Features
- [ ] test and enable ydotool to make it work on wayland linux distros as well
- [ ] implement interactive experiment development
    - [ ] use nicegui to interactively test and create playbook and tests -> e.g. crop images extract icons ... 
- [ ] built a way to better validate playbooks (e.g. two variables with saame name through variables or save_timestamp ..., check that used variables are defined before, check if filters are correct)
- [ ] make all output available as csv/json/yaml
- [ ] enhance `adare vm test` with automatic platform detection and desktop environment detection for platform-specific tests -> complexer than thought since we need database indendent experiment run with own stages and own flow console
- [x] add expect_to_fail field for tests to be successfuly if test failed and vice versa! Important an error outside the test stays an error/expcetion! We should only reverse this for the test result! -> add to docs
- [ ] use proper directory for installation; maybe convert instllation from ps1,sh to python script to use platformdirs to get installation location; also use for database then later!

## Quality of Life Improvements
- [ ] update documentation
  - [ ] add sections about timezones -> since vm syncs with local time do not interfer -> when tool uses utc all good when tool uses localtime use | localtime filter!
  - [ ] add some info about the testfunctions in the different set and what variables are allowed in the different fields
- [ ] screenshot not via websockets but via shared files (to make faster?)
- [ ] add easier way to updated/test new testfunctions
- [ ] improve code quality in general
  - [ ] we use the username/password dummy when we with virtualbox do not need the commands ... -> find a better solution!
  - [ ] variable resolving uses regex to track resolved - can we do this without regex?
- [ ] improve logging at the moment too much is going on reduce and make log level clearer define what to store at which level
- [x] split windows and unix test methods and separate testfunction modules with their own requirements (clenaer+test more functionality ;)
- [ ] rethink testfunction result -> at the moment lists -> how is it saved in databse plain json? (then dicts would be better?)
- [x] add some automatic variables -> e.g. adare_user_home als automatische Variable, die im Playbook verwendet werden kann und zum entsprechenden Home-Verzeichnis auflöst -> add to docs
- [ ] does svg as icons in playbook work? 

## Known Bugs
- [ ] on ctrl-c we see temporary two lines of the top line / relict from old implementation (-> remove); on interrupt top level total time stays there
- [ ] real testunfction error (so no failed test) are not displayed properly in flowconsole but markes as failed test
- [ ] by default on run no specific log is saved to adare run log dir if not --logfile is set as well?! -> test if fixed?!
- [x] look into timezone+localtime if this all really works like expetected together with tolerance filter -> so timestamp/timezone do not work really well -> we did some localtime resolving on adarevm/maybe also adjust for timezone
- [x] default ram for linux box 4gb and windows box 8gb. Custom set during experiment run or? -> add to docs
- [x] check if its possible that vm path in environment is relative to project directory -> add to docs
- [ ] keypress with special keys e.g. windows key? -> add to docs
- [ ] does resetting to base snapshot work at beginning of experiment?! seems like it does not!
- [x] --debug-screenshots does not work together so no screenshots get created?