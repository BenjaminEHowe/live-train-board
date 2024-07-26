# Live Train Board
A live train departure board using the [Pimoroni Badger 2040 W](https://shop.pimoroni.com/products/badger-2040-w).

Live departure board data provided by the [Rail Delivery Group](https://www.raildeliverygroup.com/).

## Getting Started
1. Install [the latest Badger 2040 firmware on your device](https://github.com/pimoroni/badger2040) (select the regular build, not `with-badger-os`).
1. Copy the files in [the `mpy` directory](/mpy) to your device.
1. Set `CRS_LOCATION`, `WIFI_COUNTRY`, `WIFI_NETWORK`, and `WIFI_PASSWORD` (and optionally `CRS_FILTER`) within `config.json`. If you're not sure what the CRS code is for your local station, [you can find it on the National Rail website](https://www.nationalrail.co.uk/find-a-station/).

## Configuration
There are several configurable values set in `config.json`:
- `API_URL_PREFIX` (optional): the prefix used for the API URL. The default value, `https://www.beh.uk/api/raildata`, is [implemented using Cloudflare Functions as part of my personal website](https://github.com/BenjaminEHowe/beh.uk/tree/395b1774582eb186d2eade88fa4af21295a25a20/functions/api/raildata).
- `CRS_LOCATION`: the CRS code for the station to show departures from.
- `CRS_FILTER` (optional): filter departures to only include trains calling at the given station.
- `DISPLAY_UPDATE_INTERVAL_SECS` (optional): how often to update the display, in seconds. The default value is `60` (seconds), but this could be increased for stations with infrequent departures.
- `EINK_REFRESH_INTERVAL` (optional): how often to perform a "full" refresh of the e ink display, to remove ghosting. The default value is to `60` -- i.e. a full refresh every 60th update. Set to 0 to disable.
- `EINK_UPDATE_SPEED` (optional): how quickly to update the display -- see [the Badger 2040 docs for details](https://github.com/pimoroni/badger2040/blob/main/docs/reference.md#update-speed). The default value is `2` (i.e. `UPDATE_FAST`).
- `NTP_HOST` (optional): the hostname of the server to use for [NTP](https://en.wikipedia.org/wiki/Network_Time_Protocol), when setting the time on boot. The default value is `time.cloudflare.com`, which is [Cloudflare's secure time service](https://blog.cloudflare.com/secure-time).
- `NTP_INTERVAL_HOURS` (optional): how often to update the time using NTP, in hours. The default value is `4` (hours), but this may need to be reduced due to [issues with clock drift](https://github.com/micropython/micropython/issues/2724). Set to 0 to disable.
- `SLEEP_MODE` (optional): when to enter "sleep mode", where the display does not update. Set to an empty string to disable.
- `WIFI_COUNTRY`: the [ISO 3166-2 country](https://en.wikipedia.org/wiki/ISO_3166-2) where the board is operating.
- `WIFI_NETWORK`: the network name (SSID) that the board should connect to.
- `WIFI_PASSWORD`: the password (PSK) for the network that the board should connect to.
