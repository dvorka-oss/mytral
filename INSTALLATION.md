# Installation

Build:

* [build on Ubuntu](#build-on-ubuntu)

Tarball:

* [download and install tarball](#download-and-install-tarball)


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
