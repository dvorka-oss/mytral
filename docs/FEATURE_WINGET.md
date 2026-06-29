# MyTraL Feature: Winget

## Design

Package identity:

| Field | Value |
|---|---|
| **Package identifier** | `Mytral.Mytral` |
| **Publisher** | Martin Dvorak |
| **Publisher URL** | https://mytral.fitness |
| **License** | AGPL-3.0 |
| **AppId (Inno Setup)** | `{C3D7F241-8B5E-4A29-9F6D-E1B02A4C7853}` (keep unchanged across releases) |



### Prerequisites

The following steps to be performed to setup the environment for winget based
releases:

1. **Fork `microsoft/winget-pkgs`** on GitHub and clone the fork locally.
```
# fork at: https://github.com/microsoft/winget-pkgs
git clone git@github.com:dvorka-oss/winget-pkgs.git C:\Users\dvorka\p\mytral\git\winget-pkgs
```
Set `WINGET_PKGS_DIR` in your environment in UI 
(This Computer/Properties/System Properties/Advanced/Environment Variables/User) or with CLI:
```powershell
[System.Environment]::SetEnvironmentVariable('WINGET_PKGS_DIR', 'C:\Users\dvorka\p\mytral\git\winget-pkgs', 'User')
```
Verify with new terminal:
```
echo %WINGET_PKGS_DIR%
```

2. **Install prerequisites** (one-time):
```
winget install Microsoft.Winget.Client    # winget CLI (for local validation)
winget install GitHub.cli                 # gh CLI (for PR submission)
gh auth login                             # authenticate gh
```



### New MyTraL Version Winget Release Process 

Step by step cheat sheet:

```
make distro-winget-from-release VERSION=1.56.0
make distro-winget-validate VERSION=1.56.0
make distro-winget-submit-pr VERSION=1.56.0 WINGET_PKGS_DIR=C:\Users\dvorka\p\mytral\git\winget-pkgs
```

Then check PRs:

* https://github.com/microsoft/winget-pkgs/pulls

**If this is the first PR you submit, then you must aggree with the policy**,
just comment as follows:

```
@microsoft-github-policy-service agree
```


---

Overall process can be described as follows - GitHub Actions builds and publishes
the installer as a GitHub release asset when a version tag is pushed.

The winget submission is done **after** the release is live, using the exact
artifact from GitHub as the source of truth. This avoids the problem of locally-built
PyInstaller binaries not being bit-identical to GHA-built ones - the SHA256 in the winget
manifest must match what users will actually download.

```
git tag v{version} && git push origin v{version}
          │
          ▼
GHA builds installer + ZIP, creates GitHub release with both attached
          │
          ▼
make distro-winget-from-release VERSION={version}
  downloads installer from GitHub · computes SHA256 · writes YAML manifests
          │
          ▼
make distro-winget-validate VERSION={version}
          │
          ▼
make distro-winget-submit-pr VERSION={version} WINGET_PKGS_DIR=C:\path\to\winget-pkgs
  copies manifests to fork · signed commit · pushes · opens PR
          │
          ▼
wingetbot validates PR → maintainer merges → winget install Mytral.Mytral works
```
