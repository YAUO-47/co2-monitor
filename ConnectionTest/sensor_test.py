from machine import I2C, Pin
import time

bus = I2C(0, sda=Pin(21), scl=Pin(22), freq=100000)
ADDRESS = 0x62


def read_words(command, count):
    """发送命令，读取并校验传感器返回的数据。"""
    bus.writeto(ADDRESS, command)
    time.sleep_ms(2)
    data = bus.readfrom(ADDRESS, count * 3)
    words = []

    for index in range(0, len(data), 3):
        word = data[index:index + 2]
        crc = 0xFF

        for byte in word:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = ((crc << 1) ^ 0x31) & 0xFF
                else:
                    crc = (crc << 1) & 0xFF

        if crc != data[index + 2]:
            raise ValueError("传感器数据校验失败")

        words.append((word[0] << 8) | word[1])

    return words


# 停止可能已经运行的测量，再重新启动。
bus.writeto(ADDRESS, b"\x3f\x86")
time.sleep_ms(500)
bus.writeto(ADDRESS, b"\x21\xb1")

print("开始测量，等待首条数据……")
time.sleep(5)

while True:
    ready = read_words(b"\xe4\xb8", 1)[0]

    if ready & 0x07FF:
        co2, raw_temperature, raw_humidity = read_words(b"\xec\x05", 3)
        temperature = -45 + 175 * raw_temperature / 65535
        humidity = 100 * raw_humidity / 65535

        print(
            "CO₂: {} ppm | 温度: {:.1f} °C | 湿度: {:.1f}%".format(
                co2, temperature, humidity
            )
        )

    time.sleep(5)