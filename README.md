# Intelligent Pet Feeder (Raspberry Pi 5)

## 1. Overview

This project implements an intelligent vision-based pet feeding system designed for multi-pet households. The system integrates real-time computer vision, weight sensing, and closed-loop control on a Raspberry Pi 5 platform.

It supports two operating modes:

* **Local Mode (`main5.py`)** – Tkinter-based GUI for real-time monitoring and manual feeding
* **Web Mode (`mainweb.py`)** – Remote dashboard accessible via browser (LAN only)

The system focuses on **precision feeding, real-time monitoring, and safe control**, rather than full automation.

---

## 2. Key Features

* Real-time pet detection (cat/dog) using YOLOv11
* Dual-bowl independent feeding system
* Closed-loop weight-based feeding control
* Hybrid weight calibration algorithm (interval + regression)
* Multi-threaded architecture for real-time responsiveness
* Local GUI + Web dashboard (concurrent operation)
* Safety mechanisms (timeout + task locking)

---

## 3. System Architecture

The system operates as a multi-threaded embedded application:

* **Vision Thread** – captures frames and performs YOLO inference (~20 FPS)
* **Sensor Loop** – reads HX711 and DHT11 data every 2 seconds
* **Control Logic** – executes feeding tasks using real-time weight feedback
* **Web Server Thread** – handles HTTP requests for remote monitoring/control

---

## 4. Hardware Requirements

* Raspberry Pi 5
* Raspberry Pi Camera (IMX500 or compatible)
* 2 × HX711 Load Cells
* 2 × SG90 Servo Motors
* DHT11 Temperature/Humidity Sensor

---

## 5. Project Structure

```
.
├── main5.py              # Local GUI version
├── mainweb.py            # Web-based version
├── best.pt               # Trained YOLO model
├── hx711/                # HX711 sensor interface (adapted library)
│   └── hx711.py
├── training/             # Model training scripts and configs
│   ├── train.py
│   └── mydata.yaml
└── README.md
```

---

## 6. Installation

Install dependencies:

```bash
pip install opencv-python numpy Pillow ultralytics adafruit-circuitpython-dht
```

Ensure:

* `best.pt` (trained YOLO model) is in the same directory
* HX711 library is available in the `/hx711` folder

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

```
http://<raspberry_pi_ip>:8000
```

---

## 8. Feeding Logic

* Feeding is **user-triggered**
* User sets target weight (e.g., 100g)
* Servo dispenses food incrementally
* HX711 monitors weight in real time
* Feeding stops when target is reached or timeout occurs

A global lock (`feed_job_lock`) ensures that only one feeding task runs at a time to prevent hardware conflicts.

---

## 9. Model Training

The YOLOv11 model was trained using a custom dataset of 2,984 annotated images of cats and dogs.

**Training configuration:**

* Epochs: 150
* Image size: 640 × 640
* Optimizer: AdamW
* Data split: 80% training / 10% validation / 10% testing

**Data augmentation techniques:**

* Mosaic augmentation (disabled in final epochs)
* Brightness and contrast adjustment
* Rotation and scaling
* Copy-paste augmentation

The training pipeline is provided in the `/training` directory, including:

* `train.py`: training script
* `mydata.yaml`: dataset configuration

This ensures reproducibility and transparency of the model development process.

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

## 12. Attribution

* YOLO framework: https://github.com/ultralytics/ultralytics
* Dataset: https://www.kaggle.com/datasets/andrewmvd/dog-and-cat-detection

### External Libraries

The HX711 load cell interface is implemented using a modified version of an open-source Python library:

https://github.com/tatobari/hx711py

Only the necessary components were integrated and adapted for this project.

---

## 13. Author

Final Year Project – University of Manchester
Student: Kuan Cheng Tai
