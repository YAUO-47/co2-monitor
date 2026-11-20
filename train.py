"""Fit a linear CO₂ forecast and evaluate it on later samples."""
import argparse
from collections import defaultdict
import json
from statistics import mean

from app import DEVICE, ROOT, readings


def minute_means(rows, before=None):
    # Unix 时间戳除以 60 得到分钟编号，同一分钟的多个读数取均值。
    buckets = defaultdict(list)
    for timestamp, ppm in rows:
        minute = timestamp // 60
        if before is None or minute < before:
            buckets[minute].append(ppm)
    return {minute: mean(values) for minute, values in buckets.items()}


def features(series, minute):
    # 当前分钟到五分钟前必须连续有数据，缺失的读数不插补。
    if all(moment in series for moment in range(minute - 5, minute + 1)):
        return series[minute], series[minute] - series[minute - 5]
    return None


def train(device, threshold):
    series = minute_means(readings(device, 0))
    if not series:
        raise ValueError("No readings for this device")
    series.pop(max(series))  # The latest bucket may still be incomplete.
    # 按时间切分，保证训练标签和测试特征各自在其对应的时段内。
    cutoff = sorted(series)[int(len(series) * 0.8)] if series else 0
    training, testing = [], []
    for minute in sorted(series):
        inputs = features(series, minute)
        if inputs is None or minute + 10 not in series:
            continue
        current, change = inputs
        example = (current, change, series[minute + 10])
        if minute + 10 < cutoff:
            training.append(example)
        elif minute - 5 >= cutoff:
            testing.append(example)
    if len(training) < 10 or len(testing) < 5:
        raise ValueError("Need more continuous data. Seed the demo or keep collecting.")
    # 最小二乘拟合：输入是过去五分钟变化量，目标是随后十分钟变化量。
    x_mean = mean(change for _, change, _ in training)
    y_mean = mean(target - current for current, _, target in training)
    variance = sum((change - x_mean)**2 for _, change, _ in training)
    covariance = sum((change - x_mean) * (target - current - y_mean)
                     for current, change, target in training)
    slope = covariance / variance if variance else 0.0
    intercept = y_mean - slope * x_mean
    # 持续性基线假设未来浓度等于当前值，作为线性模型的对照。
    metrics = {}
    for name in ("baseline", "linear"):
        pairs = [
            (current if name == "baseline" else max(0, current + intercept + slope * change), target)
            for current, change, target in testing
        ]
        metrics[name] = {
            "mae_ppm": round(mean(abs(prediction - actual) for prediction, actual in pairs), 2),
            "false_alerts": sum(prediction >= threshold > actual for prediction, actual in pairs),
            "missed_alerts": sum(actual >= threshold > prediction for prediction, actual in pairs),
        }
    model = {"slope": slope, "intercept": intercept, "train_samples": len(training),
             "test_samples": len(testing), "test_start_utc_minute": cutoff,
             "threshold_ppm": threshold, "metrics": metrics}
    folder = ROOT / "models"
    folder.mkdir(exist_ok=True)
    path = folder / (device + ".json")
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(model, indent=2))
    temporary.replace(path)
    return model


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="demo")
    parser.add_argument("--threshold", type=int, default=1000)
    args = parser.parse_args()
    if not DEVICE.fullmatch(args.device):
        parser.error("Invalid device ID")
    try:
        print(json.dumps(train(args.device, args.threshold), indent=2))
    except ValueError as error:
        parser.error(str(error))
