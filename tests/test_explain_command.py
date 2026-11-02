import unittest
from unittest.mock import AsyncMock, patch

from trumpwatch import app


class ExplainCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_explains_latest_news(self):
        class FakeDB:
            def latest_event(self):
                return (
                    'Fed',
                    'Rate decision',
                    'https://example.test/news',
                    'published',
                    'source content',
                    'fed',
                    9,
                    100,
                )

        class FakeAnalyzer:
            async def analyze(self, event):
                self.event = event
                return 'The Fed held rates steady.'

        analyzer = FakeAnalyzer()
        message = AsyncMock()
        message.text = '/explain'
        message.chat.id = 42
        original_db, original_analyzer = app.db, app.analyzer
        app.db, app.analyzer = FakeDB(), analyzer
        try:
            with patch.object(app.C, 'GROQ_KEY', 'configured'), \
                    patch.object(app.C, 'AI', True), \
                    patch('trumpwatch.app.send_text', new_callable=AsyncMock) as send_text:
                await app.explain(message)
        finally:
            app.db, app.analyzer = original_db, original_analyzer

        self.assertEqual(analyzer.event['title'], 'Rate decision')
        self.assertEqual(analyzer.event['content'], 'source content')
        send_text.assert_awaited_once()
        self.assertIn('The Fed held rates steady.', send_text.await_args.args[1])

    async def test_explains_next_calendar_event(self):
        class FakeDB:
            def next_scheduled_event(self, now):
                return ('USD CPI', 200, 'Forex Factory', 'https://example.test/calendar', 10, 'Forecast: 3.1%')

        class FakeAnalyzer:
            async def analyze(self, event):
                self.event = event
                return 'Compare actual with forecast.'

        analyzer = FakeAnalyzer()
        message = AsyncMock()
        message.text = '/explain upcoming'
        message.chat.id = 42
        original_db, original_analyzer = app.db, app.analyzer
        app.db, app.analyzer = FakeDB(), analyzer
        try:
            with patch.object(app.C, 'GROQ_KEY', 'configured'), \
                    patch.object(app.C, 'AI', True), \
                    patch('trumpwatch.app.send_text', new_callable=AsyncMock) as send_text:
                await app.explain(message)
        finally:
            app.db, app.analyzer = original_db, original_analyzer

        self.assertEqual(analyzer.event['title'], 'USD CPI')
        self.assertEqual(analyzer.event['content'], 'Forecast: 3.1%')
        send_text.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
