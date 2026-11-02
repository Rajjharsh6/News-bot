import time
import unittest

from trumpwatch import app


class NewsCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_news_command_splits_long_output_into_telegram_messages(self):
        class FakeDB:
            def latest(self,*args,**kwargs):
                return [
                    (
                        'News source',
                        f'Long headline {index} ' + ('market update ' * 25),
                        f'https://example.test/articles/{index}',
                        '2026-11-02 12:00 UTC',
                        'macro',
                        8,
                        time.time(),
                    )
                    for index in range(20)
                ]

        class FakeBot:
            def __init__(self):
                self.messages=[]

            async def send_message(self,chat_id,text,**kwargs):
                self.messages.append((chat_id,text))

        class FakeMessage:
            class Chat:
                id=123

            chat=Chat()

            async def answer(self,text):
                raise AssertionError(f'Unexpected one-message reply: {text}')

        original_db,original_bot=app.db,app.bot
        fake_bot=FakeBot()
        app.db,app.bot=FakeDB(),fake_bot
        try:
            await app.news(FakeMessage())
        finally:
            app.db,app.bot=original_db,original_bot

        self.assertGreater(len(fake_bot.messages),1)
        self.assertTrue(all(len(text)<=3900 for _,text in fake_bot.messages))
        self.assertTrue(all(chat_id==123 for chat_id,_ in fake_bot.messages))


if __name__ == '__main__':
    unittest.main()
