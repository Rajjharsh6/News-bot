import unittest

import httpx

from trumpwatch.sources import read_truthsocial


class TruthSocialReaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_reads_public_statuses_with_real_timestamps(self):
        requests=[]

        def respond(request):
            requests.append(request)
            if request.url.path.endswith('/accounts/lookup'):
                return httpx.Response(200,json={'id':'123'},request=request)
            if request.url.path.endswith('/accounts/123/statuses'):
                return httpx.Response(200,json=[{
                    'content':'<p>New public statement</p>',
                    'created_at':'2026-11-02T10:15:00Z',
                    'url':'https://truthsocial.com/@realDonaldTrump/posts/456',
                }],request=request)
            self.fail(f'Unexpected endpoint: {request.url}')

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            events=await read_truthsocial(
                client,
                'https://truthsocial.com/@realDonaldTrump',
            )

        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['title'],'New public statement')
        self.assertEqual(events[0]['published_epoch'],1793614500)
        self.assertEqual(len(requests),2)

    async def test_reports_blocked_public_access_and_points_to_rss(self):
        def respond(request):
            return httpx.Response(403,request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with self.assertRaisesRegex(RuntimeError,'TRUTHSOCIAL_RSS_URL'):
                await read_truthsocial(
                    client,
                    'https://truthsocial.com/@realDonaldTrump',
                )

    async def test_rejects_non_truthsocial_profile_hosts(self):
        async with httpx.AsyncClient() as client:
            with self.assertRaisesRegex(ValueError,'truthsocial.com'):
                await read_truthsocial(client,'https://example.com/@someone')


if __name__ == '__main__':
    unittest.main()
