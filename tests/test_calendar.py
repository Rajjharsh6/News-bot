import json
import time
import unittest
from datetime import datetime, timezone

from trumpwatch.calendar import fetch_ics, parse_forex_factory_events, parse_ics_datetime
from trumpwatch.sources import parsed_epoch


class ForexFactoryCalendarTests(unittest.TestCase):
    def test_parses_future_events_with_timezone_and_impact(self):
        now = datetime(2026, 11, 2, tzinfo=timezone.utc).timestamp()
        payload = json.dumps([
            {
                'title': 'CPI y/y',
                'country': 'USD',
                'date': '2026-11-03T08:30:00-05:00',
                'impact': 'High',
                'actual': '',
                'forecast': '3.1%',
                'previous': '3.0%',
            },
            {
                'title': 'Past release',
                'country': 'USD',
                'date': '2026-11-01T08:30:00-05:00',
                'impact': 'High',
            },
            {
                'title': 'Euro CPI',
                'country': 'EUR',
                'date': '2026-11-03T08:30:00-05:00',
                'impact': 'High',
            },
        ])

        events = parse_forex_factory_events(payload, now)

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event['title'], 'USD: CPI y/y (High impact)')
        self.assertEqual(
            event['event_time'],
            datetime.fromisoformat('2026-11-03T08:30:00-05:00').timestamp(),
        )
        self.assertEqual(event['importance'], 10)
        self.assertIn('Forecast: 3.1%', event['content'])
        self.assertIn('Previous: 3.0%', event['content'])
        self.assertEqual(event['source'], 'Forex Factory economic calendar')
        self.assertTrue(all('USD:' in item['title'] for item in events))

    def test_rejects_non_array_response(self):
        with self.assertRaises(ValueError):
            parse_forex_factory_events('{}', 0)

    def test_skips_missing_or_timezone_naive_event_dates(self):
        events = parse_forex_factory_events(json.dumps([
            {'title': 'Missing date', 'country': 'USD'},
            {'title': 'No timezone', 'country': 'USD', 'date': '2026-11-03T08:30:00'},
        ]), 0)

        self.assertEqual(events, [])

    def test_ics_tzid_is_respected(self):
        event_time = parse_ics_datetime('20261103T083000', 'America/New_York')

        self.assertEqual(
            event_time.timestamp(),
            datetime.fromisoformat('2026-11-03T08:30:00-05:00').timestamp(),
        )

    def test_utc_ics_time_stays_utc(self):
        event_time = parse_ics_datetime('20261103T133000Z', 'America/New_York')

        self.assertEqual(event_time.utcoffset().total_seconds(), 0)

    def test_rss_timestamp_is_interpreted_as_utc(self):
        source_time = time.struct_time((2026, 11, 3, 13, 30, 0, 1, 307, 0))

        self.assertEqual(
            parsed_epoch({'published_parsed': source_time}),
            datetime(2026, 11, 3, 13, 30, tzinfo=timezone.utc).timestamp(),
        )


class ICSCalendarTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_ics_retains_tzid(self):
        class Response:
            text = (
                'BEGIN:VCALENDAR\r\n'
                'BEGIN:VEVENT\r\n'
                'DTSTART;TZID=America/New_York:20300115T083000\r\n'
                'SUMMARY:Rate decision\r\n'
                'END:VEVENT\r\n'
                'END:VCALENDAR\r\n'
            )

            def raise_for_status(self):
                return None

        class Client:
            async def get(self, url):
                return Response()

        events = await fetch_ics(Client(), 'https://example.test/events.ics')

        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0]['event_time'],
            datetime.fromisoformat('2030-01-15T08:30:00-05:00').timestamp(),
        )


if __name__ == '__main__':
    unittest.main()
