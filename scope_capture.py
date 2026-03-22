import serial, time
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter

scope = serial.Serial('/dev/hmo1024', 115200, timeout=5)

def scpi(cmd):
    scope.write((cmd + '\n').encode())
    if '?' in cmd:
        # Poll until data arrives, then read until idle
        deadline = time.time() + 10.0
        while scope.in_waiting == 0 and time.time() < deadline:
            time.sleep(0.05)
        # Keep reading until no new data for 100ms
        buf = b''
        while True:
            chunk = scope.read(scope.in_waiting or 1)
            buf += chunk
            if scope.in_waiting == 0:
                time.sleep(0.1)
                if scope.in_waiting == 0:
                    break
        return buf

def read_block(scope):
    # Read until we have the full IEEE 488.2 definite-length block
    raw = b''
    while True:
        raw += scope.read(scope.in_waiting or 1)
        if len(raw) > 2:
            n_digits = int(chr(raw[1]))
            header_len = 2 + n_digits
            data_len = int(raw[2:header_len])
            if len(raw) >= header_len + data_len:
                return raw[header_len:header_len + data_len]

def capture_screen(filename='scope_capture.png'):
    scpi(':HCOP:FORM PNG')
    scope.write(b':HCOP:DATA?\n')
    png_data = read_block(scope)
    with open(filename, 'wb') as f:
        f.write(png_data)
    print(f'Screen saved to {filename} ({len(png_data)} bytes)')

def capture_waveform(channel=1):
    # Set ASCII format — returns voltages directly, no scaling needed
    scpi('FORM ASC')

    # Get time axis from header: XStart, XStop, NumSamples, ValuesPerSample
    header = scpi(f'CHAN{channel}:DATA:HEAD?').decode().strip().split(',')
    x_start   = float(header[0])
    x_stop    = float(header[1])

    # Get waveform data (comma-separated voltage values in volts)
    raw = scpi(f'CHAN{channel}:DATA?').decode().strip()
    volts = np.array([float(v) for v in raw.split(',')])

    t_ms = np.linspace(x_start * 1000, x_stop * 1000, len(volts))

    # Savitzky-Golay smoothing: preserves peaks better than a simple moving average
    volts_smooth = savgol_filter(volts, window_length=31, polyorder=3)

    print(f'CH{channel}: {len(volts)} samples  ({x_start*1000:.3f} to {x_stop*1000:.3f} ms)')
    print(f'  Min: {volts_smooth.min():.3f}V  Max: {volts_smooth.max():.3f}V')

    return t_ms, volts_smooth

# Verify connection
print(scpi('*IDN?'))

# Screen capture
capture_screen()

# Waveform download and plot
t, v = capture_waveform(channel=1)

fig, ax = plt.subplots(figsize=(10, 4))
ax.set_facecolor('black')
fig.patch.set_facecolor('#1a1a1a')
ax.plot(t, v, color='yellow', linewidth=0.8)

# Key event detection
min_idx = v.argmin()
v_plateau = v[:min_idx].max()

# Decay start: first point where voltage drops > 0.2V below plateau
decay_idx = next((i for i in range(min_idx) if v[i] < v_plateau - 0.2), 0)

# Recovery end: first point after minimum where voltage exceeds 11.3V
recover_idx = next((i for i in range(min_idx, len(v)) if v[i] > 11.3), len(v) - 1)

t_decay   = t[decay_idx]
t_trip    = t[min_idx]
t_recover = t[recover_idx]

# Vertical event lines
v_min = v.min()
v_range = v_plateau - v_min

# Extend y-axis to make room for arrows below and labels above
ax.set_ylim(v_min - v_range * 0.5, v_plateau + v_range * 0.3)

for tx, col in [(t_decay, 'cyan'), (t_trip, 'red'), (t_recover, 'lime')]:
    ax.axvline(tx, color=col, linewidth=0.8, linestyle='--')

# Duration span arrows in the space below the waveform
y_decay_arrow    = v_min - v_range * 0.15
y_recovery_arrow = v_min - v_range * 0.35
for t0, t1, label, col, y_arr in [
        (t_decay, t_trip,    f'Decay {t_trip-t_decay:.1f}ms',      'cyan', y_decay_arrow),
        (t_trip,  t_recover, f'Recovery {t_recover-t_trip:.1f}ms', 'lime', y_recovery_arrow)]:
    ax.annotate('', xy=(t1, y_arr), xytext=(t0, y_arr),
                arrowprops=dict(arrowstyle='<->', color=col, lw=1.0))
    ax.text((t0 + t1) / 2, y_arr + v_range * 0.05, label, color=col, fontsize=8, ha='center')

# Event labels just inside the top of the plot
y_top = v_plateau + v_range * 0.05
ax.text(t_decay,   y_top, 'Decay\nstart', color='cyan', fontsize=7, ha='center', va='bottom')
ax.text(t_trip,    y_top, 'ACUV\ntrip',   color='red',  fontsize=7, ha='center', va='bottom')
ax.text(t_recover, y_top, 'Recovered',    color='lime', fontsize=7, ha='center', va='bottom')

# Min voltage annotation
ax.annotate(f'Min: {v[min_idx]:.3f}V',
            xy=(t[min_idx], v[min_idx]),
            xytext=(t[min_idx] + 3, v[min_idx] + 0.3),
            color='red', ha='left',
            arrowprops=dict(arrowstyle='->', color='red', relpos=(0, 0.5)),
            fontsize=9)

ax.axhline(9.0, color='red', linewidth=0.8, linestyle='--', label='Jetson min (9V)')

ax.set_xlabel('Time (ms)', color='white')
ax.set_ylabel('Voltage (V)', color='white')
ax.set_title('CH1 — UPS Switchover', color='white')
ax.tick_params(colors='white')
ax.grid(True, color='gray', alpha=0.4)
ax.legend(facecolor='#1a1a1a', labelcolor='white')
plt.tight_layout()
plt.savefig('waveform.png', dpi=150, facecolor=fig.get_facecolor())
plt.show()
