# Installation

Install:

* [Linux (Flatpak)](#install-on-linux-using-flatpak)
* [Linux (Snap Store)](#install-on-linux-using-snap-from-snap-store)
* [Linux (download)](#install-on-linux-using-snap)
* [Ubuntu (PPA)](#install-on-ubuntu-from-ppa)
* [Windows (installer)](#install-on-windows-using-installer)
* [Windows (zip)](#install-on-windows-using-zip)

Build:

* [Ubuntu (binary)](#build-binary-on-ubuntu)
* [Ubuntu (deb)](#build--deb-on-ubuntu)
* [Snap (package)](#build-snap-on-linux)
* [Flatpak (bundle)](#build-flatpak-on-linux)
* [Windows (binary)](#build-binary-on-windows)
* [Windows (installer)](#build-windows-installer)

Run:

* [Run using Python on Ubuntu](#run-using-python-on-ubuntu)
* [Run using Docker on Debian](#run-using-docker-on-debian)
* [Run using Docker on Fedora](#run-using-docker-on-fedora)

Tarball:

* [Download and install tarball](#download-and-install-tarball)



# Install
Install MyTraL desktop application.



## Install on Ubuntu from PPA

Install MyTraL from [PPA](https://launchpad.net/~ultradvorka/+archive/ubuntu/sport) using one-liner:

```bash
sudo add-apt-repository ppa:ultradvorka/sport && sudo apt-get update && sudo apt-get install mytral
```

... or step by step:

```
sudo add-apt-repository ppa:ultradvorka/sport
sudo apt-get update
sudo apt-get install mytral
```



## Install on Windows using Installer

Download the latest installer from:

* [GitHub Releases](https://github.com/dvorka-oss/mytral/releases)

Run the installer:

```
mytral-<version>-setup.exe

# example: mytral-1.54.0-setup.exe
```

The installer places MyTraL in `C:\Program Files\MyTraL\` and optionally creates a
Desktop shortcut. It includes an uninstaller registered in Windows `Apps & features`.

Data is stored in:

```
C:\Users\<user>\AppData\Local\mytral\
```

**Uninstall:** open Windows `Apps & features`, find MyTraL, and click `Uninstall`.



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



## Install on Linux using Snap from Snap Store

The easiest way to install MyTraL on Linux is from the
[Snap Store](https://snapcraft.io/mytral). Snap works across all major Linux
distributions and keeps MyTraL up to date automatically. This package uses **strict
confinement** and is published straight to the Snap Store.

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

Install MyTraL from the Snap Store:

```bash
sudo snap install mytral
```

Start MyTraL from the application menu or run:

```bash
mytral
```

MyTraL starts the local server and opens its UI in your **default browser** (the same
experience as the Flatpak package).

**Data storage**

Under strict confinement MyTraL stores its data inside the snap's per-user common
directory:

```
~/snap/mytral/common/data/   (data)
```

Note: `sudo snap remove mytral` deletes this directory. Snapd keeps an automatic
snapshot for ~31 days, but a later reinstall does not restore it automatically (use
`snap restore` to recover). To keep a portable copy, use MyTraL's export feature.

**Upgrade:**

```bash
sudo snap refresh mytral
```

**Uninstall:**

```bash
sudo snap remove mytral
```



## Install on Linux using Snap

MyTraL is also distributed as a downloadable **classic confinement** snap attached to
each [GitHub Release](https://github.com/dvorka-oss/mytral/releases). Classic
confinement lets MyTraL open a native frameless desktop window via a browser and stores
data in the standard location, but it is not available from the Snap Store - you install
the downloaded `.snap` file directly.

Install `Snapd` if you have not already (see
[Install on Linux using Snap from Snap Store](#install-on-linux-using-snap-from-snap-store)).

Download `mytral_<version>_amd64.snap` from the latest release, then install it with the
`--dangerous` (unsigned, sideloaded) and `--classic` flags:

```bash
# example: mytral_1.57.0_amd64.snap
sudo snap install --dangerous --classic ./mytral_1.57.0_amd64.snap
```

Start MyTraL from the application menu or run:

```bash
mytral
```

With a browser MyTraL opens as a frameless desktop window. Otherwise it opens in your
default browser as a normal window; if no browser can be opened at all, it prints the
URL so you can open it manually.

**Data storage**

Because this build uses classic confinement it stores data in the same location as every
other installation - your data is never locked inside the snap:

```
~/.local/share/mytral/   (data)
~/.config/mytral/        (config)
```

**Uninstall:**

```bash
sudo snap remove mytral
```



## Install on Linux using Flatpak

Flatpak works across all major Linux distributions. MyTraL runs as a sandboxed
local web app and opens its UI in your **default browser** (via the desktop
portal) - no extra permissions and no host access required.

Install `flatpak` (if not already installed):

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install flatpak
```

**Fedora:**
```bash
sudo dnf install flatpak
```

**Arch Linux:**
```bash
sudo pacman -S flatpak
```

**openSUSE:**
```bash
sudo zypper install flatpak
```

Add the Flathub remote (one-time):

```bash
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
```

**Until MyTraL is published on Flathub**, install the local bundle from
[GitHub Releases](https://github.com/dvorka-oss/mytral/releases):

```bash
flatpak install --user ./mytral-<version>.flatpak

# example: flatpak install --user ./mytral-1.56.0.flatpak
```

... or install MyTraL from [Flathub](https://flathub.org) **when available**:

```bash
flatpak install flathub fitness.mytral.Mytral
```

The bundle is self-contained:

* If the required `org.freedesktop.Platform` runtime is missing, Flatpak offers to
  fetch it from Flathub automatically - you do **not** need to configure Flathub first.
* If you prefer, you can still add the Flathub remote with the `remote-add` command above.

Start MyTraL from the application menu or run:

```bash
flatpak run fitness.mytral.Mytral
```

MyTraL starts a local server and opens its UI in **your default browser**.

**Data storage**

Like the in other MyTraL editions, MyTraL stores your data in the standard shared
location - it is never locked inside the Flatpak sandbox, so it is shared with every
other MyTraL installation (binary/PPA/Snap/*) and survives uninstalling the Flatpak:

```
~/.local/share/mytral/   (data)
~/.config/mytral/        (config)
```

**Upgrade:**

```bash
flatpak update fitness.mytral.Mytral
```

**Uninstall:**

```bash
flatpak uninstall fitness.mytral.Mytral
```

Your data in `~/.local/share/mytral/` is **not** removed by uninstalling - delete
that directory manually if you want to remove it.



# Build

Build MyTraL desktop application from the source code.



## Build Binary on Ubuntu

Install `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install `Python`:

```bash
uv python install 3.12
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



## Build Snap on Linux

Install prerequisites (Snapcraft, plus LXD for isolated container builds):

```bash
sudo snap install snapcraft --classic
sudo snap install lxd
sudo lxd init --auto
sudo usermod -aG lxd $USER
```

After adding yourself to the `lxd` group, log out and back in (or run `newgrp lxd`)
so the new group membership takes effect.

Build the Snap package:

```bash
make distro-snap-build
```

The package is created at:

```
distro/snap/mytral_<version>_amd64.snap
```

Show the path to the built package:

```bash
make distro-snap-path
```

Build and install it locally for testing (requires sudo; Snap uses classic
confinement, so the `--classic` flag is applied automatically):

```bash
make distro-snap-install-local
```

Run MyTraL:

```bash
mytral
```

**Clean Snap artifacts:**

```bash
make distro-snap-clean
```

**Remove the locally installed Snap:**

```bash
make distro-snap-remove
```

Publish to the Snap Store (maintainers only):

```bash
make distro-snap-upload
```



## Build Flatpak on Linux

Install prerequisites:

```bash
sudo apt install flatpak flatpak-builder
```

Add the Flathub remote and install the runtime and SDK (the build targets
Python 3.12 via the `24.08` runtime):

```bash
flatpak remote-add --if-not-exists --user flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub org.freedesktop.Platform//24.08 org.freedesktop.Sdk//24.08
```

Build the Flatpak bundle:

```bash
make distro-flatpak-build
```

The single-file bundle is created at:

```
distro/flatpak/mytral-<version>.flatpak
```

Build and install it locally for testing (user scope):

```bash
make distro-flatpak-install-local
```

Run MyTraL:

```bash
flatpak run fitness.mytral.Mytral
```

**Clean Flatpak artifacts:**

```bash
make distro-flatpak-clean
```

**Remove the locally installed Flatpak:**

```bash
make distro-flatpak-remove
```



## Build Windows Installer

The Windows installer is built with [Inno Setup 6](https://jrsoftware.org/isinfo.php).

**Step 1: Build the desktop executable**

Build the desktop binary first (see [Build Binary on Windows](#build-binary-on-windows)):

```bash
make setup distro-desktop-build-win
```

Verify the binary was created:

```
distro\desktop\mytral-<version>.exe
```

**Step 2: Install Inno Setup 6**

Install via `winget` (no administrator rights required - installs to your user profile):

```
winget install --id JRSoftware.InnoSetup
```

Or download the installer from the official website and run it:

* [https://jrsoftware.org/isdl.php](https://jrsoftware.org/isdl.php)

`env.bat` automatically detects both install locations:

| Location | How installed |
|---|---|
| `C:\Program Files (x86)\Inno Setup 6\` | System-wide (requires admin) |
| `%LOCALAPPDATA%\Programs\Inno Setup 6\` | Per-user via winget or without admin |

No manual configuration is needed for either location.

**Step 3: Build the installer**

```bash
make distro-windows-installer
```

The installer is created at:

```
distro\windows\mytral-<version>-setup.exe
```

**Custom Inno Setup path (optional)**

If `ISCC.exe` is installed elsewhere, edit `build\windows\env.bat` and set:

```
set MYTRAL_ISCC=C:\your\custom\path\ISCC.exe
```

**Clean installer artifacts:**

```bash
make distro-windows-clean
```



## Build Binary on Windows

Install `uv` to `C:\Users\[user]\.local\bin`:

```bash
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Install `Python`:

```bash
uv python install 3.12
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
uv python install 3.12
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
uv python install 3.12
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


