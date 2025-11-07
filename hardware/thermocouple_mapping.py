import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

thermocouple_types = [ "102AT", "202AT", "502AT", "103AT", "203AT" ]

# From https://www.semitec-global.com/uploads/2022/01/P12-13-AT-Thermistor.pdf
# column 0 is temperature in degrees C
# other columns are restance in kiloohms corresponding to the thermocouple_type
thermocouple_table = np.array([
    [-50, 24.46, 55.66, 154.6, 329.5, 1253],
    [-40, 14.43, 32.34, 88.91, 188.5, 642.0],
    [-30, 8.834, 19.48, 52.87, 111.3, 342.5],
    [-20, 5.594, 12.11, 32.44, 67.77, 190.0],
    [-10, 3.651, 7.763, 20.48, 42.47, 109.1],
    [0, 2.449, 5.114, 13.29, 27.28, 64.88],
    [10, 1.684, 3.454, 8.840, 17.96, 39.71],
    [20, 1.184, 2.387, 6.013, 12.09, 24.96],
    [25, 1.000, 2.000, 5.000, 10.00, 20.00],
    [30, 0.8486, 1.684, 4.179, 8.313, 16.12],
    [40, 0.6189, 1.211, 2.961, 5.827, 10.65],
    [50, 0.4587, 0.8854, 2.137, 4.160, 7.181],
    [60, 0.3446, 0.6587, 1.567, 3.020, 4.943],
    [70, 0.2622, 0.4975, 1.168, 2.228, 3.464],
    [80, 0.1999, 0.3807, 0.8835, 1.668, 2.468],
    [85, 0.1751, 0.3346, 0.7722, 1.451, 2.096],
    [90, 0.1536, 0.2949, 0.6771, 1.266, 1.788],
    [100, 0, 0, 0.5265, 0.9731, 1.315],
    [110, 0, 0, 0.4128, 0.7576, 0.9807],
    ])

sensor_type = 3
thermocouple_name = thermocouple_types[sensor_type]
temperature_c = thermocouple_table[:,0]
temperature_k = temperature_c + 273.15
resistance = thermocouple_table[:,sensor_type+1]

# Plot of ADC value with R25 resistor in percent
if False:
    r25=10
    percent = 100.0 * r25 / (r25 + resistance)
    plt.plot(temperature_c, percent)
    plt.xlabel("Temperature")
    plt.ylabel("Percent")
    plt.title(f"Voltage fraction versus temperature for {thermocouple_name} thermocouple")
    plt.show()

# Fit the Steinhart-Hart formula to the data
def steinhart_hart(R, A, B, C):
    return 1 / (A + B * np.log(R) + C * (np.log(R))**3)

# Initial guess for A, B, C (can be refined for better fitting)
# A common starting point for NTC thermistors is around:
# A ~ 1e-3, B ~ 2e-4, C ~ 1e-7
initial_guess = [1e-3, 2e-4, 1e-7]

params, covariance = curve_fit(steinhart_hart,
                               resistance, temperature_k, p0=initial_guess)

A_fit, B_fit, C_fit = params
print(f"Fitted Steinhart-Hart coefficients:")
print(f"A = {A_fit:.8e}")
print(f"B = {B_fit:.8e}")
print(f"C = {C_fit:.8e}")
print(f"Covariance\n{covariance}")

if True:
    predicted_c = steinhart_hart(resistance, A_fit, B_fit, C_fit) - 273.15
    plt.plot(resistance, temperature_c, label="Datasheet")
    plt.plot(resistance, predicted_c, label="Predicted")
    plt.xlabel("Resistance")
    plt.ylabel("Temperature")
    plt.title(f"temperature versus resistance for {thermocouple_name} thermocouple")
    plt.legend()
    plt.grid(True)
    plt.show()

# To go from ADC percent to resistance use
#
# fraction = 10 / (resistance + 10)
# resistance = 10/fraction - 10
# resistance = 10 * (1 - fraction)/fraction
