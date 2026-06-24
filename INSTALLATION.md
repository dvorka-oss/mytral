# Installation

Install:

* [Linux (Snap)](#install-on-linux-using-snap) (Ubuntu, Debian, Fedora, Arch, OpenSUSE)
* [Ubuntu (PPA)](#install-on-ubuntu-from-ppa)
* [Windows (ZIP)](#install-on-windows-using-zip)

Build:

* [Ubuntu (binary)](#build-binary-on-ubuntu)
* [Ubuntu (.deb)](#build--deb-on-ubuntu)
* [Windows (binary)](#build-binary-on-windows)

Run:

* [Run using Python on Ubuntu](#run-using-python-on-ubuntu)
* [Run using Docker on Debian](#run-using-docker-on-debian)
* [Run using Docker on Fedora](#run-using-docker-on-fedora)

Tarball:

* [Download and install tarball](#download-and-install-tarball)



# Install
Install MyTraL desktop application.



## Install on Ubuntu from PPA

Install MyTraL using one-liner:

```bash
sudo add-apt-repository ppa:ultradvorka/sport && sudo apt-get update && sudo apt-get install mytral
```

... or step by step:

```
sudo add-apt-repository ppa:ultradvorka/sport
sudo apt-get update
sudo apt-get install mytral
```



## Install on Windows using ZIP
Download the latest ZIP archive with the executable:

* [GitHub Releases](https://github.com/dvorka-oss/mytral/releases)

Extract `*.exe`:

```bash
unzip mytral-<version>.exe-Win*.zip
```

Start MyTraL:

```
mytral-<version>.exe

# example: mytral-1.51.0.exe
```



## Install on Linux using Snap

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

Build MyTraL desktop application from the source code.



## Build Binary on Ubuntu

Install `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install `Python`:

```bash
uv python install 3.11
```

Clone Git repository:

```bash
git clone https://github.com/dvorka-oss/mytral.git
cd mytral
```

Install dependencies and build desktop application executable:

```bash
make setup distro-desktop-build
```

Run MyTraL desktop application:

```bash
cd distro/desktop && ./mytral-<version>

# example:
# cd distro/desktop && ./mytral-1.51.0
```

Start using MyTraL:

* Click `Add new user` button to add new athlete account.
* `Sign in`.

Optionally install MyTraL for the current user:

```
make distro-desktop-install
```



## Build .deb on Ubuntu

Install prerequisites:

```
sudo apt install dh-python pybuild-plugin-pyproject python3-hatchling
```

Build `.deb`:

```
make distro-ubuntu-deb
```

Find `.deb` package in the directory printed by the `make` target.



## Build Binary on Windows

Install `uv` to `C:\Users\[user]\.local\bin`:

```bash
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Install `Python`:

```bash
uv python install 3.11
```

Clone Git repository:

```bash
git clone https://github.com/dvorka-oss/mytral.git
cd mytral
```

Install dependencies and build desktop application executable:

```bash
make setup distro-desktop-build-win
```

Run MyTraL desktop application:

```bash
cd distro\desktop

# example: mytral-1.51.0.exe
mytral-<version>.exe
```

Data will be stored to:

```
C:\Users\[user]\Application Data\mytral\data
```

Start using MyTraL:

* Click `Add new user` button to add new athlete account.
* `Sign in`.



# Run

Run MyTraL web application.



## Run using Python on Ubuntu

Install `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install `Python`:

```bash
uv python install 3.11
```

Clone Git repository:

```bash
git clone https://github.com/dvorka-oss/mytral.git
cd mytral
```

Install dependencies:

```bash
make setup
```

Run MyTraL as web application:

```bash
make run
```

Open `http://localhost:5000` in your browser:

* Click `Add new user` button to add new athlete account.
* `Sign in`.



## Run using Docker on Debian

Install `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Build the Debian image (requires Docker and uv in `PATH`):

```bash
make distro-docker-debian-build
```

Run the container:

```bash
make distro-docker-debian-run
```

* Serves on [http://localhost:8888](http://localhost:8888) .
* Data is stored at `~/.local/share/mytral-docker-debian/`.

Open `http://localhost:8888` in your browser:

* Click `Add new user` button to add new athlete account.
* `Sign in`.

Stop the container:

```bash
docker stop mytral-debian
```



## Run using Docker on Fedora

Install `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Build the Fedora image (requires Docker and uv in `PATH`):

```bash
make distro-docker-fedora-build
```

Run the container:

```bash
make distro-docker-fedora-run
```

* Serves on [http://localhost:8888](http://localhost:8888) .
* Data is stored at `~/.local/share/mytral-docker-fedora/`.

Open `http://localhost:8888` in your browser:

* Click `Add new user` button to add new athlete account.
* `Sign in`.

Stop the container:

```bash
docker stop mytral-fedora
```



# Tarball

## Download and Install Tarball

Download the latest tarball from the
[GitHub Releases](https://github.com/dvorka-oss/mytral/releases) page.

Extract and start MyTraL:

```bash
tar xzf mytral-<version>.tar.gz
cd mytral-<version>
```

Install `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install `Python`:

```bash
uv python install 3.11
```

Install dependencies:

```bash
make setup
```

Run MyTraL as web application:

```bash
make run
```

Open `http://localhost:5000` in your browser:

* Click `Add new user` button to add new athlete account.
* `Sign in`.


