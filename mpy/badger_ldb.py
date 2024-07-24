import badger2040
import gc
import machine
import network
import ntptime
import os
import socket
import time
import ubinascii
import urequests
import ujson

with open("config.json") as f:
    config = ujson.load(f)

# constants
HTTP_CONTENT_HTML = "text/html"
HTTP_CONTENT_JSON = "application/json"
HTTP_CONTENT_PLAIN = "text/plain"
HTTP_STATUS_NOT_FOUND = "404 Not Found"
HTTP_STATUS_OK = "200 OK"
LED_MAX = 128
LED_MIN = 0
LED_RISING = "LED_RISING"
LED_FALLING = "LED_FALLING"
if config["SLEEP_MODE"]:
    SLEEP_MODE_TEXT = "SLEEP MODE"
    SLEEP_MODE_START_HOUR = int(config["SLEEP_MODE"][0:2])
    SLEEP_MODE_START_MINUTE = int(config["SLEEP_MODE"][2:4])
    SLEEP_MODE_END_HOUR = int(config["SLEEP_MODE"][5:7])
    SLEEP_MODE_END_MINUTE = int(config["SLEEP_MODE"][7:9])
PEN_BLACK = 0
PEN_WHITE = 15
TS_SLICE_START = len("0000-00-00T")
TS_SLICE_END   = len("0000-00-00T00:00")
VERSION = "0.0.1"

# state
board_id = ubinascii.hexlify(machine.unique_id()).decode()
boot_time = 0
data = {}
eink_update_count = 0
led_brightness = 0
led_direction = LED_RISING
sleep_mode_active = False
utc_offset = 0


def breathe_led(timer):
    global led_brightness, led_direction
    if led_direction == LED_RISING:
        led_brightness += config["LED_STEP"]
        if led_brightness >= LED_MAX:
            led_brightness = LED_MAX
            led_direction = LED_FALLING
    else:
        led_brightness -= config["LED_STEP"]
        if led_brightness <= LED_MIN:
            led_brightness = LED_MIN
            led_direction = LED_RISING
    badger.led(led_brightness)


def display_clear():
    badger.set_pen(PEN_WHITE)
    badger.clear()
    badger.set_pen(PEN_BLACK)


def display_update():
    global eink_update_count
    if config["EINK_REFRESH_INTERVAL"] and eink_update_count % config["EINK_REFRESH_INTERVAL"] == 0:
        badger.set_update_speed(badger2040.UPDATE_NORMAL)
        badger.update()
        badger.set_update_speed(config["EINK_UPDATE_SPEED"])
    else:
        badger.update()
    eink_update_count += 1
    gc.collect()


def get_utc_offset(timer):
    global utc_offset
    res = urequests.request("GET", "http://worldtimeapi.org/api/ip", headers={
        "user-agent": f"Mozilla/5.0 (compatible; uk.beh.live-train-board/{VERSION}; board/{board_id})",
    })
    json = ujson.loads(res.text)
    if json["dst"]:
        utc_offset = json["dst_offset"]
    else:
        utc_offset = json["raw_offset"]
    gc.collect()


def localtime(secs=None):
  return time.localtime((secs if secs else time.time()) + utc_offset)


def connect_to_wifi():
    network.hostname(f"train-board-{board_id[:16]}")
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(config["WIFI_NETWORK"], config["WIFI_PASSWORD"])
    display_clear()
    badger.text("Data provided by the Rail Delivery Group", 4, 112, scale=1)
    badger.text("Board ID:", 4, 4, scale=1)
    badger.text(board_id, 12, 18, scale=2)
    badger.text("Connecting to " + config["WIFI_NETWORK"], 4, 48, scale=1)
    display_update()
    while wlan.isconnected() == False:
        time.sleep(0.1)
    badger.text("Connected, my IP address is:", 4, 60, scale=1)
    badger.text(wlan.ifconfig()[0], 12, 72, scale=2)
    display_update()
    time.sleep(config["WIFI_SUCCESS_MESSAGE_SECS"])
    gc.collect()


def get_data():
    url = config["API_URL_PREFIX"] + "/departures/v1/" + config["CRS_LOCATION"]
    if config["CRS_FILTER"]:
        url += "/" + config["CRS_FILTER"]
    res = urequests.request("GET", url, headers={
        "user-agent": f"Mozilla/5.0 (compatible; uk.beh.live-train-board/{VERSION}; board/{board_id})",
        "x-board-id": board_id,
    })
    # TODO: handle potential request failure better
    return ujson.loads(res.text)


def set_time(timer):
    ntptime.settime()


def should_be_in_sleep_mode(
    start_hour,
    end_hour,
    start_minute = 00,
    end_minute = 00,
    current_time = None,
):
    if not current_time:
        current_time = localtime()
    current_hour = current_time[3]
    current_minute = current_time[4]
    if (
        start_hour > end_hour or
        (start_hour == end_hour and start_minute > end_minute)
    ):
        return (
            current_hour > start_hour or
            (current_hour == start_hour and current_minute >= start_minute) or
            current_hour < end_hour or
            (current_hour == end_hour and current_minute > end_minute)
        )
    else:
        return (
            (current_hour > start_hour and current_hour < end_hour) or
            (
                (current_hour == start_hour or current_hour == end_hour) and
                current_minute > start_minute and
                current_minute < end_minute
            )
        )


def update_display(timer):
    global data, sleep_mode_active

    def display_service(y, service):
        def etd_text(etd):
            if etd == "On time":
                return "O/T"
            elif etd == "Cancelled":
                return "CANX"
            elif etd == "Delayed":
                return "DLAY"
            else:
                return etd
        
        badger.text(service["std"], 0, y, scale=2)
        badger.text(service["destination"], 55, y, scale=2)
        badger.text(etd_text(service["etd"]), 250, y, scale=2)
        if service["cancelled"]:
            badger.text(service["cancelReason"], 0, y + 16, scale=1)
        else:
            badger.text(f"Plat. {service['platform']}", 0, y + 16, scale=1)
            detailText = f"A {service['operator']} service"
            if "length" in service and service['length'] != "?":
                detailText += f" formed of {service['length']} coaches"
            badger.text(detailText, 55, y + 16, scale=1)
    
    if config["SLEEP_MODE"] and should_be_in_sleep_mode(
        start_hour = SLEEP_MODE_START_HOUR,
        start_minute = SLEEP_MODE_START_MINUTE,
        end_hour = SLEEP_MODE_END_HOUR,
        end_minute = SLEEP_MODE_END_MINUTE,
    ):
        if sleep_mode_active:
            return
        else:
            display_clear()
            badger.text(SLEEP_MODE_TEXT, 75, 50, scale=3)
            display_update()
            sleep_mode_active = True
            return
    sleep_mode_active = False
    data = get_data()
    display_clear()
    # services
    for i in range(len(data["services"][:4])):
        display_service(26 * i, data["services"][i])
    # locations
    badger.text(data['location'], 3, 110 , scale=1)
    if "filterLocation" in data:
        badger.text(data['filterLocation'], 3, 120 , scale=1)
    # time
    badger.text(data["generatedAt"][TS_SLICE_START:TS_SLICE_END], 116, 107 , scale=3)
    display_update()
    gc.collect()


def run():
    global badger
    badger = badger2040.Badger2040()
    badger.set_font("bitmap8")
    badger.set_update_speed(config["EINK_UPDATE_SPEED"])
    connect_to_wifi()
    ntptime.host = config["NTP_HOST"]
    ntptime.settime()
    boot_time = time.time()
    get_utc_offset(None)

    # set timers
    machine.Timer(period=config["LED_STEP_WAIT_MS"], callback=breathe_led)
    update_display(None)
    machine.Timer(period=config["DISPLAY_UPDATE_INTERVAL_SECS"]*1000, callback=update_display)
    if config["NTP_INTERVAL_HOURS"]:
        machine.Timer(period=config["NTP_INTERVAL_HOURS"]*1000*60*60, callback=set_time)
    machine.Timer(period=86400*1000, callback=get_utc_offset)

    # web server
    addr = socket.getaddrinfo("0.0.0.0", 80)[0][-1] # see https://github.com/BenjaminEHowe/live-train-board/issues/6
    s = socket.socket()
    s.bind(addr)
    s.listen(1)
    print("listening on", addr)
    while True:
        try:
            cl, addr = s.accept()
            print("client connected from", addr[0])
            request = cl.recv(1024)
            method = request.split()[0].decode()
            path = request.split()[1].decode()
            print(f"Recieved {method} {path}")
            status = HTTP_STATUS_NOT_FOUND
            content_type = HTTP_CONTENT_PLAIN
            body = "not found"
            if path == "/data":
                status = HTTP_STATUS_OK
                content_type = HTTP_CONTENT_JSON
                body = ujson.dumps(data)
            elif path == "/health":
                status = HTTP_STATUS_OK
                content_type = HTTP_CONTENT_JSON
                body = ujson.dumps({
                    "status": "UP",
                    "uptime": time.time()-boot_time,
                })
            elif path == "/status":
                status = HTTP_STATUS_OK
                content_type = HTTP_CONTENT_JSON
                body = ujson.dumps({
                    "board": board_id,
                    "einkUpdates": eink_update_count,
                    "python": os.uname().version,
                    "uptime": time.time()-boot_time,
                    "version": f"v{VERSION}",
                })
            print(f"Returning {status}")
            cl.send(f"HTTP/1.0 {status}\r\n")
            cl.send("Content-type: {content_type}\r\n")
            cl.send("\r\n")
            cl.send(body)
            cl.close()

        except OSError as e:
            cl.close()
            print("connection closed")
