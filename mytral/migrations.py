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

from mytral import config
from mytral import loggers
from mytral import persistences
from mytral import settings
from mytral.backends.dataset import MyTraLDataset


class FsPersistenceMigrations:
    def __init__(
        self,
        logger: loggers.MytralLogger,
        cfg: config.MytralPersistenceFsConfig,
        ds: MyTraLDataset,
    ) -> None:
        self.logger = logger
        self.log_name = "[Migrations]"
        self.cfg = cfg
        self.ds = ds
        self.user_ds = ds.user()
        # map: detected data spec version > migrations to perform
        self._migrations = {
            "1.8.0": [self._migrate_1_8_0_to_1_9_0],
            "1.9.0": [self._migrate_1_9_0_to_1_50_0],
        }

    def _180_to_190_sport_to_activity_type_key(self):
        """Migration step - for every user account:

        - The sport key (str) is renamed to activity_type_key in every
          activity dict and every gear dict.

        """
        for user_id in self.ds.user_ids():
            self.logger.info(f"{self.log_name}   user: {user_id}")
            profile = self.user_ds.profile(user_id)

            # migrate gear: rename sport > activity_type_key
            gear_path = self.user_ds.user_gear_path(user_id)
            if gear_path.exists():
                gear_list = persistences.load_json(gear_path)
                if gear_list:
                    for g in gear_list:
                        if "sport" in g:
                            g["activity_type_key"] = g.pop("sport")
                    persistences.save_json(file_path=gear_path, data_dict=gear_list)
                    self.logger.info(f"{self.log_name}     gear migrated")

            # migrate activities: rename sport > activity_type_key
            for dataset_name in profile.dataset_names:
                activities_path = self.user_ds.user_activities_path(
                    user_id, dataset_name
                )
                if not activities_path.exists():
                    continue

                activities_list = persistences.load_json(activities_path)
                if not activities_list:
                    continue

                for a in activities_list:
                    if "sport" in a:
                        a["activity_type_key"] = a.pop("sport")

                persistences.save_json(
                    file_path=activities_path, data_dict=activities_list
                )
                self.logger.info(
                    f"{self.log_name}     dataset '{dataset_name}' migrated"
                )

    def _180_to_190_inject_missing_activity_types(self):
        """Migration step - for every user account:

        Inject bootstrap activity types that are missing in the user's
        activity types. All injected types are marked as is_built_in=True.
        """
        # collect bootstrap keys and their dict representations
        bootstrap_by_key: dict[str, dict] = {}
        for at in settings.UserActivityTypes.BOOTSTRAP:
            bootstrap_by_key[at.key] = at.to_dict()

        for user_id in self.ds.user_ids():
            at_path = self.user_ds.user_activity_types_path(user_id)
            if not at_path.exists():
                self.logger.info(
                    f"{self.log_name}   user '{user_id}' has no activity types file"
                )
                continue

            at_data = persistences.load_json(at_path)
            if not at_data:
                continue

            existing = persistences.normalize_dict_or_list_to_dict(at_data)
            existing_keys = set(existing.keys())
            injected = 0
            for key, at_dict in bootstrap_by_key.items():
                if key not in existing_keys:
                    existing[key] = at_dict
                    injected += 1

            if injected:
                # save as list format (current efficient format)
                persistences.save_json(
                    file_path=at_path, data_dict=list(existing.values())
                )
                self.logger.info(
                    f"{self.log_name}     user '{user_id}': "
                    f"injected {injected} missing activity types"
                )

    def _180_to_190_inject_missing_exercises(self):
        """Migration step - for every user account:

        Inject bootstrap exercises that are missing in the user's exercises.
        """
        # collect bootstrap exercises and their dict representations
        bootstrap_by_key: dict[str, dict] = {}
        for ex in settings.UserExercises.bootstrap():
            bootstrap_by_key[ex.key] = ex.to_dict()

        for user_id in self.ds.user_ids():
            ex_path = self.user_ds.user_exercises_path(user_id)
            if not ex_path.exists():
                continue

            ex_data = persistences.load_json(ex_path)
            if not ex_data:
                continue

            existing = persistences.normalize_dict_or_list_to_dict(ex_data)
            existing_keys = set(existing.keys())
            injected = 0
            for key, ex_dict in bootstrap_by_key.items():
                if key not in existing_keys:
                    existing[key] = ex_dict
                    injected += 1

            if injected:
                persistences.save_json(
                    file_path=ex_path, data_dict=list(existing.values())
                )
                self.logger.info(
                    f"{self.log_name}     user '{user_id}': "
                    f"injected {injected} missing exercises"
                )

    def _180_to_190_inject_missing_symptoms(self):
        """Migration step - for every user account:

        Inject bootstrap symptoms that are missing in the user's symptoms.
        """
        # collect bootstrap symptoms and their dict representations
        bootstrap_by_key: dict[str, dict] = {}
        for s in settings.UserSymptoms.bootstrap():
            bootstrap_by_key[s.key] = s.to_dict()

        for user_id in self.ds.user_ids():
            s_path = self.user_ds.user_symptoms_path(user_id)
            if not s_path.exists():
                continue

            s_data = persistences.load_json(s_path)
            if not s_data:
                continue

            existing = persistences.normalize_dict_or_list_to_dict(s_data)
            existing_keys = set(existing.keys())
            injected = 0
            for key, s_dict in bootstrap_by_key.items():
                if key not in existing_keys:
                    existing[key] = s_dict
                    injected += 1

            if injected:
                persistences.save_json(
                    file_path=s_path, data_dict=list(existing.values())
                )
                self.logger.info(
                    f"{self.log_name}     user '{user_id}': "
                    f"injected {injected} missing symptoms"
                )

    def _migrate_1_8_0_to_1_9_0(self):
        """Migrate dataset from 1.8.0 to 1.9.0 specification."""
        self.logger.info(f"{self.log_name} Migrating 1.8.0 to 1.9.0 specification...")

        # migration steps
        self._180_to_190_sport_to_activity_type_key()
        self._180_to_190_inject_missing_activity_types()
        self._180_to_190_inject_missing_exercises()
        self._180_to_190_inject_missing_symptoms()

        self.logger.info(f"{self.log_name} DONE migration from 1.8.0 to 1.9.0 spec")

    def _190_to_1500_del_suffer_score(self):
        """Migration step - for every user account:

        - remove suffer_score key from all activities

        """
        for user_id in self.ds.user_ids():
            self.logger.info(f"{self.log_name}   user: {user_id}")
            profile = self.user_ds.profile(user_id)

            # activities: remove suffer score
            for dataset_name in profile.dataset_names:
                activities_path = self.user_ds.user_activities_path(
                    user_id, dataset_name
                )
                if not activities_path.exists():
                    continue

                activities_list = persistences.load_json(activities_path)
                if not activities_list:
                    continue

                for a in activities_list:
                    a.pop("suffer_score", None)

                persistences.save_json(
                    file_path=activities_path, data_dict=activities_list
                )
                self.logger.info(
                    f"{self.log_name}     dataset '{dataset_name}' migrated"
                )

    def _migrate_1_9_0_to_1_50_0(self):
        """Migrate dataset from 1.9.0 to 1.50.0 specification."""
        self.logger.info(f"{self.log_name} Migrating 1.9.0 to 1.50.0 specification...")

        # remove suffer score
        self._190_to_1500_del_suffer_score()
        # new ATs added - can reuse existing migration
        self._180_to_190_inject_missing_activity_types()

        self.logger.info(f"{self.log_name} DONE migration from 1.9.0 to 1.50.0 spec")

    def migrate(self) -> str:
        """Check whether migration is needed and perform it if so.

        Returns
        -------
        str :
            New version of the data after migration.
        """
        self.logger.info(
            f"{self.log_name} checking whether MyTraL data migration is needed..."
        )
        if self.cfg.is_migrate():
            migration_steps = self._migrations.get(self.cfg.data_spec_version, [])
            for migration_step in migration_steps:
                migration_step()

            # evict all caches after migration — data files have changed on disk
            for user_id in self.ds.user_ids():
                self.user_ds.cache_evict(user_id)
            config.MytralPersistenceFsConfig.invalidate_cache()

        self.logger.info(f"{self.log_name} DONE all migration steps.")
        return self.cfg.mytral_version
