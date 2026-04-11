import time
import sys
from hx711py.hx711 import HX711

def cleanAndExit():
    print("Cleaning...")
    GPIO.cleanup()
    print("Bye!")
    sys.exit()

class HX711Wrapper:
    def __init__(self, dout_pin, sck_pin, reference_unit=114):
        self.hx = HX711(21, 24)
        self.hx.set_reading_format("MSB", "MSB")
        self.hx.set_reference_unit(reference_unit)
        self.hx.reset()
        self.hx.tare()
        print("Tare done! Add weight now...")

    def get_weight(self):
        try:
            val = self.hx.get_weight(5)
            formatted_val = round(max(0, val), 2)  # Ensure value is non-negative and rounded to 2 decimal places
            self.hx.power_down()
            self.hx.power_up()
            return formatted_val
        except (KeyboardInterrupt, SystemExit):
            cleanAndExit()
        except Exception as e:
            print(f"Error: {e}")
            return None

# Example usage
# if __name__ == "__main__":
#     try:
#         # Initialize the wrapper with appropriate GPIO pins
#         weight_sensor = HX711Wrapper(dout_pin=24, sck_pin=21)

#         # Get the weight
#         weight = weight_sensor.get_weight()
#         if weight is not None:
#             print(f"Weight: {weight}g")
#     except (KeyboardInterrupt, SystemExit):
#         cleanAndExit()
