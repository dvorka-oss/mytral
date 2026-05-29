# MyTraL Desktop Application Guide

## Overview

You now have a complete desktop application build system for MyTraL! This allows you to create a standalone, air-gapped executable that runs completely offline.

## 🎯 What You Can Do

### 1. Build Desktop Executable

**On Linux/macOS:**
```bash
make distro-desktop-build
```
This creates `distro/desktop/mytral-<version>` - a standalone executable.

**On Windows:**
```powershell
make distro-desktop-build-win
```
This creates `distro\desktop\mytral-<version>.exe` - a standalone executable.

### 2. Run in Desktop Mode (Development)
```bash
make distro-desktop-run
```
Test desktop mode without building the full executable.

### 3. Install to System
```bash
make distro-desktop-install
```
Installs the executable to:
- `/usr/local/bin/mytral` (if you have permissions)
- `~/.local/bin/mytral` (fallback)

### 4. Clean Build Artifacts
```bash
make distro-desktop-clean
```
Removes all build artifacts and generated files.

### 5. Test the Build
```bash
make distro-desktop-test
```
Verifies the executable was built successfully.

## 📁 File Structure

```
my-training-log/
├── mytral/
│   └── run_desktop.py                    # Desktop entry point [NEW]
│
├── build/desktop/
│   ├── README.md                         # Full documentation [NEW]
│   ├── BUILD_SUMMARY.md                  # Build summary [NEW]
│   ├── MYTRAL_DESKTOP_APP_DESIGN.md     # Design doc [EXISTING]
│   │
│   ├── requirements_desktop.txt          # Desktop dependencies [NEW]
│   │
│   ├── build-executable.sh               # Main build script [NEW]
│   ├── create-spec.sh                    # Spec generator [NEW]
│   ├── clean.sh                          # Cleanup script [NEW]
│   ├── install.sh                        # Install script [NEW]
│   │
│   ├── mytral-launcher.sh                # Launcher helper [NEW]
│   └── mytral.desktop                    # Linux desktop entry [NEW]
│
├── distro/
│   └── desktop/
│       └── mytral                        # Built executable [GENERATED]
│
├── Makefile                               # Updated with distro-desktop-* targets
├── pyproject.toml                         # Updated with mytral-desktop entry
└── README.md                              # Updated with deployment section
```

## 🚀 Complete Workflow Example

```bash
# 1. Setup (first time only)
uv run make setup

# 2. Build desktop executable
make distro-desktop-build

# 3. Test it locally
./distro/desktop/mytral

# 4. Install to system (optional)
make distro-desktop-install

# 5. Run from anywhere
mytral
```

## 🔧 Make Targets Reference

| Target | Description |
|--------|-------------|
| `make distro-desktop-deps` | Install desktop application dependencies |
| `make distro-desktop-build` | Build standalone executable to distro/ |
| `make distro-desktop-clean` | Clean build artifacts |
| `make distro-desktop-run` | Run in desktop mode (development, no build) |
| `make distro-desktop-test` | Verify executable was built |
| `make distro-desktop-install` | Install executable to system |

## 📦 Dependencies

Desktop-specific dependencies (in `build/desktop/requirements_desktop.txt`):

```
waitress==3.0.2       # Production WSGI server
flaskwebgui==1.0.8    # Desktop window wrapper
pyinstaller==6.11.1   # Executable packaging
```

## 💾 Data Storage

When running as desktop executable:
- **Linux/macOS**: `~/.mytral/application-data/`
- **Windows**: `%USERPROFILE%\.mytral\application-data\`

Data persists across application restarts.

## 🖥️ Platform Support

| Platform | Status | Notes |
|----------|--------|-------|
| Linux (Ubuntu) | ✅ Primary | Tested and supported |
| macOS | ✅ Compatible | Uses system WebKit |
| Windows | ✅ Compatible | Requires `;` separator in spec |

## 🔍 How It Works

```
┌─────────────────────────────────────────┐
│  mytral executable                      │
├─────────────────────────────────────────┤
│  ┌───────────────────────────────────┐  │
│  │ FlaskWebGUI (Desktop Window)      │  │
│  └─────────────┬─────────────────────┘  │
│                │                        │
│  ┌─────────────▼─────────────────────┐  │
│  │ Waitress (Production Server)      │  │
│  └─────────────┬─────────────────────┘  │
│                │                        │
│  ┌─────────────▼─────────────────────┐  │
│  │ Flask Application (MyTraL)        │  │
│  └─────────────┬─────────────────────┘  │
│                │                        │
│  ┌─────────────▼─────────────────────┐  │
│  │ Python Interpreter + Libraries    │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
         │
         ▼
~/.mytral/application-data/
```

## 📝 Entry Points

| Command | Entry Point | Description |
|---------|-------------|-------------|
| `mytral` | `mytral.cli:main` | CLI tool |
| `mytral-web` | `mytral.run:main` | Web server |
| `mytral-desktop` | `mytral.run_desktop:main` | Desktop app |

## 🎨 Customization

### Change Window Size
Edit `mytral/run_desktop.py`:
```python
ui = FlaskUI(
    routes.flask_app,
    # ...
    width=1200,    # Change this
    height=800,    # Change this
    # ...
)
```

### Add Application Icon
1. Place icon file in `build/desktop/`
2. Update `mytral.spec`:
```python
exe = EXE(
    # ...
    icon='build/desktop/mytral.ico',  # Add this
    # ...
)
```

## 🐛 Troubleshooting

### Build fails
```bash
# Reinstall dependencies
make distro-desktop-clean
make distro-desktop-deps
make distro-desktop-build
```

### Executable doesn't start
```bash
# Check what's missing
./distro/desktop/mytral --help

# Run in verbose mode (edit mytral.spec, set debug=True)
```

### Desktop window doesn't open
The app falls back to server-only mode. Access via browser:
```
http://127.0.0.1:5000
```

## 📚 Documentation

- **Build Documentation**: [build/desktop/README.md](README.md)
- **Build Summary**: [build/desktop/BUILD_SUMMARY.md](BUILD_SUMMARY.md)
- **Design Document**: [build/desktop/MYTRAL_DESKTOP_APP_DESIGN.md](MYTRAL_DESKTOP_APP_DESIGN.md)

## 🎯 Next Steps

1. **Test the Build**
   ```bash
   make distro-desktop-build
   make distro-desktop-test
   ./distro/desktop/mytral
   ```

2. **Create Distribution Package**
   - Linux: Create `.deb` or `.rpm` with `fpm`
   - macOS: Create `.dmg` with `hdiutil`
   - Windows: Create installer with Inno Setup

3. **Add Features**
   - Application icon
   - Auto-update functionality
   - System tray integration
   - Notifications

## ✨ Success!

You now have a complete desktop application build system for MyTraL. The `mytral` executable can run completely offline, stores data locally, and provides a native desktop experience!

```bash
# Build and enjoy!
make distro-desktop-build
./distro/desktop/mytral
```

---

**Happy coding! 🚀**
