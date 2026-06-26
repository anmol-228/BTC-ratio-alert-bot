import asyncio
from pathlib import Path
import tempfile
import unittest

from delta_ratio_bot.app import run_health_check, run_telegram_test
from delta_ratio_bot.config import load_config


VALID_CONFIG = """
[delta]
base_url = "https://api.delta.exchange"
underlying_assets = ["BTC"]
request_timeout_seconds = 15

[market_data]
mode = "rest"
use_websocket = false
scan_frequency_seconds = 5
max_consecutive_failures_before_backoff = 3
backoff_seconds = 30

[strategy]
enable_calls = true
enable_puts = false
ratio_min = 3
ratio_max = 8
min_net_inflow_usd = 20
max_net_inflow_usd = 100
min_strike_difference = 0
max_strike_difference = 0
min_otm_distance = 2000
max_sell_premium_percent_of_buy = 60
require_negative_atm_spread = true
premium_mode = "bid_ask"
fallback_to_mark_price = true
require_bid_ask = false
premium_multiplier_mode = "raw"
expiry_include = []
expiry_exclude = []

[alerts]
dry_run = true
cooldown_seconds = 900
send_all_matching_opportunities = true
max_alerts_per_scan = 0
realert_if_inflow_improves = true
realert_if_inflow_improves_by = 20
telegram_bot_token = ""
telegram_chat_id = ""

[logging]
level = "INFO"
save_alerts_csv = false
save_opportunities_db = false
"""


def write_config(text: str) -> Path:
    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as handle:
        handle.write(text)
        return Path(handle.name)


class OperationsTest(unittest.TestCase):
    def test_telegram_test_dry_run_succeeds_without_credentials(self) -> None:
        config = load_config(write_config(VALID_CONFIG))

        result = asyncio.run(run_telegram_test(config))

        self.assertEqual(result, 0)

    def test_telegram_test_live_mode_fails_without_credentials(self) -> None:
        config = load_config(write_config(VALID_CONFIG.replace("dry_run = true", "dry_run = false")))

        result = asyncio.run(run_telegram_test(config))

        self.assertEqual(result, 1)

    def test_health_check_passes_with_valid_dry_run_config(self) -> None:
        config = load_config(write_config(VALID_CONFIG))

        result = run_health_check(config)

        self.assertEqual(result, 0)

    def test_invalid_ratio_range_fails_config_load(self) -> None:
        config_text = VALID_CONFIG.replace("ratio_min = 3", "ratio_min = 9")

        with self.assertRaises(ValueError):
            load_config(write_config(config_text))

    def test_backoff_config_parses_correctly(self) -> None:
        config = load_config(write_config(VALID_CONFIG))

        self.assertEqual(config.market_data.max_consecutive_failures_before_backoff, 3)
        self.assertEqual(config.market_data.backoff_seconds, 30)

    def test_sell_premium_percent_config_parses_correctly(self) -> None:
        config = load_config(write_config(VALID_CONFIG))

        self.assertEqual(config.strategy.max_sell_premium_percent_of_buy, 60)


if __name__ == "__main__":
    unittest.main()
