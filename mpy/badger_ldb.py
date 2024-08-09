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


class Config:
    DEFAULT_CONFIG = {
        "API_URL_PREFIX": "https://www.beh.uk/api/raildata",
        "DISPLAY_UPDATE_INTERVAL_SECS": 60,
        "EINK_REFRESH_INTERVAL": 60,
        "EINK_UPDATE_SPEED": 2,
        "LED_STEP": 4,
        "LED_STEP_WAIT_MS": 100,
        "NTP_HOST": "time.cloudflare.com",
        "NTP_INTERVAL_HOURS": 4,
        "SLEEP_MODE": "1800-0800",
        "WIFI_SUCCESS_MESSAGE_SECS": 3,
    }
    
    SENSITIVE_CONFIG = [
        "WIFI_PASSWORD",
    ]
    
    def __init__(self, filename):
        self.filename = filename
        self.load()
    
    def export(self):
        redacted_data = self.data
        for key in self.SENSITIVE_CONFIG:
            if key in redacted_data:
                redacted_data[key] = "***"
        return {
            "default": self.DEFAULT_CONFIG,
            "user": redacted_data,
        }
    
    def get(self, key):
        if key in self.data:
            return self.data[key]
        elif key in self.DEFAULT_CONFIG:
            return self.DEFAULT_CONFIG[key]
        else:
            return None
    
    def load(self):
        with open(self.filename) as f:
            self.data = ujson.load(f)


config = Config(filename="config.json")


# constants
HTTP_BODY_CHUNK_SIZE = 1024
HTTP_CONTENT_HTML = "text/html"
HTTP_CONTENT_JSON = "application/json"
HTTP_CONTENT_PLAIN = "text/plain"
HTTP_STATUS_NOT_FOUND = "404 Not Found"
HTTP_STATUS_OK = "200 OK"
LED_MAX = 128
LED_MIN = 0
LED_RISING = "LED_RISING"
LED_FALLING = "LED_FALLING"
LOG_LIMIT = 100
if config.get("SLEEP_MODE"):
    SLEEP_MODE_TEXT = "SLEEP MODE"
    SLEEP_MODE_START_HOUR = int(config.get("SLEEP_MODE")[0:2])
    SLEEP_MODE_START_MINUTE = int(config.get("SLEEP_MODE")[2:4])
    SLEEP_MODE_END_HOUR = int(config.get("SLEEP_MODE")[5:7])
    SLEEP_MODE_END_MINUTE = int(config.get("SLEEP_MODE")[7:9])
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
ip_address = None
led_brightness = 0
led_direction = LED_RISING
logs = []
with open("shortened_station_names.json") as f:
    shortened_station_names = ujson.load(f)
sleep_mode_active = False
timers = {}
utc_offset = 0


def log(message):
    global logs
    print(message)
    ts = time.time()
    logs.append({ "ts":ts, "msg":message })
    if len(logs) > LOG_LIMIT:
        del logs[0]


def garbage_collect():
    initial_bytes_used = gc.mem_alloc()
    gc.collect()
    bytes_used = gc.mem_alloc()
    bytes_available = gc.mem_free()
    log(f"Successfully ran gc, freed {initial_bytes_used-bytes_used} B, {bytes_used} B used, {bytes_available} B available")
    

def breathe_led(timer):
    global led_brightness, led_direction
    if led_direction == LED_RISING:
        led_brightness += config.get("LED_STEP")
        if led_brightness >= LED_MAX:
            led_brightness = LED_MAX
            led_direction = LED_FALLING
    else:
        led_brightness -= config.get("LED_STEP")
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
    if config.get("EINK_REFRESH_INTERVAL") and eink_update_count % config.get("EINK_REFRESH_INTERVAL") == 0:
        badger.set_update_speed(badger2040.UPDATE_NORMAL)
        badger.update()
        badger.set_update_speed(config.get("EINK_UPDATE_SPEED"))
    else:
        badger.update()
    eink_update_count += 1


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
    garbage_collect()


def localtime(secs=None):
  return time.localtime((secs if secs else time.time()) + utc_offset)


def connect_to_wifi():
    global ip_address
    network.hostname(f"train-board-{board_id[:16]}")
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(config.get("WIFI_NETWORK"), config.get("WIFI_PASSWORD"))
    display_clear()
    badger.text("Data provided by the Rail Delivery Group", 4, 112, scale=1)
    badger.text("Board ID:", 4, 4, scale=1)
    badger.text(board_id, 12, 18, scale=2)
    badger.text("Connecting to " + config.get("WIFI_NETWORK"), 4, 48, scale=1)
    display_update()
    while wlan.isconnected() == False:
        time.sleep(0.1)
    ip_address = wlan.ifconfig()[0]
    log(f"Connected to {config.get('WIFI_NETWORK')}, my IP address is {ip_address}")
    badger.text("Connected, my IP address is:", 4, 60, scale=1)
    badger.text(ip_address, 12, 72, scale=2)
    display_update()
    time.sleep(config.get("WIFI_SUCCESS_MESSAGE_SECS"))
    garbage_collect()


def get_data():
    log("Fetching new data...")
    url = config.get("API_URL_PREFIX") + "/departures/v1/" + config.get("CRS_LOCATION")
    if config.get("CRS_FILTER"):
        url += "/" + config.get("CRS_FILTER")
    res = urequests.request("GET", url, headers={
        "user-agent": f"Mozilla/5.0 (compatible; uk.beh.live-train-board/{VERSION}; board/{board_id})",
        "x-board-id": board_id,
    })
    # TODO: handle potential request failure better
    return ujson.loads(res.text)


def get_status():
    return {
        "board": board_id,
        "eInkUpdates": eink_update_count,
        "python": os.uname().version,
        "uptime": time.time()-boot_time,
        "version": f"v{VERSION}",
    }


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

    def format_station_name(name):
        global shortened_station_names
        if len(name) < 20:
            return name
        else:
            if name not in shortened_station_names:
                shortened_station_names[name] = f"{name[0:17]}..."
            return shortened_station_names[name]

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
        badger.text(format_station_name(service["destination"]), 55, y, scale=2)
        badger.text(etd_text(service["etd"]), 250, y, scale=2)
        if service["cancelled"]:
            badger.text(service["cancelReason"], 0, y + 16, scale=1)
        else:
            badger.text(f"Plat. {service['platform']}", 0, y + 16, scale=1)
            detailText = f"A {service['operator']} service"
            if "length" in service and service['length'] != "?":
                detailText += f" formed of {service['length']} coaches"
            badger.text(detailText, 55, y + 16, scale=1)
    
    if config.get("SLEEP_MODE") and should_be_in_sleep_mode(
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
    badger.text(format_station_name(data["location"]), 3, 110, scale=1)
    if "filterLocation" in data:
        badger.text(format_station_name(data["filterLocation"]), 3, 120, scale=1)
    # ip address
    badger.text(ip_address, 220, 115, scale=1)
    # time
    badger.text(data["generatedAt"][TS_SLICE_START:TS_SLICE_END], 116, 107, scale=3)
    display_update()
    garbage_collect()


def run():
    global badger, boot_time, timers
    gc.enable()
    badger = badger2040.Badger2040()
    badger.set_font("bitmap8")
    badger.set_update_speed(config.get("EINK_UPDATE_SPEED"))
    connect_to_wifi()
    ntptime.host = config.get("NTP_HOST")
    ntptime.settime()
    boot_time = time.time()
    get_utc_offset(None)
    update_display(None)

    # set timers
    timers["led"] = machine.Timer(period=config.get("LED_STEP_WAIT_MS"), callback=breathe_led)
    timers["display"] = machine.Timer(period=config.get("DISPLAY_UPDATE_INTERVAL_SECS")*1000, callback=update_display)
    if config.get("NTP_INTERVAL_HOURS"):
        timers["ntp"] = machine.Timer(period=config.get("NTP_INTERVAL_HOURS")*1000*60*60, callback=set_time)
    timers["utc_offset"] = machine.Timer(period=86400*1000, callback=get_utc_offset)

    # web server
    addr = socket.getaddrinfo("0.0.0.0", 80)[0][-1] # see https://github.com/BenjaminEHowe/live-train-board/issues/6
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(1)
    log(f"Listening for HTTP requests on port {addr[1]}")
    while True:
        try:
            cl, addr = s.accept()
            request = cl.recv(1024)
            try:
                method = request.split()[0].decode()
                path = request.split()[1].decode()
            except IndexError:
                cl.close()
            status = HTTP_STATUS_NOT_FOUND
            content_type = HTTP_CONTENT_PLAIN
            body = "not found"
            if path == "/":
                status = HTTP_STATUS_OK
                content_type = HTTP_CONTENT_HTML
                with open("web_ui.html") as f:
                    body = f.read()
            elif path.startswith("/api"):
                content_type = HTTP_CONTENT_JSON
                body = {}
                if path == "/api/config":
                    status = HTTP_STATUS_OK
                    body = config.export()
                elif path == "/api/data":
                    status = HTTP_STATUS_OK
                    body = data
                elif path == "/api/data-status":
                    status = HTTP_STATUS_OK
                    body = {
                        "data": data,
                        "status": get_status(),
                    }
                elif path == "/api/health":
                    status = HTTP_STATUS_OK
                    body = {
                        "status": "UP",
                        "uptime": time.time()-boot_time,
                    }
                elif path == "/api/logs":
                    status = HTTP_STATUS_OK
                    body = logs
                elif path == "/api/status":
                    status = HTTP_STATUS_OK
                    body = get_status()
            if type(body) != str:
                body = ujson.dumps(body)
            bodyLength = len(body)
            log(f"Returning {status} for {method} request to {path} (length {bodyLength} characters)")
            cl.send(f"HTTP/1.0 {status}\r\n")
            cl.send(f"Content-type: {content_type}\r\n")
            cl.send("\r\n")
            bodySent = 0
            while bodySent < bodyLength:
                chunk = body[bodySent:bodySent+HTTP_BODY_CHUNK_SIZE]
                cl.send(chunk)
                bodySent += len(chunk)
                time.sleep(0.01)
            cl.close()

        except OSError as e:
            cl.close()
        
        finally:
            body = None
            garbage_collect()
