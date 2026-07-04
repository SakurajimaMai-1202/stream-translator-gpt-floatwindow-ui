# Legacy Packaging

This folder keeps the old one-profile packaging path for historical
troubleshooting only.

For current releases, run commands from the `app` directory:

```powershell
.\build_release.ps1 -Profile cuda
.\build_release.ps1 -Profile cpu
.\build_release.ps1 -Profile rocm
```

