# -*- coding: utf-8 -*-
# Copyright 2012 OpenStack Foundation
#
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

import functools
import uuid

import mock
from oslo.db import exception as db_exception
from oslo.db import options
import sqlalchemy
from sqlalchemy import exc
from testtools import matchers

from keystone.common import driver_hints
from keystone.common import sql
from keystone import config
from keystone import exception
from keystone.identity.backends import sql as identity_sql
from keystone import tests
from keystone.tests import default_fixtures
from keystone.tests.ksfixtures import database
from keystone.tests import test_backend
from keystone.token.persistence.backends import sql as token_sql


CONF = config.CONF
DEFAULT_DOMAIN_ID = CONF.identity.default_domain_id


class SqlTests(tests.SQLDriverOverrides, tests.TestCase):

    def setUp(self):
        super(SqlTests, self).setUp()
        self.useFixture(database.Database())
        self.load_backends()

        # populate the engine with tables & fixtures
        self.load_fixtures(default_fixtures)
        # defaulted by the data load
        self.user_foo['enabled'] = True

    def config_files(self):
        config_files = super(SqlTests, self).config_files()
        config_files.append(tests.dirs.tests_conf('backend_sql.conf'))
        return config_files


class SqlModels(SqlTests):

    def select_table(self, name):
        table = sqlalchemy.Table(name,
                                 sql.ModelBase.metadata,
                                 autoload=True)
        s = sqlalchemy.select([table])
        return s

    def assertExpectedSchema(self, table, cols):
        table = self.select_table(table)
        for col, type_, length in cols:
            self.assertIsInstance(table.c[col].type, type_)
            if length:
                self.assertEqual(length, table.c[col].type.length)

    def test_user_model(self):
        cols = (('id', sql.String, 64),
                ('name', sql.String, 255),
                ('password', sql.String, 128),
                ('domain_id', sql.String, 64),
                ('enabled', sql.Boolean, None),
                ('extra', sql.JsonBlob, None))
        self.assertExpectedSchema('user', cols)

    def test_group_model(self):
        cols = (('id', sql.String, 64),
                ('name', sql.String, 64),
                ('description', sql.Text, None),
                ('domain_id', sql.String, 64),
                ('extra', sql.JsonBlob, None))
        self.assertExpectedSchema('group', cols)

    def test_domain_model(self):
        cols = (('id', sql.String, 64),
                ('name', sql.String, 64),
                ('enabled', sql.Boolean, None))
        self.assertExpectedSchema('domain', cols)

    def test_project_model(self):
        cols = (('id', sql.String, 64),
                ('name', sql.String, 64),
                ('description', sql.Text, None),
                ('domain_id', sql.String, 64),
                ('enabled', sql.Boolean, None),
                ('extra', sql.JsonBlob, None))
        self.assertExpectedSchema('project', cols)

    def test_role_model(self):
        cols = (('id', sql.String, 64),
                ('name', sql.String, 255))
        self.assertExpectedSchema('role', cols)

    def test_role_assignment_model(self):
        cols = (('type', sql.Enum, None),
                ('actor_id', sql.String, 64),
                ('target_id', sql.String, 64),
                ('role_id', sql.String, 64),
                ('inherited', sql.Boolean, False))
        self.assertExpectedSchema('assignment', cols)

    def test_user_group_membership(self):
        cols = (('group_id', sql.String, 64),
                ('user_id', sql.String, 64))
        self.assertExpectedSchema('user_group_membership', cols)


class SqlIdentity(SqlTests, test_backend.IdentityTests):
    def test_password_hashed(self):
        session = sql.get_session()
        user_ref = self.identity_api._get_user(session, self.user_foo['id'])
        self.assertNotEqual(user_ref['password'], self.user_foo['password'])

    def test_delete_user_with_project_association(self):
        user = {'name': uuid.uuid4().hex,
                'domain_id': DEFAULT_DOMAIN_ID,
                'password': uuid.uuid4().hex}
        user = self.identity_api.create_user(user)
        self.assignment_api.add_user_to_project(self.tenant_bar['id'],
                                                user['id'])
        self.identity_api.delete_user(user['id'])
        self.assertRaises(exception.UserNotFound,
                          self.assignment_api.list_projects_for_user,
                          user['id'])

    def test_create_null_user_name(self):
        user = {'name': None,
                'domain_id': DEFAULT_DOMAIN_ID,
                'password': uuid.uuid4().hex}
        self.assertRaises(exception.ValidationError,
                          self.identity_api.create_user,
                          user)
        self.assertRaises(exception.UserNotFound,
                          self.identity_api.get_user_by_name,
                          user['name'],
                          DEFAULT_DOMAIN_ID)

    def test_create_null_project_name(self):
        tenant = {'id': uuid.uuid4().hex,
                  'name': None,
                  'domain_id': DEFAULT_DOMAIN_ID}
        self.assertRaises(exception.ValidationError,
                          self.assignment_api.create_project,
                          tenant['id'],
                          tenant)
        self.assertRaises(exception.ProjectNotFound,
                          self.assignment_api.get_project,
                          tenant['id'])
        self.assertRaises(exception.ProjectNotFound,
                          self.assignment_api.get_project_by_name,
                          tenant['name'],
                          DEFAULT_DOMAIN_ID)

    def test_create_null_role_name(self):
        role = {'id': uuid.uuid4().hex,
                'name': None}
        self.assertRaises(exception.UnexpectedError,
                          self.assignment_api.create_role,
                          role['id'],
                          role)
        self.assertRaises(exception.RoleNotFound,
                          self.assignment_api.get_role,
                          role['id'])

    def test_delete_project_with_user_association(self):
        user = {'name': 'fakeuser',
                'domain_id': DEFAULT_DOMAIN_ID,
                'password': 'passwd'}
        user = self.identity_api.create_user(user)
        self.assignment_api.add_user_to_project(self.tenant_bar['id'],
                                                user['id'])
        self.assignment_api.delete_project(self.tenant_bar['id'])
        tenants = self.assignment_api.list_projects_for_user(user['id'])
        self.assertEqual([], tenants)

    def test_metadata_removed_on_delete_user(self):
        # A test to check that the internal representation
        # or roles is correctly updated when a user is deleted
        user = {'name': uuid.uuid4().hex,
                'domain_id': DEFAULT_DOMAIN_ID,
                'password': 'passwd'}
        user = self.identity_api.create_user(user)
        role = {'id': uuid.uuid4().hex,
                'name': uuid.uuid4().hex}
        self.assignment_api.create_role(role['id'], role)
        self.assignment_api.add_role_to_user_and_project(
            user['id'],
            self.tenant_bar['id'],
            role['id'])
        self.identity_api.delete_user(user['id'])

        # Now check whether the internal representation of roles
        # has been deleted
        self.assertRaises(exception.MetadataNotFound,
                          self.assignment_api._get_metadata,
                          user['id'],
                          self.tenant_bar['id'])

    def test_metadata_removed_on_delete_project(self):
        # A test to check that the internal representation
        # or roles is correctly updated when a project is deleted
        user = {'name': uuid.uuid4().hex,
                'domain_id': DEFAULT_DOMAIN_ID,
                'password': 'passwd'}
        user = self.identity_api.create_user(user)
        role = {'id': uuid.uuid4().hex,
                'name': uuid.uuid4().hex}
        self.assignment_api.create_role(role['id'], role)
        self.assignment_api.add_role_to_user_and_project(
            user['id'],
            self.tenant_bar['id'],
            role['id'])
        self.assignment_api.delete_project(self.tenant_bar['id'])

        # Now check whether the internal representation of roles
        # has been deleted
        self.assertRaises(exception.MetadataNotFound,
                          self.assignment_api._get_metadata,
                          user['id'],
                          self.tenant_bar['id'])

    def test_update_project_returns_extra(self):
        """This tests for backwards-compatibility with an essex/folsom bug.

        Non-indexed attributes were returned in an 'extra' attribute, instead
        of on the entity itself; for consistency and backwards compatibility,
        those attributes should be included twice.

        This behavior is specific to the SQL driver.

        """
        tenant_id = uuid.uuid4().hex
        arbitrary_key = uuid.uuid4().hex
        arbitrary_value = uuid.uuid4().hex
        tenant = {
            'id': tenant_id,
            'name': uuid.uuid4().hex,
            'domain_id': DEFAULT_DOMAIN_ID,
            arbitrary_key: arbitrary_value}
        ref = self.assignment_api.create_project(tenant_id, tenant)
        self.assertEqual(arbitrary_value, ref[arbitrary_key])
        self.assertIsNone(ref.get('extra'))

        tenant['name'] = uuid.uuid4().hex
        ref = self.assignment_api.update_project(tenant_id, tenant)
        self.assertEqual(arbitrary_value, ref[arbitrary_key])
        self.assertEqual(arbitrary_value, ref['extra'][arbitrary_key])

    def test_update_user_returns_extra(self):
        """This tests for backwards-compatibility with an essex/folsom bug.

        Non-indexed attributes were returned in an 'extra' attribute, instead
        of on the entity itself; for consistency and backwards compatibility,
        those attributes should be included twice.

        This behavior is specific to the SQL driver.

        """
        arbitrary_key = uuid.uuid4().hex
        arbitrary_value = uuid.uuid4().hex
        user = {
            'name': uuid.uuid4().hex,
            'domain_id': DEFAULT_DOMAIN_ID,
            'password': uuid.uuid4().hex,
            arbitrary_key: arbitrary_value}
        ref = self.identity_api.create_user(user)
        self.assertEqual(arbitrary_value, ref[arbitrary_key])
        self.assertIsNone(ref.get('password'))
        self.assertIsNone(ref.get('extra'))

        user['name'] = uuid.uuid4().hex
        user['password'] = uuid.uuid4().hex
        ref = self.identity_api.update_user(ref['id'], user)
        self.assertIsNone(ref.get('password'))
        self.assertIsNone(ref['extra'].get('password'))
        self.assertEqual(arbitrary_value, ref[arbitrary_key])
        self.assertEqual(arbitrary_value, ref['extra'][arbitrary_key])

    def test_sql_user_to_dict_null_default_project_id(self):
        user = {
            'name': uuid.uuid4().hex,
            'domain_id': DEFAULT_DOMAIN_ID,
            'password': uuid.uuid4().hex}

        user = self.identity_api.create_user(user)
        session = sql.get_session()
        query = session.query(identity_sql.User)
        query = query.filter_by(id=user['id'])
        raw_user_ref = query.one()
        self.assertIsNone(raw_user_ref.default_project_id)
        user_ref = raw_user_ref.to_dict()
        self.assertNotIn('default_project_id', user_ref)
        session.close()

    def test_list_domains_for_user(self):
        domain = {'id': uuid.uuid4().hex, 'name': uuid.uuid4().hex}
        self.assignment_api.create_domain(domain['id'], domain)
        user = {'name': uuid.uuid4().hex, 'password': uuid.uuid4().hex,
                'domain_id': domain['id'], 'enabled': True}

        test_domain1 = {'id': uuid.uuid4().hex, 'name': uuid.uuid4().hex}
        self.assignment_api.create_domain(test_domain1['id'], test_domain1)
        test_domain2 = {'id': uuid.uuid4().hex, 'name': uuid.uuid4().hex}
        self.assignment_api.create_domain(test_domain2['id'], test_domain2)

        user = self.identity_api.create_user(user)
        user_domains = self.assignment_api.list_domains_for_user(user['id'])
        self.assertEqual(0, len(user_domains))
        self.assignment_api.create_grant(user_id=user['id'],
                                         domain_id=test_domain1['id'],
                                         role_id=self.role_member['id'])
        self.assignment_api.create_grant(user_id=user['id'],
                                         domain_id=test_domain2['id'],
                                         role_id=self.role_member['id'])
        user_domains = self.assignment_api.list_domains_for_user(user['id'])
        self.assertThat(user_domains, matchers.HasLength(2))

    def test_list_domains_for_user_with_grants(self):
        # Create two groups each with a role on a different domain, and
        # make user1 a member of both groups.  Both these new domains
        # should now be included, along with any direct user grants.
        domain = {'id': uuid.uuid4().hex, 'name': uuid.uuid4().hex}
        self.assignment_api.create_domain(domain['id'], domain)
        user = {'name': uuid.uuid4().hex, 'password': uuid.uuid4().hex,
                'domain_id': domain['id'], 'enabled': True}
        user = self.identity_api.create_user(user)
        group1 = {'name': uuid.uuid4().hex, 'domain_id': domain['id']}
        group1 = self.identity_api.create_group(group1)
        group2 = {'name': uuid.uuid4().hex, 'domain_id': domain['id']}
        group2 = self.identity_api.create_group(group2)

        test_domain1 = {'id': uuid.uuid4().hex, 'name': uuid.uuid4().hex}
        self.assignment_api.create_domain(test_domain1['id'], test_domain1)
        test_domain2 = {'id': uuid.uuid4().hex, 'name': uuid.uuid4().hex}
        self.assignment_api.create_domain(test_domain2['id'], test_domain2)
        test_domain3 = {'id': uuid.uuid4().hex, 'name': uuid.uuid4().hex}
        self.assignment_api.create_domain(test_domain3['id'], test_domain3)

        self.identity_api.add_user_to_group(user['id'], group1['id'])
        self.identity_api.add_user_to_group(user['id'], group2['id'])

        # Create 3 grants, one user grant, the other two as group grants
        self.assignment_api.create_grant(user_id=user['id'],
                                         domain_id=test_domain1['id'],
                                         role_id=self.role_member['id'])
        self.assignment_api.create_grant(group_id=group1['id'],
                                         domain_id=test_domain2['id'],
                                         role_id=self.role_admin['id'])
        self.assignment_api.create_grant(group_id=group2['id'],
                                         domain_id=test_domain3['id'],
                                         role_id=self.role_admin['id'])
        user_domains = self.assignment_api.list_domains_for_user(user['id'])
        self.assertThat(user_domains, matchers.HasLength(3))


class SqlTrust(SqlTests, test_backend.TrustTests):
    pass


class SqlToken(SqlTests, test_backend.TokenTests):
    def test_token_revocation_list_uses_right_columns(self):
        # This query used to be heavy with too many columns. We want
        # to make sure it is only running with the minimum columns
        # necessary.

        expected_query_args = (token_sql.TokenModel.id,
                               token_sql.TokenModel.expires)

        with mock.patch.object(token_sql, 'sql') as mock_sql:
            tok = token_sql.Token()
            tok.list_revoked_tokens()

        mock_query = mock_sql.get_session().query
        mock_query.assert_called_with(*expected_query_args)

    def test_flush_expired_tokens_batch(self):
        # TODO(dstanek): This test should be rewritten to be less
        # brittle. The code will likely need to be changed first. I
        # just copied the spirit of the existing test when I rewrote
        # mox -> mock. These tests are brittle because they have the
        # call structure for SQLAlchemy encoded in them.

        # test sqlite dialect
        with mock.patch.object(token_sql, 'sql') as mock_sql:
            mock_sql.get_session().bind.dialect.name = 'sqlite'
            tok = token_sql.Token()
            tok.flush_expired_tokens()

        filter_mock = mock_sql.get_session().query().filter()
        self.assertFalse(filter_mock.limit.called)
        self.assertTrue(filter_mock.delete.called_once)

    def test_flush_expired_tokens_batch_mysql(self):
        # test mysql dialect, we don't need to test IBM DB SA separately, since
        # other tests below test the differences between how they use the batch
        # strategy
        with mock.patch.object(token_sql, 'sql') as mock_sql:
            mock_sql.get_session().query().filter().delete.return_value = 0
            mock_sql.get_session().bind.dialect.name = 'mysql'
            tok = token_sql.Token()
            expiry_mock = mock.Mock()
            ITERS = [1, 2, 3]
            expiry_mock.return_value = iter(ITERS)
            token_sql._expiry_range_batched = expiry_mock
            tok.flush_expired_tokens()

            # The expiry strategy is only invoked once, the other calls are via
            # the yield return.
            expiry_mock.assert_called_once()
            mock_delete = mock_sql.get_session().query().filter().delete
            self.assertThat(mock_delete.call_args_list,
                            matchers.HasLength(len(ITERS)))

    def test_expiry_range_batched(self):
        upper_bound_mock = mock.Mock(side_effect=[1, "final value"])
        sess_mock = mock.Mock()
        query_mock = sess_mock.query().filter().order_by().offset().limit()
        query_mock.one.side_effect = [['test'], sql.NotFound()]
        for i, x in enumerate(token_sql._expiry_range_batched(sess_mock,
                                                              upper_bound_mock,
                                                              batch_size=50)):
            if i == 0:
                # The first time the batch iterator returns, it should return
                # the first result that comes back from the database.
                self.assertEqual(x, 'test')
            elif i == 1:
                # The second time, the database range function should return
                # nothing, so the batch iterator returns the result of the
                # upper_bound function
                self.assertEqual(x, "final value")
            else:
                self.fail("range batch function returned more than twice")

    def test_expiry_range_strategy_sqlite(self):
        tok = token_sql.Token()
        sqlite_strategy = tok._expiry_range_strategy('sqlite')
        self.assertEqual(token_sql._expiry_range_all, sqlite_strategy)

    def test_expiry_range_strategy_ibm_db_sa(self):
        tok = token_sql.Token()
        db2_strategy = tok._expiry_range_strategy('ibm_db_sa')
        self.assertIsInstance(db2_strategy, functools.partial)
        self.assertEqual(db2_strategy.func, token_sql._expiry_range_batched)
        self.assertEqual(db2_strategy.keywords, {'batch_size': 100})

    def test_expiry_range_strategy_mysql(self):
        tok = token_sql.Token()
        mysql_strategy = tok._expiry_range_strategy('mysql')
        self.assertIsInstance(mysql_strategy, functools.partial)
        self.assertEqual(mysql_strategy.func, token_sql._expiry_range_batched)
        self.assertEqual(mysql_strategy.keywords, {'batch_size': 1000})


class SqlCatalog(SqlTests, test_backend.CatalogTests):
    def test_catalog_ignored_malformed_urls(self):
        service = {
            'id': uuid.uuid4().hex,
            'type': uuid.uuid4().hex,
            'name': uuid.uuid4().hex,
            'description': uuid.uuid4().hex,
        }
        self.catalog_api.create_service(service['id'], service.copy())

        malformed_url = "http://192.168.1.104:8774/v2/$(tenant)s"
        endpoint = {
            'id': uuid.uuid4().hex,
            'region_id': None,
            'service_id': service['id'],
            'interface': 'public',
            'url': malformed_url,
        }
        self.catalog_api.create_endpoint(endpoint['id'], endpoint.copy())

        # NOTE(dstanek): there are no valid URLs, so nothing is in the catalog
        catalog = self.catalog_api.get_catalog('fake-user', 'fake-tenant')
        self.assertEqual({}, catalog)

    def test_get_catalog_with_empty_public_url(self):
        service = {
            'id': uuid.uuid4().hex,
            'type': uuid.uuid4().hex,
            'name': uuid.uuid4().hex,
            'description': uuid.uuid4().hex,
        }
        self.catalog_api.create_service(service['id'], service.copy())

        endpoint = {
            'id': uuid.uuid4().hex,
            'region_id': None,
            'interface': 'public',
            'url': '',
            'service_id': service['id'],
        }
        self.catalog_api.create_endpoint(endpoint['id'], endpoint.copy())

        catalog = self.catalog_api.get_catalog('user', 'tenant')
        catalog_endpoint = catalog[endpoint['region_id']][service['type']]
        self.assertEqual(service['name'], catalog_endpoint['name'])
        self.assertEqual(endpoint['id'], catalog_endpoint['id'])
        self.assertEqual('', catalog_endpoint['publicURL'])
        self.assertIsNone(catalog_endpoint.get('adminURL'))
        self.assertIsNone(catalog_endpoint.get('internalURL'))

    def test_create_endpoint_region_404(self):
        service = {
            'id': uuid.uuid4().hex,
            'type': uuid.uuid4().hex,
            'name': uuid.uuid4().hex,
            'description': uuid.uuid4().hex,
        }
        self.catalog_api.create_service(service['id'], service.copy())

        endpoint = {
            'id': uuid.uuid4().hex,
            'region_id': uuid.uuid4().hex,
            'service_id': service['id'],
            'interface': 'public',
            'url': uuid.uuid4().hex,
        }

        self.assertRaises(exception.ValidationError,
                          self.catalog_api.create_endpoint,
                          endpoint['id'],
                          endpoint.copy())

    def test_create_region_invalid_id(self):
        region = {
            'id': '0' * 256,
            'description': '',
            'extra': {},
        }

        self.assertRaises(exception.StringLengthExceeded,
                          self.catalog_api.create_region,
                          region.copy())

    def test_create_region_invalid_parent_id(self):
        region = {
            'id': uuid.uuid4().hex,
            'parent_region_id': '0' * 256,
        }

        self.assertRaises(exception.RegionNotFound,
                          self.catalog_api.create_region,
                          region)

    def test_delete_region_with_endpoint(self):
        # create a region
        region = {
            'id': uuid.uuid4().hex,
            'description': uuid.uuid4().hex,
        }
        self.catalog_api.create_region(region)

        # create a child region
        child_region = {
            'id': uuid.uuid4().hex,
            'description': uuid.uuid4().hex,
            'parent_id': region['id']
        }
        self.catalog_api.create_region(child_region)
        # create a service
        service = {
            'id': uuid.uuid4().hex,
            'type': uuid.uuid4().hex,
            'name': uuid.uuid4().hex,
            'description': uuid.uuid4().hex,
        }
        self.catalog_api.create_service(service['id'], service)

        # create an endpoint attached to the service and child region
        child_endpoint = {
            'id': uuid.uuid4().hex,
            'region_id': child_region['id'],
            'interface': uuid.uuid4().hex[:8],
            'url': uuid.uuid4().hex,
            'service_id': service['id'],
        }
        self.catalog_api.create_endpoint(child_endpoint['id'], child_endpoint)
        self.assertRaises(exception.RegionDeletionError,
                          self.catalog_api.delete_region,
                          child_region['id'])

        # create an endpoint attached to the service and parent region
        endpoint = {
            'id': uuid.uuid4().hex,
            'region_id': region['id'],
            'interface': uuid.uuid4().hex[:8],
            'url': uuid.uuid4().hex,
            'service_id': service['id'],
        }
        self.catalog_api.create_endpoint(endpoint['id'], endpoint)
        self.assertRaises(exception.RegionDeletionError,
                          self.catalog_api.delete_region,
                          region['id'])


class SqlPolicy(SqlTests, test_backend.PolicyTests):
    pass


class SqlInheritance(SqlTests, test_backend.InheritanceTests):
    pass


class SqlTokenCacheInvalidation(SqlTests, test_backend.TokenCacheInvalidation):
    def setUp(self):
        super(SqlTokenCacheInvalidation, self).setUp()
        self._create_test_data()


class SqlFilterTests(SqlTests, test_backend.FilterTests):
    pass


class SqlLimitTests(SqlTests, test_backend.LimitTests):
    def setUp(self):
        super(SqlLimitTests, self).setUp()
        test_backend.LimitTests.setUp(self)


class FakeTable(sql.ModelBase):
    __tablename__ = 'test_table'
    col = sql.Column(sql.String(32), primary_key=True)

    @sql.handle_conflicts('keystone')
    def insert(self):
        raise db_exception.DBDuplicateEntry

    @sql.handle_conflicts('keystone')
    def update(self):
        raise db_exception.DBError(
            inner_exception=exc.IntegrityError('a', 'a', 'a'))

    @sql.handle_conflicts('keystone')
    def lookup(self):
        raise KeyError


class SqlDecorators(tests.TestCase):

    def test_initialization_fail(self):
        self.assertRaises(exception.StringLengthExceeded,
                          FakeTable, col='a' * 64)

    def test_initialization(self):
        tt = FakeTable(col='a')
        self.assertEqual('a', tt.col)

    def test_non_ascii_init(self):
        # NOTE(I159): Non ASCII characters must cause UnicodeDecodeError
        # if encoding is not provided explicitly.
        self.assertRaises(UnicodeDecodeError, FakeTable, col='Я')

    def test_conflict_happend(self):
        self.assertRaises(exception.Conflict, FakeTable().insert)
        self.assertRaises(exception.UnexpectedError, FakeTable().update)

    def test_not_conflict_error(self):
        self.assertRaises(KeyError, FakeTable().lookup)


class SqlModuleInitialization(tests.TestCase):

    @mock.patch.object(sql.core, 'CONF')
    @mock.patch.object(options, 'set_defaults')
    def test_initialize_module(self, set_defaults, CONF):
        sql.initialize()
        set_defaults.assert_called_with(CONF,
                                        connection='sqlite:///keystone.db')


class SqlCredential(SqlTests):

    def _create_credential_with_user_id(self, user_id=uuid.uuid4().hex):
        credential_id = uuid.uuid4().hex
        new_credential = {
            'id': credential_id,
            'user_id': user_id,
            'project_id': uuid.uuid4().hex,
            'blob': uuid.uuid4().hex,
            'type': uuid.uuid4().hex,
            'extra': uuid.uuid4().hex
        }
        self.credential_api.create_credential(credential_id, new_credential)
        return new_credential

    def _validateCredentialList(self, retrieved_credentials,
                                expected_credentials):
        self.assertEqual(len(retrieved_credentials), len(expected_credentials))
        retrived_ids = [c['id'] for c in retrieved_credentials]
        for cred in expected_credentials:
            self.assertIn(cred['id'], retrived_ids)

    def setUp(self):
        super(SqlCredential, self).setUp()
        self.credentials = []
        for _ in range(3):
            self.credentials.append(
                self._create_credential_with_user_id())
        self.user_credentials = []
        for _ in range(3):
            cred = self._create_credential_with_user_id(self.user_foo['id'])
            self.user_credentials.append(cred)
            self.credentials.append(cred)

    def test_list_credentials(self):
        credentials = self.credential_api.list_credentials()
        self._validateCredentialList(credentials, self.credentials)
        # test filtering using hints
        hints = driver_hints.Hints()
        hints.add_filter('user_id', self.user_foo['id'])
        credentials = self.credential_api.list_credentials(hints)
        self._validateCredentialList(credentials, self.user_credentials)

    def test_list_credentials_for_user(self):
        credentials = self.credential_api.list_credentials_for_user(
            self.user_foo['id'])
        self._validateCredentialList(credentials, self.user_credentials)
