"""ESP32 MicroPython firmware for the SCD40."""
import time

from machine import I2C, Pin
import network
import ntptime
import requests

from settings import DEVICE_ID, SCL_PIN, SDA_PIN, SERVER, WIFI_PASSWORD, WIFI_SSID

ADDRESS = 0x62
# 将不同 MicroPython 版本的时间基准统一为 Unix 时间。
EPOCH_OFFSET = 946684800 if time.gmtime(0)[0] == 2000 else 0


def crc8(word):
    crc = 0xFF
    for byte in word:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def read_words(bus, command, count):
    bus.writeto(ADDRESS, command)
    time.sleep_ms(2)
    data = bus.readfrom(ADDRESS, count * 3)
    words = []
    # 传感器每返回两个数据字节，紧跟一个 CRC 校验字节。
    for index in range(0, len(data), 3):
        word = data[index:index + 2]
        if crc8(word) != data[index + 2]:
            raise ValueError("SCD40 CRC mismatch")
        words.append((word[0] << 8) | word[1])
    return words


def connect(wlan):
    if wlan.isconnected():
        return
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    for _ in range(20):
        if wlan.isconnected():
            return
        time.sleep(1)
    wlan.disconnect()
    raise OSError("Wi-Fi connection timed out")


def upload(payload):
    # 重试时复用相同采样时间，由后端避免重复入库。
    for attempt in range(2):
        try:
            response = requests.post(SERVER.rstrip("/") + "/readings", json=payload, timeout=5)
            try:
                if response.status_code in (200, 201):
                    return
                print("Server rejected sample:", response.status_code)
                return
            finally:
                response.close()
        except OSError as error:
            print("Upload failed:", error)
            if attempt == 0:
                time.sleep(1)


def main():
    bus = I2C(0, sda=Pin(SDA_PIN), scl=Pin(SCL_PIN), freq=100000)
    if ADDRESS not in bus.scan():
        raise OSError("SCD40 not found at 0x62")
    try:
        bus.writeto(ADDRESS, b"\x3f\x86")  # Stop measurement after a soft reset.
    except OSError:
        pass
    time.sleep_ms(500)
    bus.writeto(ADDRESS, b"\x21\xb1")
    time.sleep(5)
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    synced = False
    while True:
        try:
            connect(wlan)
            # 对时成功后再上传，服务器才能正确判断读数时间。
            if not synced:
                ntptime.settime()
                synced = True
            # 先查询是否有新数据，再读取 CO₂、温度和湿度字。
            ready, = read_words(bus, b"\xe4\xb8", 1)
            if ready & 0x07FF:
                ppm, raw_temperature, raw_humidity = read_words(bus, b"\xec\x05", 3)
                if ppm:
                    # 按 SCD4x 数据格式转换摄氏温度与相对湿度。
                    temperature = -45 + 175 * raw_temperature / 65535
                    humidity = 100 * raw_humidity / 65535
                    print("CO2 ppm:", ppm, "Temperature C:", round(temperature, 1),
                          "Humidity %:", round(humidity, 1))
                    upload({"device_id": DEVICE_ID, "sampled_at": time.time() + EPOCH_OFFSET,
                            "co2_ppm": ppm,
                            "temperature_c": round(temperature, 2),
                            "humidity_pct": round(humidity, 2)})
        except (OSError, ValueError) as error:
            print("Sample failed:", error)
        time.sleep(10)


main()
