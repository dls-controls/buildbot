# This file is part of Buildbot.  Buildbot is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright Buildbot Team Members
# Copyright Manba Team

from __future__ import absolute_import
from __future__ import print_function

import calendar
from StringIO import StringIO

from twisted.internet.defer import inlineCallbacks
from twisted.trial import unittest

import buildbot.www.change_hook as change_hook
from buildbot.test.fake.web import FakeRequest
from buildbot.test.fake.web import fakeMasterForHooks
from buildbot.www.hooks.bitbucketserver import _HEADER_EVENT
from buildbot.www.hooks.bitbucketserver import _HEADER_CT

_CT_JSON = 'application/json'

gitJsonPayload = """
{
    "actor":
    {
        "username":"John",
        "displayName":"John Smith"
    },
    "repository":
    {
        "scmId":"git",
        "project":
        {
            "key":"~JOHN",
            "name":"John Smith"
        },
            "slug":"good-repo",
        "links":
        {
            "self":
                [
                {
                    "href":"http://localhost:7990/users/john/repos/good-repo/browse"
                }
                ]
        },
        "ownerName":"JOHN",
        "public":false,
        "owner":
        {
            "username":"JOHN",
            "displayName":"JOHN"
        },
        "fullName":"JOHN/good-repo"
    },
    "push":
    {
        "changes":
            [
            {
                "created":false,
                "closed":false,
                "old":
                {
                    "type":"branch",
                    "name":"master",
                    "target":
                    {
                        "type":"commit",
                        "hash":"8d33edb8ce607b55b8d7b494ee2d1d52dbb3ff71"
                    }
                },
                "new":
                {
                    "type":"branch",
                    "name":"master",
                    "target":
                    {
                        "type":"commit",
                        "hash":"d156103f161e80ea351023e5e8d9bcb86f37924e"
                    }
                }
            }
            ]
    }
}
"""


def _prepare_request(payload, headers=None, change_dict=None):
    headers = headers or {}
    request = FakeRequest(change_dict)
    request.uri = "/change_hook/bitbucketserver"
    request.method = "POST"
    request.content = StringIO(payload)
    request.received_headers[_HEADER_CT] = _CT_JSON
    request.received_headers.update(headers)
    return request


class TestChangeHookConfiguredWithBitbucketServerChange(unittest.TestCase):

    """Unit tests for Bitbucket Server Change Hook
    """

    def setUp(self):
        self.change_hook = change_hook.ChangeHookResource(
            dialects={'bitbucketserver': {}}, master=fakeMasterForHooks())

    @inlineCallbacks
    def testGitWithChange(self):

        request = _prepare_request(gitJsonPayload, headers={_HEADER_EVENT :
            "repo:push"})

        yield request.test_render(self.change_hook)

        self.assertEqual(len(self.change_hook.master.addedChanges), 1)
        commit = self.change_hook.master.addedChanges[0]

        # self.assertEqual(commit['files'], ['somefile.py'])
        self.assertEqual(
            commit['repository'],
            'http://localhost:7990/users/john/repos/good-repo/')
        self.assertEqual(
           commit['author'], 'John Smith <John>')
        self.assertEqual(
            commit['revision'], 'd156103f161e80ea351023e5e8d9bcb86f37924e')
        self.assertEqual(
            commit['comments'], 'Bitbucket Server commit d156103f161e80ea351023e5e8d9bcb86f37924e')
        self.assertEqual(commit['branch'], 'master')
        self.assertEqual(
            commit['revlink'],
            'http://localhost:7990/users/john/repos/good-repo/commits/d156103f161e80ea351023e5e8d9bcb86f37924e')

