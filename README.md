
# Intelligent Pet Feeder (Raspberry Pi 5)

## 1. Overview

This project implements an intelligent vision-based pet feeding system designed for multi-pet households. The system integrates real-time computer vision, dual-channel weight sensing, environmental monitoring, and closed-loop feeding control on a Raspberry Pi 5 platform.

It supports two operating modes:

- **Local Mode (`main5_seperate.py`)** – Tkinter-based GUI for real-time monitoring and manual feeding control
- **Web Mode (`mainweb_seperate.py`)** – Remote dashboard accessible via browser on a trusted local area network (LAN)

The system focuses on precision feeding, real-time monitoring, and safe user-triggered control, rather than full automation.

---

## 2. Key Features

- Real-time pet detection for cats and dogs using a custom YOLOv11-based trained model (`best.pt`)
- Raspberry Pi AI Camera used for image acquisition
- YOLO inference executed on Raspberry Pi 5 using the Ultralytics framework
- Dual-bowl independent feeding system for cat and dog bowls
- Two independent HX711 + load-cell weighing channels
- Channel-specific HX711 calibration tables for cat and dog bowls
- Weight mapping using:
  - calibrated interval matching
  - tolerance-based snapping
  - piecewise linear interpolation / extrapolation
- Practical 0–1 kg calibrated feeding range
- Independent validation showing mapped-weight error within ±5 g in the tested feeding range
- Closed-loop weight-based feeding control
- DHT11 temperature and humidity monitoring
- Multi-threaded architecture for real-time responsiveness
- Local GUI and web dashboard operation
- Safety mechanisms including:
  - 30-second feeding timeout
  - task locking for safe actuation
  - minimum-weight threshold filtering

---

## 3. Camera and YOLO Inference Note

The hardware camera used in this project is the **Raspberry Pi AI Camera**, which is based on the Sony IMX500 intelligent vision sensor.

In the final implementation, the camera is used primarily for live image acquisition through the Picamera2 pipeline. The custom YOLO model (`best.pt`) is loaded and executed on the Raspberry Pi 5 using the Ultralytics framework.

The IMX500 on-sensor AI accelerator is not used for the final custom YOLO inference in this version. Future work could explore converting and deploying the model to the IMX500 accelerator to reduce CPU workload and power consumption.

---

## 4. System Architecture

The system operates as a multi-threaded embedded application:

- **Vision Thread**  
  Captures frames from the Raspberry Pi AI Camera and performs YOLO-based cat/dog detection.

- **Sensor Loop**  
  Periodically reads HX711 weight data and DHT11 temperature/humidity data.

- **Weight Mapping Module**  
  Converts processed HX711 readings into calibrated gram values using separate cat/dog calibration tables.

- **Control Logic**  
  Executes user-triggered feeding tasks using real-time weight feedback.

- **Web Server Thread**  
  Handles HTTP requests for remote monitoring and feeding control over the local network.


---

## 5. Hardware Requirements

* Raspberry Pi 5
* Raspberry Pi AI Camera with Sony IMX500 sensor, or compatible Raspberry Pi camera
* 2 × HX711 24-bit ADC modules
* 2 × 5 kg strain-gauge load cells
* 2 × SG90 servo motors
* DHT11 temperature/humidity sensor
* Cat and dog feeding bowls
* External 5 V power supply / breadboard power distribution

---

## 6. Project Structure

```text
.
├── main5_seperate.py       # Local GUI version
├── mainweb_seperate.py     # Web-enabled version
├── best.pt                 # Trained YOLOv11-based cat/dog detection model
├── training/               # Model training scripts and configuration
│   ├── train.py
│   └── mydata.yaml
└── README.md
```

> Note: the current repository uses the filename spelling `seperate`.

---

## 7. Installation

### Install Python Dependencies

```bash
pip install opencv-python numpy Pillow ultralytics adafruit-circuitpython-dht picamera2
```

### System Setup on Raspberry Pi

Enable the camera interface if required:

```bash
sudo raspi-config
```

Navigate to:

```text
Interface Options → Camera → Enable
```

If required, install camera support tools:

```bash
sudo apt update
sudo apt install libcamera-apps
```

### Additional Notes

* `RPi.GPIO` and `board` libraries are typically available on Raspberry Pi OS or can be installed through the required packages.
* The system uses `hx711py` for the HX711 load-cell interface.
* The system is designed to run on Raspberry Pi OS with GPIO-connected hardware.
* Ensure that:

  * `best.pt` is located in the project directory.
  * HX711, DHT11, servo motors, and camera hardware are connected correctly.
  * The Raspberry Pi has sufficient power supply capacity for all connected peripherals.

### Tested Environment

* Raspberry Pi 5
* Raspberry Pi OS
* Python 3
* GPIO-connected HX711, DHT11, and SG90 servo hardware
* Raspberry Pi AI Camera / Picamera2 camera pipeline

---

## 8. How to Run

### Local GUI Mode

```bash
python3 main5_seperate.py
```

The local GUI displays:

* live camera frame with YOLO detection output
* cat and dog detection counts
* cat and dog bowl weights
* temperature and humidity
* feeding history
* manual feeding controls

### Web Mode

```bash
python3 mainweb_seperate.py
```

Then open a browser and access:

```text
http://<raspberry_pi_ip>:8000
```

> Note: the web server uses port **8000 by default** and is intended for trusted LAN use only.

The web dashboard provides:

* current cat/dog bowl weights
* temperature and humidity readings
* latest YOLO detection results
* latest camera frame
* feeding history
* remote feeding controls

---

## 9. Weight Calibration

The system uses two independent weight sensing channels:

* Dog bowl HX711 channel
* Cat bowl HX711 channel

Although both channels use the same type of HX711 module and strain-gauge load cell, practical calibration showed that the two bowls produced different processed HX711 readings for the same reference weights. Therefore, the final implementation uses separate calibration tables for the cat and dog bowls.

The load cells are rated to 5 kg, but the calibrated operating range focuses on the practical pet-feeding range of **0–1 kg**. This range better matches typical household pet-feeding portions, while the 5 kg load cells provide additional mechanical headroom.

The mapping method uses:

1. **Interval matching**
   If the processed HX711 reading falls within a calibrated range, the corresponding known weight is returned directly.

2. **Tolerance-based snapping**
   If the reading is slightly outside a calibrated interval, it is snapped to the nearest calibrated weight to reduce display fluctuation.

3. **Piecewise linear interpolation / extrapolation**
   If the reading falls between calibrated regions, the system estimates the weight using the nearest calibration points. Readings slightly above the highest calibrated point but still within the intended 0–1 kg range are estimated using the nearest calibrated segment.

4. **Minimum threshold filtering**
   Very small mapped values below 5 g are treated as 0 g to reduce empty-bowl noise.

Independent validation using non-calibration test weights confirmed that the mapped weight error remained within **±5 g** across the practical 0–1 kg feeding range.

---

## 10. Feeding Logic

* Feeding is **user-triggered** rather than automatically triggered by detection.
* The user sets a target weight, for example 100 g.
* The corresponding servo opens the dispenser.
* HX711 monitors bowl weight in real time.
* Feeding stops when the mapped bowl weight reaches the target weight.
* Feeding also stops if the safety timeout is triggered.

A global lock (`feed_job_lock`) in the web-enabled version ensures that only one feeding task runs at a time to prevent hardware conflicts.

---

## 11. Model Training

The YOLOv11-based model was trained using a custom dataset of **2,984 annotated images** of cats and dogs.

### Training Configuration

* Epochs: **150**
* Image size: **640 × 640**
* Optimizer: **AdamW**
* Data split: **80% training / 10% validation / 10% testing**

### Data Augmentation

* Mosaic augmentation, disabled in the final epochs
* Brightness and contrast adjustment
* Rotation and scaling
* Copy-paste augmentation
* Simulated occlusion

The training pipeline is provided in the `/training` directory, including:

* `train.py` – training script
* `mydata.yaml` – dataset configuration

This supports reproducibility and transparency of model development.

---

## 12. YOLO Performance

The trained cat/dog detection model achieved the following validation results:

| Metric       | Result |
| ------------ | -----: |
| Precision    | 99.13% |
| Recall       | 98.38% |
| mAP@0.5      | 99.44% |
| mAP@0.5–0.95 | 88.92% |

In the deployed prototype, the Raspberry Pi 5 runs the trained `best.pt` model using the Ultralytics YOLO framework. The live camera preview is configured at 480 × 360 resolution for real-time display and inference.

---

## 13. Known Limitations

* Detection accuracy may still be affected by lighting, occlusion, and camera position.
* The web dashboard is designed for trusted LAN use only and does not currently include HTTPS or authentication.
* The custom YOLO model is executed on the Raspberry Pi 5 rather than on the IMX500 on-sensor AI accelerator.
* Load cells may require recalibration if the mechanical structure or bowl placement changes.
* Feeding is user-triggered rather than fully automatic.
* Operational history is stored locally rather than in a cloud database.

---

## 14. Future Improvements

* Secure remote access using HTTPS and authentication.
* Cloud or database-backed storage for long-term feeding history.
* Model quantization and pruning for faster inference.
* Conversion and deployment of the custom model to the IMX500 accelerator.
* Individual pet identity recognition.
* Adaptive feeding strategies based on pet behaviour and feeding history.
* Automated alerts for feeding timeout, low food supply, or abnormal behaviour.

---

## 15. Software Artefact Ownership and External Components

* `main5_seperate.py` and `mainweb_seperate.py` were developed for this project.
* `best.pt` is the trained YOLOv11-based model produced from the project training pipeline.
* The HX711 interface is implemented using the open-source `hx711py` library.
* External frameworks and libraries used include:

  * Ultralytics YOLO
  * Picamera2
  * OpenCV
  * Pillow
  * NumPy
  * RPi.GPIO
  * Adafruit DHT support libraries

---

## 16. Attribution

### YOLO Framework

* [https://github.com/ultralytics/ultralytics](https://github.com/ultralytics/ultralytics)

### Dataset

* [https://www.kaggle.com/datasets/andrewmvd/dog-and-cat-detection](https://www.kaggle.com/datasets/andrewmvd/dog-and-cat-detection)

### HX711 Library

The HX711 load-cell interface is implemented using an open-source Python library:

* [https://github.com/tatobari/hx711py](https://github.com/tatobari/hx711py)

Only the necessary components were integrated and adapted for this project.

---

## 17. Author

Third Year Individual Project – University of Manchester
**Student:** Kuan Cheng Tai
