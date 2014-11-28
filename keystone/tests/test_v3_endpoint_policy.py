# Copyright 2014 IBM Corp.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from testtools import matchers

from keystone.common import dependency
from keystone.tests import test_v3


@dependency.requires('endpoint_policy_api')
class TestExtensionCase(test_v3.RestfulTestCase):

    EXTENSION_NAME = 'endpoint_policy'
    EXTENSION_TO_ADD = 'endpoint_policy_extension'


class EndpointPolicyTestCase(TestExtensionCase):
    """Test endpoint policy CRUD.

    In general, the controller layer of the endpoint policy extension is really
    just marshalling the data around the underlying manager calls. Given that
    the manager layer is tested in depth by the backend tests, the tests we
    execute here concentrate on ensuring we are correctly passing and
    presenting the data.

    """

    def setUp(self):
        super(EndpointPolicyTestCase, self).setUp()
        self.policy = self.new_policy_ref()
        self.policy_api.create_policy(self.policy['id'], self.policy)
        self.service = self.new_service_ref()
        self.catalog_api.create_service(self.service['id'], self.service)
        self.endpoint = self.new_endpoint_ref(self.service['id'], enabled=True)
        self.catalog_api.create_endpoint(self.endpoint['id'], self.endpoint)
        self.region = self.new_region_ref()
        self.catalog_api.create_region(self.region)

    # endpoint policy crud tests

    def test_crud_for_policy_for_explicit_endpoint(self):
        """PUT, HEAD and DELETE for explicit endpoint policy."""

        url = ('/policies/%(policy_id)s/OS-ENDPOINT-POLICY'
               '/endpoints/%(endpoint_id)s') % {
                   'policy_id': self.policy['id'],
                   'endpoint_id': self.endpoint['id']}

        self.put(url, expected_status=204)
        self.get(url, expected_status=204)
        self.head(url, expected_status=204)
        self.delete(url, expected_status=204)

    def test_crud_for_policy_for_service(self):
        """PUT, HEAD and DELETE for service endpoint policy."""

        url = ('/policies/%(policy_id)s/OS-ENDPOINT-POLICY'
               '/services/%(service_id)s') % {
                   'policy_id': self.policy['id'],
                   'service_id': self.service['id']}

        self.put(url, expected_status=204)
        self.get(url, expected_status=204)
        self.head(url, expected_status=204)
        self.delete(url, expected_status=204)

    def test_crud_for_policy_for_region_and_service(self):
        """PUT, HEAD and DELETE for region and service endpoint policy."""

        url = ('/policies/%(policy_id)s/OS-ENDPOINT-POLICY'
               '/services/%(service_id)s/regions/%(region_id)s') % {
                   'policy_id': self.policy['id'],
                   'service_id': self.service['id'],
                   'region_id': self.region['id']}

        self.put(url, expected_status=204)
        self.get(url, expected_status=204)
        self.head(url, expected_status=204)
        self.delete(url, expected_status=204)

    def test_get_policy_for_endpoint(self):
        """GET /endpoints/{endpoint_id}/policy."""

        self.put('/policies/%(policy_id)s/OS-ENDPOINT-POLICY'
                 '/endpoints/%(endpoint_id)s' % {
                     'policy_id': self.policy['id'],
                     'endpoint_id': self.endpoint['id']},
                 expected_status=204)

        self.head('/endpoints/%(endpoint_id)s/OS-ENDPOINT-POLICY'
                  '/policy' % {
                      'endpoint_id': self.endpoint['id']},
                  expected_status=200)

        r = self.get('/endpoints/%(endpoint_id)s/OS-ENDPOINT-POLICY'
                     '/policy' % {
                         'endpoint_id': self.endpoint['id']},
                     expected_status=200)
        self.assertValidPolicyResponse(r, ref=self.policy)

    def test_list_endpoints_for_policy(self):
        """GET /policies/%(policy_id}/endpoints."""

        self.put('/policies/%(policy_id)s/OS-ENDPOINT-POLICY'
                 '/endpoints/%(endpoint_id)s' % {
                     'policy_id': self.policy['id'],
                     'endpoint_id': self.endpoint['id']},
                 expected_status=204)

        r = self.get('/policies/%(policy_id)s/OS-ENDPOINT-POLICY'
                     '/endpoints' % {
                         'policy_id': self.policy['id']},
                     expected_status=200)
        self.assertValidEndpointListResponse(r, ref=self.endpoint)
        self.assertThat(r.result.get('endpoints'), matchers.HasLength(1))

    def test_endpoint_association_cleanup_when_endpoint_deleted(self):
        url = ('/policies/%(policy_id)s/OS-ENDPOINT-POLICY'
               '/endpoints/%(endpoint_id)s') % {
                   'policy_id': self.policy['id'],
                   'endpoint_id': self.endpoint['id']}

        self.put(url, expected_status=204)
        self.head(url, expected_status=204)

        self.delete('/endpoints/%(endpoint_id)s' % {
            'endpoint_id': self.endpoint['id']})

        self.head(url, expected_status=404)

    def test_region_service_association_cleanup_when_region_deleted(self):
        url = ('/policies/%(policy_id)s/OS-ENDPOINT-POLICY'
               '/services/%(service_id)s/regions/%(region_id)s') % {
                   'policy_id': self.policy['id'],
                   'service_id': self.service['id'],
                   'region_id': self.region['id']}

        self.put(url, expected_status=204)
        self.head(url, expected_status=204)

        self.delete('/regions/%(region_id)s' % {
            'region_id': self.region['id']})

        self.head(url, expected_status=404)

    def test_region_service_association_cleanup_when_service_deleted(self):
        url = ('/policies/%(policy_id)s/OS-ENDPOINT-POLICY'
               '/services/%(service_id)s/regions/%(region_id)s') % {
                   'policy_id': self.policy['id'],
                   'service_id': self.service['id'],
                   'region_id': self.region['id']}

        self.put(url, expected_status=204)
        self.head(url, expected_status=204)

        self.delete('/services/%(service_id)s' % {
            'service_id': self.service['id']})

        self.head(url, expected_status=404)

    def test_service_association_cleanup_when_service_deleted(self):
        url = ('/policies/%(policy_id)s/OS-ENDPOINT-POLICY'
               '/services/%(service_id)s') % {
                   'policy_id': self.policy['id'],
                   'service_id': self.service['id']}

        self.put(url, expected_status=204)
        self.get(url, expected_status=204)

        self.delete('/services/%(service_id)s' % {
            'service_id': self.service['id']})

        self.head(url, expected_status=404)


class JsonHomeTests(TestExtensionCase, test_v3.JsonHomeTestMixin):
    EXTENSION_LOCATION = ('http://docs.openstack.org/api/openstack-identity/3/'
                          'ext/OS-ENDPOINT-POLICY/1.0/rel')
    PARAM_LOCATION = 'http://docs.openstack.org/api/openstack-identity/3/param'

    JSON_HOME_DATA = {
        EXTENSION_LOCATION + '/endpoint_policy': {
            'href-template': '/endpoints/{endpoint_id}/OS-ENDPOINT-POLICY/'
                             'policy',
            'href-vars': {
                'endpoint_id': PARAM_LOCATION + '/endpoint_id',
            },
        },
        EXTENSION_LOCATION + '/policy_endpoints': {
            'href-template': '/policies/{policy_id}/OS-ENDPOINT-POLICY/'
                             'endpoints',
            'href-vars': {
                'policy_id': PARAM_LOCATION + '/policy_id',
            },
        },
        EXTENSION_LOCATION + '/endpoint_policy_association': {
            'href-template': '/policies/{policy_id}/OS-ENDPOINT-POLICY/'
                             'endpoints/{endpoint_id}',
            'href-vars': {
                'policy_id': PARAM_LOCATION + '/policy_id',
                'endpoint_id': PARAM_LOCATION + '/endpoint_id',
            },
        },
        EXTENSION_LOCATION + '/service_policy_association': {
            'href-template': '/policies/{policy_id}/OS-ENDPOINT-POLICY/'
                             'services/{service_id}',
            'href-vars': {
                'policy_id': PARAM_LOCATION + '/policy_id',
                'service_id': PARAM_LOCATION + '/service_id',
            },
        },
        EXTENSION_LOCATION + '/region_and_service_policy_association': {
            'href-template': '/policies/{policy_id}/OS-ENDPOINT-POLICY/'
                             'services/{service_id}/regions/{region_id}',
            'href-vars': {
                'policy_id': PARAM_LOCATION + '/policy_id',
                'service_id': PARAM_LOCATION + '/service_id',
                'region_id': PARAM_LOCATION + '/region_id',
            },
        },
    }
