# Classroom CO₂ Monitor

[中文项目导读](README.zh-CN.md)

A local prototype for collecting, displaying and forecasting indoor CO₂ readings. The dashboard shows the last hour, a configurable demonstration threshold, a forecast and the freshness of the latest measurement.

## Run the demo

Requires Python 3.9 or newer. In the project directory, start the server in one terminal.

```sh
python3 app.py
```

In a second terminal, seed six hours of synthetic history and keep uploading a reading every ten seconds.

```sh
python3 simulate.py --seed
```

In a third terminal, train and evaluate the demo model.

```sh
python3 train.py --device demo
```

Open [the local dashboard](http://127.0.0.1:8000). Stop the simulator to see the dashboard mark data stale after 30 seconds. Restart it with `python3 simulate.py` to resume. PyCharm users can open the folder, select a local Python interpreter and run the same commands in the IDE terminal.

## Connect an ESP32

1. Use an ESP32 running MicroPython and an SCD40 breakout compatible with 3.3 V power and logic. Connect VCC and GND. Wire SDA and SCL to the configured GPIOs. The sample settings use GPIO21 and GPIO22 for a classic ESP32 DevKit. Check your board and breakout pinouts. See [Sensirion's SCD4x datasheet](https://sensirion.com/media/documents/E0F04247/631EF271/CD_DS_SCD40_SCD41_Datasheet_D1.pdf).
2. Connect both devices to a trusted LAN that allows clients to communicate. Start the server with `python3 app.py --host 0.0.0.0`. The server is intended for local testing and has no authentication. Keep the port off the public internet.
3. In Thonny, select the ESP32 interpreter. Copy `firmware/settings.example.py` to the board as `settings.py`, fill in Wi-Fi credentials and set `SERVER` to the computer's LAN address and port 8000. Use a firmware build with `requests` and `ntptime`, or install the corresponding MicroPython packages on the board. The ESP32 needs network access to an NTP server for time sync.
4. Copy `firmware/main.py` to the board as `main.py` and reboot. Check Thonny for the measured ppm values. Enter `room-01` in the dashboard. Disconnect and reconnect the ESP32 to observe freshness status and verify recovery. Extended outages produce gaps.
5. After collecting multiple days of readings, run `python3 train.py --device room-01`. To evaluate alerts at another demonstration threshold, pass `--threshold` in ppm. The threshold is configurable independently in the dashboard.

## Data and evaluation

`POST /readings` accepts a device ID, UTC Unix sample time in seconds, and CO₂ concentration in ppm. SQLite stores sampling and receipt times. Identical device IDs and timestamps are deduplicated. `GET /readings?device_id=demo` returns the latest hour, stale status and any available forecast.

The training script uses UTC one-minute averages. Each bucket is known at its closing boundary. The linear model estimates the change over the next ten minutes from the change over the past five minutes. The baseline carries the current value forward. The script uses a chronological split and excludes examples whose input or target crosses that split. It prints mean absolute error and counts of false and missed threshold alerts for the held-out samples.

Synthetic results document the demo workflow. Collect real readings and rerun the evaluation before drawing conclusions about forecasting performance.
