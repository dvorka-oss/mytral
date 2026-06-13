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

"""MyTraL main module: configure and start the web application."""

from mytral import blobstore as _blobstore_pkg
from mytral import config
from mytral import loggers
from mytral import releng
from mytral.backends import dataset
from mytral.tasks import manager as task_manager

#
# MyTraL CODE CONVENTIONS
#
# TYPE HINTS
# - Python 3.11 features (lower case, |, Self, NotRequired, generics)

#
# application singletons
#

# feature flags
ff = releng.FeatureFlags()

# configuration — must be created first so debug flag is available for structlog
app_config = config.MytralConfig(
    port=0,  # let config resolve: MYTRAL_PORT env var > DEFAULT_PORT
    persistence_data_dir=None,  # let config use env var or default
    auto_account_create=None,  # let config use env var or default
    user_registration=None,  # let config use env var or default
    persistence_cache=None,  # let config use env var or default
    encryption_key="",  # let config use env var or default
    signing_key="",  # let config use env var or default
    # task_timeout -let config use env var or default
    debug=None,  # let config use env var or default
)

# configure structlog globally — must happen before any logger is obtained
loggers.configure_structlog(
    debug=app_config.debug or app_config.incarnation == config.MytralIncarnation.DESKTOP
)
app_logger = loggers.MytralStructLogger().bind(
    instance_id=app_config.instance_id,
)

# config, work and temp sandboxes
app_config.paths.create_dirs()

app_config.print(logger=app_logger)
ff.print(logger=app_logger)

# MyTraL dataset @ configured persistence (filesystem, RDBMS, ...)
app_ds = dataset.MyTraLDataset(mytral_config=app_config, logger=app_logger)
# MyTraL user dataset: persistence agnostic access to the user data
app_user_ds = app_ds.user()
# blob store for activity attachments (GPX files and photos)
app_blobstore = _blobstore_pkg.create_blobstore(app_config)

# MyTraL task manager - self registers itself in Flask app as executor
app_task_manager = task_manager.TaskManager(
    dataset=app_user_ds,
    enc_key=app_config.encryption_key,
    blobstore=app_blobstore,
    config=app_config,
)
# encryption key for task parameters
_enc_key = app_config.encryption_key
