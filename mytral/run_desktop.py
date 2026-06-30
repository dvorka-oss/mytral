# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""
MyTraL desktop application entry point.

This module provides the desktop/air-gapped version of MyTraL that bundles:

- Flask application (threaded WSGI server)
- FlaskWebGUI for native desktop window
- PyInstaller for single executable packaging

SECURITY related configuration of MyTraL desktop:

- The goal is to provide Ubuntu user like experience for the desktop application:
  - DESKTOP MyTraL INCARNATION
    - desktop application has MYTRAL_INCARNATION=desktop env var set (by native runner)
      so that the init steps (which would be potentially unsafe for webapp) can be done.
      This env var / setting cannot be changed on desktop.
  - DEFAULT USER
    - User ``mytral`` / ``mytral`` w/ auto login enabled is auto created on
      the first boot so that the desktop application can AUTO LOGIN as that user.
      - SECURITY: user can change default user password
      - SECURITY: user can disable auto login.
      - SECURITY: user can create new / other users.
  - AUTO LOGIN
    - If user logs-in with username (account) which has enabled auto login,
      then the password is not checked and user is let in. This flag can be set
      only in DESKTOP incarnation and is potentially dangerous.
      - SECURITY: user can disable auto login.
- Security material:
  - SESSION signing key
    - sessions are invalidated w/ every application restart for security reasons
    - SECURITY: if user sets MYTRAL_SIGNING_KEY=...,
      then the sessions will be stable and signed by their own key.
  - ENCRYPTION key
    - Encryption key is set to a hard coded key for the sake of desktop application UX.
    - SECURITY: if user sets MYTRAL_ENCRYPTION_KEY=...,
      then their own key will be used for tokens, secrets and API keys signing.
  - Password HASHING
    - MyTraL user passwords are hashed w/ salt.
    - SECURITY: hashed passwords remain valid across different installation,
      because salt and the number of iterations and algorithm is stable.

"""

import argparse
import logging
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser

# ENV SETUP
# because mytral/__init__.py creates app_config at import time, ENV vars must be set
# ENSURE INCARNATION
os.environ["MYTRAL_INCARNATION"] = "DESKTOP"
# desktop incarnation allows user registration and auto-account creation by default
os.environ["MYTRAL_USER_REGISTRATION"] = "true"
os.environ["MYTRAL_AUTO_ACCOUNT_CREATE"] = "true"

from mytral import app_config
from mytral import app_logger
from mytral import routes
from mytral import version
from mytral.blueprints import acoach_uri_space
from mytral.blueprints import activity_types_crud
from mytral.blueprints import auth_uri_space
from mytral.blueprints import component_templates_crud
from mytral.blueprints import deployment_crud
from mytral.blueprints import exercise_types_crud
from mytral.blueprints import export_uri_space
from mytral.blueprints import gear_components_crud
from mytral.blueprints import gear_crud
from mytral.blueprints import goal_crud
from mytral.blueprints import gpx_terrain_views
from mytral.blueprints import health_uri_space
from mytral.blueprints import import_uri_space
from mytral.blueprints import lap_types_crud
from mytral.blueprints import maps_uri_space
from mytral.blueprints import outfit_crud
from mytral.blueprints import strava_api_uri_space
from mytral.blueprints import symptom_types_crud
from mytral.blueprints import tabpfn_uri_space
from mytral.blueprints import tools_uri_space
from mytral.blueprints import trimp_uri_space


def configure_pyinstaller_paths():
    """Configure paths when running as PyInstaller executable."""
    if getattr(sys, "frozen", False):
        # running as PyInstaller executable
        base_path = sys._MEIPASS
        template_folder = pathlib.Path(base_path) / "mytral" / "templates"
        static_folder = pathlib.Path(base_path) / "mytral" / "static"
        app_logger.info(f"PyInstaller mode detected, using base path: {base_path}")
        app_logger.info(f"  Templates: {template_folder}")
        app_logger.info(f"  Static: {static_folder}")

        # update Flask app's template and static folders
        routes.flask_app.template_folder = str(template_folder)
        routes.flask_app.static_folder = str(static_folder)


def open_app_window(url: str) -> None:
    """Open url in a standalone app window (no browser chrome/toolbar).

    Tries Chromium-family browsers with --app flag first; falls back to the
    system default browser via webbrowser if none is found.
    """
    chromium_browsers = [
        "chromium-browser",
        "chromium",
        "google-chrome",
        "google-chrome-stable",
        "brave-browser",
    ]
    for browser in chromium_browsers:
        if shutil.which(browser):
            app_logger.info(f"Opening standalone app window with {browser}", url=url)
            subprocess.Popen([browser, f"--app={url}"])
            return
    app_logger.warning(
        "No Chromium browser found, falling back to system browser", url=url
    )
    webbrowser.open(url)


def _wait_for_server(host: str, port: int, timeout: float = 30.0) -> None:
    """Block until the server accepts TCP connections or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.05)
    app_logger.warning(
        "Server did not become ready within timeout",
        host=host,
        port=port,
        timeout=timeout,
    )


def start_flask_in_background() -> threading.Thread:
    """Start the Flask server in a daemon thread, return it once it is ready."""
    thread = threading.Thread(target=start_flask_server, daemon=True)
    thread.start()
    _wait_for_server(app_config.host, app_config.port)
    return thread


def start_flask_server():
    """Run the Flask app via its threaded WSGI server - blocks until stopped.

    The desktop edition serves a single local user on 127.0.0.1, so the
    built-in threaded Flask/Werkzeug server is sufficient. ``use_reloader`` is
    forced off: the reloader needs the main thread for signal handling and
    would break both background-thread startup and the PyInstaller bundle.
    """
    app_logger.info(f"Starting Flask server on {app_config.host}:{app_config.port}")
    routes.flask_app.run(
        host=app_config.host,
        port=app_config.port,
        threaded=True,
        use_reloader=False,
    )


def main():
    """Main entry point for MyTraL desktop application."""

    # default port for the desktop
    app_config.port = 5151

    arg_parser = argparse.ArgumentParser(
        prog="mytral-desktop",
        description="MyTraL Desktop - My Trailing Log desktop edition.",
    )
    arg_parser.add_argument(
        "--port",
        type=int,
        metavar="PORT",
        help=f"port to listen on (default: {app_config.port}, env: MYTRAL_PORT)",
    )
    arg_parser.add_argument(
        "--host",
        type=str,
        metavar="HOST",
        help=f"host to start on (default: {app_config.DEFAULT_HOST}, env: MYTRAL_HOST)",
    )
    args = arg_parser.parse_args()
    if args.port is not None:
        app_config.port = args.port
    if args.host is not None:
        app_config.host = args.host

    # TODO DRY - call a figlet helper

    print(f""" __  __      _____          _
|  \\/  |_   |_   _| __ __ _| |
| |\\/| | | | || || '__/ _` | |
| |  | | |_| || || | | (_| | |___
|_|  |_|\\__, ||_||_|  \\__,_|_____| {version.__version__} Desktop
        |___/

MyTraL: My Trailing Log - Desktop Edition
    """)

    # configure PyInstaller paths if running as executable
    configure_pyinstaller_paths()

    # blueprints w/o blueprints - Flask app structured using Python modules
    blueprints = [
        acoach_uri_space,
        activity_types_crud,
        auth_uri_space,
        component_templates_crud,
        deployment_crud,
        exercise_types_crud,
        export_uri_space,
        import_uri_space,
        gear_components_crud,
        gear_crud,
        goal_crud,
        gpx_terrain_views,
        health_uri_space,
        lap_types_crud,
        maps_uri_space,
        outfit_crud,
        strava_api_uri_space,
        symptom_types_crud,
        tabpfn_uri_space,
        tools_uri_space,
        trimp_uri_space,
    ]

    app_logger.info(
        f"MyTraL Desktop: running on {app_config.host}:{app_config.port} w/ blueprints:"
    )
    for b in blueprints:
        app_logger.info(f"  {b.__package__}{b.__name__}")

    # control flask logging
    # outside debug, raise werkzeug to ERROR so the threaded server's
    # "development server" banner is not shown to desktop users (the desktop
    # edition serves a single local user); request logging is handled by the
    # structlog after_request hook in routes.py.
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.DEBUG if app_config.debug else logging.ERROR)

    try:
        from flaskwebgui import FlaskUI

        app_logger.info("Launching MyTraL Desktop application...")

        # run FlaskWebGUI - opens Brave/Chrome/Chromium/* in --app mode (frameless win)
        # pass start_flask_server as the server callable so FlaskWebGUI runs our
        # threaded Flask server directly (no extra WSGI dependency).
        ui = FlaskUI(
            app=routes.flask_app,
            server=start_flask_server,
            port=app_config.port,
            width=1200,
            height=800,
        )
        # launch the UI - this will block until the browser window is closed
        ui.run()

    except ImportError as e:
        app_logger.warning(
            f"FlaskWebGUI import failed ({e}) - falling back to server + browser mode"
        )
        app_logger.warning(
            "Install FlaskWebGUI for desktop window: pip install flaskwebgui"
        )
        server_thread = start_flask_in_background()
        url = f"http://{app_config.host}:{app_config.port}"
        open_app_window(url)
        server_thread.join()
    except KeyboardInterrupt:
        print("\n  MyTraL Desktop stopped.")
        app_logger.info("MyTraL Desktop: received Ctrl-C, shutting down.")
        sys.exit(0)
    except OSError as e:
        if "Address already in use" in str(e) or "98" in str(e):
            app_logger.error(
                f"Port {app_config.port} is already in use. "
                f"Another MyTraL instance may be running. "
                f"Try: pkill -f mytral"
            )
        raise
    except Exception as e:
        # if FlaskWebGUI fails for any reason, fall back to server-only mode
        app_logger.error(f"FlaskWebGUI failed: {e}")
        app_logger.info("Falling back to server-only mode...")
        app_logger.info(
            f"Open browser manually to: http://{app_config.host}:{app_config.port}"
        )
        start_flask_server()


if __name__ == "__main__":
    main()
