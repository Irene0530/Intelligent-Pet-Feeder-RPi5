# Intelligent-Pet-Feeder-RPi5

# README: Intelligent Cat and Dog Feeding System

## 1. Introduction
This software suite is the core processing unit of an intelligent vision-based pet feeder. It provides two operational modes:
**Local Mode (`main5.py`)**: A desktop GUI for real-time monitoring and manual control directly on the Raspberry Pi[cite: 233, 234].
**Web Mode (`mainweb.py`)**: A concurrent IoT dashboard allowing remote monitoring and feeding via any browser on the Local Area Network (LAN).

The system integrates YOLOv11 object detection, hybrid weight calibration, and closed-loop servo control to ensure precise and species-specific feeding.

## 2. Contextual Overview
The software acts as a central hub, managing multi-threaded loops for:
1.  **Vision**: Capturing 480x360 frames and performing YOLOv11 inference.
2.  **Sensing**: Reading weight from dual-channel HX711 ADCs and environment data from DHT11.
3.  **Control**: Executing PWM-driven feeding tasks with a safety timeout.
4.  **Networking**: Serving an HTTP dashboard for remote interaction.



## 3. Installation Instructions
### Prerequisites
**Hardware**: Raspberry Pi 5, IMX500 Camera, 2 SG90 Servos, 2 HX711 Load Cells and 2 strain gauges, DHT11 Sensor.
* **OS**: Raspberry Pi OS (64-bit recommended).

### Dependencies
Install the required Python libraries:
```bash
pip install opencv-python numpy Pillow ultralytics adafruit-circuitpython-dht
# Note: picamera2 and RPi.GPIO are usually pre-installed on Pi OS.
# For HX711, ensure the hx711py library is in your project directory.
```

## 4. How to Run
Ensure your model file `best.pt` is in the same directory as the scripts.

### To start the Local GUI:
```bash
python3 main5.py
```
### To start the Web-Enabled System:
```bash
python3 mainweb.py
```
Once `mainweb.py` is running, the console will display a URL (e.g., `http://192.168.x.x:8000`). Access this URL from any device on the same Wi-Fi to use the remote dashboard.

## 5. Technical Details
### Vision Subsystem (YOLOv11)
* **Model**: A customized YOLOv11n architecture, optimized for edge inference.
* **Training**: The model (`best.pt`) was trained for 150 epochs on a dataset of 2,984 annotated cat and dog images.
* **Modification**: The original YOLOv11 source code was adapted to handle asynchronous frame retrieval and UI-based rendering to prevent the inference loop from blocking the GUI.

### Weight Calibration
The system uses a **Hybrid Calibration Algorithm**:
1.  **Interval Matching**: Pre-defined lookup tables for common weight ranges (e.g., 65g, 100g).
2.  **Linear Regression Fallback**: Least-squares regression is used for weights between calibrated points.

## 6. Known Issues 
**Lighting Sensitivity**: Vision accuracy may decrease in low-light conditions.
**Network Security**: The web server currently operates without encryption (HTTP) and requires a secure LAN environment.


