# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import sqlalchemy as sql

from keystone.common.sql import migration_helpers


def list_constraints(project_table):
    constraints = [{'table': project_table,
                    'fk_column': 'parent_id',
                    'ref_column': project_table.c.id}]

    return constraints


def upgrade(migrate_engine):
    meta = sql.MetaData()
    meta.bind = migrate_engine

    project_table = sql.Table('project', meta, autoload=True)
    parent_id = sql.Column('parent_id', sql.String(64))
    project_table.create_column(parent_id)

    if migrate_engine.name == 'sqlite':
        return
    migration_helpers.add_constraints(list_constraints(project_table))


def downgrade(migrate_engine):
    meta = sql.MetaData()
    meta.bind = migrate_engine

    # SQLite does not support constraints, and querying the constraints
    # raises an exception
    if migrate_engine.name != 'sqlite':
        migration_helpers.remove_constraints(list_constraints(meta))

    project_table = sql.Table('project', meta, autoload=True)
    project_table.drop_column('parent_id')
