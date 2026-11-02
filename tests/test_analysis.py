import json
import unittest

import httpx

from trumpwatch.analysis import Analyzer


class GroqAnalyzerTests(unittest.IsolatedAsyncioTestCase):
    async def test_sends_chat_completion_request(self):
        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={
                'choices': [{'message': {'content': 'Summary: test context'}}],
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            analyzer = Analyzer('test-key', 'test-model', True, client)
            result = await analyzer.analyze({
                'source': 'Test source',
                'title': 'Test headline',
                'published': 'now',
                'content': 'test details',
                'url': 'https://example.test/item',
            })

        self.assertEqual(result, 'Summary: test context')
        body=json.loads(requests[0].content)
        self.assertEqual(body['max_completion_tokens'],500)
        self.assertIn('Hinglish',body['messages'][0]['content'])
        self.assertIn('70 words total',body['messages'][0]['content'])

    async def test_gpt_oss_uses_low_reasoning_effort(self):
        requests=[]

        def respond(request):
            requests.append(request)
            return httpx.Response(200,json={
                'choices':[{'message':{'content':'Short explanation'},'finish_reason':'stop'}],
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            analyzer=Analyzer('test-key','openai/gpt-oss-20b',True,client)
            result=await analyzer.analyze({
                'source':'Test source',
                'title':'Test headline',
                'published':'now',
                'content':'test details',
                'url':'https://example.test/item',
            })

        body=json.loads(requests[0].content)
        self.assertEqual(body['reasoning_effort'],'low')
        self.assertEqual(body['max_completion_tokens'],500)
        self.assertEqual(result,'Short explanation')
        self.assertEqual(str(requests[0].url), 'https://api.groq.com/openai/v1/chat/completions')
        self.assertEqual(requests[0].headers['Authorization'], 'Bearer test-key')

    async def test_disabled_analysis_does_not_make_request(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: self.fail('disabled analysis must not make a request')
        )) as client:
            analyzer = Analyzer('test-key', 'test-model', False, client)
            self.assertEqual(await analyzer.analyze({}), '')
            self.assertIn('GROQ_API_KEY', analyzer.last_error)

    async def test_reports_invalid_api_key_without_hiding_provider_status(self):
        async def respond(request):
            return httpx.Response(
                401,
                json={'error': {'message': 'Invalid API Key'}},
                request=request,
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            analyzer = Analyzer('bad-key', 'test-model', True, client)
            result = await analyzer.analyze({
                'source': 'Test source',
                'title': 'Test headline',
                'published': 'now',
                'content': '',
                'url': '',
            })

        self.assertEqual(result, '')
        self.assertIn('401', analyzer.last_error)
        self.assertIn('GROQ_API_KEY', analyzer.last_error)

    async def test_reports_model_error_detail(self):
        async def respond(request):
            return httpx.Response(
                404,
                json={'error': {'message': 'Model not found'}},
                request=request,
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            analyzer = Analyzer('test-key', 'retired-model', True, client)
            await analyzer.analyze({
                'source': 'Test source',
                'title': 'Test headline',
                'published': 'now',
                'content': '',
                'url': '',
            })

        self.assertIn('model', analyzer.last_error.lower())
        self.assertIn('Model not found', analyzer.last_error)


if __name__ == '__main__':
    unittest.main()
