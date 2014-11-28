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

import uuid

from oslo.config import cfg
from testtools import matchers

from keystone.common import controller
from keystone import exception
from keystone import tests
from keystone.tests import test_v3


CONF = cfg.CONF


def _build_role_assignment_url_and_entity(
        role_id, user_id=None, group_id=None, domain_id=None,
        project_id=None, inherited_to_projects=False,
        effective=False):

    if user_id and domain_id:
        url = ('/domains/%(domain_id)s/users/%(user_id)s'
               '/roles/%(role_id)s' % {
                   'domain_id': domain_id,
                   'user_id': user_id,
                   'role_id': role_id})
        entity = {'role': {'id': role_id},
                  'user': {'id': user_id},
                  'scope': {'domain': {'id': domain_id}}}
    elif user_id and project_id:
        url = ('/projects/%(project_id)s/users/%(user_id)s'
               '/roles/%(role_id)s' % {
                   'project_id': project_id,
                   'user_id': user_id,
                   'role_id': role_id})
        entity = {'role': {'id': role_id},
                  'user': {'id': user_id},
                  'scope': {'project': {'id': project_id}}}
    if group_id and domain_id:
        url = ('/domains/%(domain_id)s/groups/%(group_id)s'
               '/roles/%(role_id)s' % {
                   'domain_id': domain_id,
                   'group_id': group_id,
                   'role_id': role_id})
        entity = {'role': {'id': role_id},
                  'group': {'id': group_id},
                  'scope': {'domain': {'id': domain_id}}}
    elif group_id and project_id:
        url = ('/projects/%(project_id)s/groups/%(group_id)s'
               '/roles/%(role_id)s' % {
                   'project_id': project_id,
                   'group_id': group_id,
                   'role_id': role_id})
        entity = {'role': {'id': role_id},
                  'group': {'id': group_id},
                  'scope': {'project': {'id': project_id}}}

    if inherited_to_projects:
        url = '/OS-INHERIT%s/inherited_to_projects' % url
        if not effective:
            entity['OS-INHERIT:inherited_to'] = 'projects'

    return (url, entity)


class IdentityTestCase(test_v3.RestfulTestCase):

    """Test domains, projects, users, groups, & role CRUD."""

    def setUp(self):
        super(IdentityTestCase, self).setUp()

        self.group = self.new_group_ref(
            domain_id=self.domain_id)
        self.group = self.identity_api.create_group(self.group)
        self.group_id = self.group['id']

        self.credential_id = uuid.uuid4().hex
        self.credential = self.new_credential_ref(
            user_id=self.user['id'],
            project_id=self.project_id)
        self.credential['id'] = self.credential_id
        self.credential_api.create_credential(
            self.credential_id,
            self.credential)

    # domain crud tests

    def test_create_domain(self):
        """Call ``POST /domains``."""
        ref = self.new_domain_ref()
        r = self.post(
            '/domains',
            body={'domain': ref})
        return self.assertValidDomainResponse(r, ref)

    def test_create_domain_case_sensitivity(self):
        """Call `POST /domains`` twice with upper() and lower() cased name."""
        ref = self.new_domain_ref()

        # ensure the name is lowercase
        ref['name'] = ref['name'].lower()
        r = self.post(
            '/domains',
            body={'domain': ref})
        self.assertValidDomainResponse(r, ref)

        # ensure the name is uppercase
        ref['name'] = ref['name'].upper()
        r = self.post(
            '/domains',
            body={'domain': ref})
        self.assertValidDomainResponse(r, ref)

    def test_create_domain_400(self):
        """Call ``POST /domains``."""
        self.post('/domains', body={'domain': {}}, expected_status=400)

    def test_list_domains(self):
        """Call ``GET /domains``."""
        resource_url = '/domains'
        r = self.get(resource_url)
        self.assertValidDomainListResponse(r, ref=self.domain,
                                           resource_url=resource_url)

    def test_list_domains_xml(self):
        """Call ``GET /domains (xml data)``."""
        resource_url = '/domains'
        r = self.get(resource_url, content_type='xml')
        self.assertValidDomainListResponse(r, ref=self.domain,
                                           resource_url=resource_url)

    def test_get_domain(self):
        """Call ``GET /domains/{domain_id}``."""
        r = self.get('/domains/%(domain_id)s' % {
            'domain_id': self.domain_id})
        self.assertValidDomainResponse(r, self.domain)

    def test_update_domain(self):
        """Call ``PATCH /domains/{domain_id}``."""
        ref = self.new_domain_ref()
        del ref['id']
        r = self.patch('/domains/%(domain_id)s' % {
            'domain_id': self.domain_id},
            body={'domain': ref})
        self.assertValidDomainResponse(r, ref)

    def test_disable_domain(self):
        """Call ``PATCH /domains/{domain_id}`` (set enabled=False)."""
        # Create a 2nd set of entities in a 2nd domain
        self.domain2 = self.new_domain_ref()
        self.assignment_api.create_domain(self.domain2['id'], self.domain2)

        self.project2 = self.new_project_ref(
            domain_id=self.domain2['id'])
        self.assignment_api.create_project(self.project2['id'], self.project2)

        self.user2 = self.new_user_ref(
            domain_id=self.domain2['id'],
            project_id=self.project2['id'])
        password = self.user2['password']
        self.user2 = self.identity_api.create_user(self.user2)
        self.user2['password'] = password

        self.assignment_api.add_user_to_project(self.project2['id'],
                                                self.user2['id'])

        # First check a user in that domain can authenticate, via
        # Both v2 and v3
        body = {
            'auth': {
                'passwordCredentials': {
                    'userId': self.user2['id'],
                    'password': self.user2['password']
                },
                'tenantId': self.project2['id']
            }
        }
        self.admin_request(path='/v2.0/tokens', method='POST', body=body)

        auth_data = self.build_authentication_request(
            user_id=self.user2['id'],
            password=self.user2['password'],
            project_id=self.project2['id'])
        self.v3_authenticate_token(auth_data)

        # Now disable the domain
        self.domain2['enabled'] = False
        r = self.patch('/domains/%(domain_id)s' % {
            'domain_id': self.domain2['id']},
            body={'domain': {'enabled': False}})
        self.assertValidDomainResponse(r, self.domain2)

        # Make sure the user can no longer authenticate, via
        # either API
        body = {
            'auth': {
                'passwordCredentials': {
                    'userId': self.user2['id'],
                    'password': self.user2['password']
                },
                'tenantId': self.project2['id']
            }
        }
        self.admin_request(
            path='/v2.0/tokens', method='POST', body=body, expected_status=401)

        # Try looking up in v3 by name and id
        auth_data = self.build_authentication_request(
            user_id=self.user2['id'],
            password=self.user2['password'],
            project_id=self.project2['id'])
        self.v3_authenticate_token(auth_data, expected_status=401)

        auth_data = self.build_authentication_request(
            username=self.user2['name'],
            user_domain_id=self.domain2['id'],
            password=self.user2['password'],
            project_id=self.project2['id'])
        self.v3_authenticate_token(auth_data, expected_status=401)

    def test_delete_enabled_domain_fails(self):
        """Call ``DELETE /domains/{domain_id}`` (when domain enabled)."""

        # Try deleting an enabled domain, which should fail
        self.delete('/domains/%(domain_id)s' % {
            'domain_id': self.domain['id']},
            expected_status=exception.ForbiddenAction.code)

    def test_delete_domain(self):
        """Call ``DELETE /domains/{domain_id}``.

        The sample data set up already has a user, group, project
        and credential that is part of self.domain. Since the user
        we will authenticate with is in this domain, we create a
        another set of entities in a second domain.  Deleting this
        second domain should delete all these new entities. In addition,
        all the entities in the regular self.domain should be unaffected
        by the delete.

        Test Plan:

        - Create domain2 and a 2nd set of entities
        - Disable domain2
        - Delete domain2
        - Check entities in domain2 have been deleted
        - Check entities in self.domain are unaffected

        """

        # Create a 2nd set of entities in a 2nd domain
        self.domain2 = self.new_domain_ref()
        self.assignment_api.create_domain(self.domain2['id'], self.domain2)

        self.project2 = self.new_project_ref(
            domain_id=self.domain2['id'])
        self.assignment_api.create_project(self.project2['id'], self.project2)

        self.user2 = self.new_user_ref(
            domain_id=self.domain2['id'],
            project_id=self.project2['id'])
        self.user2 = self.identity_api.create_user(self.user2)

        self.group2 = self.new_group_ref(
            domain_id=self.domain2['id'])
        self.group2 = self.identity_api.create_group(self.group2)

        self.credential2 = self.new_credential_ref(
            user_id=self.user2['id'],
            project_id=self.project2['id'])
        self.credential_api.create_credential(
            self.credential2['id'],
            self.credential2)

        # Now disable the new domain and delete it
        self.domain2['enabled'] = False
        r = self.patch('/domains/%(domain_id)s' % {
            'domain_id': self.domain2['id']},
            body={'domain': {'enabled': False}})
        self.assertValidDomainResponse(r, self.domain2)
        self.delete('/domains/%(domain_id)s' % {
            'domain_id': self.domain2['id']})

        # Check all the domain2 relevant entities are gone
        self.assertRaises(exception.DomainNotFound,
                          self.assignment_api.get_domain,
                          self.domain2['id'])
        self.assertRaises(exception.ProjectNotFound,
                          self.assignment_api.get_project,
                          self.project2['id'])
        self.assertRaises(exception.GroupNotFound,
                          self.identity_api.get_group,
                          self.group2['id'])
        self.assertRaises(exception.UserNotFound,
                          self.identity_api.get_user,
                          self.user2['id'])
        self.assertRaises(exception.CredentialNotFound,
                          self.credential_api.get_credential,
                          self.credential2['id'])

        # ...and that all self.domain entities are still here
        r = self.assignment_api.get_domain(self.domain['id'])
        self.assertDictEqual(r, self.domain)
        r = self.assignment_api.get_project(self.project['id'])
        self.assertDictEqual(r, self.project)
        r = self.identity_api.get_group(self.group['id'])
        self.assertDictEqual(r, self.group)
        r = self.identity_api.get_user(self.user['id'])
        self.user.pop('password')
        self.assertDictEqual(r, self.user)
        r = self.credential_api.get_credential(self.credential['id'])
        self.assertDictEqual(r, self.credential)

    def test_delete_default_domain_fails(self):
        # Attempting to delete the default domain results in 403 Forbidden.

        # Need to disable it first.
        self.patch('/domains/%(domain_id)s' % {
            'domain_id': CONF.identity.default_domain_id},
            body={'domain': {'enabled': False}})

        self.delete('/domains/%(domain_id)s' % {
            'domain_id': CONF.identity.default_domain_id},
            expected_status=exception.ForbiddenAction.code)

    def test_delete_new_default_domain_fails(self):
        # If change the default domain ID, deleting the new default domain
        # results in a 403 Forbidden.

        # Create a new domain that's not the default
        new_domain = self.new_domain_ref()
        new_domain_id = new_domain['id']
        self.assignment_api.create_domain(new_domain_id, new_domain)

        # Disable the new domain so can delete it later.
        self.patch('/domains/%(domain_id)s' % {
            'domain_id': new_domain_id},
            body={'domain': {'enabled': False}})

        # Change the default domain
        self.config_fixture.config(group='identity',
                                   default_domain_id=new_domain_id)

        # Attempt to delete the new domain

        self.delete('/domains/%(domain_id)s' % {'domain_id': new_domain_id},
                    expected_status=exception.ForbiddenAction.code)

    def test_delete_old_default_domain(self):
        # If change the default domain ID, deleting the old default domain
        # works.

        # Create a new domain that's not the default
        new_domain = self.new_domain_ref()
        new_domain_id = new_domain['id']
        self.assignment_api.create_domain(new_domain_id, new_domain)

        old_default_domain_id = CONF.identity.default_domain_id

        # Disable the default domain so we can delete it later.
        self.patch('/domains/%(domain_id)s' % {
            'domain_id': old_default_domain_id},
            body={'domain': {'enabled': False}})

        # Change the default domain
        self.config_fixture.config(group='identity',
                                   default_domain_id=new_domain_id)

        # Delete the old default domain

        self.delete(
            '/domains/%(domain_id)s' % {'domain_id': old_default_domain_id})

    def test_token_revoked_once_domain_disabled(self):
        """Test token from a disabled domain has been invalidated.

        Test that a token that was valid for an enabled domain
        becomes invalid once that domain is disabled.

        """

        self.domain = self.new_domain_ref()
        self.assignment_api.create_domain(self.domain['id'], self.domain)

        self.user2 = self.new_user_ref(domain_id=self.domain['id'])
        password = self.user2['password']
        self.user2 = self.identity_api.create_user(self.user2)
        self.user2['password'] = password

        # build a request body
        auth_body = self.build_authentication_request(
            user_id=self.user2['id'],
            password=self.user2['password'])

        # sends a request for the user's token
        token_resp = self.post('/auth/tokens', body=auth_body)

        subject_token = token_resp.headers.get('x-subject-token')

        # validates the returned token and it should be valid.
        self.head('/auth/tokens',
                  headers={'x-subject-token': subject_token},
                  expected_status=200)

        # now disable the domain
        self.domain['enabled'] = False
        url = "/domains/%(domain_id)s" % {'domain_id': self.domain['id']}
        self.patch(url,
                   body={'domain': {'enabled': False}},
                   expected_status=200)

        # validates the same token again and it should be 'not found'
        # as the domain has already been disabled.
        self.head('/auth/tokens',
                  headers={'x-subject-token': subject_token},
                  expected_status=404)

    def test_delete_domain_hierarchy(self):
        """Call ``DELETE /domains/{domain_id}``."""
        domain = self.new_domain_ref()
        self.assignment_api.create_domain(domain['id'], domain)

        root_project = self.new_project_ref(
            domain_id=domain['id'])
        self.assignment_api.create_project(root_project['id'], root_project)

        leaf_project = self.new_project_ref(
            domain_id=domain['id'],
            parent_id=root_project['id'])
        self.assignment_api.create_project(leaf_project['id'], leaf_project)

        # Need to disable it first.
        self.patch('/domains/%(domain_id)s' % {
            'domain_id': domain['id']},
            body={'domain': {'enabled': False}})

        self.delete(
            '/domains/%(domain_id)s' % {
                'domain_id': domain['id']})

        self.assertRaises(exception.DomainNotFound,
                          self.assignment_api.get_domain,
                          domain['id'])

        self.assertRaises(exception.ProjectNotFound,
                          self.assignment_api.get_project,
                          root_project['id'])

        self.assertRaises(exception.ProjectNotFound,
                          self.assignment_api.get_project,
                          leaf_project['id'])

    # project crud tests

    def test_list_projects(self):
        """Call ``GET /projects``."""
        resource_url = '/projects'
        r = self.get(resource_url)
        self.assertValidProjectListResponse(r, ref=self.project,
                                            resource_url=resource_url)

    def test_list_projects_xml(self):
        """Call ``GET /projects`` (xml data)."""
        resource_url = '/projects'
        r = self.get(resource_url, content_type='xml')
        self.assertValidProjectListResponse(r, ref=self.project,
                                            resource_url=resource_url)

    def test_create_project(self):
        """Call ``POST /projects``."""
        ref = self.new_project_ref(domain_id=self.domain_id)
        r = self.post(
            '/projects',
            body={'project': ref})
        self.assertValidProjectResponse(r, ref)

    def test_create_hierarchical_project(self):
        """Call ``POST /projects``."""
        ref = self.new_project_ref(domain_id=self.domain_id,
                                   parent_id=self.project_id)
        r = self.post(
            '/projects',
            body={'project': ref})
        self.assertValidProjectResponse(r, ref)

    def test_create_project_400(self):
        """Call ``POST /projects``."""
        self.post('/projects', body={'project': {}}, expected_status=400)

    def test_get_project(self):
        """Call ``GET /projects/{project_id}``."""
        r = self.get(
            '/projects/%(project_id)s' % {
                'project_id': self.project_id})
        self.assertValidProjectResponse(r, self.project)

    def _get_projects_in_hierarchy(self):
        """Creates a project hierarchy where self.project is the top of it,
           having a sub-project and a sub-sub-project in its hierarchy.

        """
        resp = self.get(
            '/projects/%(project_id)s' % {
                'project_id': self.project_id})

        projects = [resp.result]

        for i in range(2):
            new_ref = self.new_project_ref(
                domain_id=self.domain_id,
                parent_id=projects[i]['project']['id'])
            resp = self.post('/projects',
                             body={'project': new_ref})

            projects.append(resp.result)

        return projects

    def test_get_project_with_parents(self):
        """Call ``GET /projects/{project_id}?parents``."""
        projects = self._get_projects_in_hierarchy()

        r = self.get(
            '/projects/%(project_id)s?parents' % {
                'project_id': projects[1]['project']['id']})

        self.assertValidProjectResponse(r, projects[1]['project'])
        self.assertIn(projects[0], r.result['project']['parents'])
        self.assertNotIn(projects[2], r.result['project']['parents'])

    def test_get_project_with_subtree(self):
        """Call ``GET /projects/{project_id}?subtree``."""
        projects = self._get_projects_in_hierarchy()

        r = self.get(
            '/projects/%(project_id)s?subtree' % {
                'project_id': projects[1]['project']['id']})

        self.assertValidProjectResponse(r, projects[1]['project'])
        self.assertNotIn(projects[0], r.result['project']['subtree'])
        self.assertIn(projects[2], r.result['project']['subtree'])

    def test_update_project(self):
        """Call ``PATCH /projects/{project_id}``."""
        ref = self.new_project_ref(domain_id=self.domain_id)
        del ref['id']
        r = self.patch(
            '/projects/%(project_id)s' % {
                'project_id': self.project_id},
            body={'project': ref})
        self.assertValidProjectResponse(r, ref)

    def test_update_project_parent_id(self):
        """Call ``PATCH /projects/{project_id}``."""
        project = self.new_project_ref(domain_id=self.domain_id,
                                       parent_id=self.project_id)
        self.assignment_api.create_project(project['id'], project)
        project['parent_id'] = None
        self.patch(
            '/projects/%(project_id)s' % {
                'project_id': project['id']},
            body={'project': project},
            expected_status=403)

    def test_update_project_domain_id(self):
        """Call ``PATCH /projects/{project_id}`` with domain_id."""
        project = self.new_project_ref(domain_id=self.domain['id'])
        self.assignment_api.create_project(project['id'], project)
        project['domain_id'] = CONF.identity.default_domain_id
        r = self.patch('/projects/%(project_id)s' % {
            'project_id': project['id']},
            body={'project': project},
            expected_status=exception.ValidationError.code)
        self.config_fixture.config(domain_id_immutable=False)
        project['domain_id'] = self.domain['id']
        r = self.patch('/projects/%(project_id)s' % {
            'project_id': project['id']},
            body={'project': project})
        self.assertValidProjectResponse(r, project)

    def test_delete_project(self):
        """Call ``DELETE /projects/{project_id}``

        As well as making sure the delete succeeds, we ensure
        that any credentials that reference this projects are
        also deleted, while other credentials are unaffected.

        """
        # First check the credential for this project is present
        r = self.credential_api.get_credential(self.credential['id'])
        self.assertDictEqual(r, self.credential)
        # Create a second credential with a different project
        self.project2 = self.new_project_ref(
            domain_id=self.domain['id'])
        self.assignment_api.create_project(self.project2['id'], self.project2)
        self.credential2 = self.new_credential_ref(
            user_id=self.user['id'],
            project_id=self.project2['id'])
        self.credential_api.create_credential(
            self.credential2['id'],
            self.credential2)

        # Now delete the project
        self.delete(
            '/projects/%(project_id)s' % {
                'project_id': self.project_id})

        # Deleting the project should have deleted any credentials
        # that reference this project
        self.assertRaises(exception.CredentialNotFound,
                          self.credential_api.get_credential,
                          credential_id=self.credential['id'])
        # But the credential for project2 is unaffected
        r = self.credential_api.get_credential(self.credential2['id'])
        self.assertDictEqual(r, self.credential2)

    def test_delete_not_leaf_project(self):
        """Call ``DELETE /projects/{project_id}``."""
        leaf_project = self.new_project_ref(domain_id=self.domain_id,
                                            parent_id=self.project_id)
        self.assignment_api.create_project(leaf_project['id'], leaf_project)
        self.delete(
            '/projects/%(project_id)s' % {
                'project_id': self.project_id},
            expected_status=403)

    # user crud tests

    def test_create_user(self):
        """Call ``POST /users``."""
        ref = self.new_user_ref(domain_id=self.domain_id)
        r = self.post(
            '/users',
            body={'user': ref})
        return self.assertValidUserResponse(r, ref)

    def test_create_user_without_domain(self):
        """Call ``POST /users`` without specifying domain.

        According to the identity-api specification, if you do not
        explicitly specific the domain_id in the entity, it should
        take the domain scope of the token as the domain_id.

        """
        # Create a user with a role on the domain so we can get a
        # domain scoped token
        domain = self.new_domain_ref()
        self.assignment_api.create_domain(domain['id'], domain)
        user = self.new_user_ref(domain_id=domain['id'])
        password = user['password']
        user = self.identity_api.create_user(user)
        user['password'] = password
        self.assignment_api.create_grant(
            role_id=self.role_id, user_id=user['id'],
            domain_id=domain['id'])

        ref = self.new_user_ref(domain_id=domain['id'])
        ref_nd = ref.copy()
        ref_nd.pop('domain_id')
        auth = self.build_authentication_request(
            user_id=user['id'],
            password=user['password'],
            domain_id=domain['id'])
        r = self.post('/users', body={'user': ref_nd}, auth=auth)
        self.assertValidUserResponse(r, ref)

        # Now try the same thing without a domain token - which should fail
        ref = self.new_user_ref(domain_id=domain['id'])
        ref_nd = ref.copy()
        ref_nd.pop('domain_id')
        auth = self.build_authentication_request(
            user_id=self.user['id'],
            password=self.user['password'],
            project_id=self.project['id'])
        r = self.post('/users', body={'user': ref_nd}, auth=auth)
        # TODO(henry-nash): Due to bug #1283539 we currently automatically
        # use the default domain_id if a domain scoped token is not being
        # used. Change the code below to expect a failure once this bug is
        # fixed.
        ref['domain_id'] = CONF.identity.default_domain_id
        return self.assertValidUserResponse(r, ref)

    def test_create_user_400(self):
        """Call ``POST /users``."""
        self.post('/users', body={'user': {}}, expected_status=400)

    def test_list_users(self):
        """Call ``GET /users``."""
        resource_url = '/users'
        r = self.get(resource_url)
        self.assertValidUserListResponse(r, ref=self.user,
                                         resource_url=resource_url)

    def test_list_users_with_multiple_backends(self):
        """Call ``GET /users`` when multiple backends is enabled.

        In this scenario, the controller requires a domain to be specified
        either as a filter or by using a domain scoped token.

        """
        self.config_fixture.config(group='identity',
                                   domain_specific_drivers_enabled=True)

        # Create a user with a role on the domain so we can get a
        # domain scoped token
        domain = self.new_domain_ref()
        self.assignment_api.create_domain(domain['id'], domain)
        user = self.new_user_ref(domain_id=domain['id'])
        password = user['password']
        user = self.identity_api.create_user(user)
        user['password'] = password
        self.assignment_api.create_grant(
            role_id=self.role_id, user_id=user['id'],
            domain_id=domain['id'])

        ref = self.new_user_ref(domain_id=domain['id'])
        ref_nd = ref.copy()
        ref_nd.pop('domain_id')
        auth = self.build_authentication_request(
            user_id=user['id'],
            password=user['password'],
            domain_id=domain['id'])

        # First try using a domain scoped token
        resource_url = '/users'
        r = self.get(resource_url, auth=auth)
        self.assertValidUserListResponse(r, ref=user,
                                         resource_url=resource_url)

        # Now try with an explicit filter
        resource_url = ('/users?domain_id=%(domain_id)s' %
                        {'domain_id': domain['id']})
        r = self.get(resource_url)
        self.assertValidUserListResponse(r, ref=user,
                                         resource_url=resource_url)

        # Now try the same thing without a domain token or filter,
        # which should fail
        r = self.get('/users', expected_status=exception.Unauthorized.code)

    def test_list_users_with_static_admin_token_and_multiple_backends(self):
        # domain-specific operations with the bootstrap ADMIN token is
        # disallowed when domain-specific drivers are enabled
        self.config_fixture.config(group='identity',
                                   domain_specific_drivers_enabled=True)
        self.get('/users', token=CONF.admin_token,
                 expected_status=exception.Unauthorized.code)

    def test_list_users_no_default_project(self):
        """Call ``GET /users`` making sure no default_project_id."""
        user = self.new_user_ref(self.domain_id)
        user = self.identity_api.create_user(user)
        resource_url = '/users'
        r = self.get(resource_url)
        self.assertValidUserListResponse(r, ref=user,
                                         resource_url=resource_url)

    def test_list_users_xml(self):
        """Call ``GET /users`` (xml data)."""
        resource_url = '/users'
        r = self.get(resource_url, content_type='xml')
        self.assertValidUserListResponse(r, ref=self.user,
                                         resource_url=resource_url)

    def test_get_user(self):
        """Call ``GET /users/{user_id}``."""
        r = self.get('/users/%(user_id)s' % {
            'user_id': self.user['id']})
        self.assertValidUserResponse(r, self.user)

    def test_get_user_with_default_project(self):
        """Call ``GET /users/{user_id}`` making sure of default_project_id."""
        user = self.new_user_ref(domain_id=self.domain_id,
                                 project_id=self.project_id)
        user = self.identity_api.create_user(user)
        r = self.get('/users/%(user_id)s' % {'user_id': user['id']})
        self.assertValidUserResponse(r, user)

    def test_add_user_to_group(self):
        """Call ``PUT /groups/{group_id}/users/{user_id}``."""
        self.put('/groups/%(group_id)s/users/%(user_id)s' % {
            'group_id': self.group_id, 'user_id': self.user['id']})

    def test_list_groups_for_user(self):
        """Call ``GET /users/{user_id}/groups``."""

        self.user1 = self.new_user_ref(
            domain_id=self.domain['id'])
        password = self.user1['password']
        self.user1 = self.identity_api.create_user(self.user1)
        self.user1['password'] = password
        self.user2 = self.new_user_ref(
            domain_id=self.domain['id'])
        password = self.user2['password']
        self.user2 = self.identity_api.create_user(self.user2)
        self.user2['password'] = password
        self.put('/groups/%(group_id)s/users/%(user_id)s' % {
            'group_id': self.group_id, 'user_id': self.user1['id']})

        # Scenarios below are written to test the default policy configuration

        # One should be allowed to list one's own groups
        auth = self.build_authentication_request(
            user_id=self.user1['id'],
            password=self.user1['password'])
        resource_url = ('/users/%(user_id)s/groups' %
                        {'user_id': self.user1['id']})
        r = self.get(resource_url, auth=auth)
        self.assertValidGroupListResponse(r, ref=self.group,
                                          resource_url=resource_url)

        # Administrator is allowed to list others' groups
        resource_url = ('/users/%(user_id)s/groups' %
                        {'user_id': self.user1['id']})
        r = self.get(resource_url)
        self.assertValidGroupListResponse(r, ref=self.group,
                                          resource_url=resource_url)

        # Ordinary users should not be allowed to list other's groups
        auth = self.build_authentication_request(
            user_id=self.user2['id'],
            password=self.user2['password'])
        r = self.get('/users/%(user_id)s/groups' % {
            'user_id': self.user1['id']}, auth=auth,
            expected_status=exception.ForbiddenAction.code)

    def test_check_user_in_group(self):
        """Call ``HEAD /groups/{group_id}/users/{user_id}``."""
        self.put('/groups/%(group_id)s/users/%(user_id)s' % {
            'group_id': self.group_id, 'user_id': self.user['id']})
        self.head('/groups/%(group_id)s/users/%(user_id)s' % {
            'group_id': self.group_id, 'user_id': self.user['id']})

    def test_list_users_in_group(self):
        """Call ``GET /groups/{group_id}/users``."""
        self.put('/groups/%(group_id)s/users/%(user_id)s' % {
            'group_id': self.group_id, 'user_id': self.user['id']})
        resource_url = ('/groups/%(group_id)s/users' %
                        {'group_id': self.group_id})
        r = self.get(resource_url)
        self.assertValidUserListResponse(r, ref=self.user,
                                         resource_url=resource_url)
        self.assertIn('/groups/%(group_id)s/users' % {
            'group_id': self.group_id}, r.result['links']['self'])

    def test_remove_user_from_group(self):
        """Call ``DELETE /groups/{group_id}/users/{user_id}``."""
        self.put('/groups/%(group_id)s/users/%(user_id)s' % {
            'group_id': self.group_id, 'user_id': self.user['id']})
        self.delete('/groups/%(group_id)s/users/%(user_id)s' % {
            'group_id': self.group_id, 'user_id': self.user['id']})

    def test_update_user(self):
        """Call ``PATCH /users/{user_id}``."""
        user = self.new_user_ref(domain_id=self.domain_id)
        del user['id']
        r = self.patch('/users/%(user_id)s' % {
            'user_id': self.user['id']},
            body={'user': user})
        self.assertValidUserResponse(r, user)

    def test_update_user_domain_id(self):
        """Call ``PATCH /users/{user_id}`` with domain_id."""
        user = self.new_user_ref(domain_id=self.domain['id'])
        user = self.identity_api.create_user(user)
        user['domain_id'] = CONF.identity.default_domain_id
        r = self.patch('/users/%(user_id)s' % {
            'user_id': user['id']},
            body={'user': user},
            expected_status=exception.ValidationError.code)
        self.config_fixture.config(domain_id_immutable=False)
        user['domain_id'] = self.domain['id']
        r = self.patch('/users/%(user_id)s' % {
            'user_id': user['id']},
            body={'user': user})
        self.assertValidUserResponse(r, user)

    def test_delete_user(self):
        """Call ``DELETE /users/{user_id}``.

        As well as making sure the delete succeeds, we ensure
        that any credentials that reference this user are
        also deleted, while other credentials are unaffected.
        In addition, no tokens should remain valid for this user.

        """
        # First check the credential for this user is present
        r = self.credential_api.get_credential(self.credential['id'])
        self.assertDictEqual(r, self.credential)
        # Create a second credential with a different user
        self.user2 = self.new_user_ref(
            domain_id=self.domain['id'],
            project_id=self.project['id'])
        self.user2 = self.identity_api.create_user(self.user2)
        self.credential2 = self.new_credential_ref(
            user_id=self.user2['id'],
            project_id=self.project['id'])
        self.credential_api.create_credential(
            self.credential2['id'],
            self.credential2)
        # Create a token for this user which we can check later
        # gets deleted
        auth_data = self.build_authentication_request(
            user_id=self.user['id'],
            password=self.user['password'],
            project_id=self.project['id'])
        token = self.get_requested_token(auth_data)
        # Confirm token is valid for now
        self.head('/auth/tokens',
                  headers={'X-Subject-Token': token},
                  expected_status=200)

        # Now delete the user
        self.delete('/users/%(user_id)s' % {
            'user_id': self.user['id']})

        # Deleting the user should have deleted any credentials
        # that reference this project
        self.assertRaises(exception.CredentialNotFound,
                          self.credential_api.get_credential,
                          self.credential['id'])
        # And the no tokens we remain valid
        tokens = self.token_provider_api._persistence._list_tokens(
            self.user['id'])
        self.assertEqual(0, len(tokens))
        # But the credential for user2 is unaffected
        r = self.credential_api.get_credential(self.credential2['id'])
        self.assertDictEqual(r, self.credential2)

    # group crud tests

    def test_create_group(self):
        """Call ``POST /groups``."""
        ref = self.new_group_ref(domain_id=self.domain_id)
        r = self.post(
            '/groups',
            body={'group': ref})
        return self.assertValidGroupResponse(r, ref)

    def test_create_group_400(self):
        """Call ``POST /groups``."""
        self.post('/groups', body={'group': {}}, expected_status=400)

    def test_list_groups(self):
        """Call ``GET /groups``."""
        resource_url = '/groups'
        r = self.get(resource_url)
        self.assertValidGroupListResponse(r, ref=self.group,
                                          resource_url=resource_url)

    def test_list_groups_xml(self):
        """Call ``GET /groups`` (xml data)."""
        resource_url = '/groups'
        r = self.get(resource_url, content_type='xml')
        self.assertValidGroupListResponse(r, ref=self.group,
                                          resource_url=resource_url)

    def test_get_group(self):
        """Call ``GET /groups/{group_id}``."""
        r = self.get('/groups/%(group_id)s' % {
            'group_id': self.group_id})
        self.assertValidGroupResponse(r, self.group)

    def test_update_group(self):
        """Call ``PATCH /groups/{group_id}``."""
        group = self.new_group_ref(domain_id=self.domain_id)
        del group['id']
        r = self.patch('/groups/%(group_id)s' % {
            'group_id': self.group_id},
            body={'group': group})
        self.assertValidGroupResponse(r, group)

    def test_update_group_domain_id(self):
        """Call ``PATCH /groups/{group_id}`` with domain_id."""
        group = self.new_group_ref(domain_id=self.domain['id'])
        group = self.identity_api.create_group(group)
        group['domain_id'] = CONF.identity.default_domain_id
        r = self.patch('/groups/%(group_id)s' % {
            'group_id': group['id']},
            body={'group': group},
            expected_status=exception.ValidationError.code)
        self.config_fixture.config(domain_id_immutable=False)
        group['domain_id'] = self.domain['id']
        r = self.patch('/groups/%(group_id)s' % {
            'group_id': group['id']},
            body={'group': group})
        self.assertValidGroupResponse(r, group)

    def test_delete_group(self):
        """Call ``DELETE /groups/{group_id}``."""
        self.delete('/groups/%(group_id)s' % {
            'group_id': self.group_id})

    # role crud tests

    def test_create_role(self):
        """Call ``POST /roles``."""
        ref = self.new_role_ref()
        r = self.post(
            '/roles',
            body={'role': ref})
        return self.assertValidRoleResponse(r, ref)

    def test_create_role_400(self):
        """Call ``POST /roles``."""
        self.post('/roles', body={'role': {}}, expected_status=400)

    def test_list_roles(self):
        """Call ``GET /roles``."""
        resource_url = '/roles'
        r = self.get(resource_url)
        self.assertValidRoleListResponse(r, ref=self.role,
                                         resource_url=resource_url)

    def test_list_roles_xml(self):
        """Call ``GET /roles`` (xml data)."""
        resource_url = '/roles'
        r = self.get(resource_url, content_type='xml')
        self.assertValidRoleListResponse(r, ref=self.role,
                                         resource_url=resource_url)

    def test_get_role(self):
        """Call ``GET /roles/{role_id}``."""
        r = self.get('/roles/%(role_id)s' % {
            'role_id': self.role_id})
        self.assertValidRoleResponse(r, self.role)

    def test_update_role(self):
        """Call ``PATCH /roles/{role_id}``."""
        ref = self.new_role_ref()
        del ref['id']
        r = self.patch('/roles/%(role_id)s' % {
            'role_id': self.role_id},
            body={'role': ref})
        self.assertValidRoleResponse(r, ref)

    def test_delete_role(self):
        """Call ``DELETE /roles/{role_id}``."""
        self.delete('/roles/%(role_id)s' % {
            'role_id': self.role_id})

    def _create_new_user_and_assign_role_on_project(self):
        """Create a new user and assign user a role on a project."""
        # Create a new user
        new_user = self.new_user_ref(domain_id=self.domain_id)
        user_ref = self.identity_api.create_user(new_user)
        # Assign the user a role on the project
        collection_url = (
            '/projects/%(project_id)s/users/%(user_id)s/roles' % {
                'project_id': self.project_id,
                'user_id': user_ref['id']})
        member_url = ('%(collection_url)s/%(role_id)s' % {
            'collection_url': collection_url,
            'role_id': self.role_id})
        self.put(member_url, expected_status=204)
        # Check the user has the role assigned
        self.head(member_url, expected_status=204)
        return member_url, user_ref

    # TODO(lbragstad): Move this test to tests/test_v3_assignment.py
    def test_delete_user_before_removing_role_assignment_succeeds(self):
        """Call ``DELETE`` on the user before the role assignment."""
        member_url, user = self._create_new_user_and_assign_role_on_project()
        # Delete the user from identity backend
        self.identity_api.driver.delete_user(user['id'])
        # Clean up the role assignment
        self.delete(member_url, expected_status=204)
        # Make sure the role is gone
        self.head(member_url, expected_status=404)

    # TODO(lbragstad): Move this test to tests/test_v3_assignment.py
    def test_delete_user_and_check_role_assignment_fails(self):
        """Call ``DELETE`` on the user and check the role assignment."""
        member_url, user = self._create_new_user_and_assign_role_on_project()
        # Delete the user from identity backend
        self.identity_api.driver.delete_user(user['id'])
        # We should get a 404 when looking for the user in the identity
        # backend because we're not performing a delete operation on the role.
        self.head(member_url, expected_status=404)

    def test_crud_user_project_role_grants(self):
        collection_url = (
            '/projects/%(project_id)s/users/%(user_id)s/roles' % {
                'project_id': self.project['id'],
                'user_id': self.user['id']})
        member_url = '%(collection_url)s/%(role_id)s' % {
            'collection_url': collection_url,
            'role_id': self.role_id}

        self.put(member_url)
        self.head(member_url)
        r = self.get(collection_url)
        self.assertValidRoleListResponse(r, ref=self.role,
                                         resource_url=collection_url)

        # FIXME(gyee): this test is no longer valid as user
        # have no role in the project. Can't get a scoped token
        # self.delete(member_url)
        # r = self.get(collection_url)
        # self.assertValidRoleListResponse(r, expected_length=0)
        # self.assertIn(collection_url, r.result['links']['self'])

    def test_crud_user_project_role_grants_no_user(self):
        """Grant role on a project to a user that doesn't exist, 404 result.

        When grant a role on a project to a user that doesn't exist, the server
        returns 404 Not Found for the user.

        """

        user_id = uuid.uuid4().hex

        collection_url = (
            '/projects/%(project_id)s/users/%(user_id)s/roles' % {
                'project_id': self.project['id'], 'user_id': user_id})
        member_url = '%(collection_url)s/%(role_id)s' % {
            'collection_url': collection_url,
            'role_id': self.role_id}

        self.put(member_url, expected_status=404)

    def test_crud_user_domain_role_grants(self):
        collection_url = (
            '/domains/%(domain_id)s/users/%(user_id)s/roles' % {
                'domain_id': self.domain_id,
                'user_id': self.user['id']})
        member_url = '%(collection_url)s/%(role_id)s' % {
            'collection_url': collection_url,
            'role_id': self.role_id}

        self.put(member_url)
        self.head(member_url)
        r = self.get(collection_url)
        self.assertValidRoleListResponse(r, ref=self.role,
                                         resource_url=collection_url)

        self.delete(member_url)
        r = self.get(collection_url)
        self.assertValidRoleListResponse(r, expected_length=0,
                                         resource_url=collection_url)

    def test_crud_user_domain_role_grants_no_user(self):
        """Grant role on a domain to a user that doesn't exist, 404 result.

        When grant a role on a domain to a user that doesn't exist, the server
        returns 404 Not Found for the user.

        """

        user_id = uuid.uuid4().hex

        collection_url = (
            '/domains/%(domain_id)s/users/%(user_id)s/roles' % {
                'domain_id': self.domain_id, 'user_id': user_id})
        member_url = '%(collection_url)s/%(role_id)s' % {
            'collection_url': collection_url,
            'role_id': self.role_id}

        self.put(member_url, expected_status=404)

    def test_crud_group_project_role_grants(self):
        collection_url = (
            '/projects/%(project_id)s/groups/%(group_id)s/roles' % {
                'project_id': self.project_id,
                'group_id': self.group_id})
        member_url = '%(collection_url)s/%(role_id)s' % {
            'collection_url': collection_url,
            'role_id': self.role_id}

        self.put(member_url)
        self.head(member_url)
        r = self.get(collection_url)
        self.assertValidRoleListResponse(r, ref=self.role,
                                         resource_url=collection_url)

        self.delete(member_url)
        r = self.get(collection_url)
        self.assertValidRoleListResponse(r, expected_length=0,
                                         resource_url=collection_url)

    def test_crud_group_project_role_grants_no_group(self):
        """Grant role on a project to a group that doesn't exist, 404 result.

        When grant a role on a project to a group that doesn't exist, the
        server returns 404 Not Found for the group.

        """

        group_id = uuid.uuid4().hex

        collection_url = (
            '/projects/%(project_id)s/groups/%(group_id)s/roles' % {
                'project_id': self.project_id,
                'group_id': group_id})
        member_url = '%(collection_url)s/%(role_id)s' % {
            'collection_url': collection_url,
            'role_id': self.role_id}

        self.put(member_url, expected_status=404)

    def test_crud_group_domain_role_grants(self):
        collection_url = (
            '/domains/%(domain_id)s/groups/%(group_id)s/roles' % {
                'domain_id': self.domain_id,
                'group_id': self.group_id})
        member_url = '%(collection_url)s/%(role_id)s' % {
            'collection_url': collection_url,
            'role_id': self.role_id}

        self.put(member_url)
        self.head(member_url)
        r = self.get(collection_url)
        self.assertValidRoleListResponse(r, ref=self.role,
                                         resource_url=collection_url)

        self.delete(member_url)
        r = self.get(collection_url)
        self.assertValidRoleListResponse(r, expected_length=0,
                                         resource_url=collection_url)

    def test_crud_group_domain_role_grants_no_group(self):
        """Grant role on a domain to a group that doesn't exist, 404 result.

        When grant a role on a domain to a group that doesn't exist, the server
        returns 404 Not Found for the group.

        """

        group_id = uuid.uuid4().hex

        collection_url = (
            '/domains/%(domain_id)s/groups/%(group_id)s/roles' % {
                'domain_id': self.domain_id,
                'group_id': group_id})
        member_url = '%(collection_url)s/%(role_id)s' % {
            'collection_url': collection_url,
            'role_id': self.role_id}

        self.put(member_url, expected_status=404)

    def test_token_revoked_once_group_role_grant_revoked(self):
        """Test token is revoked when group role grant is revoked

        When a role granted to a group is revoked for a given scope,
        all tokens related to this scope and belonging to one of the members
        of this group should be revoked.

        The revocation should be independently to the presence
        of the revoke API.
        """

        # If enabled, the revoke API will revoke tokens first.
        # This ensures that tokens are revoked even without revoke API.
        self.assignment_api.revoke_api = None

        # creates grant from group on project.
        self.assignment_api.create_grant(role_id=self.role['id'],
                                         project_id=self.project['id'],
                                         group_id=self.group['id'])

        # adds user to the group.
        self.identity_api.add_user_to_group(user_id=self.user['id'],
                                            group_id=self.group['id'])

        # creates a token for the user
        auth_body = self.build_authentication_request(
            user_id=self.user['id'],
            password=self.user['password'],
            project_id=self.project['id'])
        token_resp = self.post('/auth/tokens', body=auth_body)
        token = token_resp.headers.get('x-subject-token')

        # validates the returned token; it should be valid.
        self.head('/auth/tokens',
                  headers={'x-subject-token': token},
                  expected_status=200)

        # revokes the grant from group on project.
        self.assignment_api.delete_grant(role_id=self.role['id'],
                                         project_id=self.project['id'],
                                         group_id=self.group['id'])

        # validates the same token again; it should not longer be valid.
        self.head('/auth/tokens',
                  headers={'x-subject-token': token},
                  expected_status=404)

    def test_get_role_assignments(self):
        """Call ``GET /role_assignments``.

        The sample data set up already has a user, group and project
        that is part of self.domain. We use these plus a new user
        we create as our data set, making sure we ignore any
        role assignments that are already in existence.

        Since we don't yet support a first class entity for role
        assignments, we are only testing the LIST API.  To create
        and delete the role assignments we use the old grant APIs.

        Test Plan:

        - Create extra user for tests
        - Get a list of all existing role assignments
        - Add a new assignment for each of the four combinations, i.e.
          group+domain, user+domain, group+project, user+project, using
          the same role each time
        - Get a new list of all role assignments, checking these four new
          ones have been added
        - Then delete the four we added
        - Get a new list of all role assignments, checking the four have
          been removed

        """

        # Since the default fixtures already assign some roles to the
        # user it creates, we also need a new user that will not have any
        # existing assignments
        self.user1 = self.new_user_ref(
            domain_id=self.domain['id'])
        self.user1 = self.identity_api.create_user(self.user1)

        collection_url = '/role_assignments'
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        existing_assignments = len(r.result.get('role_assignments'))

        # Now add one of each of the four types of assignment, making sure
        # that we get them all back.
        gd_url, gd_entity = _build_role_assignment_url_and_entity(
            domain_id=self.domain_id, group_id=self.group_id,
            role_id=self.role_id)
        self.put(gd_url)
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(existing_assignments + 1,
                         len(r.result.get('role_assignments')))
        self.assertRoleAssignmentInListResponse(r, gd_entity, link_url=gd_url)

        ud_url, ud_entity = _build_role_assignment_url_and_entity(
            domain_id=self.domain_id, user_id=self.user1['id'],
            role_id=self.role_id)
        self.put(ud_url)
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(existing_assignments + 2,
                         len(r.result.get('role_assignments')))
        self.assertRoleAssignmentInListResponse(r, ud_entity, link_url=ud_url)

        gp_url, gp_entity = _build_role_assignment_url_and_entity(
            project_id=self.project_id, group_id=self.group_id,
            role_id=self.role_id)
        self.put(gp_url)
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(existing_assignments + 3,
                         len(r.result.get('role_assignments')))
        self.assertRoleAssignmentInListResponse(r, gp_entity, link_url=gp_url)

        up_url, up_entity = _build_role_assignment_url_and_entity(
            project_id=self.project_id, user_id=self.user1['id'],
            role_id=self.role_id)
        self.put(up_url)
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(existing_assignments + 4,
                         len(r.result.get('role_assignments')))
        self.assertRoleAssignmentInListResponse(r, up_entity, link_url=up_url)

        # Now delete the four we added and make sure they are removed
        # from the collection.

        self.delete(gd_url)
        self.delete(ud_url)
        self.delete(gp_url)
        self.delete(up_url)
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(existing_assignments,
                         len(r.result.get('role_assignments')))
        self.assertRoleAssignmentNotInListResponse(r, gd_entity)
        self.assertRoleAssignmentNotInListResponse(r, ud_entity)
        self.assertRoleAssignmentNotInListResponse(r, gp_entity)
        self.assertRoleAssignmentNotInListResponse(r, up_entity)

    def test_get_effective_role_assignments(self):
        """Call ``GET /role_assignments?effective``.

        Test Plan:

        - Create two extra user for tests
        - Add these users to a group
        - Add a role assignment for the group on a domain
        - Get a list of all role assignments, checking one has been added
        - Then get a list of all effective role assignments - the group
          assignment should have turned into assignments on the domain
          for each of the group members.

        """
        self.user1 = self.new_user_ref(
            domain_id=self.domain['id'])
        password = self.user1['password']
        self.user1 = self.identity_api.create_user(self.user1)
        self.user1['password'] = password
        self.user2 = self.new_user_ref(
            domain_id=self.domain['id'])
        password = self.user2['password']
        self.user2 = self.identity_api.create_user(self.user2)
        self.user2['password'] = password
        self.identity_api.add_user_to_group(self.user1['id'], self.group['id'])
        self.identity_api.add_user_to_group(self.user2['id'], self.group['id'])

        collection_url = '/role_assignments'
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        existing_assignments = len(r.result.get('role_assignments'))

        gd_url, gd_entity = _build_role_assignment_url_and_entity(
            domain_id=self.domain_id, group_id=self.group_id,
            role_id=self.role_id)
        self.put(gd_url)
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(existing_assignments + 1,
                         len(r.result.get('role_assignments')))
        self.assertRoleAssignmentInListResponse(r, gd_entity, link_url=gd_url)

        # Now re-read the collection asking for effective roles - this
        # should mean the group assignment is translated into the two
        # member user assignments
        collection_url = '/role_assignments?effective'
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(existing_assignments + 2,
                         len(r.result.get('role_assignments')))
        unused, ud_entity = _build_role_assignment_url_and_entity(
            domain_id=self.domain_id, user_id=self.user1['id'],
            role_id=self.role_id)
        gd_url, unused = _build_role_assignment_url_and_entity(
            domain_id=self.domain_id, group_id=self.group['id'],
            role_id=self.role_id)
        self.assertRoleAssignmentInListResponse(r, ud_entity, link_url=gd_url)
        ud_url, ud_entity = _build_role_assignment_url_and_entity(
            domain_id=self.domain_id, user_id=self.user2['id'],
            role_id=self.role_id)
        self.assertRoleAssignmentInListResponse(r, ud_entity, link_url=gd_url)

    def test_check_effective_values_for_role_assignments(self):
        """Call ``GET /role_assignments?effective=value``.

        Check the various ways of specifying the 'effective'
        query parameter.  If the 'effective' query parameter
        is included then this should always be treated as meaning 'True'
        unless it is specified as:

        {url}?effective=0

        This is by design to match the agreed way of handling
        policy checking on query/filter parameters.

        Test Plan:

        - Create two extra user for tests
        - Add these users to a group
        - Add a role assignment for the group on a domain
        - Get a list of all role assignments, checking one has been added
        - Then issue various request with different ways of defining
          the 'effective' query parameter. As we have tested the
          correctness of the data coming back when we get effective roles
          in other tests, here we just use the count of entities to
          know if we are getting effective roles or not

        """
        self.user1 = self.new_user_ref(
            domain_id=self.domain['id'])
        password = self.user1['password']
        self.user1 = self.identity_api.create_user(self.user1)
        self.user1['password'] = password
        self.user2 = self.new_user_ref(
            domain_id=self.domain['id'])
        password = self.user2['password']
        self.user2 = self.identity_api.create_user(self.user2)
        self.user2['password'] = password
        self.identity_api.add_user_to_group(self.user1['id'], self.group['id'])
        self.identity_api.add_user_to_group(self.user2['id'], self.group['id'])

        collection_url = '/role_assignments'
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        existing_assignments = len(r.result.get('role_assignments'))

        gd_url, gd_entity = _build_role_assignment_url_and_entity(
            domain_id=self.domain_id, group_id=self.group_id,
            role_id=self.role_id)
        self.put(gd_url)
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(existing_assignments + 1,
                         len(r.result.get('role_assignments')))
        self.assertRoleAssignmentInListResponse(r, gd_entity, link_url=gd_url)

        # Now re-read the collection asking for effective roles,
        # using the most common way of defining "effective'. This
        # should mean the group assignment is translated into the two
        # member user assignments
        collection_url = '/role_assignments?effective'
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(existing_assignments + 2,
                         len(r.result.get('role_assignments')))
        # Now set 'effective' to false explicitly - should get
        # back the regular roles
        collection_url = '/role_assignments?effective=0'
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(existing_assignments + 1,
                         len(r.result.get('role_assignments')))
        # Now try setting  'effective' to 'False' explicitly- this is
        # NOT supported as a way of setting a query or filter
        # parameter to false by design. Hence we should get back
        # effective roles.
        collection_url = '/role_assignments?effective=False'
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(existing_assignments + 2,
                         len(r.result.get('role_assignments')))
        # Now set 'effective' to True explicitly
        collection_url = '/role_assignments?effective=True'
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(existing_assignments + 2,
                         len(r.result.get('role_assignments')))

    def test_filtered_role_assignments(self):
        """Call ``GET /role_assignments?filters``.

        Test Plan:

        - Create extra users, group, role and project for tests
        - Make the following assignments:
          Give group1, role1 on project1 and domain
          Give user1, role2 on project1 and domain
          Make User1 a member of Group1
        - Test a series of single filter list calls, checking that
          the correct results are obtained
        - Test a multi-filtered list call
        - Test listing all effective roles for a given user
        - Test the equivalent of the list of roles in a project scoped
          token (all effective roles for a user on a project)

        """

        # Since the default fixtures already assign some roles to the
        # user it creates, we also need a new user that will not have any
        # existing assignments
        self.user1 = self.new_user_ref(
            domain_id=self.domain['id'])
        password = self.user1['password']
        self.user1 = self.identity_api.create_user(self.user1)
        self.user1['password'] = password
        self.user2 = self.new_user_ref(
            domain_id=self.domain['id'])
        password = self.user2['password']
        self.user2 = self.identity_api.create_user(self.user2)
        self.user2['password'] = password
        self.group1 = self.new_group_ref(
            domain_id=self.domain['id'])
        self.group1 = self.identity_api.create_group(self.group1)
        self.identity_api.add_user_to_group(self.user1['id'],
                                            self.group1['id'])
        self.identity_api.add_user_to_group(self.user2['id'],
                                            self.group1['id'])
        self.project1 = self.new_project_ref(
            domain_id=self.domain['id'])
        self.assignment_api.create_project(self.project1['id'], self.project1)
        self.role1 = self.new_role_ref()
        self.assignment_api.create_role(self.role1['id'], self.role1)
        self.role2 = self.new_role_ref()
        self.assignment_api.create_role(self.role2['id'], self.role2)

        # Now add one of each of the four types of assignment

        gd_url, gd_entity = _build_role_assignment_url_and_entity(
            domain_id=self.domain_id, group_id=self.group1['id'],
            role_id=self.role1['id'])
        self.put(gd_url)

        ud_url, ud_entity = _build_role_assignment_url_and_entity(
            domain_id=self.domain_id, user_id=self.user1['id'],
            role_id=self.role2['id'])
        self.put(ud_url)

        gp_url, gp_entity = _build_role_assignment_url_and_entity(
            project_id=self.project1['id'], group_id=self.group1['id'],
            role_id=self.role1['id'])
        self.put(gp_url)

        up_url, up_entity = _build_role_assignment_url_and_entity(
            project_id=self.project1['id'], user_id=self.user1['id'],
            role_id=self.role2['id'])
        self.put(up_url)

        # Now list by various filters to make sure we get back the right ones

        collection_url = ('/role_assignments?scope.project.id=%s' %
                          self.project1['id'])
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(2, len(r.result.get('role_assignments')))
        self.assertRoleAssignmentInListResponse(r, up_entity, link_url=up_url)
        self.assertRoleAssignmentInListResponse(r, gp_entity, link_url=gp_url)

        collection_url = ('/role_assignments?scope.domain.id=%s' %
                          self.domain['id'])
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(2, len(r.result.get('role_assignments')))
        self.assertRoleAssignmentInListResponse(r, ud_entity, link_url=ud_url)
        self.assertRoleAssignmentInListResponse(r, gd_entity, link_url=gd_url)

        collection_url = '/role_assignments?user.id=%s' % self.user1['id']
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(2, len(r.result.get('role_assignments')))
        self.assertRoleAssignmentInListResponse(r, up_entity, link_url=up_url)
        self.assertRoleAssignmentInListResponse(r, ud_entity, link_url=ud_url)

        collection_url = '/role_assignments?group.id=%s' % self.group1['id']
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(2, len(r.result.get('role_assignments')))
        self.assertRoleAssignmentInListResponse(r, gd_entity, link_url=gd_url)
        self.assertRoleAssignmentInListResponse(r, gp_entity, link_url=gp_url)

        collection_url = '/role_assignments?role.id=%s' % self.role1['id']
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(2, len(r.result.get('role_assignments')))
        self.assertRoleAssignmentInListResponse(r, gd_entity, link_url=gd_url)
        self.assertRoleAssignmentInListResponse(r, gp_entity, link_url=gp_url)

        # Let's try combining two filers together....

        collection_url = (
            '/role_assignments?user.id=%(user_id)s'
            '&scope.project.id=%(project_id)s' % {
                'user_id': self.user1['id'],
                'project_id': self.project1['id']})
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(1, len(r.result.get('role_assignments')))
        self.assertRoleAssignmentInListResponse(r, up_entity, link_url=up_url)

        # Now for a harder one - filter for user with effective
        # roles - this should return role assignment that were directly
        # assigned as well as by virtue of group membership

        collection_url = ('/role_assignments?effective&user.id=%s' %
                          self.user1['id'])
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(4, len(r.result.get('role_assignments')))
        # Should have the two direct roles...
        self.assertRoleAssignmentInListResponse(r, up_entity, link_url=up_url)
        self.assertRoleAssignmentInListResponse(r, ud_entity, link_url=ud_url)
        # ...and the two via group membership...
        unused, up1_entity = _build_role_assignment_url_and_entity(
            project_id=self.project1['id'], user_id=self.user1['id'],
            role_id=self.role1['id'])
        unused, ud1_entity = _build_role_assignment_url_and_entity(
            domain_id=self.domain_id, user_id=self.user1['id'],
            role_id=self.role1['id'])
        gp1_url, unused = _build_role_assignment_url_and_entity(
            project_id=self.project1['id'], group_id=self.group1['id'],
            role_id=self.role1['id'])
        gd1_url, unused = _build_role_assignment_url_and_entity(
            domain_id=self.domain_id, group_id=self.group1['id'],
            role_id=self.role1['id'])
        self.assertRoleAssignmentInListResponse(r, up1_entity,
                                                link_url=gp1_url)
        self.assertRoleAssignmentInListResponse(r, ud1_entity,
                                                link_url=gd1_url)

        # ...and for the grand-daddy of them all, simulate the request
        # that would generate the list of effective roles in a project
        # scoped token.

        collection_url = (
            '/role_assignments?effective&user.id=%(user_id)s'
            '&scope.project.id=%(project_id)s' % {
                'user_id': self.user1['id'],
                'project_id': self.project1['id']})
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(2, len(r.result.get('role_assignments')))
        # Should have one direct role and one from group membership...
        self.assertRoleAssignmentInListResponse(r, up_entity, link_url=up_url)
        self.assertRoleAssignmentInListResponse(r, up1_entity,
                                                link_url=gp1_url)


class IdentityInheritanceTestCase(test_v3.RestfulTestCase):

    """Test inheritance crud and its effects."""

    def config_overrides(self):
        super(IdentityInheritanceTestCase, self).config_overrides()
        self.config_fixture.config(group='os_inherit', enabled=True)

    def test_crud_user_inherited_domain_role_grants(self):
        role_list = []
        for _ in range(2):
            role = {'id': uuid.uuid4().hex, 'name': uuid.uuid4().hex}
            self.assignment_api.create_role(role['id'], role)
            role_list.append(role)

        # Create a non-inherited role as a spoiler
        self.assignment_api.create_grant(
            role_list[1]['id'], user_id=self.user['id'],
            domain_id=self.domain_id)

        base_collection_url = (
            '/OS-INHERIT/domains/%(domain_id)s/users/%(user_id)s/roles' % {
                'domain_id': self.domain_id,
                'user_id': self.user['id']})
        member_url = '%(collection_url)s/%(role_id)s/inherited_to_projects' % {
            'collection_url': base_collection_url,
            'role_id': role_list[0]['id']}
        collection_url = base_collection_url + '/inherited_to_projects'

        self.put(member_url)

        # Check we can read it back
        self.head(member_url)
        r = self.get(collection_url)
        self.assertValidRoleListResponse(r, ref=role_list[0],
                                         resource_url=collection_url)

        # Now delete and check its gone
        self.delete(member_url)
        r = self.get(collection_url)
        self.assertValidRoleListResponse(r, expected_length=0,
                                         resource_url=collection_url)

    def test_list_role_assignments_for_inherited_domain_grants(self):
        """Call ``GET /role_assignments with inherited domain grants``.

        Test Plan:

        - Create 4 roles
        - Create a domain with a user and two projects
        - Assign two direct roles to project1
        - Assign a spoiler role to project2
        - Issue the URL to add inherited role to the domain
        - Issue the URL to check it is indeed on the domain
        - Issue the URL to check effective roles on project1 - this
          should return 3 roles.

        """
        role_list = []
        for _ in range(4):
            role = {'id': uuid.uuid4().hex, 'name': uuid.uuid4().hex}
            self.assignment_api.create_role(role['id'], role)
            role_list.append(role)

        domain = self.new_domain_ref()
        self.assignment_api.create_domain(domain['id'], domain)
        user1 = self.new_user_ref(
            domain_id=domain['id'])
        password = user1['password']
        user1 = self.identity_api.create_user(user1)
        user1['password'] = password
        project1 = self.new_project_ref(
            domain_id=domain['id'])
        self.assignment_api.create_project(project1['id'], project1)
        project2 = self.new_project_ref(
            domain_id=domain['id'])
        self.assignment_api.create_project(project2['id'], project2)
        # Add some roles to the project
        self.assignment_api.add_role_to_user_and_project(
            user1['id'], project1['id'], role_list[0]['id'])
        self.assignment_api.add_role_to_user_and_project(
            user1['id'], project1['id'], role_list[1]['id'])
        # ..and one on a different project as a spoiler
        self.assignment_api.add_role_to_user_and_project(
            user1['id'], project2['id'], role_list[2]['id'])

        # Now create our inherited role on the domain
        base_collection_url = (
            '/OS-INHERIT/domains/%(domain_id)s/users/%(user_id)s/roles' % {
                'domain_id': domain['id'],
                'user_id': user1['id']})
        member_url = '%(collection_url)s/%(role_id)s/inherited_to_projects' % {
            'collection_url': base_collection_url,
            'role_id': role_list[3]['id']}
        collection_url = base_collection_url + '/inherited_to_projects'

        self.put(member_url)
        self.head(member_url)
        r = self.get(collection_url)
        self.assertValidRoleListResponse(r, ref=role_list[3],
                                         resource_url=collection_url)

        # Now use the list domain role assignments api to check if this
        # is included
        collection_url = (
            '/role_assignments?user.id=%(user_id)s'
            '&scope.domain.id=%(domain_id)s' % {
                'user_id': user1['id'],
                'domain_id': domain['id']})
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(1, len(r.result.get('role_assignments')))
        ud_url, ud_entity = _build_role_assignment_url_and_entity(
            domain_id=domain['id'], user_id=user1['id'],
            role_id=role_list[3]['id'], inherited_to_projects=True)
        self.assertRoleAssignmentInListResponse(r, ud_entity, link_url=ud_url)

        # Now ask for effective list role assignments - the role should
        # turn into a project role, along with the two direct roles that are
        # on the project
        collection_url = (
            '/role_assignments?effective&user.id=%(user_id)s'
            '&scope.project.id=%(project_id)s' % {
                'user_id': user1['id'],
                'project_id': project1['id']})
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(3, len(r.result.get('role_assignments')))
        # An effective role for an inherited role will be a project
        # entity, with a domain link to the inherited assignment
        unused, up_entity = _build_role_assignment_url_and_entity(
            project_id=project1['id'], user_id=user1['id'],
            role_id=role_list[3]['id'])
        ud_url, unused = _build_role_assignment_url_and_entity(
            domain_id=domain['id'], user_id=user1['id'],
            role_id=role_list[3]['id'], inherited_to_projects=True)
        self.assertRoleAssignmentInListResponse(r, up_entity, link_url=ud_url)

    def test_list_role_assignments_for_disabled_inheritance_extension(self):
        """Call ``GET /role_assignments with inherited domain grants``.

        Test Plan:

        - Issue the URL to add inherited role to the domain
        - Issue the URL to check effective roles on project include the
          inherited role
        - Disable the extension
        - Re-check the effective roles, proving the inherited role no longer
          shows up.

        """

        role_list = []
        for _ in range(4):
            role = {'id': uuid.uuid4().hex, 'name': uuid.uuid4().hex}
            self.assignment_api.create_role(role['id'], role)
            role_list.append(role)

        domain = self.new_domain_ref()
        self.assignment_api.create_domain(domain['id'], domain)
        user1 = self.new_user_ref(
            domain_id=domain['id'])
        password = user1['password']
        user1 = self.identity_api.create_user(user1)
        user1['password'] = password
        project1 = self.new_project_ref(
            domain_id=domain['id'])
        self.assignment_api.create_project(project1['id'], project1)
        project2 = self.new_project_ref(
            domain_id=domain['id'])
        self.assignment_api.create_project(project2['id'], project2)
        # Add some roles to the project
        self.assignment_api.add_role_to_user_and_project(
            user1['id'], project1['id'], role_list[0]['id'])
        self.assignment_api.add_role_to_user_and_project(
            user1['id'], project1['id'], role_list[1]['id'])
        # ..and one on a different project as a spoiler
        self.assignment_api.add_role_to_user_and_project(
            user1['id'], project2['id'], role_list[2]['id'])

        # Now create our inherited role on the domain
        base_collection_url = (
            '/OS-INHERIT/domains/%(domain_id)s/users/%(user_id)s/roles' % {
                'domain_id': domain['id'],
                'user_id': user1['id']})
        member_url = '%(collection_url)s/%(role_id)s/inherited_to_projects' % {
            'collection_url': base_collection_url,
            'role_id': role_list[3]['id']}
        collection_url = base_collection_url + '/inherited_to_projects'

        self.put(member_url)
        self.head(member_url)
        r = self.get(collection_url)
        self.assertValidRoleListResponse(r, ref=role_list[3],
                                         resource_url=collection_url)

        # Get effective list role assignments - the role should
        # turn into a project role, along with the two direct roles that are
        # on the project
        collection_url = (
            '/role_assignments?effective&user.id=%(user_id)s'
            '&scope.project.id=%(project_id)s' % {
                'user_id': user1['id'],
                'project_id': project1['id']})
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(3, len(r.result.get('role_assignments')))

        unused, up_entity = _build_role_assignment_url_and_entity(
            project_id=project1['id'], user_id=user1['id'],
            role_id=role_list[3]['id'])
        ud_url, unused = _build_role_assignment_url_and_entity(
            domain_id=domain['id'], user_id=user1['id'],
            role_id=role_list[3]['id'], inherited_to_projects=True)
        self.assertRoleAssignmentInListResponse(r, up_entity, link_url=ud_url)

        # Disable the extension and re-check the list, the role inherited
        # from the project should no longer show up
        self.config_fixture.config(group='os_inherit', enabled=False)
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(2, len(r.result.get('role_assignments')))

        unused, up_entity = _build_role_assignment_url_and_entity(
            project_id=project1['id'], user_id=user1['id'],
            role_id=role_list[3]['id'])
        ud_url, unused = _build_role_assignment_url_and_entity(
            domain_id=domain['id'], user_id=user1['id'],
            role_id=role_list[3]['id'], inherited_to_projects=True)
        self.assertRoleAssignmentNotInListResponse(r, up_entity,
                                                   link_url=ud_url)

    def test_list_role_assignments_for_inherited_group_domain_grants(self):
        """Call ``GET /role_assignments with inherited group domain grants``.

        Test Plan:

        - Create 4 roles
        - Create a domain with a user and two projects
        - Assign two direct roles to project1
        - Assign a spoiler role to project2
        - Issue the URL to add inherited role to the domain
        - Issue the URL to check it is indeed on the domain
        - Issue the URL to check effective roles on project1 - this
          should return 3 roles.

        """
        role_list = []
        for _ in range(4):
            role = {'id': uuid.uuid4().hex, 'name': uuid.uuid4().hex}
            self.assignment_api.create_role(role['id'], role)
            role_list.append(role)

        domain = self.new_domain_ref()
        self.assignment_api.create_domain(domain['id'], domain)
        user1 = self.new_user_ref(
            domain_id=domain['id'])
        password = user1['password']
        user1 = self.identity_api.create_user(user1)
        user1['password'] = password
        user2 = self.new_user_ref(
            domain_id=domain['id'])
        password = user2['password']
        user2 = self.identity_api.create_user(user2)
        user2['password'] = password
        group1 = self.new_group_ref(
            domain_id=domain['id'])
        group1 = self.identity_api.create_group(group1)
        self.identity_api.add_user_to_group(user1['id'],
                                            group1['id'])
        self.identity_api.add_user_to_group(user2['id'],
                                            group1['id'])
        project1 = self.new_project_ref(
            domain_id=domain['id'])
        self.assignment_api.create_project(project1['id'], project1)
        project2 = self.new_project_ref(
            domain_id=domain['id'])
        self.assignment_api.create_project(project2['id'], project2)
        # Add some roles to the project
        self.assignment_api.add_role_to_user_and_project(
            user1['id'], project1['id'], role_list[0]['id'])
        self.assignment_api.add_role_to_user_and_project(
            user1['id'], project1['id'], role_list[1]['id'])
        # ..and one on a different project as a spoiler
        self.assignment_api.add_role_to_user_and_project(
            user1['id'], project2['id'], role_list[2]['id'])

        # Now create our inherited role on the domain
        base_collection_url = (
            '/OS-INHERIT/domains/%(domain_id)s/groups/%(group_id)s/roles' % {
                'domain_id': domain['id'],
                'group_id': group1['id']})
        member_url = '%(collection_url)s/%(role_id)s/inherited_to_projects' % {
            'collection_url': base_collection_url,
            'role_id': role_list[3]['id']}
        collection_url = base_collection_url + '/inherited_to_projects'

        self.put(member_url)
        self.head(member_url)
        r = self.get(collection_url)
        self.assertValidRoleListResponse(r, ref=role_list[3],
                                         resource_url=collection_url)

        # Now use the list domain role assignments api to check if this
        # is included
        collection_url = (
            '/role_assignments?group.id=%(group_id)s'
            '&scope.domain.id=%(domain_id)s' % {
                'group_id': group1['id'],
                'domain_id': domain['id']})
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(1, len(r.result.get('role_assignments')))
        gd_url, gd_entity = _build_role_assignment_url_and_entity(
            domain_id=domain['id'], group_id=group1['id'],
            role_id=role_list[3]['id'], inherited_to_projects=True)
        self.assertRoleAssignmentInListResponse(r, gd_entity, link_url=gd_url)

        # Now ask for effective list role assignments - the role should
        # turn into a user project role, along with the two direct roles
        # that are on the project
        collection_url = (
            '/role_assignments?effective&user.id=%(user_id)s'
            '&scope.project.id=%(project_id)s' % {
                'user_id': user1['id'],
                'project_id': project1['id']})
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(3, len(r.result.get('role_assignments')))
        # An effective role for an inherited role will be a project
        # entity, with a domain link to the inherited assignment
        unused, up_entity = _build_role_assignment_url_and_entity(
            project_id=project1['id'], user_id=user1['id'],
            role_id=role_list[3]['id'])
        gd_url, unused = _build_role_assignment_url_and_entity(
            domain_id=domain['id'], group_id=group1['id'],
            role_id=role_list[3]['id'], inherited_to_projects=True)
        self.assertRoleAssignmentInListResponse(r, up_entity, link_url=gd_url)

    def test_filtered_role_assignments_for_inherited_grants(self):
        """Call ``GET /role_assignments?scope.OS-INHERIT:inherited_to``.

        Test Plan:

        - Create 5 roles
        - Create a domain with a user, group and two projects
        - Assign three direct spoiler roles to projects
        - Issue the URL to add an inherited user role to the domain
        - Issue the URL to add an inherited group role to the domain
        - Issue the URL to filter by inherited roles - this should
          return just the 2 inherited roles.

        """
        role_list = []
        for _ in range(5):
            role = {'id': uuid.uuid4().hex, 'name': uuid.uuid4().hex}
            self.assignment_api.create_role(role['id'], role)
            role_list.append(role)

        domain = self.new_domain_ref()
        self.assignment_api.create_domain(domain['id'], domain)
        user1 = self.new_user_ref(
            domain_id=domain['id'])
        password = user1['password']
        user1 = self.identity_api.create_user(user1)
        user1['password'] = password
        group1 = self.new_group_ref(
            domain_id=domain['id'])
        group1 = self.identity_api.create_group(group1)
        project1 = self.new_project_ref(
            domain_id=domain['id'])
        self.assignment_api.create_project(project1['id'], project1)
        project2 = self.new_project_ref(
            domain_id=domain['id'])
        self.assignment_api.create_project(project2['id'], project2)
        # Add some spoiler roles to the projects
        self.assignment_api.add_role_to_user_and_project(
            user1['id'], project1['id'], role_list[0]['id'])
        self.assignment_api.add_role_to_user_and_project(
            user1['id'], project2['id'], role_list[1]['id'])
        # Create a non-inherited role as a spoiler
        self.assignment_api.create_grant(
            role_list[2]['id'], user_id=user1['id'], domain_id=domain['id'])

        # Now create two inherited roles on the domain, one for a user
        # and one for a domain
        base_collection_url = (
            '/OS-INHERIT/domains/%(domain_id)s/users/%(user_id)s/roles' % {
                'domain_id': domain['id'],
                'user_id': user1['id']})
        member_url = '%(collection_url)s/%(role_id)s/inherited_to_projects' % {
            'collection_url': base_collection_url,
            'role_id': role_list[3]['id']}
        collection_url = base_collection_url + '/inherited_to_projects'

        self.put(member_url)
        self.head(member_url)
        r = self.get(collection_url)
        self.assertValidRoleListResponse(r, ref=role_list[3],
                                         resource_url=collection_url)

        base_collection_url = (
            '/OS-INHERIT/domains/%(domain_id)s/groups/%(group_id)s/roles' % {
                'domain_id': domain['id'],
                'group_id': group1['id']})
        member_url = '%(collection_url)s/%(role_id)s/inherited_to_projects' % {
            'collection_url': base_collection_url,
            'role_id': role_list[4]['id']}
        collection_url = base_collection_url + '/inherited_to_projects'

        self.put(member_url)
        self.head(member_url)
        r = self.get(collection_url)
        self.assertValidRoleListResponse(r, ref=role_list[4],
                                         resource_url=collection_url)

        # Now use the list role assignments api to get a list of inherited
        # roles on the domain - should get back the two roles
        collection_url = (
            '/role_assignments?scope.OS-INHERIT:inherited_to=projects')
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)
        self.assertEqual(2, len(r.result.get('role_assignments')))
        ud_url, ud_entity = _build_role_assignment_url_and_entity(
            domain_id=domain['id'], user_id=user1['id'],
            role_id=role_list[3]['id'], inherited_to_projects=True)
        gd_url, gd_entity = _build_role_assignment_url_and_entity(
            domain_id=domain['id'], group_id=group1['id'],
            role_id=role_list[4]['id'], inherited_to_projects=True)
        self.assertRoleAssignmentInListResponse(r, ud_entity, link_url=ud_url)
        self.assertRoleAssignmentInListResponse(r, gd_entity, link_url=gd_url)

    def _setup_hierarchical_projects_scenario(self):
        """Creates basic hierarchical projects scenario

        Creates a root and a leaf project and non-inherited and inherited
        roles as well.

        """
        # Create project hierarchy
        root = self.new_project_ref(domain_id=self.domain['id'])
        leaf = self.new_project_ref(domain_id=self.domain['id'],
                                    parent_id=root['id'])

        self.assignment_api.create_project(root['id'], root)
        self.assignment_api.create_project(leaf['id'], leaf)

        # Create 'non-inherited' and 'inherited' roles
        non_inherited_role = {'id': uuid.uuid4().hex, 'name': 'non-inherited'}
        self.assignment_api.create_role(non_inherited_role['id'],
                                        non_inherited_role)
        inherited_role = {'id': uuid.uuid4().hex, 'name': 'inherited'}
        self.assignment_api.create_role(inherited_role['id'], inherited_role)

        return (root['id'], leaf['id'],
                non_inherited_role['id'], inherited_role['id'])

    def test_get_token_from_inherited_user_project_role_grants(self):
        # Create default scenario
        root_id, leaf_id, non_inherited_role_id, inherited_role_id = (
            self._setup_hierarchical_projects_scenario())

        # Define root and leaf projects authentication data
        root_project_auth_data = self.build_authentication_request(
            user_id=self.user['id'],
            password=self.user['password'],
            project_id=root_id)
        leaf_project_auth_data = self.build_authentication_request(
            user_id=self.user['id'],
            password=self.user['password'],
            project_id=leaf_id)

        # Check the user cannot get a token on root nor leaf project
        self.v3_authenticate_token(root_project_auth_data, expected_status=401)
        self.v3_authenticate_token(leaf_project_auth_data, expected_status=401)

        # Grant non-inherited role for user on root project
        non_inher_up_url, non_inher_up_entity = (
            _build_role_assignment_url_and_entity(
                project_id=root_id, user_id=self.user['id'],
                role_id=non_inherited_role_id))
        self.put(non_inher_up_url)

        # Check the user can only get a token on root project
        self.v3_authenticate_token(root_project_auth_data)
        self.v3_authenticate_token(leaf_project_auth_data, expected_status=401)

        # Grant inherited role for user on root project
        inher_up_url, inher_up_entity = _build_role_assignment_url_and_entity(
            project_id=root_id, user_id=self.user['id'],
            role_id=inherited_role_id, inherited_to_projects=True)
        self.put(inher_up_url)

        # Check the user can get a token on both projects
        self.v3_authenticate_token(root_project_auth_data)
        self.v3_authenticate_token(leaf_project_auth_data)

        # Delete inherited grant
        self.delete(inher_up_url)

        # Check the user can only get a token on root project
        self.v3_authenticate_token(root_project_auth_data)
        self.v3_authenticate_token(leaf_project_auth_data, expected_status=401)

        # Delete non-inherited grant
        self.delete(non_inher_up_url)

        # Check the user cannot get a token on root project anymore
        self.v3_authenticate_token(root_project_auth_data, expected_status=401)

    def test_get_token_from_inherited_group_project_role_grants(self):
        # Create default scenario
        root_id, leaf_id, non_inherited_role_id, inherited_role_id = (
            self._setup_hierarchical_projects_scenario())

        # Create group and add user to it
        group = self.new_group_ref(domain_id=self.domain['id'])
        group = self.identity_api.create_group(group)
        self.identity_api.add_user_to_group(self.user['id'], group['id'])

        # Define root and leaf projects authentication data
        root_project_auth_data = self.build_authentication_request(
            user_id=self.user['id'],
            password=self.user['password'],
            project_id=root_id)
        leaf_project_auth_data = self.build_authentication_request(
            user_id=self.user['id'],
            password=self.user['password'],
            project_id=leaf_id)

        # Check the user cannot get a token on root nor leaf project
        self.v3_authenticate_token(root_project_auth_data, expected_status=401)
        self.v3_authenticate_token(leaf_project_auth_data, expected_status=401)

        # Grant non-inherited role for user on root project
        non_inher_gp_url, non_inher_gp_entity = (
            _build_role_assignment_url_and_entity(
                project_id=root_id, group_id=group['id'],
                role_id=non_inherited_role_id))
        self.put(non_inher_gp_url)

        # Check the user can only get a token on root project
        self.v3_authenticate_token(root_project_auth_data)
        self.v3_authenticate_token(leaf_project_auth_data, expected_status=401)

        # Grant inherited role for user on root project
        inher_gp_url, inher_gp_entity = _build_role_assignment_url_and_entity(
            project_id=root_id, group_id=group['id'],
            role_id=inherited_role_id, inherited_to_projects=True)
        self.put(inher_gp_url)

        # Check the user can get a token on both projects
        self.v3_authenticate_token(root_project_auth_data)
        self.v3_authenticate_token(leaf_project_auth_data)

        # Delete inherited grant
        self.delete(inher_gp_url)

        # Check the user can only get a token on root project
        self.v3_authenticate_token(root_project_auth_data)
        self.v3_authenticate_token(leaf_project_auth_data, expected_status=401)

        # Delete non-inherited grant
        self.delete(non_inher_gp_url)

        # Check the user cannot get a token on root project anymore
        self.v3_authenticate_token(root_project_auth_data, expected_status=401)

    def test_get_role_assignments_for_project_hierarchy(self):
        # Create default scenario
        root_id, leaf_id, non_inherited_role_id, inherited_role_id = (
            self._setup_hierarchical_projects_scenario())

        # Grant non-inherited role
        non_inher_up_url, non_inher_up_entity = (
            _build_role_assignment_url_and_entity(
                project_id=root_id, user_id=self.user['id'],
                role_id=non_inherited_role_id))
        self.put(non_inher_up_url)

        # Grant inherited role
        inher_up_url, inher_up_entity = _build_role_assignment_url_and_entity(
            project_id=root_id, user_id=self.user['id'],
            role_id=inherited_role_id, inherited_to_projects=True)
        self.put(inher_up_url)

        # Get effective role assignments
        collection_url = '/role_assignments'
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)

        # Assert that the user has non-inherited role on root project
        self.assertRoleAssignmentInListResponse(r, non_inher_up_entity,
                                                non_inher_up_url)

        # Assert that the user has inherited role on root project
        self.assertRoleAssignmentInListResponse(r, inher_up_entity,
                                                inher_up_url)

        # Assert that the user does not have non-inherited role on leaf project
        non_inher_up_url = ('/projects/%s/users/%s/roles/%s' %
                            (leaf_id, self.user['id'], non_inherited_role_id))
        non_inher_up_entity['scope']['project']['id'] = leaf_id
        self.assertRoleAssignmentNotInListResponse(r, non_inher_up_entity,
                                                   non_inher_up_url)

        # Assert that the user does not have inherited role on leaf project
        inher_up_entity['scope']['project']['id'] = leaf_id
        self.assertRoleAssignmentNotInListResponse(r, inher_up_entity,
                                                   inher_up_url)

    def test_get_effective_role_assignments_for_project_hierarchy(self):
        # Create default scenario
        root_id, leaf_id, non_inherited_role_id, inherited_role_id = (
            self._setup_hierarchical_projects_scenario())

        # Grant non-inherited role
        non_inher_up_url, non_inher_up_entity = (
            _build_role_assignment_url_and_entity(
                project_id=root_id, user_id=self.user['id'],
                role_id=non_inherited_role_id))
        self.put(non_inher_up_url)

        # Grant inherited role
        inher_up_url, inher_up_entity = _build_role_assignment_url_and_entity(
            project_id=root_id, user_id=self.user['id'],
            role_id=inherited_role_id, inherited_to_projects=True)
        self.put(inher_up_url)

        # Get effective role assignments
        collection_url = '/role_assignments?effective'
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)

        # Assert that the user has non-inherited role on root project
        self.assertRoleAssignmentInListResponse(r, non_inher_up_entity,
                                                non_inher_up_url)

        # Assert that the user has inherited role on root project
        self.assertRoleAssignmentInListResponse(r, inher_up_entity,
                                                inher_up_url)

        # Assert that the user does not have non-inherited role on leaf project
        non_inher_up_url = ('/projects/%s/users/%s/roles/%s' %
                            (leaf_id, self.user['id'], non_inherited_role_id))
        non_inher_up_entity['scope']['project']['id'] = leaf_id
        self.assertRoleAssignmentNotInListResponse(r, non_inher_up_entity,
                                                   non_inher_up_url)

        # Assert that the user has inherited role on leaf project
        inher_up_entity['scope']['project']['id'] = leaf_id
        self.assertRoleAssignmentInListResponse(r, inher_up_entity,
                                                inher_up_url)

    def test_get_inherited_role_assignments_for_project_hierarchy(self):
        # Create default scenario
        root_id, leaf_id, non_inherited_role_id, inherited_role_id = (
            self._setup_hierarchical_projects_scenario())

        # Grant non-inherited role
        non_inher_up_url, non_inher_up_entity = (
            _build_role_assignment_url_and_entity(
                project_id=root_id, user_id=self.user['id'],
                role_id=non_inherited_role_id))
        self.put(non_inher_up_url)

        # Grant inherited role
        inher_up_url, inher_up_entity = _build_role_assignment_url_and_entity(
            project_id=root_id, user_id=self.user['id'],
            role_id=inherited_role_id, inherited_to_projects=True)
        self.put(inher_up_url)

        # Get effective role assignments
        collection_url = ('/role_assignments'
                          '?scope.OS-INHERIT:inherited_to=projects')
        r = self.get(collection_url)
        self.assertValidRoleAssignmentListResponse(r,
                                                   resource_url=collection_url)

        # Assert that the user does not have non-inherited role on root project
        self.assertRoleAssignmentNotInListResponse(r, non_inher_up_entity,
                                                   non_inher_up_url)

        # Assert that the user has inherited role on root project
        self.assertRoleAssignmentInListResponse(r, inher_up_entity,
                                                inher_up_url)

        # Assert that the user does not have non-inherited role on leaf project
        non_inher_up_url = ('/projects/%s/users/%s/roles/%s' %
                            (leaf_id, self.user['id'], non_inherited_role_id))
        non_inher_up_entity['scope']['project']['id'] = leaf_id
        self.assertRoleAssignmentNotInListResponse(r, non_inher_up_entity,
                                                   non_inher_up_url)

        # Assert that the user does not have inherited role on leaf project
        inher_up_entity['scope']['project']['id'] = leaf_id
        self.assertRoleAssignmentNotInListResponse(r, inher_up_entity,
                                                   inher_up_url)


class IdentityInheritanceDisabledTestCase(test_v3.RestfulTestCase):

    """Test inheritance crud and its effects."""

    def config_overrides(self):
        super(IdentityInheritanceDisabledTestCase, self).config_overrides()
        self.config_fixture.config(group='os_inherit', enabled=False)

    def test_crud_inherited_role_grants_failed_if_disabled(self):
        role = {'id': uuid.uuid4().hex, 'name': uuid.uuid4().hex}
        self.assignment_api.create_role(role['id'], role)

        base_collection_url = (
            '/OS-INHERIT/domains/%(domain_id)s/users/%(user_id)s/roles' % {
                'domain_id': self.domain_id,
                'user_id': self.user['id']})
        member_url = '%(collection_url)s/%(role_id)s/inherited_to_projects' % {
            'collection_url': base_collection_url,
            'role_id': role['id']}
        collection_url = base_collection_url + '/inherited_to_projects'

        self.put(member_url, expected_status=404)
        self.head(member_url, expected_status=404)
        self.get(collection_url, expected_status=404)
        self.delete(member_url, expected_status=404)


class TestV3toV2Methods(tests.TestCase):

    """Test V3 to V2 conversion methods."""

    def setUp(self):
        super(TestV3toV2Methods, self).setUp()
        self.load_backends()
        self.user_id = uuid.uuid4().hex
        self.default_project_id = uuid.uuid4().hex
        self.tenant_id = uuid.uuid4().hex
        self.domain_id = uuid.uuid4().hex
        # User with only default_project_id in ref
        self.user1 = {'id': self.user_id,
                      'name': self.user_id,
                      'default_project_id': self.default_project_id,
                      'domain_id': self.domain_id}
        # User without default_project_id or tenantId in ref
        self.user2 = {'id': self.user_id,
                      'name': self.user_id,
                      'domain_id': self.domain_id}
        # User with both tenantId and default_project_id in ref
        self.user3 = {'id': self.user_id,
                      'name': self.user_id,
                      'default_project_id': self.default_project_id,
                      'tenantId': self.tenant_id,
                      'domain_id': self.domain_id}
        # User with only tenantId in ref
        self.user4 = {'id': self.user_id,
                      'name': self.user_id,
                      'tenantId': self.tenant_id,
                      'domain_id': self.domain_id}

        # Expected result if the user is meant to have a tenantId element
        self.expected_user = {'id': self.user_id,
                              'name': self.user_id,
                              'username': self.user_id,
                              'tenantId': self.default_project_id}

        # Expected result if the user is not meant to have a tenantId element
        self.expected_user_no_tenant_id = {'id': self.user_id,
                                           'name': self.user_id,
                                           'username': self.user_id}

    def test_v3_to_v2_user_method(self):

        updated_user1 = controller.V2Controller.v3_to_v2_user(self.user1)
        self.assertIs(self.user1, updated_user1)
        self.assertDictEqual(self.user1, self.expected_user)
        updated_user2 = controller.V2Controller.v3_to_v2_user(self.user2)
        self.assertIs(self.user2, updated_user2)
        self.assertDictEqual(self.user2, self.expected_user_no_tenant_id)
        updated_user3 = controller.V2Controller.v3_to_v2_user(self.user3)
        self.assertIs(self.user3, updated_user3)
        self.assertDictEqual(self.user3, self.expected_user)
        updated_user4 = controller.V2Controller.v3_to_v2_user(self.user4)
        self.assertIs(self.user4, updated_user4)
        self.assertDictEqual(self.user4, self.expected_user_no_tenant_id)

    def test_v3_to_v2_user_method_list(self):
        user_list = [self.user1, self.user2, self.user3, self.user4]
        updated_list = controller.V2Controller.v3_to_v2_user(user_list)

        self.assertEqual(len(updated_list), len(user_list))

        for i, ref in enumerate(updated_list):
            # Order should not change.
            self.assertIs(ref, user_list[i])

        self.assertDictEqual(self.user1, self.expected_user)
        self.assertDictEqual(self.user2, self.expected_user_no_tenant_id)
        self.assertDictEqual(self.user3, self.expected_user)
        self.assertDictEqual(self.user4, self.expected_user_no_tenant_id)

    def test_v2controller_filter_domain_id(self):
        # V2.0 is not domain aware, ensure domain_id is popped off the ref.
        other_data = uuid.uuid4().hex
        domain_id = uuid.uuid4().hex
        ref = {'domain_id': domain_id,
               'other_data': other_data}

        ref_no_domain = {'other_data': other_data}
        expected_ref = ref_no_domain.copy()

        updated_ref = controller.V2Controller.filter_domain_id(ref)
        self.assertIs(ref, updated_ref)
        self.assertDictEqual(ref, expected_ref)
        # Make sure we don't error/muck up data if domain_id isn't present
        updated_ref = controller.V2Controller.filter_domain_id(ref_no_domain)
        self.assertIs(ref_no_domain, updated_ref)
        self.assertDictEqual(ref_no_domain, expected_ref)

    def test_v3controller_filter_domain_id(self):
        # No data should be filtered out in this case.
        other_data = uuid.uuid4().hex
        domain_id = uuid.uuid4().hex
        ref = {'domain_id': domain_id,
               'other_data': other_data}

        expected_ref = ref.copy()
        updated_ref = controller.V3Controller.filter_domain_id(ref)
        self.assertIs(ref, updated_ref)
        self.assertDictEqual(ref, expected_ref)


class UserSelfServiceChangingPasswordsTestCase(test_v3.RestfulTestCase):

    def setUp(self):
        super(UserSelfServiceChangingPasswordsTestCase, self).setUp()
        self.user_ref = self.new_user_ref(domain_id=self.domain['id'])
        password = self.user_ref['password']
        self.user_ref = self.identity_api.create_user(self.user_ref)
        self.user_ref['password'] = password
        self.token = self.get_request_token(self.user_ref['password'], 201)

    def get_request_token(self, password, expected_status):
        auth_data = self.build_authentication_request(
            user_id=self.user_ref['id'],
            password=password)
        r = self.v3_authenticate_token(auth_data,
                                       expected_status=expected_status)
        return r.headers.get('X-Subject-Token')

    def change_password(self, expected_status, **kwargs):
        """Returns a test response for a change password request."""
        return self.post('/users/%s/password' % self.user_ref['id'],
                         body={'user': kwargs},
                         token=self.token,
                         expected_status=expected_status)

    def test_changing_password(self):
        # original password works
        self.get_request_token(self.user_ref['password'],
                               expected_status=201)

        # change password
        new_password = uuid.uuid4().hex
        self.change_password(password=new_password,
                             original_password=self.user_ref['password'],
                             expected_status=204)

        # old password fails
        self.get_request_token(self.user_ref['password'], expected_status=401)

        # new password works
        self.get_request_token(new_password, expected_status=201)

    def test_changing_password_with_missing_original_password_fails(self):
        r = self.change_password(password=uuid.uuid4().hex,
                                 expected_status=400)
        self.assertThat(r.result['error']['message'],
                        matchers.Contains('original_password'))

    def test_changing_password_with_missing_password_fails(self):
        r = self.change_password(original_password=self.user_ref['password'],
                                 expected_status=400)
        self.assertThat(r.result['error']['message'],
                        matchers.Contains('password'))

    def test_changing_password_with_incorrect_password_fails(self):
        self.change_password(password=uuid.uuid4().hex,
                             original_password=uuid.uuid4().hex,
                             expected_status=401)

    def test_changing_password_with_disabled_user_fails(self):
        # disable the user account
        self.user_ref['enabled'] = False
        self.patch('/users/%s' % self.user_ref['id'],
                   body={'user': self.user_ref})

        self.change_password(password=uuid.uuid4().hex,
                             original_password=self.user_ref['password'],
                             expected_status=401)
