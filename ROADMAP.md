# ADARE Development Roadmap  

This document tracks ongoing development tasks, planned features, quality-of-life improvements, known bugs, and areas requiring additional testing for **ADARE**.  

---

## ✅ Current Development Tasks  
- [x] Provide all output in JSON/YML format for automation (toggle via flag to use this as stdout (logging errors+warnings in json; or save to file)  -> need to be tested more first way is implemented

---

## 🚀 Planned Features  
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
- [ ] Extend `expect_to_fail` with `expect_to_fail_on: ExceptionType` (specific exception handling)  
- [ ] Improve ULID handling in CLI → allow lookup by unique partial combinations  
- [ ] Allow metadata descriptions in test function sets  
- [ ] Add new test function sets:  
  - [ ] YAML  
- [ ] integrated log viewer with `adare run log adare ULID` or `adare run log adarevm` that we can view logs but also filter them!

---

## 🛠 Quality of Life Improvements  
- [ ] Expand documentation:  
  - [ ] Timezone handling (VM syncs with local time vs. UTC)  
  - [ ] Experiment development guide (pause, idle, tips)  
  - [ ] Default VM resources (cores, RAM) and how to configure them  
  - [ ] Current limitation: SVG icons not supported  
  - [ ] Installation guide → add `eval "$(_ADARE_COMPLETE=zsh_source adare)"` and autocomplete tutorial  
- [ ] Simplify and clarify logging:  
  - [ ] Define logging levels more clearly  
  - [ ] Replace excessive debug logging with structured log levels  
  - [ ] Make errors more readable and actionable
  - [ ] Remove Claude: log messages
- [ ] Improve the possible solutions on Exceptions to be correct and provide only working options!

---

## 🧹 Code Quality  
- [ ] Rethink test function results: currently lists → should be dictionaries for better JSON/database handling  
- [x] Replace generic `Exception` catches with specific ones  
- [ ] We have custom exceptions? are these clever named and used? should we have more? (general question: Exception vs Return False/None)
- [ ] Refactor `detect_xsession` to use existing system commands with proper parameterization  
- [ ] Consider lazy loading of modules at least for certain libraries -> improve speed

---

## 🐞 Known Bugs  
- [ ] Visual bug: On `Ctrl-C`, duplicate top-line output appears (legacy artifact)  
- [ ] Visual bug: Flow console occasionally shows three red dots at the bottom → cause unknown  
- [ ] Visual bug: last stage spinner ("Stopping computer vision server") briefly disappears before finishing  
- [ ] Visual bug: flow console at some points was stuck and then suddenly completly finished?
- [ ] Visual bug: when no tag is set for experiment or env only # is single in a line (in this case remove it)
- [ ] ctrl-c in multi execute setup does not show prompt that ask wheter to skip all coming or to continue with next experiment

---

## 🔍 Areas Needing More Testing  
- [ ] Verify behavior when adding a new environment to an existing experiment  
- [ ] Verify if ADARE runs without the cloned repository  
- [ ] Test if VM download via URL in environment works 
- [x] Test if list/info commands work outside of an project and then prefix all with the project name (also check if project name is unique?!)
- [ ] Test if environment with zenodo url works!
