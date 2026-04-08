# Intelligent-Pet-Feeder-RPi5

## 1. Introduction
[cite_start]This software suite serves as the core processing unit for an intelligent vision-based pet feeding system designed for multi-pet households[cite: 44, 46]. Utilizing the **Raspberry Pi 5** as an edge computing core, the system provides two distinct operational modes:

* [cite_start]**Local Mode (`main5.py`)**: A desktop graphical user interface (GUI) built with Tkinter for real-time monitoring and manual control directly on the device[cite: 233, 234].
* [cite_start]**Web Mode (`mainweb.py`)**: A concurrent IoT dashboard powered by a multi-threaded HTTP server, allowing remote monitoring and feeding via any browser on the Local Area Network (LAN) [cite: 243-245].

[cite_start]The system integrates YOLOv11 object detection, a custom hybrid weight calibration algorithm, and closed-loop servo control to ensure precise, species-specific feeding[cite: 46, 51].

---

## 2. Contextual Overview
[cite_start]The software operates as a central hub, managing asynchronous multi-threaded loops to maintain high responsiveness[cite: 50, 136]:

* [cite_start]**Vision**: Continuous capture of 480x360 frames with real-time YOLOv11 inference at approximately 20 fps[cite: 326, 331, 436].
* [cite_start]**Sensing**: Dual-channel weight acquisition from HX711 ADCs and ambient environmental data (temperature/humidity) from a DHT11 sensor[cite: 46, 303, 304].
* [cite_start]**Control**: Execution of PWM-driven feeding tasks using a setpoint-based closed-loop strategy with a 30-second safety timeout[cite: 49, 344, 355].
* [cite_start]**Networking**: A background daemon thread serving a responsive HTML/CSS dashboard for remote interaction[cite: 137, 138, 222].

---

## 3. Installation Instructions

### Prerequisites
* [cite_start]**Hardware**: Raspberry Pi 5, IMX500 Camera, 2x SG90 Servos, 2x HX711 Load Cells (with strain gauges), and a DHT11 Sensor [cite: 122-131].
* **OS**: Raspberry Pi OS (64-bit recommended).

### Dependencies
Ensure Python 3 is installed, then install the required libraries:

```bash
pip install opencv-python numpy Pillow ultralytics adafruit-circuitpython-dht
```

*Note: `picamera2` and `RPi.GPIO` are typically pre-installed on Raspberry Pi OS. [cite_start]For HX711 functionality, ensure the `hx711py` library is present in the project directory [cite: 267-269].*

---

## 4. How to Run
[cite_start]Ensure the trained model file `best.pt` is located in the same directory as the Python scripts[cite: 322, 325].

### To start the Local GUI:
```bash
python3 main5.py
```

### To start the Web-Enabled System:
```bash
python3 mainweb.py
```

[cite_start]Once `mainweb.py` is initialized, the console will display the local access URL (e.g., `http://192.168.x.x:8000`)[cite: 252]. [cite_start]Access this URL from any device on the same Wi-Fi network to use the remote dashboard[cite: 252].

---

## 5. Technical Details

### Vision Subsystem (YOLOv11)
[cite_start]The vision module utilizes a lightweight **YOLOv11n (Nano)** architecture optimized for edge inference[cite: 162, 321, 439].

* **Dataset Acquisition**: The model was trained using the "Dog and Cat Detection" dataset sourced from [Andrewmvd (Kaggle)](https://www.kaggle.com/datasets/andrewmvd/dog-and-cat-detection).
* [cite_start]**Data Partitioning**: A total of 2,984 annotated images were partitioned into **Training (80%)**, **Validation (10%)**, and **Testing (10%)** sets[cite: 155, 157].
* **Training Configuration**:
    * **imgsz**: 640x640 pixels.
    * **Epochs**: 150.
    * [cite_start]**Optimizer**: AdamW[cite: 159].
    * **Hardware Acceleration**: Trained with Automatic Mixed Precision (AMP) enabled.
* [cite_start]**Augmentation Strategy**: The pipeline employed Mosaic augmentation (disabled for the final 10 epochs), Copy-Paste (0.3), HSV adjustments, and spatial transformations (rotation, shear, and scaling) to improve generalization[cite: 156, 161].

### Weight Calibration
[cite_start]To address the non-linearity of low-cost load cells, a **Hybrid Calibration Algorithm** is implemented in the `WeightMapper` class[cite: 166, 278]:

1.  [cite_start]**Interval Matching**: Uses a lookup table generated through combinatorial summation of base calibration points (65g, 100g, 200g, 265g) for high-precision local matching [cite: 178-183].
2.  [cite_start]**Linear Regression Fallback**: Employs a least-squares linear regression model to estimate weights falling outside pre-calibrated intervals[cite: 185, 191, 196].
3.  [cite_start]**Digital Filtering**: Includes a 5g noise threshold to suppress sensor drift and idle fluctuations[cite: 197, 284].

---

## 6. Known Issues and Attribution

* [cite_start]**Lighting Sensitivity**: Object detection accuracy may decrease in low-light or high-glare environments[cite: 427].
* [cite_start]**Network Security**: The web server currently operates over unencrypted HTTP and is intended for use within a secure Local Area Network (LAN)[cite: 448].
* **Attribution**: This project utilizes the [Ultralytics](https://github.com/ultralytics/ultralytics) framework. [cite_start]Modifications were made to the standard YOLOv11 implementation to support asynchronous frame processing and integration with the Tkinter GUI and ThreadingHTTPServer[cite: 764, 912].


