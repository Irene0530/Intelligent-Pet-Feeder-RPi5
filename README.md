
````markdown
# Intelligent Pet Feeder (Raspberry Pi 5)

## 1. Overview
This project implements an intelligent vision-based pet feeding system designed for multi-pet households. The system integrates real-time computer vision, weight sensing, and closed-loop control on a Raspberry Pi 5 platform.

It supports two operating modes:

- **Local Mode (`main5.py`)** – Tkinter-based GUI for real-time monitoring and manual feeding
- **Web Mode (`mainweb.py`)** – Remote dashboard accessible via browser (LAN only)

The system focuses on precision feeding, real-time monitoring, and safe control, rather than full automation.

---

## 2. Key Features
- Real-time pet detection (cat/dog) using a YOLOv11-based trained model
- Dual-bowl independent feeding system
- Closed-loop weight-based feeding control
- Hybrid weight calibration algorithm (interval matching + regression fallback)
- Multi-threaded architecture for real-time responsiveness
- Local GUI + Web dashboard (concurrent operation)
- Safety mechanisms (timeout + task locking)

---

## 3. System Architecture
The system operates as a multi-threaded embedded application:

- **Vision Thread** – captures frames and performs YOLO inference (~20 FPS)
- **Sensor Loop** – reads HX711 and DHT11 data every 2 seconds
- **Control Logic** – executes feeding tasks using real-time weight feedback
- **Web Server Thread** – handles HTTP requests for remote monitoring/control

### Context Diagram
Camera -> YOLOWorker -> GUI / Web Dashboard
HX711 + DHT11 -> Sensor Loop -> Shared State -> GUI / Web Dashboard
User Input (GUI / Web) -> request_feed() -> ServoFeeder -> HX711 feedback
````

---

## 4. Hardware Requirements

* Raspberry Pi 5
* Raspberry Pi AI Camera (IMX500-based) or compatible Raspberry Pi camera
* 2 × HX711 load-cell channels
* 2 × strain-gauge load cells
* 2 × SG90 servo motors
* DHT11 temperature/humidity sensor

---

## 5. Project Structure

```text
.
├── main5.py              # Local GUI version
├── mainweb.py            # Web-based version
├── best.pt               # Trained YOLOv11-based model
├── hx711.py              # HX711 sensor interface (adapted library)
├── training/             # Model training scripts and configs
│   ├── train.py
│   └── mydata.yaml
└── README.md
```

---

## 6. Installation

### Install Python Dependencies

```bash
pip install opencv-python numpy Pillow ultralytics adafruit-circuitpython-dht picamera2
```

### System Setup (Raspberry Pi)

Ensure the camera interface is enabled:

```bash
sudo raspi-config
```

Navigate to:

**Interface Options → Camera → Enable**

If required, install camera support tools:

```bash
sudo apt update
sudo apt install libcamera-apps
```

### Additional Notes

* `RPi.GPIO` and `board` libraries are typically pre-installed on Raspberry Pi OS
* The HX711 module is included locally in the project (`hx711.py`)
* The system is designed to run on Raspberry Pi OS with GPIO-connected hardware
* Ensure:

  * `best.pt` is located in the project directory
  * `hx711.py` is present in the same directory

### Tested Environment

* Raspberry Pi 5
* Raspberry Pi OS
* Python 3
* GPIO-connected hardware peripherals

---

## 7. How to Run

### Local GUI Mode

```bash
python3 main5.py
```

### Web Mode

```bash
python3 mainweb.py
```

Then open a browser and access:

```text
http://<raspberry_pi_ip>:8000
```

> Note: the web server uses port **8000 by default**.

---

## 8. Feeding Logic

* Feeding is **user-triggered**
* The user sets a target weight (for example, 100 g)
* The servo dispenses food incrementally
* HX711 monitors bowl weight in real time
* Feeding stops when the target is reached or the timeout is triggered

A global lock (`feed_job_lock`) ensures that only one feeding task runs at a time to prevent hardware conflicts.

---

## 9. Model Training

The YOLOv11-based model was trained using a custom dataset of **2,984 annotated images** of cats and dogs.

### Training Configuration

* Epochs: **150**
* Image size: **640 × 640**
* Optimizer: **AdamW**
* Data split: **80% training / 10% validation / 10% testing**

### Data Augmentation

* Mosaic augmentation (disabled in final epochs)
* Brightness and contrast adjustment
* Rotation and scaling
* Copy-paste augmentation

The training pipeline is provided in the `/training` directory, including:

* `train.py` – training script
* `mydata.yaml` – dataset configuration

This supports reproducibility and transparency of model development.

---

## 10. Known Limitations

* Detection accuracy depends on lighting conditions
* No HTTPS (LAN-only usage recommended)
* Load cells may require recalibration over time
* Feeding is not automatically triggered by detection

---

## 11. Future Improvements

* Cloud data storage and analytics
* Secure remote access (HTTPS / authentication)
* Model optimisation for faster inference
* Adaptive feeding strategies based on behaviour

---

## 12. Software Artefact Ownership and External Components

* `main5.py` and `mainweb.py` were developed for this project.
* `best.pt` is the trained YOLOv11-based model produced from the project training pipeline.
* `hx711.py` is adapted from the open-source `hx711py` library referenced below.
* External frameworks and libraries used include Ultralytics YOLO, Picamera2, OpenCV, Pillow, and Adafruit DHT support libraries.

---

## 13. Attribution

### YOLO Framework

* [https://github.com/ultralytics/ultralytics](https://github.com/ultralytics/ultralytics)

### Dataset

* [https://www.kaggle.com/datasets/andrewmvd/dog-and-cat-detection](https://www.kaggle.com/datasets/andrewmvd/dog-and-cat-detection)

### External Libraries

The HX711 load-cell interface is implemented using a modified version of an open-source Python library:

* [https://github.com/tatobari/hx711py](https://github.com/tatobari/hx711py)

Only the necessary components were integrated and adapted for this project.

---

## 14. Author
Third Year Individual Project – University of Manchester
**Student:** Kuan Cheng Tai

