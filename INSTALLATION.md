# Installation

Build:

* [Build on Ubuntu](#build-on-ubuntu)

Run:

* [Run using Python on Ubuntu](#run-using-python-on-ubuntu)
* [Run using Docker on Debian](#run-using-docker-on-debian)
* [Run using Docker on Fedora](#run-using-docker-on-fedora)

Tarball:

* [Download and install tarball](#download-and-install-tarball)


# Build

Build MyTraL desktop application from the source code.

## Build on Ubuntu

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
# Example:
# cd distro/desktop && ./mytral-1.51.0

cd distro/desktop && ./mytral-[major.minor.patch]
```

Start using MyTraL:

* Click `Add new user` button to add new athlete account.
* `Sign in`.

Optionally install MyTraL for the current user:

```
make distro-desktop-install
```


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

## Download and install tarball

Download the latest tarball from the
[GitHub releases](https://github.com/dvorka/mytral/releases) page.

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


