import tempfile
import unittest
from pathlib import Path

from trumpwatch.db import DB


class AlertDeduplicationTests(unittest.TestCase):
    def test_same_headline_is_claimed_only_once_during_cooldown(self):
        with tempfile.TemporaryDirectory() as directory:
            db = DB(str(Path(directory) / 'test.sqlite3'))

            self.assertTrue(db.claim_news_alert('Fed announces rate decision'))
            self.assertFalse(db.claim_news_alert(' FED announces rate decision! '))

    def test_headline_can_be_claimed_after_cooldown(self):
        with tempfile.TemporaryDirectory() as directory:
            db = DB(str(Path(directory) / 'test.sqlite3'))

            self.assertTrue(db.claim_news_alert('Employment report', cooldown_seconds=0))
            self.assertTrue(db.claim_news_alert('Employment report', cooldown_seconds=0))


class ExplanationStorageTests(unittest.TestCase):
    def test_latest_news_event_returns_stored_content(self):
        with tempfile.TemporaryDirectory() as directory:
            db = DB(str(Path(directory) / 'test.sqlite3'))
            with db.conn() as connection:
                connection.execute(
                    'INSERT INTO events(id,source,title,url,published,content,category,score,created,published_epoch) '
                    'VALUES(?,?,?,?,?,?,?,?,?,?)',
                    ('id', 'Source', 'Headline', 'https://example.test', 'now', 'Details', 'macro', 8, 1, 100),
                )

            event = db.latest_event()

            self.assertEqual(event[1], 'Headline')
            self.assertEqual(event[4], 'Details')
            self.assertEqual(event[6], 8)

    def test_next_scheduled_event_persists_calendar_details(self):
        with tempfile.TemporaryDirectory() as directory:
            db = DB(str(Path(directory) / 'test.sqlite3'))
            db.upsert_schedule({
                'id': 'event',
                'title': 'USD: CPI',
                'event_time': 200,
                'source': 'Forex Factory economic calendar',
                'url': 'https://example.test/calendar',
                'importance': 10,
                'content': 'Forecast: 3.1%; Previous: 3.0%',
            })

            event = db.next_scheduled_event(100)

            self.assertEqual(event[0], 'USD: CPI')
            self.assertEqual(event[5], 'Forecast: 3.1%; Previous: 3.0%')

    def test_calendar_queries_exclude_non_usd_events_already_in_database(self):
        with tempfile.TemporaryDirectory() as directory:
            db = DB(str(Path(directory) / 'test.sqlite3'))
            for event_id,title,source,event_time in (
                ('eur','EUR: German CPI','Forex Factory economic calendar',150),
                ('usd','USD: CPI','Forex Factory economic calendar',200),
                ('fed','FOMC rate decision','Federal Reserve official FOMC calendar',250),
                ('ics','EUR rates event','Calendar ICS',300),
            ):
                db.upsert_schedule({
                    'id':event_id,
                    'title':title,
                    'event_time':event_time,
                    'source':source,
                    'url':'https://example.test/calendar',
                    'importance':10,
                })

            upcoming=db.upcoming(100,10)
            next_event=db.next_scheduled_event(100)
            reminders=db.reminder_candidates(100)

            self.assertEqual([row[0] for row in upcoming],['usd','fed'])
            self.assertEqual(next_event[0],'USD: CPI')
            self.assertEqual([row[0] for row in reminders],['usd','fed'])
