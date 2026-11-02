import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from trumpwatch import app


class TelegramCalendarTableTests(unittest.TestCase):
    def test_formats_events_as_html_preformatted_table(self):
        event_time = datetime(2026, 11, 3, 8, 30, tzinfo=ZoneInfo('UTC')).timestamp()
        rows = [(
            'event-id',
            'USD: CPI & inflation (High impact)',
            event_time,
            'Forex Factory economic calendar',
            'https://www.forexfactory.com/calendar',
            10,
        )]

        result = app.format_calendar_table(rows, 'Upcoming USD events')

        self.assertIn('<b>Upcoming USD events</b>', result)
        self.assertIn('<pre>', result)
        self.assertIn('DATE / TIME', result)
        self.assertIn('02:00 PM IST', result)
        self.assertIn('HIGH', result)
        self.assertIn('CPI &amp; inflation', result)
        self.assertNotIn('USD: ', result)
        self.assertNotIn('(High impact)', result)


if __name__ == '__main__':
    unittest.main()
