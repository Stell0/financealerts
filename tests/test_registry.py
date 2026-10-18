import csv
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from papertrader_data import load_snapshot
from registry import merge_universe, read_securities, resolve, synchronize

FIXTURE = Path(__file__).parent / 'fixtures' / 'papertrader' / 'securities.csv'


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.rows = read_securities(FIXTURE.read_text())

    def test_initial_registry_contains_all_registered_identities(self):
        tickers = Path('config/tickers.txt').read_text().split()
        universe = merge_universe(tickers, '', self.rows)
        self.assertEqual({row['security_id'] for row in self.rows},
                         {item.identity for item in universe if item.security})
        self.assertEqual(tickers, [item.ticker for item in universe])

    def test_aliases_have_one_identity_but_goog_has_separate_prices(self):
        universe = merge_universe(['GOOG', 'GOOGL', 'BTCUSD', 'BTC-USD'], '', self.rows)
        alphabet = [item for item in universe if item.yahoo_symbol in {'GOOG', 'GOOGL'}]
        self.assertEqual(len(alphabet), 1)
        self.assertEqual(alphabet[0].ticker, 'GOOG')
        self.assertEqual(alphabet[0].security['ticker'], 'GOOGL')
        self.assertEqual(resolve('GOOGL', self.rows).yahoo_symbol, 'GOOGL')
        bitcoin = [item for item in universe if item.ticker == 'BTCUSD']
        self.assertEqual(len(bitcoin), 1)
        self.assertEqual(bitcoin[0].yahoo_symbol, 'BTC-USD')

    def test_merge_environment_is_additive_stable_and_override_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tickers.txt'
            path.write_text(' tsla \nGOOG\n')
            universe = synchronize(path, ' aapl AAPL btc-usd ', self.rows)
            self.assertIn('AAPL', [item.ticker for item in universe])
            before = path.read_bytes(), path.stat().st_mtime_ns
            again = synchronize(path, 'aapl AAPL btc-usd', self.rows)
            self.assertEqual(universe, again)
            self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))
            override = synchronize(path, '', self.rows, override='GOOGL')
            self.assertEqual([item.yahoo_symbol for item in override], ['GOOGL'])
            self.assertIn('GOOG', path.read_text().split())

    def test_provider_symbols_are_not_unqualified_registry_tickers(self):
        self.assertEqual(resolve('108490', self.rows).yahoo_symbol, '108490.KQ')
        self.assertEqual(resolve('AKE', self.rows).yahoo_symbol, 'AKE.PA')

    def test_reject_malformed_csv_and_ambiguous_identities(self):
        with self.assertRaises(ValueError):
            read_securities('ticker\nTSLA\n')
        with self.assertRaises(ValueError):
            read_securities(FIXTURE.read_text() + FIXTURE.read_text().splitlines()[1] + '\n')
        with self.assertRaises(ValueError):
            resolve('../bad', self.rows)
        other = dict(next(row for row in self.rows if row['ticker'] == 'GOOGL'))
        other['security_id'] = 'other'
        with self.assertRaises(ValueError):
            resolve('GOOG', [*self.rows, other])

    @patch('papertrader_data.fetch_text')
    def test_remote_snapshot_reads_both_tables_at_one_revision(self, fetch):
        sha = 'a' * 40
        fetch.side_effect = ['{"sha":"' + sha + '"}', FIXTURE.read_text(), 'security_id\n']
        rows, assessments = load_snapshot()
        self.assertEqual(len(rows), 92)
        self.assertEqual(assessments, 'security_id\n')
        for call in fetch.call_args_list[1:]:
            self.assertIn('/' + sha + '/', call.args[0])


if __name__ == '__main__':
    unittest.main()
