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
import argparse
import logging

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


def main():
    """Main entry point for MyTraL - used by tools like ``uv`` to run it."""

    arg_parser = argparse.ArgumentParser(
        prog="mytral-web",
        description="MyTraL Web - My Trailing Log web server.",
    )
    arg_parser.add_argument(
        "--port",
        type=int,
        metavar="PORT",
        help=f"port to listen on (default: {app_config.port}, env: MYTRAL_PORT)",
    )
    args = arg_parser.parse_args()
    if args.port is not None:
        app_config.port = args.port

    print(f""" __  __      _____          _
|  \\/  |_   |_   _| __ __ _| |
| |\\/| | | | || || '__/ _` | |
| |  | | |_| || || | | (_| | |___
|_|  |_|\\__, ||_||_|  \\__,_|_____| {version.__version__}
        |___/

MyTraL: My Trailing Log
    """)

    # blueprints w/o blueprints - Flask app structured using Python modules
    blueprints = [
        acoach_uri_space,
        activity_types_crud,
        auth_uri_space,
        component_templates_crud,
        deployment_crud,
        exercise_types_crud,
        gear_components_crud,
        gear_crud,
        goal_crud,
        health_uri_space,
        import_uri_space,
        irm3d_uri_space,
        export_uri_space,
        lap_types_crud,
        maps_uri_space,
        outfit_crud,
        strava_api_uri_space,
        symptom_types_crud,
        tabpfn_uri_space,
        tools_uri_space,
        trimp_uri_space,
    ]

    app_logger.info(f"MyTraL: running on port {app_config.port} w/ blueprints:")
    for b in blueprints:
        app_logger.info(f"  {b.__package__}{b.__name__}")

    # suppress werkzeug's stdlib access log
    # - request logging is handled by the structlog after_request hook in routes.py
    #   so we keep a single
    # - structured log stream - werkzeug WARNING+ (errors) still come through
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    routes.flask_app.run(
        host=app_config.host, debug=app_config.debug, port=app_config.port
    )


if __name__ == "__main__":
    main()
