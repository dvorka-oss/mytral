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
import json
import os
import pathlib
import traceback
import zipfile
from datetime import datetime
from typing import Any

import msgpack

from mytral import loggers

EXT_CSV = "csv"
EXT_JAY = "jay"
EXT_JSON = "json"
EXT_ZIP = "zip"
EXT_UNKNOWN = "unknown"

DIRNAME_WORK = "work"


def create_ts_filename(prefix: str = "_strava-export", ext: str = "json") -> str:
    now = datetime.now()
    ext = f".{ext}" if ext else ""
    return (
        f"{prefix}"
        f"-{now.year}{now.month:02}{now.day:02}"
        f"-{now.hour}h{now.minute}m{now.second}s{ext}"
    )


def create_user_work(user_dir: pathlib.Path) -> pathlib.Path:
    user_work_dir: pathlib.Path = user_dir / DIRNAME_WORK
    user_work_dir.mkdir(parents=True, exist_ok=True)
    return user_work_dir


def load_text(file_path: pathlib.Path | str) -> str:
    file_path = pathlib.Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Unable to load file: {file_path}")
    with open(file_path, "r") as file:
        data = file.read()
    return data


def save_json(file_path: pathlib.Path | str, data_dict: dict | list):
    file_path = pathlib.Path(file_path)
    with open(file_path, "w", encoding="utf-8") as file_handle:
        json.dump(obj=data_dict, fp=file_handle, indent=4, ensure_ascii=False)

    return file_path


def load_json(
    file_path: pathlib.Path | str, logger: loggers.MytralLogger | None = None
) -> dict | list:
    file_path = pathlib.Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Unable to load file: {file_path}")
    try:
        with open(file_path, "r", encoding="utf-8") as file_handle:
            data_dict = json.load(file_handle)
    except Exception as ex:
        ex.add_note(f"while loading JSON file {file_path}")
        logger: loggers.MytralLogger = logger or loggers.MytralStructLogger()
        logger.error(
            f"Unable to load JSON file '{file_path}': {ex}\n{traceback.format_exc()}"
        )
        raise

    return data_dict


def normalize_dict_or_list_to_dict(data: dict | list) -> dict:
    """Convert list to dict for backward compatibility.

    If data is already a dict (old format), return as-is.
    If data is a list (new format), convert to dict indexed by 'key' attribute.

    Parameters
    ----------
    data : dict | list
        Loaded JSON data in either old (dict) or new (list) format.

    Returns
    -------
    dict
        Dictionary indexed by entity keys for runtime use.

    """
    if isinstance(data, dict):
        # old format: already a dict, return as-is
        return data
    elif isinstance(data, list):
        # new format: convert list to dict indexed by 'key'
        # handle empty list
        if not data:
            return {}
        return {item["key"]: item for item in data}
    else:
        raise ValueError(f"Expected dict or list, got {type(data)}")


def zip_directory(directory_path: pathlib.Path, zip_file_path: pathlib.Path):
    with zipfile.ZipFile(zip_file_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for root, _, files in os.walk(directory_path):
            for file in files:
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, directory_path)
                zip_file.write(file_path, relative_path)


def save_dict(
    data: dict[str, Any], filepath: str, logger: loggers.MytralLogger | None = None
) -> bool:
    """Save a dictionary to a file using MessagePack serialization.

    Parameters
    ----------
    data : dict[str, Any]
        Dictionary to save
    filepath : str
        Path to the output file

    Returns
    -------
    bool
        True if successful, False otherwise
    """
    try:
        # create directory if it doesn't exist
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        # serialize and save the data
        with open(filepath, "wb") as f:
            f.write(msgpack.packb(data))
        return True
    except Exception as e:
        e.add_note(f"while saving dict to {filepath}")
        logger = logger or loggers.MytralStructLogger()
        logger.error(f"Error saving dictionary to {filepath}: {str(e)}")
        return False


def load_dict(
    filepath: str, logger: loggers.MytralLogger | None = None
) -> dict[str, Any] | None:
    """Load a dictionary from a MessagePack serialized file.

    Parameters
    ----------
    filepath : str
        Path to the input file

    Returns
    -------
    dict[str, Any] | None :
        Loaded dictionary if successful, None otherwise
    """
    try:
        if not os.path.exists(filepath):
            return None

        with open(filepath, "rb") as f:
            data = f.read()
            return msgpack.unpackb(data)
    except Exception as e:
        e.add_note(f"while loading dict from {filepath}")
        logger = logger or loggers.MytralStructLogger()
        logger.error(f"Error loading dictionary from {filepath}: {str(e)}")
        return None


def save_dict_to_bytes(
    data: dict[str, Any], logger: loggers.MytralLogger | None = None
) -> bytes | None:
    """Serialize a dictionary to MessagePack bytes.

    Parameters
    ----------
    data : dict[str, Any]
        Dictionary to serialize

    Returns
    -------
    bytes | None :
        Serialized data if successful, None otherwise
    """
    try:
        return msgpack.packb(data)
    except Exception as e:
        logger = logger or loggers.MytralStructLogger()
        logger.error(f"Error serializing dictionary to bytes: {str(e)}")
        return None


def load_dict_from_bytes(
    data: bytes, logger: loggers.MytralLogger | None = None
) -> dict[str, Any] | None:
    """Deserialize MessagePack bytes to a dictionary.

    Parameters
    ----------
    data : bytes
        MessagePack serialized bytes

    Returns
    -------
    dict[str, Any] | None :
        Deserialized dictionary if successful, None otherwise

    """
    try:
        return msgpack.unpackb(data)
    except Exception as e:
        logger = logger or loggers.MytralStructLogger()
        logger.error(f"Error deserializing bytes to dictionary: {str(e)}")
        return None
