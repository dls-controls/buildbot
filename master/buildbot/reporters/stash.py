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

from __future__ import absolute_import
from __future__ import print_function

from twisted.internet import defer

from buildbot.process.properties import Interpolate
from buildbot.process.properties import Properties
from buildbot.process.results import SUCCESS
from buildbot.reporters import http
from buildbot.util import httpclientservice
from buildbot.util.logger import Logger
import re

log = Logger()

# Magic words understood by Stash REST API
STASH_INPROGRESS = 'INPROGRESS'
STASH_SUCCESSFUL = 'SUCCESSFUL'
STASH_FAILED = 'FAILED'


class StashStatusPush(http.HttpStatusPushBase):
    name = "StashStatusPush"

    @defer.inlineCallbacks
    def reconfigService(self, base_url, user, password, key=None, statusName=None,
                        startDescription=None, endDescription=None,
                        verbose=False, **kwargs):
        yield http.HttpStatusPushBase.reconfigService(self, wantProperties=True,
                                                      **kwargs)
        self.key = key or Interpolate('%(prop:buildername)s')
        self.statusName = statusName
        self.endDescription = endDescription or 'Build done.'
        self.startDescription = startDescription or 'Build started.'
        self.verbose = verbose
        self._http = yield httpclientservice.HTTPClientService.getService(
            self.master, base_url, auth=(user, password))

    @defer.inlineCallbacks
    def send(self, build):
        props = Properties.fromDict(build['properties'])
        results = build['results']
        got_revision = props.getProperty('got_revision', None)
        if build['complete']:
            status = STASH_SUCCESSFUL if results == SUCCESS else STASH_FAILED
            description = self.endDescription
        else:
            status = STASH_INPROGRESS
            description = self.startDescription
        for sourcestamp in build['buildset']['sourcestamps']:
            if isinstance(got_revision, dict):
                current_got_revision = got_revision[sourcestamp['codebase']]
            else:
                current_got_revision = got_revision
            sha = sourcestamp['revision'] or current_got_revision
            if sha is None:
                log.error("Unable to get commit hash")
                continue
            key = yield props.render(self.key)
            payload = {
                'state': status,
                'url': build['url'],
                'key': key,
            }
            if description:
                payload['description'] = yield props.render(description)
            if self.statusName:
                payload['name'] = yield props.render(self.statusName)
            response = yield self._http.post('/rest/build-status/1.0/commits/' + sha,
                                             json=payload)
            if response.code == 204:
                if self.verbose:
                    log.info('Status "{status}" sent for {sha}.',
                             status=status, sha=sha)
            else:
                content = yield response.content()
                log.error("{code}: Unable to send Stash status: {content}",
                          code=response.code, content=content)


class StashPRCommentPush(http.HttpStatusPushBase):
    name = "StashPRCommentPush"

    @defer.inlineCallbacks
    def reconfigService(self, base_url, user, password, text=None, statusName=None,
                        startDescription=None, endDescription=None,
                        verbose=False, **kwargs):
        yield http.HttpStatusPushBase.reconfigService(self, wantProperties=True,
                                                      **kwargs)
        self.text = text or Interpolate('Builder: %(prop:buildername)s Status: %(prop:statustext)s')
        self.statusName = statusName
        self.endDescription = endDescription or 'Build done.'
        self.startDescription = startDescription or 'Build started.'
        self.verbose = verbose
        self._http = yield httpclientservice.HTTPClientService.getService(
            self.master, base_url, auth=(user, password))

    @defer.inlineCallbacks
    def send(self, build):
        if build['complete'] \
           and build['properties'].has_key("pullrequesturl") \
           and build['properties'].has_key("got_revision"):
                yield self.sendPullRequestComment(build)

    @defer.inlineCallbacks
    def sendPullRequestComment(self, build):
        props = Properties.fromDict(build['properties'])
        pr_url = props.getProperty("pullrequesturl")
        got_revision = props.getProperty('got_revision')
        match = re.search("^(http|https)://([^/]+)/(.+)$", pr_url)

        if not match:
            log.error("not valid pull request URL: %s" % (pr_url,))
            defer.returnValue(None)
            return

        path = match.group(3)

        if isinstance(got_revision, dict):
            merged_link = []
            for sourcestamp in build['buildset']['sourcestamps']:
                merged_link.append("%s/commits/%s" % (sourcestamp['repository'].rstrip('/'),
                                                     got_revision[sourcestamp['codebase']]))
            merged_link = ' & '.join(merged_link)
        else:
            merged_link = "%s/commits/%s" % (props.getProperty('repository').rstrip('/'), got_revision)

        status = "SUCCESS" if build['results']==SUCCESS else "FAILED"
        props.setProperty('mergedlink', merged_link, self.name)
        props.setProperty('statustext', status, self.name)
        props.setProperty('url', build['url'], self.name)

        comment_text = yield props.render(self.text)
        payload = {
                'text' : comment_text
                }
        response = yield self._http.post('/rest/api/1.0/%s/comments' % (path),
                                          json=payload)
        if response.code == 201:
            log.info('{comment_text} sent for {got_revision}', comment_text=comment_text, got_revision=got_revision)
        else:
            content = yield response.content()
            log.error("{code}: Unable to send any comment: {content}",
                      code=response.code, content=content)
        defer.returnValue(None)
