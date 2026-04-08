#!/usr/bin/env python3
import sys
import time
import threading
import importlib
from itertools import combinations

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


GPIO = _safe_import("RPi.GPIO")
board = _safe_import("board")
adafruit_dht = _safe_import("adafruit_dht")
picamera2_mod = _safe_import("picamera2")
ultralytics_mod = _safe_import("ultralytics")
hx711_mod = _safe_import("hx711py.hx711")

Picamera2 = getattr(picamera2_mod, "Picamera2", None)
YOLO = getattr(ultralytics_mod, "YOLO", None)
HX711 = getattr(hx711_mod, "HX711", None)


class WeightMapper:
    """Weight mapper: interval-first, linear fallback, max 5kg"""

    def __init__(self):
        self.max_mapped_weight = 5000
        self.base_rules = [
            (230, 250, 65),
            (350, 390, 100),
            (730, 750, 200),
            (985, 1010, 265),
        ]
        self.mapping_rules = self._build_combined_rules()
        self.linear_a, self.linear_b = self._fit_linear_model()

    def _build_combined_rules(self):
        rules = []
        for r in range(1, len(self.base_rules) + 1):
            for combo in combinations(self.base_rules, r):
                min_sum = sum(item[0] for item in combo)
                max_sum = sum(item[1] for item in combo)
                mapped_sum = sum(item[2] for item in combo)
                rules.append((min_sum, max_sum, mapped_sum))

        deduped = list(dict.fromkeys(rules))
        deduped.sort(key=lambda x: ((x[1] - x[0]), x[0]))
        return deduped

    def _fit_linear_model(self):
        x_values = [((min_val + max_val) / 2) for min_val, max_val, _ in self.base_rules]
        y_values = [mapped for _, _, mapped in self.base_rules]

        n = len(x_values)
        if n < 2:
            return 0.0, 0.0

        sum_x = sum(x_values)
        sum_y = sum(y_values)
        sum_xx = sum(x * x for x in x_values)
        sum_xy = sum(x * y for x, y in zip(x_values, y_values))

        denominator = n * sum_xx - sum_x * sum_x
        if denominator == 0:
            return 0.0, y_values[0]

        a = (n * sum_xy - sum_x * sum_y) / denominator
        b = (sum_y - a * sum_x) / n
        return a, b

    def map_weight(self, raw_weight):
        if raw_weight is None:
            return None

        for min_val, max_val, mapped_val in self.mapping_rules:
            if min_val <= raw_weight <= max_val:
                return mapped_val

        estimated = self.linear_a * raw_weight + self.linear_b
        estimated = int(round(estimated))
        estimated = max(0, min(self.max_mapped_weight, estimated))
        return estimated


class HX711Wrapper:
    MIN_WEIGHT_THRESHOLD = 5

    def __init__(self, name, dout_pin, sck_pin, reference_unit=114):
        if HX711 is None:
            raise RuntimeError("hx711py is not installed, cannot read load cell")

        self.name = name
        self.hx = HX711(dout_pin, sck_pin)
        self.hx.set_reading_format("MSB", "MSB")
        self.hx.set_reference_unit(reference_unit)
        self.hx.reset()
        self.hx.tare()
        self.mapper = WeightMapper()

    def get_raw_weight(self):
        try:
            val = self.hx.get_weight(5)
            weight = round(max(0, val), 2)
            self.hx.power_down()
            self.hx.power_up()
            return weight
        except Exception:
            return None

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

    FEED_ANGLE = 90
    POLL_INTERVAL_SECONDS = 0.2
    MAX_FEED_SECONDS = 30
    PULSE_COUNT = 5
    PULSE_WIDTH_SECONDS = 0.25
    PULSE_GAP_SECONDS = 0.05

    def __init__(self, cat_pin=18, dog_pin=13):
        if GPIO is None:
            raise RuntimeError("RPi.GPIO is not installed, cannot control servos")

        self.cat_pin = cat_pin
        self.dog_pin = dog_pin
        self.lock = threading.Lock()

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.cat_pin, GPIO.OUT)
        GPIO.setup(self.dog_pin, GPIO.OUT)

        self.cat_pwm = GPIO.PWM(self.cat_pin, 50)
        self.dog_pwm = GPIO.PWM(self.dog_pin, 50)
        self.cat_pwm.start(0)
        self.dog_pwm.start(0)
        self.close_all()

    @staticmethod
    def _angle_to_duty(angle):
        return 2.5 + (angle / 180.0) * 10

    def _pulse_to_angle(self, pwm, angle):
        duty_cycle = self._angle_to_duty(angle)
        for pulse_index in range(self.PULSE_COUNT):
            pwm.ChangeDutyCycle(duty_cycle)
            time.sleep(self.PULSE_WIDTH_SECONDS)
            pwm.ChangeDutyCycle(0)
            if pulse_index < self.PULSE_COUNT - 1:
                time.sleep(self.PULSE_GAP_SECONDS)

    def close_all(self):
        with self.lock:
            self._pulse_to_angle(self.cat_pwm, 0)
            self._pulse_to_angle(self.dog_pwm, 0)

    def dispense_until_target(self, target, scale, target_weight, on_progress=None):
        if scale is None:
            raise RuntimeError("Scale is not initialized")
        if target_weight <= 0:
            raise ValueError("Target weight must be greater than 0")

        pwm = self.cat_pwm if target == "cat" else self.dog_pwm
        last_weight = None

        with self.lock:
            self._pulse_to_angle(pwm, self.FEED_ANGLE)

            started_at = time.time()
            try:
                while time.time() - started_at < self.MAX_FEED_SECONDS:
                    current_weight = scale.get_mapped_weight()
                    if current_weight is not None:
                        last_weight = current_weight
                        if on_progress is not None:
                            on_progress(current_weight)
                        if current_weight >= target_weight:
                            break
                    time.sleep(self.POLL_INTERVAL_SECONDS)
            finally:
                self._pulse_to_angle(pwm, 0)

        return last_weight

    def cleanup(self):
        try:
            self.cat_pwm.stop()
            self.dog_pwm.stop()
        except Exception:
            pass


class YOLOWorker(threading.Thread):
    def __init__(self, on_frame, on_status):
        super().__init__(daemon=True)
        self.on_frame = on_frame
        self.on_status = on_status
        self.running = False
        self.picam2 = None
        self.model = None

    def run(self):
        try:
            if YOLO is None:
                raise RuntimeError("ultralytics is not installed, cannot run YOLO inference")
            if Picamera2 is None:
                raise RuntimeError("picamera2 is not installed, cannot open Pi camera")

            self.on_status("Loading YOLO model...")
            self.model = YOLO("best.pt")

            self.on_status("Initializing camera...")
            self.picam2 = Picamera2()
            preview_config = self.picam2.create_preview_configuration(
                main={"size": (480, 360), "format": "RGB888"}
            )
            self.picam2.configure(preview_config)
            self.picam2.start()

            self.running = True
            self.on_status("YOLO realtime inference started")

            while self.running:
                frame = self.picam2.capture_array("main")
                if frame is None:
                    continue

                if len(frame.shape) == 3 and frame.shape[2] == 3:
                    rgb = frame
                else:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                results = self.model(rgb, conf=0.5, iou=0.5, verbose=False)
                plotted = results[0].plot()
                plotted = cv2.cvtColor(plotted, cv2.COLOR_BGR2RGB)

                dets = []
                cat_count = 0
                dog_count = 0

                if results[0].boxes is not None:
                    boxes = results[0].boxes.cpu().numpy()
                    names = self.model.names
                    for box in boxes:
                        cls = int(box.cls[0])
                        conf = float(box.conf[0])
                        name = names.get(cls, str(cls))
                        dets.append((name, conf))
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
                self.on_frame(plotted, payload)
                time.sleep(0.03)

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
        self.root = root
        self.root.title("Pet Feeder Control (Raspberry Pi 5B)")
        self.root.geometry("1180x720")

        self.dht = None
        self.cat_scale = None
        self.dog_scale = None
        self.servo = None
        self.yolo_worker = None

        self.frame_lock = threading.Lock()
        self.latest_frame = None
        self.latest_payload = None
        self.last_payload_signature = None
        self.last_status_text = None
        self.last_cat_history_weight = None
        self.last_dog_history_weight = None
        self.weight_history_threshold = 5

        self.temp_var = tk.StringVar(value="Temperature: -- °C")
        self.humi_var = tk.StringVar(value="Humidity: -- %")
        self.cat_weight_var = tk.StringVar(value="Cat Bowl: -- g")
        self.dog_weight_var = tk.StringVar(value="Dog Bowl: -- g")
        self.status_var = tk.StringVar(value="Status: Initializing...")
        self.cat_target_var = tk.StringVar(value="100")
        self.dog_target_var = tk.StringVar(value="100")

        self._build_ui()
        self._setup_hardware()
        self._loop_sensor_update()
        self._loop_video_update()

    def _build_ui(self):
        self.root.columnconfigure(0, weight=2)
        self.root.columnconfigure(1, weight=4)
        self.root.columnconfigure(2, weight=3)
        self.root.rowconfigure(0, weight=1)

        left = ttk.Frame(self.root, padding=10)
        center = ttk.Frame(self.root, padding=10)
        right = ttk.Frame(self.root, padding=10)

        left.grid(row=0, column=0, sticky="nsew")
        center.grid(row=0, column=1, sticky="nsew")
        right.grid(row=0, column=2, sticky="nsew")

        env_group = ttk.LabelFrame(left, text="Environment", padding=10)
        env_group.pack(fill="x", pady=6)
        ttk.Label(env_group, textvariable=self.temp_var, font=("Arial", 12)).pack(anchor="w", pady=3)
        ttk.Label(env_group, textvariable=self.humi_var, font=("Arial", 12)).pack(anchor="w", pady=3)

        food_group = ttk.LabelFrame(left, text="Mapped Food Weight", padding=10)
        food_group.pack(fill="x", pady=6)
        ttk.Label(food_group, textvariable=self.cat_weight_var, font=("Arial", 12)).pack(anchor="w", pady=3)
        ttk.Label(food_group, textvariable=self.dog_weight_var, font=("Arial", 12)).pack(anchor="w", pady=3)

        servo_group = ttk.LabelFrame(left, text="Servo Feeding", padding=10)
        servo_group.pack(fill="x", pady=6)

        cat_row = ttk.Frame(servo_group)
        cat_row.pack(fill="x", pady=4)
        dog_row = ttk.Frame(servo_group)
        dog_row.pack(fill="x", pady=4)
        tips_row = ttk.Frame(servo_group)
        tips_row.pack(fill="x", pady=(2, 0))

        ttk.Label(cat_row, text="Cat target (g):", font=("Arial", 11)).pack(side="left", padx=(0, 6))
        ttk.Entry(cat_row, textvariable=self.cat_target_var, width=10).pack(side="left", padx=(0, 6))
        ttk.Button(cat_row, text="Start Cat Feeding", command=lambda: self.feed_async("cat")).pack(side="left")

        ttk.Label(dog_row, text="Dog target (g):", font=("Arial", 11)).pack(side="left", padx=(0, 6))
        ttk.Entry(dog_row, textvariable=self.dog_target_var, width=10).pack(side="left", padx=(0, 6))
        ttk.Button(dog_row, text="Start Dog Feeding", command=lambda: self.feed_async("dog")).pack(side="left")

        ttk.Label(
            tips_row,
            text="Servo opens until bowl weight reaches the target, then returns to 0°.",
            wraplength=300,
        ).pack(anchor="w")

        ttk.Label(left, textvariable=self.status_var, foreground="blue", wraplength=300).pack(anchor="w", pady=8)

        video_group = ttk.LabelFrame(center, text="YOLO Live View", padding=8)
        video_group.pack(fill="both", expand=True)

        self.video_container = tk.Frame(video_group, width=480, height=360, bg="black")
        self.video_container.pack(anchor="center", padx=8, pady=8)
        self.video_container.pack_propagate(False)

        self.video_label = tk.Label(self.video_container, text="Waiting for stream...", bg="black", fg="white")
        self.video_label.pack(fill="both", expand=True)

        infer_group = ttk.LabelFrame(right, text="YOLO Inference", padding=8)
        infer_group.pack(fill="both", expand=True, pady=(0, 6))

        self.infer_text = tk.Text(infer_group, width=40)
        self.infer_text.pack(fill="both", expand=True)

        history_group = ttk.LabelFrame(right, text="Weight History", padding=8)
        history_group.pack(fill="both", expand=True)

        self.history_text = tk.Text(history_group, width=40, height=12)
        self.history_text.pack(fill="both", expand=True)
        self.history_text.insert(tk.END, "Timestamped weight changes will appear here.\n")

    def _setup_hardware(self):
        try:
            if adafruit_dht is None or board is None:
                raise RuntimeError("adafruit_dht/board not installed")
            self.dht = adafruit_dht.DHT11(board.D4)
        except Exception as e:
            self._set_status(f"DHT11 init failed ({e})")

        try:
            self.cat_scale = HX711Wrapper("Cat Bowl", dout_pin=20, sck_pin=21)
            self.dog_scale = HX711Wrapper("Dog Bowl", dout_pin=10, sck_pin=11)
        except Exception as e:
            self._set_status(f"HX711 init failed ({e})")

        try:
            self.servo = ServoFeeder(cat_pin=18, dog_pin=13)
        except Exception as e:
            self._set_status(f"Servo init failed ({e})")

        self.yolo_worker = YOLOWorker(on_frame=self._on_yolo_frame, on_status=self._set_status)
        self.yolo_worker.start()

    def _set_status(self, text):
        if text != self.last_status_text:
            self.last_status_text = text
            print(f"[STATUS] {text}", flush=True)
        self.root.after(0, lambda: self.status_var.set(f"Status: {text}"))

    def _loop_sensor_update(self):
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

        # HX711
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

            self._append_weight_history_if_changed(cat_status, dog_status)
        except Exception:
            pass

        self.root.after(2000, self._loop_sensor_update)

    def _on_yolo_frame(self, frame_rgb, payload):
        with self.frame_lock:
            self.latest_frame = frame_rgb
            self.latest_payload = payload

    def _loop_video_update(self):
        frame = None
        payload = None
        with self.frame_lock:
            if self.latest_frame is not None:
                frame = self.latest_frame.copy()
            if self.latest_payload is not None:
                payload = dict(self.latest_payload)

        if frame is not None:
            h, w = frame.shape[:2]
            target_w, target_h = 480, 360
            scale = min(target_w / w, target_h / h)
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            resized = cv2.resize(frame, (new_w, new_h))

            img = Image.fromarray(resized)
            tk_img = ImageTk.PhotoImage(img)
            self.video_label.configure(image=tk_img, text="")
            self.video_label.image = tk_img

        if payload is not None:
            signature = (
                payload.get("timestamp"),
                payload.get("cat_count"),
                payload.get("dog_count"),
                tuple(payload.get("detections", [])),
            )
            if signature != self.last_payload_signature:
                self.last_payload_signature = signature
                self._render_infer(payload)

        self.root.after(50, self._loop_video_update)

    def _render_infer(self, payload):
        ts = payload.get("timestamp", "--:--:--")
        cat_count = payload.get("cat_count", 0)
        dog_count = payload.get("dog_count", 0)
        detections = payload.get("detections", [])

        lines = [
            f"[{ts}] Inference Result",
            f"Cat: {cat_count}  Dog: {dog_count}",
            "-" * 28,
        ]
        for idx, (name, conf) in enumerate(detections, 1):
            lines.append(f"{idx}. {name} ({conf:.2f})")

        self.infer_text.delete("1.0", tk.END)
        self.infer_text.insert(tk.END, "\n".join(lines))

    def _append_weight_history_if_changed(self, cat_status, dog_status):
        changed = False
        parts = []

        cat_weight = cat_status["mapped_weight"] if cat_status is not None else None
        dog_weight = dog_status["mapped_weight"] if dog_status is not None else None

        if self._is_weight_history_change(cat_weight, self.last_cat_history_weight):
            self.last_cat_history_weight = cat_weight
            cat_raw = cat_status["raw_weight"] if cat_status is not None else None
            parts.append(
                f"Cat raw={cat_raw if cat_raw is not None else '--'} mapped={cat_weight if cat_weight is not None else '--'}g"
            )
            changed = True

        if self._is_weight_history_change(dog_weight, self.last_dog_history_weight):
            self.last_dog_history_weight = dog_weight
            dog_raw = dog_status["raw_weight"] if dog_status is not None else None
            parts.append(
                f"Dog raw={dog_raw if dog_raw is not None else '--'} mapped={dog_weight if dog_weight is not None else '--'}g"
            )
            changed = True

        if not changed:
            return

        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] " + " | ".join(parts) + "\n"
        print(line, end="", flush=True)
        self.history_text.insert(tk.END, line)
        self.history_text.see(tk.END)

    def _is_weight_history_change(self, current_weight, last_weight):
        if current_weight is None or last_weight is None:
            return current_weight != last_weight
        return abs(current_weight - last_weight) > self.weight_history_threshold

    def feed_async(self, target):
        if self.servo is None:
            messagebox.showwarning("Notice", "Servo is not initialized")
            return

        scale = self.cat_scale if target == "cat" else self.dog_scale
        target_var = self.cat_target_var if target == "cat" else self.dog_target_var

        if scale is None:
            messagebox.showwarning("Notice", "Scale is not initialized")
            return

        try:
            target_weight = int(float(target_var.get().strip()))
        except ValueError:
            messagebox.showwarning("Notice", "Please enter a valid target weight")
            return

        if target_weight <= 0:
            messagebox.showwarning("Notice", "Target weight must be greater than 0")
            return

        def _job():
            try:
                name = "Cat Bowl" if target == "cat" else "Dog Bowl"
                current_weight = scale.get_mapped_weight()
                if current_weight is not None and current_weight >= target_weight:
                    self._set_status(f"{name} is already at {current_weight}g, target reached")
                    return

                self._set_status(f"Feeding {name} to target {target_weight}g")
                final_weight = self.servo.dispense_until_target(
                    target,
                    scale,
                    target_weight,
                    on_progress=lambda weight: self._set_status(
                        f"Feeding {name}: {weight}g / {target_weight}g"
                    ),
                )

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

        threading.Thread(target=_job, daemon=True).start()

    def close(self):
        try:
            if self.yolo_worker is not None:
                self.yolo_worker.stop()
                self.yolo_worker.join(timeout=2)
        except Exception:
            pass

        try:
            if self.dht is not None:
                self.dht.exit()
        except Exception:
            pass

        try:
            if self.servo is not None:
                self.servo.cleanup()
        except Exception:
            pass

        try:
            if GPIO is not None:
                GPIO.cleanup()
        except Exception:
            pass


def main():
    root = tk.Tk()
    app = MainApp(root)

    def on_close():
        app.close()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
