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

import ldap.dn
from testtools import matchers

from keystone.common import ldap as ks_ldap
from keystone.common.ldap import core as common_ldap_core
from keystone import tests
from keystone.tests import default_fixtures
from keystone.tests import fakeldap


class DnCompareTest(tests.BaseTestCase):
    """Tests for the DN comparison functions in keystone.common.ldap.core."""

    def test_prep(self):
        # prep_case_insensitive returns the string with spaces at the front and
        # end if it's already lowercase and no insignificant characters.
        value = 'lowercase value'
        self.assertEqual(value, ks_ldap.prep_case_insensitive(value))

    def test_prep_lowercase(self):
        # prep_case_insensitive returns the string with spaces at the front and
        # end and lowercases the value.
        value = 'UPPERCASE VALUE'
        exp_value = value.lower()
        self.assertEqual(exp_value, ks_ldap.prep_case_insensitive(value))

    def test_prep_insignificant(self):
        # prep_case_insensitive remove insignificant spaces.
        value = 'before   after'
        exp_value = 'before after'
        self.assertEqual(exp_value, ks_ldap.prep_case_insensitive(value))

    def test_prep_insignificant_pre_post(self):
        # prep_case_insensitive remove insignificant spaces.
        value = '   value   '
        exp_value = 'value'
        self.assertEqual(exp_value, ks_ldap.prep_case_insensitive(value))

    def test_ava_equal_same(self):
        # is_ava_value_equal returns True if the two values are the same.
        value = 'val1'
        self.assertTrue(ks_ldap.is_ava_value_equal('cn', value, value))

    def test_ava_equal_complex(self):
        # is_ava_value_equal returns True if the two values are the same using
        # a value that's got different capitalization and insignificant chars.
        val1 = 'before   after'
        val2 = '  BEFORE  afTer '
        self.assertTrue(ks_ldap.is_ava_value_equal('cn', val1, val2))

    def test_ava_different(self):
        # is_ava_value_equal returns False if the values aren't the same.
        self.assertFalse(ks_ldap.is_ava_value_equal('cn', 'val1', 'val2'))

    def test_rdn_same(self):
        # is_rdn_equal returns True if the two values are the same.
        rdn = ldap.dn.str2dn('cn=val1')[0]
        self.assertTrue(ks_ldap.is_rdn_equal(rdn, rdn))

    def test_rdn_diff_length(self):
        # is_rdn_equal returns False if the RDNs have a different number of
        # AVAs.
        rdn1 = ldap.dn.str2dn('cn=cn1')[0]
        rdn2 = ldap.dn.str2dn('cn=cn1+ou=ou1')[0]
        self.assertFalse(ks_ldap.is_rdn_equal(rdn1, rdn2))

    def test_rdn_multi_ava_same_order(self):
        # is_rdn_equal returns True if the RDNs have the same number of AVAs
        # and the values are the same.
        rdn1 = ldap.dn.str2dn('cn=cn1+ou=ou1')[0]
        rdn2 = ldap.dn.str2dn('cn=CN1+ou=OU1')[0]
        self.assertTrue(ks_ldap.is_rdn_equal(rdn1, rdn2))

    def test_rdn_multi_ava_diff_order(self):
        # is_rdn_equal returns True if the RDNs have the same number of AVAs
        # and the values are the same, even if in a different order
        rdn1 = ldap.dn.str2dn('cn=cn1+ou=ou1')[0]
        rdn2 = ldap.dn.str2dn('ou=OU1+cn=CN1')[0]
        self.assertTrue(ks_ldap.is_rdn_equal(rdn1, rdn2))

    def test_rdn_multi_ava_diff_type(self):
        # is_rdn_equal returns False if the RDNs have the same number of AVAs
        # and the attribute types are different.
        rdn1 = ldap.dn.str2dn('cn=cn1+ou=ou1')[0]
        rdn2 = ldap.dn.str2dn('cn=cn1+sn=sn1')[0]
        self.assertFalse(ks_ldap.is_rdn_equal(rdn1, rdn2))

    def test_rdn_attr_type_case_diff(self):
        # is_rdn_equal returns True for same RDNs even when attr type case is
        # different.
        rdn1 = ldap.dn.str2dn('cn=cn1')[0]
        rdn2 = ldap.dn.str2dn('CN=cn1')[0]
        self.assertTrue(ks_ldap.is_rdn_equal(rdn1, rdn2))

    def test_rdn_attr_type_alias(self):
        # is_rdn_equal returns False for same RDNs even when attr type alias is
        # used. Note that this is a limitation since an LDAP server should
        # consider them equal.
        rdn1 = ldap.dn.str2dn('cn=cn1')[0]
        rdn2 = ldap.dn.str2dn('2.5.4.3=cn1')[0]
        self.assertFalse(ks_ldap.is_rdn_equal(rdn1, rdn2))

    def test_dn_same(self):
        # is_dn_equal returns True if the DNs are the same.
        dn = 'cn=Babs Jansen,ou=OpenStack'
        self.assertTrue(ks_ldap.is_dn_equal(dn, dn))

    def test_dn_diff_length(self):
        # is_dn_equal returns False if the DNs don't have the same number of
        # RDNs
        dn1 = 'cn=Babs Jansen,ou=OpenStack'
        dn2 = 'cn=Babs Jansen,ou=OpenStack,dc=example.com'
        self.assertFalse(ks_ldap.is_dn_equal(dn1, dn2))

    def test_dn_equal_rdns(self):
        # is_dn_equal returns True if the DNs have the same number of RDNs
        # and each RDN is the same.
        dn1 = 'cn=Babs Jansen,ou=OpenStack+cn=OpenSource'
        dn2 = 'CN=Babs Jansen,cn=OpenSource+ou=OpenStack'
        self.assertTrue(ks_ldap.is_dn_equal(dn1, dn2))

    def test_dn_parsed_dns(self):
        # is_dn_equal can also accept parsed DNs.
        dn_str1 = ldap.dn.str2dn('cn=Babs Jansen,ou=OpenStack+cn=OpenSource')
        dn_str2 = ldap.dn.str2dn('CN=Babs Jansen,cn=OpenSource+ou=OpenStack')
        self.assertTrue(ks_ldap.is_dn_equal(dn_str1, dn_str2))

    def test_startswith_under_child(self):
        # dn_startswith returns True if descendant_dn is a child of dn.
        child = 'cn=Babs Jansen,ou=OpenStack'
        parent = 'ou=OpenStack'
        self.assertTrue(ks_ldap.dn_startswith(child, parent))

    def test_startswith_parent(self):
        # dn_startswith returns False if descendant_dn is a parent of dn.
        child = 'cn=Babs Jansen,ou=OpenStack'
        parent = 'ou=OpenStack'
        self.assertFalse(ks_ldap.dn_startswith(parent, child))

    def test_startswith_same(self):
        # dn_startswith returns False if DNs are the same.
        dn = 'cn=Babs Jansen,ou=OpenStack'
        self.assertFalse(ks_ldap.dn_startswith(dn, dn))

    def test_startswith_not_parent(self):
        # dn_startswith returns False if descendant_dn is not under the dn
        child = 'cn=Babs Jansen,ou=OpenStack'
        parent = 'dc=example.com'
        self.assertFalse(ks_ldap.dn_startswith(child, parent))

    def test_startswith_descendant(self):
        # dn_startswith returns True if descendant_dn is a descendant of dn.
        descendant = 'cn=Babs Jansen,ou=Keystone,ou=OpenStack,dc=example.com'
        dn = 'ou=OpenStack,dc=example.com'
        self.assertTrue(ks_ldap.dn_startswith(descendant, dn))

        descendant = 'uid=12345,ou=Users,dc=example,dc=com'
        dn = 'ou=Users,dc=example,dc=com'
        self.assertTrue(ks_ldap.dn_startswith(descendant, dn))

    def test_startswith_parsed_dns(self):
        # dn_startswith also accepts parsed DNs.
        descendant = ldap.dn.str2dn('cn=Babs Jansen,ou=OpenStack')
        dn = ldap.dn.str2dn('ou=OpenStack')
        self.assertTrue(ks_ldap.dn_startswith(descendant, dn))


class LDAPDeleteTreeTest(tests.TestCase):

    def setUp(self):
        super(LDAPDeleteTreeTest, self).setUp()

        ks_ldap.register_handler('fake://',
                                 fakeldap.FakeLdapNoSubtreeDelete)
        self.load_backends()
        self.load_fixtures(default_fixtures)

        self.addCleanup(self.clear_database)
        self.addCleanup(common_ldap_core._HANDLERS.clear)

    def clear_database(self):
        for shelf in fakeldap.FakeShelves:
            fakeldap.FakeShelves[shelf].clear()

    def config_overrides(self):
        super(LDAPDeleteTreeTest, self).config_overrides()
        self.config_fixture.config(
            group='identity',
            driver='keystone.identity.backends.ldap.Identity')

    def config_files(self):
        config_files = super(LDAPDeleteTreeTest, self).config_files()
        config_files.append(tests.dirs.tests_conf('backend_ldap.conf'))
        return config_files

    def test_deleteTree(self):
        """Test manually deleting a tree.

        Few LDAP servers support CONTROL_DELETETREE.  This test
        exercises the alternate code paths in BaseLdap.deleteTree.

        """
        conn = self.identity_api.user.get_connection()
        id_attr = self.identity_api.user.id_attr
        objclass = self.identity_api.user.object_class.lower()
        tree_dn = self.identity_api.user.tree_dn

        def create_entry(name, parent_dn=None):
            if not parent_dn:
                parent_dn = tree_dn
            dn = '%s=%s,%s' % (id_attr, name, parent_dn)
            attrs = [('objectclass', [objclass, 'ldapsubentry']),
                     (id_attr, [name])]
            conn.add_s(dn, attrs)
            return dn

        # create 3 entries like this:
        # cn=base
        # cn=child,cn=base
        # cn=grandchild,cn=child,cn=base
        # then attempt to deleteTree(cn=base)
        base_id = 'base'
        base_dn = create_entry(base_id)
        child_dn = create_entry('child', base_dn)
        grandchild_dn = create_entry('grandchild', child_dn)

        # verify that the three entries were created
        scope = ldap.SCOPE_SUBTREE
        filt = '(|(objectclass=*)(objectclass=ldapsubentry))'
        entries = conn.search_s(base_dn, scope, filt,
                                attrlist=common_ldap_core.DN_ONLY)
        self.assertThat(entries, matchers.HasLength(3))
        sort_ents = sorted([e[0] for e in entries], key=len, reverse=True)
        self.assertEqual([grandchild_dn, child_dn, base_dn], sort_ents)

        # verify that a non-leaf node can't be deleted directly by the
        # LDAP server
        self.assertRaises(ldap.NOT_ALLOWED_ON_NONLEAF,
                          conn.delete_s, base_dn)
        self.assertRaises(ldap.NOT_ALLOWED_ON_NONLEAF,
                          conn.delete_s, child_dn)

        # call our deleteTree implementation
        self.identity_api.user.deleteTree(base_id)
        self.assertRaises(ldap.NO_SUCH_OBJECT,
                          conn.search_s, base_dn, ldap.SCOPE_BASE)
        self.assertRaises(ldap.NO_SUCH_OBJECT,
                          conn.search_s, child_dn, ldap.SCOPE_BASE)
        self.assertRaises(ldap.NO_SUCH_OBJECT,
                          conn.search_s, grandchild_dn, ldap.SCOPE_BASE)
