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
import dataclasses
import datetime
import enum
import os
import pathlib
import random
import secrets
import sys

from mytral import persistences
from mytral import security
from mytral import utils
from mytral import version


class PersistenceType(enum.Enum):
    FILESYSTEM = enum.auto()

    # not supported yet:
    # RDBMS = enum.auto()
    # MEMORY = enum.auto()


class BlobStoreType(enum.Enum):
    FILESYSTEM = "filesystem"
    MINIO = "minio"
    S3 = "s3"


class HostPlatform(enum.Enum):
    LINUX = enum.auto()
    WINDOWS = enum.auto()
    MACOS = enum.auto()


class MytralIncarnation(enum.Enum):
    WEBAPP = enum.auto()  # default
    DESKTOP = enum.auto()


class MyTraLConfigPaths:
    """MyTraL filesystem configuration helps with OS-specific file system paths
    resolution:

     - The user DATA directory for activity JSON files (XDG_DATA_HOME on Linux).
     - The installation CONFIGURATION directory (must not be on data shared drive).
     - The cache / work directory with data which might be purged at any time.
     - The temporary directory for transient files.

    Platform-specific paths follow OS conventions and the XDG Base Directory
    Specification on Linux:

    - Linux:   data=``~/.local/share/mytral`` (``$XDG_DATA_HOME/mytral``),
               config=``~/.config/mytral`` (``$XDG_CONFIG_HOME/mytral``),
               cache=``~/.cache/mytral`` (``$XDG_CACHE_HOME/mytral``),
               tmp=``/tmp/mytral`` (or ``$TMPDIR/mytral`` if set)
    - macOS:   data=``~/Library/Application Support/mytral``,
               config=``~/Library/Application Support/mytral``,
               cache=``~/Library/Caches/mytral``,
               tmp=``$TMPDIR/mytral``
    - Windows: data=``%APPDATA%\\mytral``,
               config=``%APPDATA%\\mytral``,
               cache=``%LOCALAPPDATA%\\mytral\\cache``,
               tmp=``%TEMP%\\mytral``

    Attributes
    ----------
    platform : HostPlatform
        Detected or explicitly provided host platform.
    data_path : pathlib.Path
        Platform-specific user data directory for MyTraL (activity JSON files).
        On Linux this follows XDG_DATA_HOME (defaults to ``~/.local/share/mytral``).
    config_path : pathlib.Path
        Platform-specific configuration directory for MyTraL.
    work_path : pathlib.Path
        Platform-specific cache / work directory for MyTraL.
    tmp_path : pathlib.Path
        Platform-specific temporary directory for MyTraL.
    """

    # Cross-desktop group (XDG) Base Directory Specification
    # (https://specifications.freedesktop.org/basedir-spec/latest/)
    # ──────────────────────────────────────────────────────────────────────────────────
    # Purpose        Env variable        Linux default           MyTraL subdirectory
    # ───────────── ─────────────────── ─────────────────────── ────────────────────────
    # User data      XDG_DATA_HOME       ~/.local/share          ~/.local/share/mytral/
    # Config         XDG_CONFIG_HOME     ~/.config               ~/.config/mytral/
    # Cache / work   XDG_CACHE_HOME      ~/.cache                ~/.cache/mytral/
    # State (logs.)  XDG_STATE_HOME      ~/.local/state          ~/.local/state/mytral/
    # Tmp files      TMPDIR              /tmp                    /tmp/mytral/
    # ──────────────────────────────────────────────────────────────────────────────────

    APP_NAME = "mytral"

    @staticmethod
    def detect_platform() -> HostPlatform:
        """Detect the host operating system platform.

        Returns
        -------
        HostPlatform
            Detected platform enum value.

        Raises
        ------
        RuntimeError
            If the platform cannot be determined.
        """
        if sys.platform.startswith("linux"):
            return HostPlatform.LINUX
        elif sys.platform == "darwin":
            return HostPlatform.MACOS
        elif sys.platform in ("win32", "cygwin"):
            return HostPlatform.WINDOWS
        raise RuntimeError(f"unsupported platform: {sys.platform}")

    def __init__(self, platform: HostPlatform | None = None):
        self.platform = platform or self.detect_platform()
        self.data_path = self._get_data_path()
        self.config_path = self._get_config_path()
        self.work_path = self._get_work_path()
        self.tmp_path = self._get_tmp_path()

    def _get_data_path(self) -> pathlib.Path:
        """Return the platform-specific user data directory path.

        On Linux this follows the XDG Base Directory Specification and uses
        ``XDG_DATA_HOME`` (defaulting to ``~/.local/share``).

        Returns
        -------
        pathlib.Path
            Path to the MyTraL user data directory.
        """
        if self.platform == HostPlatform.LINUX:
            xdg_data = os.environ.get("XDG_DATA_HOME", "")
            base = (
                pathlib.Path(xdg_data)
                if xdg_data
                else pathlib.Path.home() / ".local" / "share"
            )
            return base / self.APP_NAME
        elif self.platform == HostPlatform.MACOS:
            return (
                pathlib.Path.home() / "Library" / "Application Support" / self.APP_NAME
            )
        elif self.platform == HostPlatform.WINDOWS:
            appdata = os.environ.get("APPDATA", "")
            base = (
                pathlib.Path(appdata)
                if appdata
                else pathlib.Path.home() / "AppData" / "Roaming"
            )
            return base / self.APP_NAME
        raise ValueError(f"unsupported platform: {self.platform}")

    def _get_config_path(self) -> pathlib.Path:
        """Return the platform-specific configuration directory path.

        Returns
        -------
        pathlib.Path
            Path to the MyTraL configuration directory.
        """
        if self.platform == HostPlatform.LINUX:
            xdg_config = os.environ.get("XDG_CONFIG_HOME", "")
            base = (
                pathlib.Path(xdg_config)
                if xdg_config
                else pathlib.Path.home() / ".config"
            )
            return base / self.APP_NAME
        elif self.platform == HostPlatform.MACOS:
            return (
                pathlib.Path.home() / "Library" / "Application Support" / self.APP_NAME
            )
        elif self.platform == HostPlatform.WINDOWS:
            appdata = os.environ.get("APPDATA", "")
            base = (
                pathlib.Path(appdata)
                if appdata
                else pathlib.Path.home() / "AppData" / "Roaming"
            )
            return base / self.APP_NAME
        raise ValueError(f"unsupported platform: {self.platform}")

    def _get_work_path(self) -> pathlib.Path:
        """Return the platform-specific work / cache directory path.

        Returns
        -------
        pathlib.Path
            Path to the MyTraL cache directory.
        """
        if self.platform == HostPlatform.LINUX:
            xdg_cache = os.environ.get("XDG_CACHE_HOME", "")
            base = (
                pathlib.Path(xdg_cache) if xdg_cache else pathlib.Path.home() / ".cache"
            )
            return base / self.APP_NAME
        elif self.platform == HostPlatform.MACOS:
            return pathlib.Path.home() / "Library" / "Caches" / self.APP_NAME
        elif self.platform == HostPlatform.WINDOWS:
            localappdata = os.environ.get("LOCALAPPDATA", "")
            base = (
                pathlib.Path(localappdata)
                if localappdata
                else pathlib.Path.home() / "AppData" / "Local"
            )
            return base / self.APP_NAME / "cache"
        raise ValueError(f"unsupported platform: {self.platform}")

    def _get_tmp_path(self) -> pathlib.Path:
        """Return the platform-specific temporary directory path.

        Returns
        -------
        pathlib.Path
            Path to the MyTraL temporary directory.
        """
        if self.platform == HostPlatform.LINUX:
            tmpdir = os.environ.get("TMPDIR", "")
            base = pathlib.Path(tmpdir) if tmpdir else pathlib.Path("/tmp")
            return base / self.APP_NAME
        elif self.platform == HostPlatform.MACOS:
            tmpdir = os.environ.get("TMPDIR", "")
            base = pathlib.Path(tmpdir) if tmpdir else pathlib.Path("/tmp")
            return base / self.APP_NAME
        elif self.platform == HostPlatform.WINDOWS:
            temp = os.environ.get("TEMP", "") or os.environ.get("TMP", "")
            base = (
                pathlib.Path(temp)
                if temp
                else pathlib.Path.home() / "AppData" / "Local" / "Temp"
            )
            return base / self.APP_NAME
        raise ValueError(f"unsupported platform: {self.platform}")

    def create_dirs(self) -> None:
        """Create data, config, cache and temp directories for MyTraL."""
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.config_path.mkdir(parents=True, exist_ok=True)
        self.work_path.mkdir(parents=True, exist_ok=True)
        self.tmp_path.mkdir(parents=True, exist_ok=True)


#
# CONFIG: web app
#


class MytralConfig:
    """MyTraL configuration.

    Attributes
    ----------
    instance_id : str
        Unique identifier for this application instance. The purpose of this
        attribute is to uniquely identify MyTraL server instance in serverless /
        stateless deployments.
    boot_at : str
        Timestamp when the application was started, in ISO format or as a UNIX
        timestamp string. The purpose of this attribute is MyTraL debugging
        in stateless deployments.
    port : int
        MyTraL application port. When 0 (default), resolved from the
        MYTRAL_PORT environment variable; falls back to DEFAULT_PORT when
        the env var is not set or explicitly passed.
    persistence_type : PersistenceType
        Persistence type - file system, database, memory, ...
    persistence_data_dir : Path | None
        Application file system root. The path is expected to be directory which
        contains ``data`` directory.
        If the constructor parameter is not set, then the constructor will try to get
        ``MYTRAL_DATA_DIR`` environment variable value. If env variable is not set or
        directory does not exist, then it fallbacks to the platform-specific user data
        directory (``XDG_DATA_HOME/mytral`` on Linux, i.e. ``~/.local/share/mytral``).
        The structure of the persistence based directory is expected to be:
        ``[persistence_data_dir]/data/[user UUID]/*.json``
    persistence_cache : bool | None
        Enable in-memory caching of user data. When True (default), data is cached
        for performance. When False, all data is loaded from filesystem on every
        request - use this in autoscaling environments with multiple server instances
        sharing the same filesystem to ensure data consistency across instances.
        Can be controlled via MYTRAL_ENABLE_CACHE environment variable (set to
        "false" to disable caching).
    auto_account_creation : bool | None
        Whether to allow automatic creation of new user accounts when an unknow user
        logs in to MyTraL, or whether to refuse user login (default). This is useful
        for local development where developer wants to skip the registration.
        If the constructor parameter is ``False``, then the constructor tries to get
        ``MYTRAL_AUTO_ACCOUNT_CREATE`` environment variable value.
    user_registration : bool | None
        Allow new users to register via /signup page. When False, only existing
        users can log in and auto_account_create during login may still work.
        This is useful for production deployments to control who can create accounts.
    encryption_key : str
        Configuration encryption key. When empty, read from MYTRAL_ENCRYPTION_KEY
        env var; falls back to a random key when the env var is not set (sensitive
        data in the configuration will not be decrypted).
    signing_key : str
        Flask session signing key. When empty, read from MYTRAL_SIGNING_KEY env var;
        falls back to a random key when the env var is not set (sessions lost on
        restart).
    cors_origins : list[str]
        Allowed CORS origins. When None, read from MYTRAL_CORS_ORIGINS env var;
        defaults to ["http://localhost:5000"] when the env var is not set.
    task_timeout : int
        Task timeout in seconds.
    debug : bool
        Whether to run Flask application in debug or production mode.

    """

    # environment variables
    ENV_MYTRAL_HOST = "MYTRAL_HOST"  # bind address for the Flask server
    ENV_MYTRAL_PORT = "MYTRAL_PORT"  # bind port for the application server
    ENV_MYTRAL_CORS_ORIGINS = (
        "MYTRAL_CORS_ORIGINS"  # comma-separated allowed CORS origins
        # e.g. MYTRAL_CORS_ORIGINS=https://mytral.fitness,https://www.mytral.fitness
    )
    ENV_MYTRAL_DATA_DIR = "MYTRAL_DATA_DIR"  # path to persistence dir w/ 'data' subdir
    ENV_MYTRAL_PERSISTENCE_CACHE = "MYTRAL_PERSISTENCE_CACHE"  # bool
    ENV_MYTRAL_AUTO_ACCOUNT_CREATE = "MYTRAL_AUTO_ACCOUNT_CREATE"  # bool
    ENV_MYTRAL_USER_REGISTRATION = "MYTRAL_USER_REGISTRATION"  # bool
    ENV_MYTRAL_ENCRYPTION_KEY = "MYTRAL_ENCRYPTION_KEY"  # configuration encryption key
    ENV_MYTRAL_SIGNING_KEY = "MYTRAL_SIGNING_KEY"  # Flask session signing key
    ENV_TASK_TIMEOUT = "MYTRAL_TASK_TIMEOUT"  # task timeout in seconds
    ENV_MYTRAL_INCARNATION = "MYTRAL_INCARNATION"  # desktop / webapp / ...
    ENV_MYTRAL_DEBUG = "MYTRAL_DEBUG"  # enable Flask debug mode (development only)
    ENV_MYTRAL_BLOBSTORE_TYPE = "MYTRAL_BLOBSTORE_TYPE"
    ENV_MYTRAL_BLOBSTORE_MINIO_ENDPOINT = "MYTRAL_BLOBSTORE_MINIO_ENDPOINT"
    ENV_MYTRAL_BLOBSTORE_MINIO_ACCESS_KEY = "MYTRAL_BLOBSTORE_MINIO_ACCESS_KEY"
    ENV_MYTRAL_BLOBSTORE_MINIO_SECRET_KEY = "MYTRAL_BLOBSTORE_MINIO_SECRET_KEY"
    ENV_MYTRAL_BLOBSTORE_MINIO_BUCKET = "MYTRAL_BLOBSTORE_MINIO_BUCKET"
    ENV_MYTRAL_BLOBSTORE_MINIO_SECURE = "MYTRAL_BLOBSTORE_MINIO_SECURE"
    ENV_MYTRAL_BLOBSTORE_S3_REGION = "MYTRAL_BLOBSTORE_S3_REGION"
    ENV_MYTRAL_BLOBSTORE_S3_BUCKET = "MYTRAL_BLOBSTORE_S3_BUCKET"
    ENV_MYTRAL_BLOBSTORE_S3_ACCESS_KEY = "MYTRAL_BLOBSTORE_S3_ACCESS_KEY"
    ENV_MYTRAL_BLOBSTORE_S3_SECRET_KEY = "MYTRAL_BLOBSTORE_S3_SECRET_KEY"
    ENV_MYTRAL_BLOBSTORE_S3_SESSION_TOKEN = "MYTRAL_BLOBSTORE_S3_SESSION_TOKEN"

    # environment variable values
    ENV_VALUE_TRUE = "true"
    ENV_VALUE_FALSE = "false"

    # defaults
    DEFAULT_HOST: str = "127.0.0.1"
    DEFAULT_PORT: int = 5000
    DEFAULT_TASK_TIMEOUT: int = 3600

    @staticmethod
    def gen_takenoko(syllables=4) -> str:
        consonants = "bcdfghjklmnpqrstvwxyz"
        vowels = "aeiou"
        return "".join(
            random.choice(consonants) + random.choice(vowels) for _ in range(syllables)
        )

    @property
    def user_data_dir(self) -> pathlib.Path:
        return self.persistence_data_dir / "data"

    def __init__(
        self,
        instance_id: str = "",
        boot_at: str = "",
        host: str = "",
        port: int = 0,
        cors_origins: list[str] | None = None,
        persistence_type: PersistenceType = PersistenceType.FILESYSTEM,
        persistence_data_dir: pathlib.Path | None = None,
        persistence_cache: bool | None = None,
        auto_account_create: bool | None = None,
        user_registration: bool | None = None,
        encryption_key: str = "",
        signing_key: str = "",
        task_timeout: int = DEFAULT_TASK_TIMEOUT,
        incarnation: MytralIncarnation | None = None,
        debug: bool | None = None,
    ) -> None:
        """MyTraL application configuration constructor."""
        # collected during __init__ so they can be emitted via print()
        self._init_warnings: list[str] = []

        self.instance_id = instance_id or MytralConfig.gen_takenoko()
        self.boot_at = boot_at or str(datetime.datetime.now())
        # port resolution: explicit (non-zero) > MYTRAL_PORT env var > DEFAULT_PORT
        if port != 0:
            self.port = port
        else:
            port_env = os.getenv(MytralConfig.ENV_MYTRAL_PORT)
            if port_env is not None:
                try:
                    self.port = int(port_env)
                except ValueError:
                    self._init_warnings.append(
                        f"Invalid {MytralConfig.ENV_MYTRAL_PORT} value '{port_env}', "
                        f"using default port {MytralConfig.DEFAULT_PORT}"
                    )
                    self.port = MytralConfig.DEFAULT_PORT
            else:
                self.port = MytralConfig.DEFAULT_PORT
        self.persistence_type = persistence_type

        # debug mode
        if debug is None:
            self.debug = utils.getenv_bool(
                MytralConfig.ENV_MYTRAL_DEBUG, default=bool(debug)
            )
        else:
            self.debug = bool(debug)

        # MyTraL incarnation
        if incarnation is None:
            self.incarnation = (
                MytralIncarnation.DESKTOP
                if os.getenv(MytralConfig.ENV_MYTRAL_INCARNATION)
                == MytralIncarnation.DESKTOP.name
                else MytralIncarnation.WEBAPP
            )
        else:
            self.incarnation = incarnation

        # host
        # - bind to 127.0.0.1 by default
        # - set MYTRAL_HOST=0.0.0.0 for intentional external exposure - CAN BE DANGEROUS
        if not host:
            host_env = os.environ.get(
                MytralConfig.ENV_MYTRAL_HOST, MytralConfig.DEFAULT_HOST
            )
            self.host = host_env
        else:
            self.host = host
            # host safety check
            if self.debug and host not in (
                MytralConfig.DEFAULT_HOST,
                "localhost",
                "::1",
            ):
                raise RuntimeError(
                    f"Refusing to start with debug=True on non-loopback host '{host}'. "
                    "Set MYTRAL_HOST to a loopback address or disable debug mode."
                )

        # config, work and tmp paths
        self.paths = MyTraLConfigPaths()

        # persistence data directory
        if persistence_data_dir is None:
            persistence_data_dir_env = os.getenv(MytralConfig.ENV_MYTRAL_DATA_DIR, "")
            self.persistence_data_dir = (
                pathlib.Path(persistence_data_dir_env).absolute()
                if os.getenv(MytralConfig.ENV_MYTRAL_DATA_DIR)
                else self.paths.data_path
            )
        else:
            self.persistence_data_dir = pathlib.Path(persistence_data_dir).absolute()

        # allow auto account creation for development
        if auto_account_create is None:
            self.auto_account_creation = utils.getenv_bool(
                MytralConfig.ENV_MYTRAL_AUTO_ACCOUNT_CREATE
            )
        else:
            self.auto_account_creation = bool(auto_account_create)

        # allow user registration
        if user_registration is None:
            self.user_registration = utils.getenv_bool(
                MytralConfig.ENV_MYTRAL_USER_REGISTRATION
            )
        else:
            self.user_registration = bool(user_registration)

        # enable in-memory cache for the persistence
        if persistence_cache is None:
            self.persistence_cache = utils.getenv_bool(
                MytralConfig.ENV_MYTRAL_PERSISTENCE_CACHE, default=True
            )
        else:
            self.persistence_cache = bool(persistence_cache)

        # encryption key for sensitive configuration values like API keys
        # - IF the key is not specified (arg or env var),
        #   THEN use DEVELOPMENT key if in debug mode,
        #   otherwise raise error - production deployments MUST specify the key
        if encryption_key:
            self.encryption_key = encryption_key
        else:
            encryption_key_env = os.environ.get(
                MytralConfig.ENV_MYTRAL_ENCRYPTION_KEY, ""
            )
            if encryption_key_env:
                self.encryption_key = encryption_key_env
            else:
                if self.debug:
                    self.encryption_key = security.DEFAULT_ENC_KEY
                    self._init_warnings.append(
                        "MYTRAL_ENCRYPTION_KEY is not set - because MyTraL is running "
                        "in the DEBUG mode, DEFAULT DEVELOPMENT key may be used as "
                        "a fallback. However, this is NOT SECURE and should NEVER be "
                        "used in production. Set MYTRAL_ENCRYPTION_KEY in environment "
                        "for stable encryption."
                    )
                elif self.incarnation == MytralIncarnation.DESKTOP:
                    self.encryption_key = security.DEFAULT_ENC_KEY
                    self._init_warnings.append(
                        "MYTRAL_ENCRYPTION_KEY is not set - the DEFAULT DEVELOPMENT"
                        "key will be used as a fall back. "
                        "This is NOT SECURE and should NEVER be used in production. Set"
                        " MYTRAL_ENCRYPTION_KEY in environment for stable encryption."
                    )
                else:
                    raise RuntimeError(
                        "MYTRAL_ENCRYPTION_KEY is not set - this is required for "
                        "production deployments. "
                        "Set MYTRAL_ENCRYPTION_KEY in environment for stable "
                        "encryption."
                    )

        # Flask session signing key - if not set, sessions are lost on every restart
        if signing_key:
            self.signing_key = signing_key
        else:
            signing_key_env = os.environ.get(MytralConfig.ENV_MYTRAL_SIGNING_KEY, "")
            if signing_key_env:
                self.signing_key = signing_key_env
            else:
                self.signing_key = secrets.token_hex(32)
                self._init_warnings.append(
                    "MYTRAL_SIGNING_KEY is not set - using a random key. "
                    "All Flask sessions will be invalidated on restart. "
                    "Set MYTRAL_SIGNING_KEY in environment for persistent sessions."
                )

        #  CORS origins ~ list of strings w/ allowed CORS origins for the API
        #  e.g. "http://localhost:3000,https://mytral.fitness"
        if cors_origins:
            self.cors_origins = cors_origins
        else:
            cors_origins_env = os.getenv(MytralConfig.ENV_MYTRAL_CORS_ORIGINS, "")
            if not cors_origins_env:
                self._init_warnings.append(
                    "MYTRAL_CORS_ORIGINS is not set - defaulting to "
                    "http://localhost:5000. "
                    "Set MYTRAL_CORS_ORIGINS in environment for production deployments."
                )
            cors_origins_raw = (cors_origins_env or "http://localhost:5000").split(",")
            self.cors_origins = [o.strip() for o in cors_origins_raw if o.strip()]

        self.task_timeout = task_timeout or MytralConfig.DEFAULT_TASK_TIMEOUT

        # blobstore configuration
        blobstore_type_raw = os.environ.get(
            MytralConfig.ENV_MYTRAL_BLOBSTORE_TYPE, BlobStoreType.FILESYSTEM.value
        )
        try:
            self.blobstore_type: BlobStoreType = BlobStoreType(blobstore_type_raw)
        except ValueError:
            self.blobstore_type = BlobStoreType.FILESYSTEM

        # filesystem blobstore
        self.blobstore_filesystem_subdir: str = "blobs"

        # upload size limits
        # 20 MiB: typical GPX files are 100–500 KB; 20 MiB covers ultra-marathon
        # tracks with 1-second polling (~10 MB) plus a generous safety margin
        self.blobstore_max_gpx_size_bytes: int = 20 * 1024 * 1024
        # 5 MiB: FIT files are compact binary; 5 MiB covers ~8 hours of 5-second polling
        self.blobstore_max_fit_size_bytes: int = 5 * 1024 * 1024
        # 64 MiB: covers FIT, GPX and HRM; GPX ultra tracks can be large
        self.blobstore_max_recording_size_bytes: int = 64 * 1024 * 1024
        # 25 MiB: covers modern smartphone RAW-quality JPEGs while keeping
        # individual upload latency acceptable on slower connections
        self.blobstore_max_photo_size_bytes: int = 25 * 1024 * 1024
        # 50 photos per activity: one batch per session, prevents runaway storage
        self.blobstore_max_photo_count_per_activity: int = 50
        # 250 MiB per request: allows a full batch of 10 × 25 MiB photos at once
        self.blobstore_max_photo_request_bytes: int = 250 * 1024 * 1024
        # 4096 px: preserves quality for large-screen display without wasting space
        self.blobstore_photo_max_dimension_px: int = 4096
        # 1440 px: sharp feed-card display up to 720 CSS px wide on 2× HiDPI screens
        self.blobstore_thumbnail_max_dimension_px: int = 1440

        # MinIO blobstore
        self.blobstore_minio_endpoint: str = os.environ.get(
            MytralConfig.ENV_MYTRAL_BLOBSTORE_MINIO_ENDPOINT, ""
        )
        self.blobstore_minio_access_key: str = os.environ.get(
            MytralConfig.ENV_MYTRAL_BLOBSTORE_MINIO_ACCESS_KEY, ""
        )
        self.blobstore_minio_secret_key: str = os.environ.get(
            MytralConfig.ENV_MYTRAL_BLOBSTORE_MINIO_SECRET_KEY, ""
        )
        self.blobstore_minio_bucket: str = os.environ.get(
            MytralConfig.ENV_MYTRAL_BLOBSTORE_MINIO_BUCKET, "mytral-blobs"
        )
        self.blobstore_minio_secure: bool = (
            os.environ.get(
                MytralConfig.ENV_MYTRAL_BLOBSTORE_MINIO_SECURE, "false"
            ).lower()
            == MytralConfig.ENV_VALUE_TRUE
        )

        # AWS S3 blobstore
        self.blobstore_s3_region: str = os.environ.get(
            MytralConfig.ENV_MYTRAL_BLOBSTORE_S3_REGION, ""
        )
        self.blobstore_s3_bucket: str = os.environ.get(
            MytralConfig.ENV_MYTRAL_BLOBSTORE_S3_BUCKET, ""
        )
        self.blobstore_s3_access_key: str = os.environ.get(
            MytralConfig.ENV_MYTRAL_BLOBSTORE_S3_ACCESS_KEY, ""
        )
        self.blobstore_s3_secret_key: str = os.environ.get(
            MytralConfig.ENV_MYTRAL_BLOBSTORE_S3_SECRET_KEY, ""
        )
        self.blobstore_s3_session_token: str = os.environ.get(
            MytralConfig.ENV_MYTRAL_BLOBSTORE_S3_SESSION_TOKEN, ""
        )

    def print(self, logger) -> None:
        logger.info("MyTraL configuration:")
        logger.info(f" - incarnation             : {self.incarnation.name}")
        logger.info(f" - instance_id             : {self.instance_id}")
        logger.info(f" - boot_at                 : {self.boot_at}")
        logger.info(f" - host                    : {self.host}")
        logger.info(f" - port                    : {self.port}")
        logger.info(f" - cors_origins            : {self.cors_origins}")

        logger.info(f" - persistence type        : {self.persistence_type.name}")
        logger.info(f" - persistence data dir    : {self.persistence_data_dir}")
        logger.info(f" - persistence usr data dir: {self.user_data_dir}")
        logger.info(f" - persistence config dir  : {self.paths.config_path}")
        logger.info(f" - persistence work dir    : {self.paths.work_path}")
        logger.info(f" - persistence tmp dir     : {self.paths.tmp_path}")
        logger.info(f" - persistence cache       : {self.persistence_cache}")

        logger.info(f" - blobstore_type          : {self.blobstore_type.value}")

        if self.blobstore_type.value == BlobStoreType.MINIO.value:
            logger.info(f" - blobstore_minio_endpoint: {self.blobstore_minio_endpoint}")
            logger.info(f" - blobstore_minio_bucket  : {self.blobstore_minio_bucket}")
            logger.info(f" - blobstore_minio_secure  : {self.blobstore_minio_secure}")
            key_status = "(set)" if self.blobstore_minio_access_key else "(not set)"
            logger.info(f" - blobstore_minio_access_key: {key_status}")
            key_status = "(set)" if self.blobstore_minio_secret_key else "(not set)"
            logger.info(f" - blobstore_minio_secret_key: {key_status}")
        elif self.blobstore_type.value == BlobStoreType.S3.value:
            logger.info(f" - blobstore_s3_region     : {self.blobstore_s3_region}")
            logger.info(f" - blobstore_s3_bucket     : {self.blobstore_s3_bucket}")
            key_status = "(set)" if self.blobstore_s3_access_key else "(not set)"
            logger.info(f" - blobstore_s3_access_key : {key_status}")
            key_status = "(set)" if self.blobstore_s3_secret_key else "(not set)"
            logger.info(f" - blobstore_s3_secret_key : {key_status}")
            key_status = "(set)" if self.blobstore_s3_session_token else "(not set)"
            logger.info(f" - blobstore_s3_session_token : {key_status}")

        logger.info(f" - auto_account_creation   : {self.auto_account_creation}")
        logger.info(f" - user_registration       : {self.user_registration}")

        encryption_key_status = (
            f"(set {self.encryption_key})"
            if self.encryption_key and self.encryption_key != security.DEFAULT_ENC_KEY
            else "(not set - using default)"
        )
        logger.info(f" - encryption_key          : {encryption_key_status}")
        signing_key_status = "(set)" if self.signing_key else "(not set)"
        logger.info(f" - signing_key             : {signing_key_status}")

        logger.info(f" - task_timeout            : {self.task_timeout}")
        logger.info(f" - debug                   : {self.debug}")
        if self._init_warnings:
            logger.info("MyTraL configuration WARNINGS:")
            for warning in self._init_warnings:
                logger.warning(f" - {warning}")


#
# CONFIG: filesystem persistence
#


@dataclasses.dataclass
class PersistenceEntry:
    """Persistence entry descriptor with type and specification version.

    Attributes
    ----------
    type : str
        Persistence type identifier (e.g. "filesystem").
    specification : str
        Specification version string.
    """

    KEY_TYPE = "type"
    KEY_SPECIFICATION = "specification"

    type: str
    specification: str


@dataclasses.dataclass
class PersistenceConfig:
    """Persistence configuration for data and blobstore backends.

    Attributes
    ----------
    data : PersistenceEntry
        Data persistence configuration.
    blobstore : PersistenceEntry
        Blobstore persistence configuration.
    """

    KEY_DATA = "data"
    KEY_BLOBSTORE = "blobstore"

    data: PersistenceEntry
    blobstore: PersistenceEntry


@dataclasses.dataclass
class MytralMeta:
    """MyTraL metadata section of the persistence filesystem configuration.

    Attributes
    ----------
    version : str
        MyTraL version string.
    persistence : PersistenceConfig
        Persistence backend configuration.
    """

    KEY_VERSION = "version"
    KEY_PERSISTENCE = "persistence"

    version: str
    persistence: PersistenceConfig


@dataclasses.dataclass
class DatasetInfo:
    """Dataset metadata describing creation, modification and revision.

    Attributes
    ----------
    created : str
        Dataset creation timestamp.
    modified : str
        Dataset last modification timestamp.
    revision : int
        Dataset revision number.
    """

    KEY_CREATED = "created"
    KEY_MODIFIED = "modified"
    KEY_REVISION = "revision"

    created: str
    modified: str
    revision: int


@dataclasses.dataclass
class MytralPersistenceFsConfigBean:
    """MyTraL persistence filesystem configuration dataclass.

    Maps the JSON descriptor stored alongside persisted data that records
    the MyTraL version, persistence backend setup, and dataset metadata.

    Example
    -------
    ${MYTRAL_DATA_DIR}/data/config.json

    {
        "mytral": {
            "version": "1.9.0dev",
            "persistence": {
                "data": {
                    "type": "filesystem",
                    "specification": "1.8.0"
                },
                "blobstore": {
                    "type": "filesystem",
                    "specification": "1.8.0"
                }
            }
        },
            "dataset": {
                "created": "2024-05-27 14:25",
                "modified": "2026-05-27 14:25",
                "revision": 14345
            }
    }

    Attributes
    ----------
    mytral : MytralMeta
        MyTraL metadata including version and persistence configuration.
    dataset : DatasetInfo
        Dataset metadata including creation, modification and revision.
    """

    KEY_MYTRAL = "mytral"
    KEY_DATASET = "dataset"

    mytral: MytralMeta
    dataset: DatasetInfo


class MytralPersistenceFsConfig:
    FILENAME_CFG = "config.json"

    # class-level migration cache — survives across instances
    _migrate_cache: bool | None = None
    _cached_data_spec_version: str | None = None

    @staticmethod
    def _parse_version(version_str: str) -> tuple[int, int, int]:
        """Parse a semantic version string into (major, minor, patch) integers.

        The patch component may contain a non-digit suffix (e.g. "0dev")
        which is stripped.
        """
        parts = version_str.split(".")
        major = int(parts[0])
        minor = int(parts[1])
        # patch may contain non-digit suffix (e.g. "0dev") - extract leading digits
        patch_str = parts[2]
        patch_digits = ""
        for c in patch_str:
            if c.isdigit():
                patch_digits += c
            else:
                break
        patch = int(patch_digits) if patch_digits else 0
        return major, minor, patch

    @property
    def data_spec_version(self):
        return self._data_spec_version

    @property
    def mytral_version(self):
        return self._mytral_version

    def __init__(self, mytral_config: MytralConfig):
        self._log_name = "[MyTraL persistence filesystem config]"
        self._mytral_version = version.__version__
        (
            self._mytral_version_major,
            self._mytral_version_minor,
            self._mytral_version_patch,
        ) = self._parse_version(self._mytral_version)
        self._data_spec_version = ""
        self._mytral_config = mytral_config

        # if the cache is warm, skip the disk read
        if MytralPersistenceFsConfig._migrate_cache is not None:
            self._data_spec_version = (
                MytralPersistenceFsConfig._cached_data_spec_version or ""
            )
            return

        # load data spec version right away
        self._cfg_path = (
            self._mytral_config.persistence_data_dir / "data" / self.FILENAME_CFG
        )
        if not self._cfg_path.exists():
            self._config_save(self._get_initial_config())
        cfg = self._config_load()
        self._data_spec_version = cfg.mytral.persistence.data.specification
        if "." not in self._data_spec_version:
            raise ValueError(
                f"{self._log_name} data spec version is invalid: "
                f"'{self._data_spec_version}'"
            )

        # populate the class-level cache after the first disk read
        MytralPersistenceFsConfig._migrate_cache = self.is_migrate()
        MytralPersistenceFsConfig._cached_data_spec_version = self._data_spec_version

    def _get_initial_config(self) -> MytralPersistenceFsConfigBean:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        return MytralPersistenceFsConfigBean(
            mytral=MytralMeta(
                version=self._mytral_version,
                persistence=PersistenceConfig(
                    data=PersistenceEntry(
                        type="filesystem",
                        specification=(
                            f"{self._mytral_version_major}."
                            f"{self._mytral_version_minor}."
                            f"{self._mytral_version_patch}"
                        ),
                    ),
                    blobstore=PersistenceEntry(
                        type="filesystem",
                        specification=(
                            f"{self._mytral_version_major}."
                            f"{self._mytral_version_minor}."
                            f"{self._mytral_version_patch}"
                        ),
                    ),
                ),
            ),
            dataset=DatasetInfo(
                created=now,
                modified=now,
                revision=1,
            ),
        )

    def _config_load(self) -> MytralPersistenceFsConfigBean:
        """Load persistence config from disk."""
        raw_data = persistences.load_json(self._cfg_path)

        if not isinstance(raw_data, dict):
            raise ValueError(
                f"{self._log_name} Expected a JSON object/dict from config file, "
                f"got {type(raw_data).__name__}"
            )

        return MytralPersistenceFsConfigBean(
            mytral=MytralMeta(
                version=raw_data[MytralPersistenceFsConfigBean.KEY_MYTRAL][
                    MytralMeta.KEY_VERSION
                ],
                persistence=PersistenceConfig(
                    data=PersistenceEntry(
                        **raw_data[MytralPersistenceFsConfigBean.KEY_MYTRAL][
                            MytralMeta.KEY_PERSISTENCE
                        ][PersistenceConfig.KEY_DATA]
                    ),
                    blobstore=PersistenceEntry(
                        **raw_data[MytralPersistenceFsConfigBean.KEY_MYTRAL][
                            MytralMeta.KEY_PERSISTENCE
                        ][PersistenceConfig.KEY_BLOBSTORE]
                    ),
                ),
            ),
            dataset=DatasetInfo(**raw_data[MytralPersistenceFsConfigBean.KEY_DATASET]),
        )

    def _config_save(self, cfg: MytralPersistenceFsConfigBean) -> None:
        """Save persistence config to disk."""
        persistences.save_json(self._cfg_path, dataclasses.asdict(cfg))

    @classmethod
    def invalidate_cache(cls) -> None:
        """Invalidate the migration cache.

        Forces the next instantiation to read config.json from disk and
        re-compute the migration status.
        """
        cls._migrate_cache = None
        cls._cached_data_spec_version = None

    def update_data_spec_version(self) -> None:
        """Update data spec version in config.json after a successful migration.

        Reads the current config from disk, updates the data specification
        to match the running mytral version, bumps the dataset revision
        and modified timestamp, then saves back to disk.
        """
        new_spec = (
            f"{self._mytral_version_major}."
            f"{self._mytral_version_minor}."
            f"{self._mytral_version_patch}"
        )
        cfg = self._config_load()
        cfg.mytral.version = self._mytral_version
        cfg.mytral.persistence.data.specification = new_spec
        cfg.dataset.modified = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        cfg.dataset.revision += 1
        self._config_save(cfg)
        self._data_spec_version = new_spec

    def is_migrate(
        self,
    ) -> bool:
        """Determine whether the data specification version is older than mytral.

        Returns
        -------
        bool
            True if data_spec_version is semantically lower than the running
            mytral version and a migration is needed.
        """
        spec_major, spec_minor, spec_patch = self._parse_version(
            self._data_spec_version
        )
        return (spec_major, spec_minor, spec_patch) < (
            self._mytral_version_major,
            self._mytral_version_minor,
            self._mytral_version_patch,
        )
