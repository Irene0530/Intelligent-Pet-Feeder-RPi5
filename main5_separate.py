#!/usr/bin/env python3
import sys
import time
import threading
import importlib
import tkinter as tk
from tkinter import ttk, messagebox

import cv2
import numpy as np
from PIL import Image, ImageTk


def _safe_import(module_name):
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None

# 逐个导入硬件/AI库，失败则返回None
GPIO = _safe_import("RPi.GPIO")
board = _safe_import("board")
adafruit_dht = _safe_import("adafruit_dht")
picamera2_mod = _safe_import("picamera2")
ultralytics_mod = _safe_import("ultralytics")
hx711_mod = _safe_import("hx711py.hx711")
# 提取库中的核心类（避免后续调用时反复判断
Picamera2 = getattr(picamera2_mod, "Picamera2", None)#getattr：安全获取模块中的类（比如picamera2_mod中的Picamera2类），不存在则返回 None
YOLO = getattr(ultralytics_mod, "YOLO", None)
HX711 = getattr(hx711_mod, "HX711", None)


class WeightMapper:
    """
    Weight mapper based on measured HX711 calibration samples.

    Mapping strategy:
    1. If the processed HX711 value falls inside a measured calibration range,
       return the known real weight directly.
    2. If the value falls between two calibration points, use piecewise linear interpolation.
    3. If the value is outside the calibrated range, use linear extrapolation from
       the nearest two calibration points, then clamp to 0-5000g.

    Note:
    The values used here are processed outputs from hx.get_weight(5), not raw ADC counts.
    Keep the same reference_unit and tare method when collecting future calibration data.
    """

    def __init__(self, calibration_rules=None, snap_tolerance=8):
        self.max_mapped_weight = 5000  # 最大映射重量 5000g = 5kg
        # 允许实测时出现少量漂移。
        # 例如 100g 标定范围是 373-377，但实际运行可能读到 371/379。
        # 在 ±snap_tolerance 内仍然直接吸附到对应的真实重量，避免显示 99g/101g。
        self.snap_tolerance = snap_tolerance

        # 实测标定规则：(读数最小值, 读数最大值, 真实重量g)
        # 如果外部没有传入单独的猫/狗标定表，则使用通用标定表作为兜底。
        self.calibration_rules = calibration_rules or [
            (25, 31, 8),
            (119, 127, 33),
            (263, 274, 73),
            (325, 336, 89),
            (366, 377, 100),
            (730, 742, 200),
            (987, 997, 268),
            (1154, 1171, 314),
            (1996, 2040, 544),
            (2369, 2440, 650),
            (2497, 2545, 678),
            (2853, 2904, 773),
        ]

        # 标准化规则：支持两种格式
        # 1) (min, max, weight)
        # 2) (min, max, weight, snap_tolerance)
        # 第4个参数用于给某些标定点单独设置更大的吸附容差。
        self.calibration_rules = [self._normalize_rule(rule) for rule in self.calibration_rules]

        # 使用每个标定范围的中心点做插值
        self.calibration_points = [
            ((min_val + max_val) / 2.0, mapped_val)
            for min_val, max_val, mapped_val, _ in self.calibration_rules
        ]
        self.calibration_points.sort(key=lambda item: item[0])

    def _normalize_rule(self, rule):
        """把标定规则统一成 (min, max, weight, tolerance) 格式。"""
        if len(rule) == 3:
            min_val, max_val, mapped_val = rule
            tolerance = self.snap_tolerance
        elif len(rule) == 4:
            min_val, max_val, mapped_val, tolerance = rule
        else:
            raise ValueError("Calibration rule must be (min, max, weight) or (min, max, weight, tolerance)")
        return float(min_val), float(max_val), int(mapped_val), float(tolerance)

    @staticmethod
    def _linear_interpolate(x0, y0, x1, y1, x):
        """线性插值/外推：已知两点(x0,y0)、(x1,y1)，估算x对应的y。"""
        if x1 == x0:
            return y0
        return y0 + (x - x0) * (y1 - y0) / (x1 - x0)

    def _estimate_from_points(self, raw_value):
        points = self.calibration_points

        # 标定点不足时无法插值
        if len(points) == 0:
            return 0
        if len(points) == 1:
            return points[0][1]

        # 低于最小标定点：用前两个点外推
        if raw_value <= points[0][0]:
            x0, y0 = points[0]
            x1, y1 = points[1]
            return self._linear_interpolate(x0, y0, x1, y1, raw_value)

        # 高于最大标定点：用最后两个点外推
        if raw_value >= points[-1][0]:
            x0, y0 = points[-2]
            x1, y1 = points[-1]
            return self._linear_interpolate(x0, y0, x1, y1, raw_value)

        # 位于两个标定点之间：分段线性插值
        for i in range(len(points) - 1):
            x0, y0 = points[i]
            x1, y1 = points[i + 1]
            if x0 <= raw_value <= x1:
                return self._linear_interpolate(x0, y0, x1, y1, raw_value)

        # 理论上不会走到这里，兜底返回最后一个标定重量
        return points[-1][1]

    def map_weight(self, raw_weight):
        if raw_weight is None:
            return None

        try:
            raw_value = float(raw_weight)
        except (TypeError, ValueError):
            return None

        # 第一步：如果落入实测范围，直接返回真实标定重量
        for min_val, max_val, mapped_val, _ in self.calibration_rules:
            if min_val <= raw_value <= max_val:
                return mapped_val

        # 第二步：如果只是在标定范围附近轻微漂移，也直接吸附到该标定重量。
        # 这样可以避免同一个砝码在猫碗/狗碗显示成 99g 和 101g 这种小误差。
        nearest_rule = None
        nearest_distance = None
        for min_val, max_val, mapped_val, tolerance in self.calibration_rules:
            if raw_value < min_val:
                distance = min_val - raw_value
            elif raw_value > max_val:
                distance = raw_value - max_val
            else:
                distance = 0

            if nearest_distance is None or distance < nearest_distance:
                nearest_distance = distance
                nearest_rule = (min_val, max_val, mapped_val, tolerance)

        if nearest_rule is not None and nearest_distance is not None:
            # 使用该标定点自己的容差；没有单独设置时使用默认容差。
            if nearest_distance <= nearest_rule[3]:
                return nearest_rule[2]

        # 第三步：不在实测范围附近时，用相邻标定点进行插值/外推
        estimated = self._estimate_from_points(raw_value)
        estimated = int(round(estimated))

        # 限制在合理范围内
        estimated = max(0, min(self.max_mapped_weight, estimated))
        return estimated


# 猫碗 raw value 普遍更大，因此猫/狗分开使用不同标定表。
# 下面的规则基于你测出来的两组数据：低读数表用于 Dog Bowl，高读数表用于 Cat Bowl。
DOG_CALIBRATION_RULES = [
    (25, 31, 8),
    (119, 127, 33),
    (263, 268, 73),
    (325, 329, 89),
    (366, 374, 100),
    (730, 735, 200),
    (987, 995, 268),
    (1154, 1162, 314),
    (1996, 2008, 544),
    (2369, 2380, 650),  # 650g 暂时使用合并范围；之后可按猫/狗实测再拆分
    (2497, 2506, 678),
    (2853, 2860, 773),
]

CAT_CALIBRATION_RULES = [
    (28, 31, 8),
    (123, 126, 33),
    (270, 274, 73),
    (331, 336, 89),
    (373, 377, 100),
    (736, 742, 200),
    (994, 997, 268),
    (1167, 1171, 314),

    # 猫碗在高重量区更容易出现漂移，所以给高重量点单独设置更大的吸附容差。
    # 格式：(min_raw, max_raw, real_weight, snap_tolerance)
    (2034, 2040, 544, 10),
    (2436, 2440, 650, 10),  # 650g 暂时使用合并范围；之后可按猫/狗实测再拆分
    (2541, 2545, 678, 10),
    (2901, 2904, 773, 10),
]


class HX711Wrapper:
    MIN_WEIGHT_THRESHOLD = 5# 最小重量阈值（小于5g视为0）

    def __init__(self, name, dout_pin, sck_pin, reference_unit=114, calibration_rules=None):
        if HX711 is None:
            raise RuntimeError("hx711py is not installed, cannot read load cell")

        self.name = name# 传感器名称（比如"Cat Bowl"）
        self.hx = HX711(dout_pin, sck_pin)# 初始化HX711
        self.hx.set_reading_format("MSB", "MSB") # 设置读取格式（高位优先）
        self.hx.set_reference_unit(reference_unit)# 校准系数（需根据硬件调整）
        self.hx.reset() # 重置传感器
        self.hx.tare()# 去皮（归零）
        self.mapper = WeightMapper(calibration_rules=calibration_rules) # 关联重量映射器

    def get_raw_weight(self):
        try:
            val = self.hx.get_weight(5)# 读取5次取平均（提高精度）
            weight = round(max(0, val), 2)# 保证非负，保留2位小数
            self.hx.power_down()
            self.hx.power_up()
            return weight
        except Exception:
            return None
    #返回结构化状态，方便后续界面展示和历史记录
    def get_mapped_weight(self):
        raw = self.get_raw_weight()
        mapped = self.mapper.map_weight(raw)
        if mapped is not None and mapped < self.MIN_WEIGHT_THRESHOLD:
            return 0
        return mapped

    def get_status(self):
        raw = self.get_raw_weight()
        mapped = self.mapper.map_weight(raw)
        if mapped is not None and mapped < self.MIN_WEIGHT_THRESHOLD:
            mapped = 0
        return {
            "name": self.name,
            "raw_weight": raw,
            "mapped_weight": mapped,
        }


class ServoFeeder:
    """Dual-servo feeder control"""

    FEED_ANGLE = 90# 出粮时舵机角度（90度打开）
    POLL_INTERVAL_SECONDS = 0.2# 重量检测间隔（0.2秒）
    MAX_FEED_SECONDS = 30# 最大出粮时间（避免卡死后一直出粮）
    PULSE_COUNT = 5# 舵机角度切换时的脉冲数（保证角度稳定）
    PULSE_WIDTH_SECONDS = 0.25# 单个脉冲宽度
    PULSE_GAP_SECONDS = 0.05 # 脉冲间隔

    def __init__(self, cat_pin=18, dog_pin=13):
        if GPIO is None:
            raise RuntimeError("RPi.GPIO is not installed, cannot control servos")

        self.cat_pin = cat_pin# 猫舵机引脚
        self.dog_pin = dog_pin# 狗舵机引脚
        self.lock = threading.Lock()# 线程锁（避免多线程同时控制舵机）
        # GPIO初始化
        GPIO.setmode(GPIO.BCM)# 使用BCM引脚编号（树莓派标准）
        GPIO.setup(self.cat_pin, GPIO.OUT)
        GPIO.setup(self.dog_pin, GPIO.OUT)
        # 初始化PWM（50Hz是舵机标准频率）
        self.cat_pwm = GPIO.PWM(self.cat_pin, 50)
        self.dog_pwm = GPIO.PWM(self.dog_pin, 50)
        self.cat_pwm.start(0)# 初始占空比0（舵机不动）
        self.dog_pwm.start(0)# 初始占空比0（舵机不动）
        self.close_all()# 初始关闭所有舵机（角度0）

    @staticmethod
    def _angle_to_duty(angle):
        return 2.5 + (angle / 180.0) * 10

    def _pulse_to_angle(self, pwm, angle):
        duty_cycle = self._angle_to_duty(angle)
         # 多次脉冲保证舵机稳定到目标角度（避免单次脉冲角度不准）
        for pulse_index in range(self.PULSE_COUNT):
            pwm.ChangeDutyCycle(duty_cycle)# 设置占空比（角度）
            time.sleep(self.PULSE_WIDTH_SECONDS)# 保持脉冲
            pwm.ChangeDutyCycle(0)# 停止脉冲
             # 最后一个脉冲后不需要间隔
            if pulse_index < self.PULSE_COUNT - 1:
                time.sleep(self.PULSE_GAP_SECONDS)

    def close_all(self):
        with self.lock:# 加锁保证线程安全
            self._pulse_to_angle(self.cat_pwm, 0)
            self._pulse_to_angle(self.dog_pwm, 0)

    def dispense_until_target(self, target, scale, target_weight, on_progress=None):
        if scale is None:
            raise RuntimeError("Scale is not initialized")
        if target_weight <= 0:
            raise ValueError("Target weight must be greater than 0")
        # 选择对应的舵机PWM
        pwm = self.cat_pwm if target == "cat" else self.dog_pwm
        last_weight = None

        with self.lock:# 加锁避免并发控制
            self._pulse_to_angle(pwm, self.FEED_ANGLE) # 第一步：打开舵机（90度）

            started_at = time.time() # 记录开始时间（防止超时）
            try: # 循环检测重量，直到达到目标或超时
                while time.time() - started_at < self.MAX_FEED_SECONDS:
                    current_weight = scale.get_mapped_weight()
                    if current_weight is not None:
                        last_weight = current_weight
                        if on_progress is not None:# 进度回调（用于界面展示）
                            on_progress(current_weight)
                        if current_weight >= target_weight: # 达到目标重量则退出循环
                            break
                    time.sleep(self.POLL_INTERVAL_SECONDS)
            finally:
                self._pulse_to_angle(pwm, 0)# 无论是否成功，最后都关闭舵机（0度）

        return last_weight# 返回最终重量

    def cleanup(self):#停止 PWM，释放 GPIO 资源
        try:
            self.cat_pwm.stop()
            self.dog_pwm.stop()
        except Exception:
            pass


class YOLOWorker(threading.Thread):
    def __init__(self, on_frame, on_status):
        super().__init__(daemon=True)# 设为守护线程（主程序退出时自动结束）
        self.on_frame = on_frame# 帧回调（传递检测后的帧和结果）
        self.on_status = on_status# 状态回调（传递检测状态）
        self.running = False# 运行标志
        self.picam2 = None# 摄像头实例
        self.model = None# YOLO模型实例

    def run(self):
        try:
            if YOLO is None:# 检查依赖库
                raise RuntimeError("ultralytics is not installed, cannot run YOLO inference")
            if Picamera2 is None:
                raise RuntimeError("picamera2 is not installed, cannot open Pi camera")
            # 加载YOLO模型
            self.on_status("Loading YOLO model...")
            self.model = YOLO("best.pt")
            # 初始化摄像头
            self.on_status("Initializing camera...")
            self.picam2 = Picamera2()
            # 配置摄像头：预览模式，主流尺寸480x360，RGB888格式
            preview_config = self.picam2.create_preview_configuration(
                main={"size": (480, 360), "format": "RGB888"}
            )
            self.picam2.configure(preview_config)
            self.picam2.start()

            self.running = True
            self.on_status("YOLO realtime inference started")
            # 循环检测
            while self.running:
                # 读取摄像头帧
                frame = self.picam2.capture_array("main")
                if frame is None:
                    continue
                # 保证帧是RGB格式（兼容不同摄像头输出）
                if len(frame.shape) == 3 and frame.shape[2] == 3:
                    rgb = frame
                else:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                results = self.model(rgb, conf=0.5, iou=0.5, verbose=False)
                plotted = results[0].plot()# 绘制检测框
                plotted = cv2.cvtColor(plotted, cv2.COLOR_BGR2RGB)# 转换为RGB格式（cv2默认BGR，PIL需要RGB）
                # 解析检测结果
                dets = []# 检测列表：[(名称, 置信度), ...]
                cat_count = 0
                dog_count = 0

                if results[0].boxes is not None:
                    boxes = results[0].boxes.cpu().numpy()# 转为numpy数组（方便处理）
                    names = self.model.names # 类别名称映射（比如0→cat，1→dog）
                    for box in boxes:
                        cls = int(box.cls[0])# 类别ID
                        conf = float(box.conf[0])# 置信度
                        name = names.get(cls, str(cls)) # 类别名称
                        dets.append((name, conf))
                        # 统计猫/狗数量（不区分大小写）
                        low = name.lower()
                        if "cat" in low:
                            cat_count += 1
                        elif "dog" in low:
                            dog_count += 1

                payload = {
                    "detections": dets,
                    "cat_count": cat_count,
                    "dog_count": dog_count,
                    "timestamp": time.strftime("%H:%M:%S"),
                }
                self.on_frame(plotted, payload) # 回调传递帧和结果
                time.sleep(0.03) # 约30fps，避免过度占用CPU

        except Exception as e:
            self.on_status(f"YOLO error: {e}")
        finally:
            try:
                if self.picam2 is not None:
                    self.picam2.stop()
                    self.picam2.close()
            except Exception:
                pass
            self.on_status("YOLO stopped")

    def stop(self):
        self.running = False


class MainApp:
    def __init__(self, root):
        self.root = root# tkinter根窗口
        self.root.title("Pet Feeder Control (Raspberry Pi 5B)")
        self.root.geometry("1180x720")# 窗口尺寸
        # 硬件实例初始化
        self.dht = None
        self.cat_scale = None
        self.dog_scale = None
        self.servo = None
        self.yolo_worker = None
        # 线程锁（保护共享数据）
        self.frame_lock = threading.Lock()
        # 共享数据（YOLO帧和结果）
        self.latest_frame = None
        self.latest_payload = None
        self.last_payload_signature = None# 结果签名（避免重复渲染）
        self.last_status_text = None # 最后状态文本（避免重复更新）
        # 重量历史相关
        self.last_cat_history_weight = None
        self.last_dog_history_weight = None
        self.weight_history_threshold = 5 # 重量变化阈值（超过5g才记录）
        # tkinter变量（绑定界面展示）
        self.temp_var = tk.StringVar(value="Temperature: -- °C")
        self.humi_var = tk.StringVar(value="Humidity: -- %")
        self.cat_weight_var = tk.StringVar(value="Cat Bowl: -- g")
        self.dog_weight_var = tk.StringVar(value="Dog Bowl: -- g")
        self.status_var = tk.StringVar(value="Status: Initializing...")
        self.cat_target_var = tk.StringVar(value="100")# 默认猫目标重量100g
        self.dog_target_var = tk.StringVar(value="100") # 默认狗目标重量100g
        # 初始化流程
        self._build_ui()# 构建界面
        self._setup_hardware()# 初始化硬件
        self._loop_sensor_update()# 启动传感器循环更新
        self._loop_video_update()# 启动视频循环更新

    def _build_ui(self):
        # 配置列权重（窗口缩放时的比例）
        self.root.columnconfigure(0, weight=2)# 左列（传感器+控制）
        self.root.columnconfigure(1, weight=4)# 中列（视频流）
        self.root.columnconfigure(2, weight=3)# 右列（检测结果+历史）
        self.root.rowconfigure(0, weight=1)# 行权重
        # 创建三列框架
        left = ttk.Frame(self.root, padding=10)
        center = ttk.Frame(self.root, padding=10)
        right = ttk.Frame(self.root, padding=10)
        # 布局三列
        left.grid(row=0, column=0, sticky="nsew")# 上下左右填满
        center.grid(row=0, column=1, sticky="nsew")
        right.grid(row=0, column=2, sticky="nsew")
        # 左列：环境温湿度
        env_group = ttk.LabelFrame(left, text="Environment", padding=10)
        env_group.pack(fill="x", pady=6)
        ttk.Label(env_group, textvariable=self.temp_var, font=("Arial", 12)).pack(anchor="w", pady=3)
        ttk.Label(env_group, textvariable=self.humi_var, font=("Arial", 12)).pack(anchor="w", pady=3)
        # 左列：食物重量
        food_group = ttk.LabelFrame(left, text="Mapped Food Weight", padding=10)
        food_group.pack(fill="x", pady=6)
        ttk.Label(food_group, textvariable=self.cat_weight_var, font=("Arial", 12)).pack(anchor="w", pady=3)
        ttk.Label(food_group, textvariable=self.dog_weight_var, font=("Arial", 12)).pack(anchor="w", pady=3)
        # 左列：舵机喂食控制
        servo_group = ttk.LabelFrame(left, text="Servo Feeding", padding=10)
        servo_group.pack(fill="x", pady=6)
        # 猫喂食行
        cat_row = ttk.Frame(servo_group)
        cat_row.pack(fill="x", pady=4)
        # 狗喂食行
        dog_row = ttk.Frame(servo_group)
        dog_row.pack(fill="x", pady=4)
        # 提示行
        tips_row = ttk.Frame(servo_group)
        tips_row.pack(fill="x", pady=(2, 0))

        ttk.Label(cat_row, text="Cat target (g):", font=("Arial", 11)).pack(side="left", padx=(0, 6))
        ttk.Entry(cat_row, textvariable=self.cat_target_var, width=10).pack(side="left", padx=(0, 6))
        # 绑定异步喂食函数（lambda传递参数"cat"）
        ttk.Button(cat_row, text="Start Cat Feeding", command=lambda: self.feed_async("cat")).pack(side="left")

        ttk.Label(dog_row, text="Dog target (g):", font=("Arial", 11)).pack(side="left", padx=(0, 6))
        ttk.Entry(dog_row, textvariable=self.dog_target_var, width=10).pack(side="left", padx=(0, 6))
        ttk.Button(dog_row, text="Start Dog Feeding", command=lambda: self.feed_async("dog")).pack(side="left")
        # 提示行
        ttk.Label(
            tips_row,
            text="Servo opens until bowl weight reaches the target, then returns to 0°.",
            wraplength=300,
        ).pack(anchor="w")
        # 左列：状态提示（蓝色文字）
        ttk.Label(left, textvariable=self.status_var, foreground="blue", wraplength=300).pack(anchor="w", pady=8)
        # 中列：YOLO视频流
        video_group = ttk.LabelFrame(center, text="YOLO Live View", padding=8)
        video_group.pack(fill="both", expand=True)
        # 视频容器（固定尺寸480x360）
        self.video_container = tk.Frame(video_group, width=480, height=360, bg="black")
        self.video_container.pack(anchor="center", padx=8, pady=8)
        self.video_container.pack_propagate(False)# 禁止容器随内容缩放

        # 视频标签（初始显示提示文字）
        self.video_label = tk.Label(self.video_container, text="Waiting for stream...", bg="black", fg="white")
        self.video_label.pack(fill="both", expand=True)
        # 右列：YOLO检测结果
        infer_group = ttk.LabelFrame(right, text="YOLO Inference", padding=8)
        infer_group.pack(fill="both", expand=True, pady=(0, 6))

        self.infer_text = tk.Text(infer_group, width=40)
        self.infer_text.pack(fill="both", expand=True)
         # 右列：重量历史
        history_group = ttk.LabelFrame(right, text="Weight History", padding=8)
        history_group.pack(fill="both", expand=True)

        self.history_text = tk.Text(history_group, width=40, height=12)
        self.history_text.pack(fill="both", expand=True)
        self.history_text.insert(tk.END, "Timestamped weight changes will appear here.\n")

    def _setup_hardware(self):
        try:# 初始化DHT11
            if adafruit_dht is None or board is None:
                raise RuntimeError("adafruit_dht/board not installed")
            self.dht = adafruit_dht.DHT11(board.D4)# D4引脚
        except Exception as e:
            self._set_status(f"DHT11 init failed ({e})")

        try:# 初始化称重传感器（猫：20/21引脚，狗：10/11引脚）
            self.cat_scale = HX711Wrapper(
                "Cat Bowl",
                dout_pin=20,
                sck_pin=21,
                calibration_rules=CAT_CALIBRATION_RULES,
            )
            self.dog_scale = HX711Wrapper(
                "Dog Bowl",
                dout_pin=10,
                sck_pin=11,
                calibration_rules=DOG_CALIBRATION_RULES,
            )
        except Exception as e:
            self._set_status(f"HX711 init failed ({e})")

        try:# 初始化舵机（猫：18引脚，狗：13引脚）
            self.servo = ServoFeeder(cat_pin=18, dog_pin=13)
        except Exception as e:
            self._set_status(f"Servo init failed ({e})")
        # 启动YOLO线程
        self.yolo_worker = YOLOWorker(on_frame=self._on_yolo_frame, on_status=self._set_status)
        self.yolo_worker.start()

    def _set_status(self, text):
        if text != self.last_status_text:# 避免重复更新
            self.last_status_text = text
            print(f"[STATUS] {text}", flush=True)
        #用after(0)保证在GUI主线程更新（避免线程安全问题）
        self.root.after(0, lambda: self.status_var.set(f"Status: {text}"))

    def _loop_sensor_update(self):# 1. 更新DHT11温湿度
        # DHT11
        try:
            if self.dht is not None:
                temp = self.dht.temperature
                humi = self.dht.humidity
                if temp is not None:
                    self.temp_var.set(f"Temperature: {temp:.1f} °C")
                if humi is not None:
                    self.humi_var.set(f"Humidity: {humi:.1f} %")
        except Exception:
            pass

        # 2. 更新称重传感器重量
        try:
            cat_status = None
            dog_status = None

            if self.cat_scale is not None:
                cat_status = self.cat_scale.get_status()
                cat_weight = cat_status["mapped_weight"]
                self.cat_weight_var.set(f"Cat Bowl: {cat_weight if cat_weight is not None else '--'} g")
            if self.dog_scale is not None:
                dog_status = self.dog_scale.get_status()
                dog_weight = dog_status["mapped_weight"]
                self.dog_weight_var.set(f"Dog Bowl: {dog_weight if dog_weight is not None else '--'} g")
            # 3. 记录重量历史（仅当变化超过阈值时）
            self._append_weight_history_if_changed(cat_status, dog_status)
        except Exception:
            pass
         # 4. 2秒后再次执行（非阻塞循环）
        self.root.after(2000, self._loop_sensor_update)

    def _on_yolo_frame(self, frame_rgb, payload):
        with self.frame_lock:# 加锁保护共享数据
            self.latest_frame = frame_rgb
            self.latest_payload = payload

    def _loop_video_update(self):
        frame = None
        payload = None
        with self.frame_lock:# 加锁读取共享数据（避免YOLO线程写入时读取）
            if self.latest_frame is not None:
                frame = self.latest_frame.copy() # 拷贝避免原数据被修改
            if self.latest_payload is not None:
                payload = dict(self.latest_payload) # 拷贝字典
        # 1. 更新视频帧
        if frame is not None:
            h, w = frame.shape[:2]
            target_w, target_h = 480, 360
            # 计算缩放比例（保持宽高比）
            scale = min(target_w / w, target_h / h)
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            resized = cv2.resize(frame, (new_w, new_h))# 缩放帧
            # 转换为PIL图像（tkinter支持的格式）
            img = Image.fromarray(resized)
            tk_img = ImageTk.PhotoImage(img)
            # 更新视频标签（必须保留tk_img引用，否则会被GC回收）
            self.video_label.configure(image=tk_img, text="")
            self.video_label.image = tk_img
        # 2. 更新检测结果（仅当结果变化时）
        if payload is not None:# 生成结果签名（避免重复渲染）
            signature = (
                payload.get("timestamp"),
                payload.get("cat_count"),
                payload.get("dog_count"),
                tuple(payload.get("detections", [])),
            )
            if signature != self.last_payload_signature:
                self.last_payload_signature = signature
                self._render_infer(payload)
        # 3. 50ms后再次执行
        self.root.after(50, self._loop_video_update)

    def _render_infer(self, payload):
        ts = payload.get("timestamp", "--:--:--")
        cat_count = payload.get("cat_count", 0)
        dog_count = payload.get("dog_count", 0)
        detections = payload.get("detections", [])
        # 构造显示文本
        lines = [
            f"[{ts}] Inference Result",
            f"Cat: {cat_count}  Dog: {dog_count}",
            "-" * 28,
        ]
        for idx, (name, conf) in enumerate(detections, 1):
            lines.append(f"{idx}. {name} ({conf:.2f})")
         # 更新文本框
        self.infer_text.delete("1.0", tk.END)
        self.infer_text.insert(tk.END, "\n".join(lines))

    def _append_weight_history_if_changed(self, cat_status, dog_status):
        changed = False
        parts = []
        # 获取当前重量
        cat_weight = cat_status["mapped_weight"] if cat_status is not None else None
        dog_weight = dog_status["mapped_weight"] if dog_status is not None else None
        # 检查猫重量是否变化（超过阈值）
        if self._is_weight_history_change(cat_weight, self.last_cat_history_weight):
            self.last_cat_history_weight = cat_weight
            cat_raw = cat_status["raw_weight"] if cat_status is not None else None
            parts.append(
                f"Cat raw={cat_raw if cat_raw is not None else '--'} mapped={cat_weight if cat_weight is not None else '--'}g"
            )
            changed = True
         # 检查狗重量是否变化（超过阈值）
        if self._is_weight_history_change(dog_weight, self.last_dog_history_weight):
            self.last_dog_history_weight = dog_weight
            dog_raw = dog_status["raw_weight"] if dog_status is not None else None
            parts.append(
                f"Dog raw={dog_raw if dog_raw is not None else '--'} mapped={dog_weight if dog_weight is not None else '--'}g"
            )
            changed = True
        # 只有变化时才记录
        if not changed:
            return
        # 构造历史行并插入文本框
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] " + " | ".join(parts) + "\n"
        print(line, end="", flush=True)
        self.history_text.insert(tk.END, line)
        self.history_text.see(tk.END)# 滚动到最后一行

    def _is_weight_history_change(self, current_weight, last_weight):
        if current_weight is None or last_weight is None:
            return current_weight != last_weight # 有一个为空则视为变化
        return abs(current_weight - last_weight) > self.weight_history_threshold # 超过阈值视为变化

    def feed_async(self, target):# 检查舵机是否初始化
        if self.servo is None:
            messagebox.showwarning("Notice", "Servo is not initialized")
            return
        # 选择对应的传感器和目标变量
        scale = self.cat_scale if target == "cat" else self.dog_scale
        target_var = self.cat_target_var if target == "cat" else self.dog_target_var
        # 检查传感器是否初始化
        if scale is None:
            messagebox.showwarning("Notice", "Scale is not initialized")
            return
        # 解析目标重量
        try:
            target_weight = int(float(target_var.get().strip()))
        except ValueError:
            messagebox.showwarning("Notice", "Please enter a valid target weight")
            return
        # 检查目标重量是否合法
        if target_weight <= 0:
            messagebox.showwarning("Notice", "Target weight must be greater than 0")
            return
        # 定义喂食任务（新线程执行）
        def _job():
            try:
                name = "Cat Bowl" if target == "cat" else "Dog Bowl"
                current_weight = scale.get_mapped_weight()
                # 提前检查是否已达到目标
                if current_weight is not None and current_weight >= target_weight:
                    self._set_status(f"{name} is already at {current_weight}g, target reached")
                    return
                # 开始喂食
                self._set_status(f"Feeding {name} to target {target_weight}g")
                final_weight = self.servo.dispense_until_target(
                    target,
                    scale,
                    target_weight,
                    # 进度回调：实时更新状态
                    on_progress=lambda weight: self._set_status(
                        f"Feeding {name}: {weight}g / {target_weight}g"
                    ),
                )
                # 喂食结束后更新状态
                if final_weight is None:
                    self._set_status(f"Feeding stopped: unable to read {name} weight")
                elif final_weight >= target_weight:
                    self._set_status(f"Feeding completed: {name} reached {final_weight}g")
                else:
                    self._set_status(
                        f"Feeding stopped at {final_weight}g before target {target_weight}g"
                    )
            except Exception as e:
                self._set_status(f"Feeding failed: {e}")
        # 启动新线程执行喂食任务（守护线程）
        threading.Thread(target=_job, daemon=True).start()

    def close(self):
        try:# 停止YOLO线程
            if self.yolo_worker is not None:
                self.yolo_worker.stop()
                self.yolo_worker.join(timeout=2)
        except Exception:
            pass

        try:# 关闭DHT11
            if self.dht is not None:
                self.dht.exit()
        except Exception:
            pass

        try:# 清理舵机
            if self.servo is not None:
                self.servo.cleanup()
        except Exception:
            pass

        try:# 清理GPIO
            if GPIO is not None:
                GPIO.cleanup()
        except Exception:
            pass


def main():
    root = tk.Tk()#创建tkinter根窗口
    app = MainApp(root)# 初始化主程序

    # 窗口关闭回调（保证资源清理）
    def on_close():
        app.close()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)# 绑定关闭事件，点击窗口关闭按钮时，先清理资源再销毁窗口
    root.mainloop()# 启动GUI主循环


if __name__ == "__main__":
    main()
