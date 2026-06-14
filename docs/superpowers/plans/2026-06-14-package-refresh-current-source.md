# Package Refresh Current Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure the Windows package script builds the current source and includes watermark dependencies.

**Architecture:** Keep the existing PyInstaller flow, but refresh the editable project install before tests/build so the build environment sees the latest `src` code and dependency list. Extend the existing spec dependency collection to include `blind_watermark` for the new watermark feature.

**Tech Stack:** PowerShell, PyInstaller, Python packaging, unittest.

---

### Task 1: Refresh Project Install Before Packaging

**Files:**
- Modify: `scripts/package.ps1`

- [ ] **Step 1: Add an install step after PyInstaller check**

Insert this command before tests:

```powershell
Run-Python -Title "Install current project" -PyArgs @("-m", "pip", "install", "-e", ".")
```

- [ ] **Step 2: Keep cleanup behavior unchanged**

Confirm the script still removes `build`, `dist`, and `release` unless `-NoClean` is supplied.

- [ ] **Step 3: Validate script syntax**

Run:

```powershell
rtk powershell -NoProfile -Command "$null = [System.Management.Automation.PSParser]::Tokenize((Get-Content -LiteralPath 'scripts\package.ps1' -Raw), [ref]$null)"
```

Expected: exit code `0`.

### Task 2: Include Watermark Dependencies in Spec

**Files:**
- Modify: `DayZ_Texture_Tool.spec`

- [ ] **Step 1: Collect blind_watermark**

Add the same `collect_all` pattern already used for UI libraries:

```python
tmp_ret = collect_all('blind_watermark')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
```

- [ ] **Step 2: Run full tests**

Run:

```powershell
rtk powershell -NoProfile -Command "python -m unittest discover tests -v"
```

Expected: all tests pass.

### Task 3: Packaging Smoke Test

**Files:**
- Verify: `release/DayZ_Texture_Tool`

- [ ] **Step 1: Run a package build without zip if dependencies are available**

Run:

```powershell
rtk powershell -NoProfile -ExecutionPolicy Bypass -File scripts\package.ps1 -NoZip
```

Expected: `release\DayZ_Texture_Tool` exists.

- [ ] **Step 2: Check git status and sync CodeGraph**

Run:

```powershell
rtk git -c core.excludesFile= status --short
rtk codegraph sync
rtk codegraph status
```

Expected: only intentional source/doc changes remain; CodeGraph is up to date.
