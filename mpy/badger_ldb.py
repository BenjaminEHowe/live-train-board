import badger2040
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


def breathe_led(timer):
    global badger, led_brightness, led_direction
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


def get_data():
    url = config["API_URL_PREFIX"] + "/departures/v1/" + config["CRS_LOCATION"]
    if config["CRS_FILTER"]:
        url += "/" + config["CRS_FILTER"]
    res = urequests.request("GET", url, headers={
        "user-agent": f"Mozilla/5.0 (compatible; uk.beh.live-train-board/{VERSION}; board/{board_id})",
    })
    # TODO: handle potential request failure better
    return ujson.loads(res.text)


def set_time(timer):
    ntptime.settime()


def update_display(timer):
    global badger, data, eink_update_count
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
    
    data = get_data()
    badger.set_pen(PEN_WHITE)
    badger.clear()
    badger.set_pen(PEN_BLACK)
    # services
    for i in range(len(data["services"][:4])):
        display_service(26 * i, data["services"][i])
    # locations
    badger.text(data['location'], 3, 110 , scale=1)
    if "filterLocation" in data:
        badger.text(data['filterLocation'], 3, 120 , scale=1)
    # time
    badger.text(data["generatedAt"][TS_SLICE_START:TS_SLICE_END], 116, 107 , scale=3)
    if config["EINK_REFRESH_INTERVAL"] and eink_update_count % config["EINK_REFRESH_INTERVAL"] == 0:
        badger.set_update_speed(badger2040.UPDATE_NORMAL)
        badger.update()
        badger.set_update_speed(config["EINK_UPDATE_SPEED"])
    else:
        badger.update()
    eink_update_count += 1


badger = badger2040.Badger2040()
network.hostname(f"train-board-{board_id[:16]}")
badger.connect()
ntptime.host = config["NTP_HOST"]
ntptime.settime()
boot_time = time.time()
badger.set_font("bitmap8")

# set timers
machine.Timer(period=config["LED_STEP_WAIT_MS"], callback=breathe_led)
update_display(None)
machine.Timer(period=config["DISPLAY_UPDATE_INTERVAL_SECS"]*1000, callback=update_display)
if config["NTP_INTERVAL_HOURS"]:
    machine.Timer(period=config["NTP_INTERVAL_HOURS"]*1000*60*60, callback=set_time)

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
