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
# Copyright Mamba Team
import logging
from dateutil.parser import parse as dateparse

from twisted.python import log

import json

_HEADER_CT = 'Content-Type'
_HEADER_EVENT = 'X-Event-Key'

class BitbucketServerEventHandler(object):

    def __init__(self, codebase=None, options={}):
        self._codebase = codebase
        self.options = options

    def process(self, request):
        payload = self._get_payload(request)
        event_type = request.getHeader(_HEADER_EVENT)
        print("Processing event %s: %r" % (_HEADER_EVENT, event_type,))
        event_type = event_type.replace(":", "_")
        handler = getattr(self, 'handle_%s' % event_type, None)

        if handler is None:
            raise ValueError('Unknown event: %r' % (event_type,))

        return handler(payload)

    def _get_payload(self, request):
        content = request.content.read()
        content_type = request.getHeader(_HEADER_CT)
        if content_type.startswith('application/json'):
            payload = json.loads(content)
        elif content_type.startswith('application/x-www-form-urlencoded'):
            payload = json.loads(request.args['payload'][0])
        else:
            raise ValueError('Unknown content type: %r' % (content_type,))

        print("Payload: %r" % payload)

        return payload

    def handle_repo_push(self, payload):
        changes = []
        repository = payload['repository']['fullName'].split('/')[-1]
        project = payload['repository']['project']['name']
        author=payload['actor']['username']
        repo_url=payload['repository']['links']['self'][0]['href'].rstrip('browse')
        for change in payload['push']['changes']:
            changes.append({
                'author': "%s <%s>" %
                (payload['actor']['displayName'], payload['actor']['username']),
                'comments': 'Bitbucket Server commit %s' %
                change['new']['target']['hash'],
                'revision': change['new']['target']['hash'],
                'branch': change['new']['name'],
                'revlink': '%scommits/%s' % (repo_url,
                    change['new']['target']['hash']),
                'repository': repo_url,
                'category' : 'push',
                'project': project
            })
            log.msg('New revision: %s' % (change['new']['target']['hash'],))
        log.msg('Received %s changes from bitbucket' % (len(changes),))
        return (changes, payload['repository']['scmId'])

    def handle_pullrequest_created(self, payload):
        return self.handle_pullrequest(
                payload, 
                "refs/pull-requests/%d/merge" % (int(payload['pullrequest']['id']),))

    def handle_pullrequest_updated(self, payload):
        return self.handle_pullrequest(
                payload, 
                "refs/pull-requests/%d/merge" % (int(payload['pullrequest']['id']),))

    def handle_pullrequest_fulfilled(self, payload):
        return self.handle_pullrequest(
                payload, 
                "refs/heads/%s" % (payload['pullrequest']['toRef']['branch']['name'],))

    def handle_pullrequest(self, payload, refname):
        changes = []
        pr_number = int(payload['pullrequest']['id'])
        repo_url=payload['repository']['links']['self'][0]['href'].rstrip('browse')
        change = {
            'revision': None,
            'revlink': payload['pullrequest']['link'],
            'repository': repo_url, 
            'branch' : refname,
            'project': payload['repository']['project']['name'],
            'category': 'pull',
            'author': '%s <%s>' % (payload['actor']['displayName'],
                                   payload['actor']['username']),
            'comments': 'Bitbucket Server Pull Request #%d' % (pr_number, ),
            'properties' : { "pull_request_url" :
                payload['pullrequest']['link'] }
        }

        if callable(self._codebase):
            change['codebase'] = self._codebase(payload)
        elif self._codebase is not None:
            change['codebase'] = self._codebase

        changes.append(change)

        log.msg("Received %d changes from Bitbucket PR #%d" % (
            len(changes), pr_number))
        return changes, payload['repository']['scmId']


def getChanges(request, options=None):
    """
    Process the Bitbucket webhook event.

    :param twisted.web.server.Request request: the http request object

    """
    if not isinstance(options, dict):
        options = {}

    handler = BitbucketServerEventHandler(options.get('codebase', None),
            options)
    return handler.process(request)
