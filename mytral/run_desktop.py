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

- Flask application
- Waitress production WSGI server
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
import sys
import threading
import time

# ENV SETUP
# because mytral/__init__.py creates app_config at import time, ENV vars must be set
# ENSURE INCARNATION
os.environ["MYTRAL_INCARNATION"] = "DESKTOP"

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
from mytral.blueprints import health_uri_space
from mytral.blueprints import import_uri_space
from mytral.blueprints import irm3d_uri_space
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


def start_waitress_server():
    """Start production-grade Waitress WSGI server."""
    try:
        from waitress import serve

        app_logger.info(
            f"Starting Waitress production server on {app_config.host}"
            f":{app_config.port}"
        )
        serve(routes.flask_app, host=app_config.host, port=app_config.port, threads=4)
    except ImportError:
        app_logger.error("Waitress not installed. Install with: pip install waitress")
        sys.exit(1)


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
        irm3d_uri_space,
        gear_components_crud,
        gear_crud,
        goal_crud,
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
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.DEBUG if app_config.debug else logging.WARNING)

    try:
        from flaskwebgui import FlaskUI

        app_logger.info("Launching MyTraL Desktop application...")

        # start waitress in a separate thread
        # Waitress is a production-grade WSGI server
        server_thread = threading.Thread(target=start_waitress_server, daemon=True)
        server_thread.start()

        # give server time to start
        time.sleep(2)

        # launch desktop UI with FlaskWebGUI
        # - FlaskWebGUI opens a desktop window pointing to our Waitress server
        ui = FlaskUI(
            app=routes.flask_app,
            server="flask",  # FlaskUI internal mode - but we ignore it
            port=app_config.port,
            width=1200,
            height=800,
        )

        # launch the UI (this will block and open browser window)
        ui.run()
    except ImportError as e:
        app_logger.warning(
            f"FlaskWebGUI import failed ({e}) - falling back to Waitress server mode"
        )
        app_logger.warning(
            "Install FlaskWebGUI for desktop window: pip install flaskwebgui"
        )
        start_waitress_server()
    except Exception as e:
        # If FlaskWebGUI fails for any reason, fall back to Waitress only
        app_logger.error(f"FlaskWebGUI failed: {e}")
        app_logger.info("Falling back to Waitress server mode.")
        app_logger.info(
            f"Open browser manually to: http://{app_config.host}:{app_config.port}"
        )
        start_waitress_server()


if __name__ == "__main__":
    main()
