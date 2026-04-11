#!/usr/bin/env python3

import time
import adafruit_dht
import board
from datetime import datetime
import logging

# ===================== 硬件配置 =====================
DHT_PIN = board.D4     # DHT11温湿度传感器 (BCM4)

# 传感器阈值配置
TEMPERATURE_THRESHOLD = 35     # 温度阈值，高于此值表示温度过高
HUMIDITY_THRESHOLD = 80        # 湿度阈值，高于此值表示湿度过高

# ===================== 全局变量 =====================
dht_device = None       # DHT11设备对象

# ===================== 初始化函数 =====================
def setup_dht11():
    """初始化DHT11传感器"""
    global dht_device
    try:
        dht_device = adafruit_dht.DHT11(DHT_PIN)
        logging.info("DHT11传感器初始化成功")
    except Exception as e:
        logging.error(f"DHT11传感器初始化失败: {e}")
        dht_device = None

def read_dht11():
    """读取DHT11温湿度传感器数据"""
    temperature = None
    humidity = None
    
    if dht_device:
        try:
            temperature = dht_device.temperature
            humidity = dht_device.humidity
            
            # 如果读取到无效数据，重试一次
            if temperature is None or humidity is None:
                time.sleep(1)
                temperature = dht_device.temperature
                humidity = dht_device.humidity
                
        except RuntimeError as error:
            # DHT11读取错误很常见，记录但不中断程序
            logging.warning(f"DHT11读取失败: {error}")
        except Exception as error:
            logging.error(f"DHT11错误: {error}")
    
    return temperature, humidity

def read_all_sensors():
    """读取所有传感器数据"""
    # 读取DHT11温湿度
    temperature, humidity = read_dht11()
    
    return {
        # DHT11数据
        'temperature': temperature,
        'humidity': humidity,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

# ===================== 报警判断函数 =====================
def check_alarms(sensor_data):
    """检查传感器是否触发报警"""
    alarms = []
    
    # 温度报警检查（仅当DHT11读数有效时）
    if sensor_data['temperature'] is not None and sensor_data['temperature'] > TEMPERATURE_THRESHOLD:
        alarms.append({
            'type': '温度过高',
            'message': f"温度: {sensor_data['temperature']:.1f}°C (阈值: >{TEMPERATURE_THRESHOLD}°C)",
            'value': sensor_data['temperature'],
            'threshold': TEMPERATURE_THRESHOLD
        })
    
    # 湿度报警检查（仅当DHT11读数有效时）
    if sensor_data['humidity'] is not None and sensor_data['humidity'] > HUMIDITY_THRESHOLD:
        alarms.append({
            'type': '湿度过高',
            'message': f"湿度: {sensor_data['humidity']:.1f}% (阈值: >{HUMIDITY_THRESHOLD}%)",
            'value': sensor_data['humidity'],
            'threshold': HUMIDITY_THRESHOLD
        })
    
    return alarms

# ===================== 显示和日志函数 =====================
def display_sensor_data(sensor_data, alarm_list):
    """显示传感器数据和报警状态"""
    print("\n" + "=" * 50)
    print(f"时间: {sensor_data['timestamp']}")
    print("-" * 50)
    
    # DHT11温湿度传感器
    temp_color = "\033[91m" if sensor_data['temperature'] is not None and sensor_data['temperature'] > TEMPERATURE_THRESHOLD else "\033[92m"
    humidity_color = "\033[91m" if sensor_data['humidity'] is not None and sensor_data['humidity'] > HUMIDITY_THRESHOLD else "\033[92m"
    
    if sensor_data['temperature'] is not None:
        temp_status = "正常" if sensor_data['temperature'] <= TEMPERATURE_THRESHOLD else "🌡️ 温度过高!"
        print(f"{temp_color}温度: {sensor_data['temperature']:5.1f}°C - {temp_status}\033[0m")
    else:
        print("温度: \033[93m读取失败\033[0m")
    
    if sensor_data['humidity'] is not None:
        humidity_status = "正常" if sensor_data['humidity'] <= HUMIDITY_THRESHOLD else "💦 湿度过高!"
        print(f"{humidity_color}湿度: {sensor_data['humidity']:5.1f}% - {humidity_status}\033[0m")
    else:
        print("湿度: \033[93m读取失败\033[0m")
    
    # 显示报警信息
    if alarm_list:
        print("-" * 50)
        print("⚠️  \033[91m报警信息:\033[0m")
        for alarm in alarm_list:
            print(f"   - \033[91m{alarm['type']}: {alarm['message']}\033[0m")
    
    # 显示分隔线
    if not alarm_list:
        print("-" * 50)
        print("状态: \033[92m正常\033[0m")

def setup_logging():
    """设置日志记录"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('dht11_monitor.log'),
            logging.StreamHandler()
        ]
    )

# ===================== 主程序 =====================
def main():
    """主函数"""
    
    # 初始化
    setup_logging()
    setup_dht11()
    
    print("\033[94m" + "=" * 50)
    print("DHT11温湿度监测系统")
    print("=" * 50 + "\033[0m")
    print(f"温度报警阈值: \033[93m> {TEMPERATURE_THRESHOLD}°C\033[0m")
    print(f"湿度报警阈值: \033[93m> {HUMIDITY_THRESHOLD}%\033[0m")
    print("\033[94m" + "=" * 50 + "\033[0m")
    print("按 Ctrl+C 停止程序")
    
    logging.info("DHT11温湿度监测系统启动")
    logging.info(f"温度报警阈值: > {TEMPERATURE_THRESHOLD}°C")
    logging.info(f"湿度报警阈值: > {HUMIDITY_THRESHOLD}%")
    
    try:
        while True:
            # 读取传感器数据
            sensor_data = read_all_sensors()
            
            # 检查报警
            alarms = check_alarms(sensor_data)
            
            # 显示数据
            display_sensor_data(sensor_data, alarms)
            
            # 记录到日志文件
            if alarms:
                for alarm in alarms:
                    logging.warning(f"{alarm['type']} - {alarm['message']}")
            
            # 等待2秒（DHT11需要较长的读取间隔）
            time.sleep(2)
            
    except KeyboardInterrupt:
        print("\n\033[93m正在停止系统...\033[0m")
    except Exception as e:
        logging.error(f"系统出错: {e}")
        print(f"\033[91m系统出错: {e}\033[0m")
    finally:
        # 清理资源
        if dht_device:
            dht_device.exit()
        print("\033[92m系统已安全停止\033[0m")
        logging.info("DHT11温湿度监测系统停止")

if __name__ == "__main__":
    main()