# Live Train Board
A live train departure board using the [Pimoroni Badger 2040 W](https://shop.pimoroni.com/products/badger-2040-w).

## Getting Started
1. Install [the latest Badger 2040 firmware on your device](https://github.com/pimoroni/badger2040) (select the regular build, not `with-badger-os`).
1. Copy the files in [the `mpy` directory](/mpy) to your device.
1. Set your Wi-Fi details (and country, if not in the UK) within `WIFI_CONFIG.py`.
1. Set `CRS_LOCATION` (and optionally `CRS_FILTER`) within `badger_ldb.py`. If you're not sure what the CRS code is for your local station, [you can find it on the National Rail website](https://www.nationalrail.co.uk/find-a-station/).
