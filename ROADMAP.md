# ADARE Development Roadmap  

This document tracks ongoing development tasks, planned features, quality-of-life improvements, known bugs, and areas requiring additional testing for **ADARE**.  

---

## ✅ Current Development Tasks  
- [x] Provide all output in JSON/YML format for automation (toggle via flag to use this as stdout (logging errors+warnings in json; or save to file)  -> need to be tested more first way is implemented

---

## 🚀 Planned Features
- [ ] make test mode default and --reproducible or other flag for those that are fixed and be used later
- [ ] add clone to clone already existing experiment  
- [ ] add datasets that are downloaded to an project and retrieved from an URL (e.g. hosted by us in minio instance)
- [ ] add no_idle action to disable the default idle (e.g. when wanting to save a timestamp) -> or better only idle between gui actions
- [ ] experiment run by glob (does not work as load does not work by glob)
- [x] add a wait_until action that wait until a specific icon/text occurs? (also with timeout parameter/chedcking itnerval) -> how to design it in a way we not make more screenshots than be able to check it as checking takes some time?! -> test
- [x] add settings (default true) that in case of an failed test pulls all files mentioned in the playbook
- [ ] Add support for Wayland-based Linux systems  
  - [ ] Validate if `ydotool` is suitable and reliable -> if yes make sure to coply to AGPLv3 
    - [ ] it is suitable but we need to develop some python bindings; build as indepedent package to be usable later similar to pyautogui! -> or wait until pyautogui supports wayland via ydotool (existing pr since 20.09.2025)
- [ ] Replace `pyautogui.screenshot` as default screenshot in linux vms with `maim` for improved stability (`grim` for wayland)
- [ ] Implement interactive experiment development tools  
  - [ ] Idea: Use **NiceGUI** for web-based interactive playbook and test creation (e.g., cropping images, extracting icons)  
- [ ] Add playbook variable validation:  
  - [ ] Prevent duplicate variable names  
  - [ ] Ensure all variables are defined before use  
  - [ ] Validate filter correctness  
- [ ] Enhance `adare vm test` with automatic platform and desktop environment detection  
- [ ] Use standardized installation directory (via `platformdirs`) and migrate installer scripts to Python  
- [ ] Implement condition/wait/retry logic in playbooks  
- [ ] Implement watchers that if gui find failed searches for specific things (e.g. remove popup) and then tries again
- [ ] Extend `expect_to_fail` with `expect_to_fail_on: ExceptionType` (specific exception handling)  
- [ ] Improve ULID handling in CLI → allow lookup by unique partial combinations  
- [ ] Allow metadata descriptions in test function sets  
- [ ] Add new test function sets:  
  - [ ] YAML  
- [ ] integrated log viewer with `adare run log adare ULID` or `adare run log adarevm` that we can view logs but also filter them!
- [ ] more advanced wait_until logic -> use image diffs to identify changed areas?! Only search in changed ares?! -> analyze if this works or is too complex?!
- [ ] add option --custom-testfunction PATH_TO_DIR; which is then used instead of the existing one (even if same name) -> not copied only used; this will help developing testfunctions!
- [ ] make adarevm installable via setuptools to allow for older python versions to also allow for older distros as Ubuntu 18.04, 16.04, ... ...
- [ ] visual tests

---

## 🛠 Quality of Life Improvements  
- [ ] Expand documentation:  
  - [ ] Timezone handling (VM syncs with local time vs. UTC)  
  - [ ] Experiment development guide (pause, idle, tips)  
  - [ ] Default VM resources (cores, RAM) and how to configure them  
  - [ ] Current limitation: SVG icons not supported  
  - [ ] Installation guide → add `eval "$(_ADARE_COMPLETE=zsh_source adare)"` and autocomplete tutorial 
  - [ ] add info that we can only run one experiment inside a specific vm/env if not in a separate project 
- [ ] Simplify and clarify logging:  
  - [ ] Define logging levels more clearly  
  - [ ] Replace excessive debug logging with structured log levels  
  - [ ] Make errors more readable and actionable
  - [ ] Remove Claude: log messages
- [ ] Improve the possible solutions on Exceptions to be correct and provide only working options!
- [ ] in help we see for alias the command doubled? can we only see e.g. list (l) and remove (rm) or somehting similar? 

---

## 🧹 Code Quality  
- [ ] Rethink test function results: currently lists → should be dictionaries for better JSON/database handling  
- [ ] We have custom exceptions? are these clever named and used? should we have more? (general question: Exception vs Return False/None)
- [ ] Refactor `detect_xsession` to use existing system commands with proper parameterization  
- [ ] Consider lazy loading of modules at least for certain libraries -> improve speed
- [ ] Think about the access pattern to both database. Can we simplify/improve this?
- [ ] as a lot of database need the project directory find a way to not give it as parameter but instead retrieve it everytime of find a better clever mechanism to keep the code clean
- [ ] we validate on experiment load against files and analyze it would be faster and better to validate against database
- [ ] we should load playbook into database on load already not only on exeuction or? we then run from database and not file?!
- [ ] remove all kind of icons from logging messages. ✅🆕
- [ ] in some terminal files we use directly database and do queries. Should we not provide this through an API that provides the data? What is better code quality?

---

## 🐞 Known Bugs  
- [ ] Visual bug: On `Ctrl-C`, duplicate top-line output appears (legacy artifact)  
- [ ] Visual bug: Flow console occasionally shows three red dots at the bottom → cause unknown  
- [ ] Visual bug: last stage spinner ("Stopping computer vision server") briefly disappears before finishing  
- [ ] Visual bug: flow console at some points was stuck and then suddenly completly finished?
- [ ] commands can be lists and this gives some weird results! recognize on parsing and give error already on loading if possible
- [ ] multiple project shared directory and vm?! should not happen -> clear separation for multiple projects not happening also not in testfunction sets -> maybe database per project?! 
- [ ] even if vm does not exist the env is added to envs with "no vm"
- [ ] if dir exists exp load is weird and first deletes the directory but tells the directrory does already exist so load does not work? and then we can run it again it 

---

## 🔍 Areas Needing More Testing  
- [ ] Verify if ADARE runs without the cloned repository  
- [ ] Test if VM download via URL in environment works 
- [ ] Test if environment with zenodo url works!
- [ ] Test if auto_pull_on_test_failure works!
- [ ] Test how settings idle work
- [ ] Test that json output works fine for all commands 
