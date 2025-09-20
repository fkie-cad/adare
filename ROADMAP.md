# ADARE Development Roadmap  

This document tracks ongoing development tasks, planned features, quality-of-life improvements, known bugs, and areas requiring additional testing for **ADARE**.  

---

## ✅ Current Development Tasks  


---

## 🚀 Planned Features  
- [ ] Add support for Wayland-based Linux systems  
  - [ ] Validate `ydotool`  
- [ ] Replace `pyautogui.screenshot` with `maim` for improved stability under Wayland  
- [ ] Implement interactive experiment development tools  
  - [ ] Idea: Use **NiceGUI** for web-based interactive playbook and test creation (e.g., cropping images, extracting icons)  
- [ ] Add playbook variable validation:  
  - [ ] Prevent duplicate variable names  
  - [ ] Ensure all variables are defined before use  
  - [ ] Validate filter correctness  
- [ ] Provide all output in JSON format for automation (toggle via flag or save to file)  
- [ ] Enhance `adare vm test` with automatic platform and desktop environment detection  
- [ ] Use standardized installation directory (via `platformdirs`) and migrate installer scripts to Python  
- [ ] Implement condition/wait/retry logic in playbooks  
- [ ] Extend `expect_to_fail` with `expect_to_fail_on: ExceptionType` (specific exception handling)  
- [ ] Improve ULID handling in CLI → allow lookup by unique partial combinations  
- [ ] Allow metadata descriptions in test function sets  
- [ ] Add new test function sets:  
  - [ ] YAML  

---

## 🛠 Quality of Life Improvements  
- [ ] Expand documentation:  
  - [ ] Timezone handling (VM syncs with local time vs. UTC)  
  - [ ] Advanced experiment runs (multi-env execution, glob experiment names)  
  - [ ] Experiment development guide (pause, idle, tips)  
  - [ ] Default VM resources (cores, RAM) and how to configure them  
  - [ ] Current limitation: SVG icons not supported  
  - [ ] Installation guide → add `eval "$(_ADARE_COMPLETE=zsh_source adare)"` and autocomplete tutorial  
- [ ] Simplify and clarify logging:  
  - [ ] Define logging levels more clearly  
  - [ ] Replace excessive debug logging with structured log levels  
  - [ ] Make errors more readable and actionable  

---

## 🧹 Code Quality  
- [ ] Rethink test function results: currently lists → should be dictionaries for better JSON/database handling  
- [ ] Replace generic `Exception` catches with specific ones  
- [ ] Refactor `detect_xession` to use existing system commands with proper parameterization  

---

## 🐞 Known Bugs  
- [ ] Visual bug: On `Ctrl-C`, duplicate top-line output appears (legacy artifact)  
- [ ] Visual bug: Flow console occasionally shows three red dots at the bottom → cause unknown  
- [ ] Visual bug: last stage spinner ("Stopping computer vision server") briefly disappears before finishing  
- [ ] Visual bug: flow console at some points was stuck and then suddenly completly finished?

---

## 🔍 Areas Needing More Testing  
- [ ] Verify behavior when adding a new environment to an existing experiment  
- [ ] Verify if ADARE runs without the cloned repository  
- [ ] Test if VM download via URL in environment works
- [ ] Running experiment with a non-existent environment caused weird display instead of throwing an exception (fixed/test pending)  
