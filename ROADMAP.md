# ADARE Development Roadmap  

This document tracks ongoing development tasks, planned features, quality-of-life improvements, known bugs, and areas requiring additional testing for **ADARE**.  

---

## ✅ Current Development Tasks  
- [x] Provide all output in JSON/YML format for automation (toggle via flag to use this as stdout (logging errors+warnings in json; or save to file)  -> need to be tested more first way is implemented

---

## 🚀 Planned Features
- [x] Add support for preinstalled agent to make especially windows development faster? -> needs to be tested!
- [ ] perform actions with virtualbox SDK and get screenshots from video stream directly!
- [ ] add datasets that are downloaded to an project and retrieved from an URL (e.g. hosted by us in minio instance)
- [ ] add no_idle action to disable the default idle (e.g. when wanting to save a timestamp) -> or better only idle between gui actions
- [ ] experiment run by glob (does not work as load does not work by glob)
- [ ] Add support for Wayland-based Linux systems  
  - [ ] Validate if `ydotool` is suitable and reliable -> if yes make sure to coply to AGPLv3 
    - [ ] it is suitable but we need to develop some python bindings; build as indepedent package to be usable later similar to pyautogui! -> or wait until pyautogui supports wayland via ydotool (existing pr since 20.09.2025)
- [ ] Replace `pyautogui.screenshot` as default screenshot in linux vms with `maim` for improved stability (`grim` for wayland)
- [ ] Implement interactive experiment development tools  
  - [ ] Idea: Use **NiceGUI** for web-based interactive playbook and test creation (e.g., cropping images, extracting icons)  
- [ ] Enhance `adare vm test` with automatic platform and desktop environment detection  
- [ ] Use standardized installation directory (via `platformdirs`) and migrate installer scripts to Python  
- [ ] Implement watchers that if gui find failed searches for specific things (e.g. remove popup) and then tries again
- [ ] Extend `expect_to_fail` with `expect_to_fail_on: ExceptionType` (specific exception handling)  
- [ ] Improve ULID handling in CLI → allow lookup by unique partial combinations  
- [ ] Allow metadata descriptions in test function sets  
- [ ] Add new test function sets:  
  - [ ] YAML  
- [ ] integrated log viewer with `adare run log adare ULID` or `adare run log adarevm` that we can view logs but also filter them!
- [ ] more advanced wait_until logic -> use image diffs to identify changed areas?! Only search in changed ares?! -> analyze if this works or is too complex?!
- [ ] wait_until not search twice but remeber the action and execute it then directly?!
- [ ] add option --custom-testfunction PATH_TO_DIR; which is then used instead of the existing one (even if same name) -> not copied only used; this will help developing testfunctions!
- [ ] lets us save results in variables we use later again?! 
- [ ] document (potentially implment variable feature to write/overwrite variables in playbook dynamically)
- [ ] diff feature documentation; also test for windows with mft parsing
- [ ] glob dokumentieren
- [ ] Anaylze how we can make project wide shared data work with online experiment download? We therefore need references to data that needs to be downloaded in experiment directory!
- [ ] support for python3.14
- [ ] rethink environments; why not let an experiment run in any environment and just provide an warning if not in the environments; update environments in database from file every time we do any experiment run oder env load command!
- [ ] check if we need to place building wheel into a single stage showing? I think yes!
- [ ] adjust our tool be Model View Controller for frontend and terminal support later
 
---

## 🛠 Quality of Life Improvements  
- [ ] Expand documentation:  
  - [ ] update VM creation with prev. installation for speedup 
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

---

## 🧹 Code Quality  
- [ ] Rethink test function results: currently lists → should be dictionaries for better JSON/database handling  
- [ ] backend/experiment has way to many files. Try to structure the overall software better!
- [ ] We have custom exceptions? are these clever named and used? should we have more? (general question: Exception vs Return False/None)
- [ ] Refactor `detect_xsession` to use existing system commands with proper parameterization  
- [ ] Consider lazy loading of modules at least for certain libraries -> improve speed
- [ ] Think about the access pattern to both database. Can we simplify/improve this?
- [ ] we validate on experiment load against files and analyze it would be faster and better to validate against database
- [ ] remove all kind of emojis/icons from logging messages. ✅🆕
- [ ] in some terminal files we use directly database and do queries. Should we not provide this through an API that provides the data? What is better code quality?
- [ ] add tests for modular code parts; make code more modular where required!
- [ ] background commands in vm (as installation); when to check for results (move to separate thread?)
- [ ] address: DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. 
- [ ] command line seems slow responsive; improve

---

## 🐞 Known Bugs  
- [ ] Visual bug: On `Ctrl-C`, duplicate top-line output appears (legacy artifact)  
- [ ] Visual bug: Flow console occasionally shows three red dots at the bottom → cause unknown  
- [ ] Visual bug: last stage spinner ("Stopping computer vision server") briefly disappears before finishing  
- [ ] Visual bug: flow console at some points was stuck and then suddenly completly finished?
- [ ] adare exp list gives error

---

## 🔍 Areas Needing More Testing  
- [ ] Verify if ADARE runs without the cloned repository  
- [ ] Test if VM download via URL in environment works 
- [ ] Test if environment with zenodo url works!
- [ ] Test if auto_pull_on_test_failure works!
- [ ] Test how settings idle work
- [ ] Test that json output works fine for all commands 
- [ ] Test clone feature
- [ ] Visual tests
