import unittest
from unittest.mock import AsyncMock, patch

from trumpwatch import app


class DeliveryRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_text_retries_failed_chunk(self):
        class FakeBot:
            calls = 0

            async def send_message(self, *args, **kwargs):
                self.calls += 1
                if self.calls < 3:
                    raise RuntimeError('temporary delivery failure')

        fake_bot = FakeBot()
        original_bot = app.bot
        app.bot = fake_bot
        try:
            with patch('trumpwatch.app.asyncio.sleep', new_callable=AsyncMock) as sleep:
                await app.send_text(123, 'test message')
        finally:
            app.bot = original_bot

        self.assertEqual(fake_bot.calls, 3)
        self.assertEqual(sleep.await_count, 2)
