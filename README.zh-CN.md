# 教室 CO₂ 监测与预测

## 从哪开始读

沿着一条读数走一遍。先看 simulate.py 的 send() 发送了哪些字段，再看 app.py 的 do_POST() 如何校验和保存这条读数。然后看 do_GET() 如何从 SQLite 读取数据，以及 dashboard.html 的 refresh() 如何把返回内容显示为数字和曲线。最后读 train.py，理解预测的系数是怎么得来的。

| 文件 | 作用 |
| --- | --- |
| app.py | 电脑端入口。提供网页、上传和查询接口，保存读数并计算实时预测 |
| simulate.py | 生成合成历史，之后每 10 秒走 HTTP 接口上传一条模拟读数 |
| dashboard.html | 浏览器端。每 5 秒刷新，显示最近一小时、当前读数、演示阈值和预测 |
| train.py | 训练每台设备的线性模型，按时间划分训练和测试数据并输出评估指标 |
| firmware/main.py | ESP32 的 MicroPython 程序，通过 I²C 读 SCD40，通过 Wi-Fi 上传 |
| firmware/settings.example.py | ESP32 配置模板，包含网络、服务器地址、设备编号和引脚 |
| readings.sqlite3 | 服务启动时自动创建的读数数据库 |
| models/ | 运行训练脚本后创建，按设备保存参数和评估结果 |
| .idea/、.venv/ | IDE 配置和 Python 虚拟环境 |

模拟器和 ESP32 都调用 POST /readings，每条读数包含 device_id、sampled_at 和 co2_ppm。浏览器调用 GET /readings。换成实体设备时，浏览器和后端仍使用同一套接口。

## 先跑模拟版

在 PyCharm 里从项目目录各开一个终端，依次执行以下命令。上传模拟历史完成后再训练，保持模拟器运行，网页才会接到新读数。

1. `python3 app.py`
2. `python3 simulate.py --seed`
3. `python3 train.py --device demo`

打开浏览器的 http://127.0.0.1:8000。默认设备 demo 的曲线来自模拟器。停掉模拟器超过 30 秒，页面应显示数据过期并暂停预测。

## 真机需要准备什么

电脑端只需要 Python 3.9 或更新版本。SQLite 和 HTTP 服务使用 Python 标准库。之前尝试过的 FastAPI、Streamlit 和 scikit-learn 属于原先规划。

硬件需要 ESP32、支持 3.3 V 供电和逻辑的 SCD40 模块、USB 数据线和接线。拿到开发板后，安装 Thonny 或使用已有的刷写工具，按板型刷 MicroPython。ESP32 上应可以 import requests 和 import ntptime，缺少哪个就在板上补哪个。

1. 按模块和板子的丝印核对电源、GND、SDA、SCL。示例配置使用经典 ESP32 DevKit 的 GPIO21 和 GPIO22。
2. 在电脑上运行 `python3 app.py --host 0.0.0.0`，使用可信且允许设备互访的局域网。
3. 将配置模板复制到板上，命名为 settings.py。填写自己的 Wi-Fi 和电脑局域网地址，保留设备编号 room-01 或自行指定。将固件复制到板上的 main.py。ESP32 需能访问 NTP 服务完成对时。
4. 重启板子，确认串口出现 CO2 ppm。网页切换到 room-01，确认读数持续更新，再断开并恢复 Wi-Fi 验证过期状态和恢复。
5. 连续采集多个时段的真实数据后，运行 `python3 train.py --device room-01`。预测还需要最近连续的分钟读数，以及一条新鲜的采样。

## 预测具体怎么算

先把 CO₂ 读数聚合成每分钟的均值。取最近一个已结束分钟的均值 C，再减去五分钟前的均值，得到变化量 Δ5。模型从历史数据拟合截距 b 和斜率 w，使 b + w × Δ5 尽量接近随后十分钟的实际变化。网页显示的预测是 C + b + w × Δ5，最低为 0 ppm。

举例，最近一分钟为 800 ppm，五分钟前为 750 ppm，则 Δ5 是 50 ppm。假设训练得到 b = 10、w = 1.4，预测为 880 ppm。例中的参数只用于说明公式。设备自己的参数保存在 models/设备编号.json。

训练时用较早的数据拟合，用较晚的数据比较模型与持续性基线。基线直接预测十分钟后仍为 800 ppm。看平均绝对误差（MAE，单位 ppm），也看演示阈值的误报、漏报次数。温湿度、开窗和人数都没有作为当前模型的输入，突发开窗或人群进出时误差可能较大。用 demo 跑出的结果只用于检查流程，真机表现需要在保留的实测数据上评估。
