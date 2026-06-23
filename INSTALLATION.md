# Installation

Install:

* [Linux via Snap](#install-on-linux-via-snap) (Ubuntu, Debian, Fedora, Arch, OpenSUSE)
* [Windows](#install-on-windows)

Build:

* [build on Ubuntu](#build-on-ubuntu)
* [build on Windows](#build-on-windows)

Run:

* [Run via Python on Linux](#run-via-python-on-linux)
* [Run via Python on Windows](#run-via-python-on-windows)
* [Run via Python on macOS](#run-via-python-on-macos)
* [Run on Debian in Docker](#run-on-debian-in-docker)
* [Run on Fedora in Docker](#run-on-fedora-in-docker)

Tarball:

* [download and install tarball](#download-and-install-tarball)



# Install

## Install on Windows

Download the latest MyTraL desktop executable from the
[GitHub releases](https://github.com/dvorka/my-training-log/releases) page.

1. Download `mytral-<version>.exe`.
2. Move it to a folder of your choice (e.g. `C:\Users\<you>\bin\`).
3. Double-click `mytral-<version>.exe` — MyTraL opens in your default browser.

Data is stored in `%USERPROFILE%\.mytral\application-data\` and persists across restarts.



## Install on Linux via Snap

Snap works across all major Linux distributions and keeps MyTraL up to date automatically.
MyTraL uses **classic confinement** so it can open a native desktop window via Chrome/Chromium.

**Prerequisite:** Chrome or Chromium must be installed — MyTraL opens its UI in a frameless
Chrome window (not as a browser tab).

Install `Snapd` (if not already installed):

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install snapd
```

**Fedora:**
```bash
sudo dnf install snapd
sudo ln -s /var/lib/snapd/snap /snap
```

**Arch Linux:**
```bash
sudo pacman -S snapd
sudo systemctl enable --now snapd.socket
```

**openSUSE:**
```bash
sudo zypper install snapd
sudo systemctl enable --now snapd
```

Install MyTraL from the Snap Store (classic confinement requires the `--classic` flag):

```bash
sudo snap install mytral --classic
```

Start MyTraL from the application menu or run:

```bash
mytral
```

MyTraL opens as a native desktop window. If Chrome/Chromium is not found it falls back to
printing the URL so you can open it manually in any browser.

**Data storage**

Because MyTraL uses classic confinement it stores data in the same location as every other
installation - your data is never locked inside the snap:

```
~/.local/share/mytral/   (data)
~/.config/mytral/        (config)
```

**Upgrade:**

```bash
sudo snap refresh mytral
```

**Uninstall:**

```bash
sudo snap remove mytral
```

`snap remove` only removes the snap package itself. Your data in `~/.local/share/mytral/`
is **not touched**.



# Build

Build MyTraL from source code.

## Build on Ubuntu

Install Python 3.11 and uv:

```bash
sudo apt install python3.11 python3.11-venv curl
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Clone the repository:

```bash
git clone https://github.com/dvorka/my-training-log.git
cd my-training-log
```

Install dependencies and start MyTraL:

```bash
uv run mytral-web
```

Open `http://localhost:5000` in your browser.



## Build on Windows

Install [Python 3.11](https://www.python.org/downloads/) for Windows, then install uv (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Clone the repository:

```powershell
git clone https://github.com/dvorka/my-training-log.git
cd my-training-log
```

Install dependencies and start the web server:

```powershell
uv run mytral-web
```

To build a standalone Windows executable:

```powershell
make distro-desktop-build-win
```

The executable is created at `distro\desktop\mytral-<version>.exe`.



# Run

## Run via Python on Linux

Install [uv](https://github.com/astral-sh/uv) (fast Python package manager):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install Python 3.11:

```bash
uv python install 3.11
```

Clone the repository and set up the project:

```bash
git clone https://github.com/dvorka/my-training-log.git
cd my-training-log
make setup
```

Start MyTraL:

```bash
uv run mytral-web
```

Open `http://localhost:5000` in your browser.


## Run via Python on Windows

Install [uv](https://github.com/astral-sh/uv) (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Install Python 3.11:

```powershell
uv python install 3.11
```

Clone the repository and install dependencies:

```powershell
git clone https://github.com/dvorka/my-training-log.git
cd my-training-log
uv sync --all-groups
```

Start MyTraL:

```powershell
uv run mytral-web
```

Open `http://localhost:5000` in your browser.


## Run via Python on macOS

Install [uv](https://github.com/astral-sh/uv):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install Python 3.11:

```bash
uv python install 3.11
```

Clone the repository and set up the project (requires Xcode Command Line Tools for `make`):

```bash
git clone https://github.com/dvorka/my-training-log.git
cd my-training-log
make setup
```

Start MyTraL:

```bash
uv run mytral-web
```

Open `http://localhost:5000` in your browser.


## Run on Debian in Docker

Build the Debian image (requires Docker and uv in `PATH`):

```bash
make distro-docker-debian-build
```

Run the container (serves on http://localhost:8888):

```bash
make distro-docker-debian-run
```

Data is stored at `~/.local/share/mytral-docker/`.

Stop the container:

```bash
docker stop mytral-debian
```

## Run on Fedora in Docker

Build the Fedora image (requires Docker and uv in `PATH`):

```bash
make distro-docker-fedora-build
```

Run the container (serves on http://localhost:8888):

```bash
make distro-docker-fedora-run
```

Data is stored at `~/.local/share/mytral-docker-fedora/`.

Stop the container:

```bash
docker stop mytral-fedora
```



# Tarball

## Download and install tarball

Download the latest tarball from the
[GitHub releases](https://github.com/dvorka/my-training-log/releases) page.

Install uv if not already installed:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Extract and start MyTraL:

```bash
tar xzf mytral-<version>.tar.gz
cd mytral-<version>
uv run mytral-web
```

Open `http://localhost:5000` in your browser.
