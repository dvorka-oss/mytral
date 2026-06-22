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

"""Command line interface for MyTraL."""

import argparse
import sys

# import version directly to avoid initializing the whole mytral module
try:
    from mytral.version import __version__
except ImportError:
    __version__ = "unknown"


def cmd_help():
    """Show available MyTraL commands."""
    print(f"""MyTraL CLI v{__version__}

Usage: mytral <command> [options]

Available commands:
  help                          Show this help message
  import strava                 Import training data from Strava
  upgrade --from X --to Y       Upgrade data from version X to version Y

Examples:
  mytral help
  mytral import strava
  mytral upgrade --from 1.0.0 --to 1.1.0

For more information visit: https://github.com/dvorka-oss/mytral

""")


def cmd_import_strava():
    """Import training data from Strava."""
    print("HERE WOULD COME CODE")


def cmd_upgrade(from_version, to_version):
    """Upgrade data from one version to another.

    Parameters
    ----------
    from_version : str
        source version
    to_version : str
        target version

    """
    print("HERE WOULD COME CODE")


def main():
    """Main entry point for MyTraL CLI."""
    parser = argparse.ArgumentParser(
        description="MyTraL Command Line Interface",
        add_help=False,
    )
    parser.add_argument("command", nargs="?", help="Command to execute")
    parser.add_argument("subcommand", nargs="?", help="Subcommand to execute")
    parser.add_argument("--from", dest="from_version", help="Source version")
    parser.add_argument("--to", dest="to_version", help="Target version")

    args = parser.parse_args()

    if not args.command or args.command == "help":
        cmd_help()
        return 0

    if args.command == "import" and args.subcommand == "strava":
        cmd_import_strava()
        return 0

    if args.command == "upgrade":
        if not args.from_version or not args.to_version:
            print("Error: upgrade command requires --from and --to arguments")
            print("Example: mytral upgrade --from 1.0.0 --to 1.1.0")
            return 1
        cmd_upgrade(args.from_version, args.to_version)
        return 0

    print(f"Unknown command: {args.command}")
    print("Run 'mytral help' to see available commands")
    return 1


if __name__ == "__main__":
    sys.exit(main())
