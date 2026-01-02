# @ & |

import tkinter as tk
from tkinter import BOTH, ttk
import lgpio

import serial
import time
import numpy as np
from scipy.signal import savgol_filter  # type: ignore

time.sleep(5)

# -------------------- Global scaling --------------------
SCALE = 0.5  # 0.5 => 480x640 becomes 240x320

def S(px: int) -> int:
    """Scale any pixel value."""
    return int(round(px * SCALE))

def SF(pt: int) -> int:
    """Scale font sizes in points."""
    return max(1, int(round(pt * SCALE)))

def F(name="Arial", size=12, style=None):
    """Build a Tk font tuple with scaled size."""
    if style:
        return (name, SF(size), style)
    return (name, SF(size))

BASE_W, BASE_H = 480, 640
WIN_W, WIN_H   = S(BASE_W), S(BASE_H)

# -------------------- Serial communication --------------------
SERIAL_PORT = '/dev/ttyACM0'
SERIAL_RATE = 9600
ser = serial.Serial(SERIAL_PORT, SERIAL_RATE, timeout=1)
ser.reset_input_buffer()

# Savitzky-Golay filter setup
window_length = 31
polyorder = 3

# -------------------- GPIO pins (BCM) --------------------
ARROW_DOWN_GPIO  = 17
ARROW_LEFT_GPIO  = 23
ARROW_RIGHT_GPIO = 27
OK_GPIO          = 22

chip = lgpio.gpiochip_open(0)
for pin in [ARROW_DOWN_GPIO, ARROW_LEFT_GPIO, ARROW_RIGHT_GPIO, OK_GPIO]:
    lgpio.gpio_claim_input(chip, pin, lgpio.SET_PULL_UP)

PIN_TO_NAME = {
    OK_GPIO: "ok",
    ARROW_DOWN_GPIO: "down",
    ARROW_LEFT_GPIO: "left",
    ARROW_RIGHT_GPIO: "right",
}

DEBOUNCE_MS = {
    OK_GPIO: 500,
    ARROW_DOWN_GPIO: 500,
    ARROW_LEFT_GPIO: 300,
    ARROW_RIGHT_GPIO: 300,
}

_prev_level = {pin: 1 for pin in PIN_TO_NAME}
_last_ts_ms = {pin: 0 for pin in PIN_TO_NAME}

ACTIVE_HANDLERS = {"ok": None, "down": None, "left": None, "right": None}

def set_active_handlers(mapping):
    for key in ACTIVE_HANDLERS:
        ACTIVE_HANDLERS[key] = mapping.get(key, None)

def _now_ms():
    return int(time.time() * 1000)

def poll_buttons():
    now = _now_ms()
    for pin, name in PIN_TO_NAME.items():
        level = lgpio.gpio_read(chip, pin)  # 1 idle, 0 pressed
        if _prev_level[pin] == 1 and level == 0:
            if (now - _last_ts_ms[pin]) >= DEBOUNCE_MS[pin]:
                _last_ts_ms[pin] = now
                handler = ACTIVE_HANDLERS.get(name)
                if handler:
                    handler()
        _prev_level[pin] = level
    root.after(10, poll_buttons)

# -------------------- UI & App Logic --------------------

root = tk.Tk()
W, H = 240, 320
SW, SH = 1920, 1080
X = (SW - W) // 2
Y = (SH - H) // 2
root.geometry(f"{W}x{H}+{X}+{Y}")

DEFAULT_BUTTON_COLOR = "#f0f0f0"
current_screen = None
focused_button = None

def remove_nan_ovf(array):
    i = 0
    while i < len(array):
        if array[i] == "ovf" or array[i] == "nan":
            array[i] = 0
        else:
            i += 1
    return array

def filter_and_find_peaks(data, window_length, polyorder):
    filtered_data = savgol_filter(data, window_length, polyorder)
    peak_index = np.argmax(filtered_data)
    min_index = np.argmin(filtered_data)
    return abs(peak_index - min_index)

def update_focus(button):
    global focused_button
    if focused_button:
        try:
            focused_button.config(bg=DEFAULT_BUTTON_COLOR)
        except tk.TclError:
            pass
    button.config(bg="green")
    focused_button = button

# -------- Page 1 - booting screen --------
def show_circle_with_text():
    global current_screen
    current_screen = "circle"
    set_active_handlers({})

    for w in root.winfo_children():
        w.destroy()

    canvas = tk.Canvas(root, width=WIN_W, height=WIN_H, highlightthickness=0)
    canvas.pack(fill=BOTH, expand=True)

    canvas.create_oval(S(80), S(160), S(400), S(480), outline="black", width=S(2), tags="circle")
    canvas.create_text(S(240), S(320), text="AmiNIC", font=F("Arial", 48), fill="black", tags="circle_text")

    root.after(5000, home_screen)

# -------- Page 2 - home screen (now with Temperature) --------
def home_screen():
    global current_screen, focused_button
    current_screen = "home"

    for widget in root.winfo_children():
        widget.destroy()

    # Buttons: New Measurement, Temperature, TURN OFF
    button1 = tk.Button(root, text="New Measurement", font=F("Arial", 28), bg=DEFAULT_BUTTON_COLOR)
    button1.place(x=S(60), y=S(160), width=S(360), height=S(80))

    button2 = tk.Button(root, text="Temperature", font=F("Arial", 28), bg=DEFAULT_BUTTON_COLOR)
    button2.place(x=S(60), y=S(260), width=S(360), height=S(80))

    button3 = tk.Button(root, text="TURN OFF", font=F("Arial", 28), bg=DEFAULT_BUTTON_COLOR)
    button3.place(x=S(140), y=S(360), width=S(200), height=S(80))

    # Start with button1 focused
    update_focus(button1)

    buttons_order = [button1, button2, button3]

    def focus_down():
        # cycle focus through 1 -> 2 -> 3 -> 1 ...
        idx = buttons_order.index(focused_button)
        next_btn = buttons_order[(idx + 1) % len(buttons_order)]
        update_focus(next_btn)

    def ok_action():
        if focused_button == button1:
            ser.write(b"init_start")
            show_loading_screen()
        elif focused_button == button2:
            ser.write(b"temp")
            show_temperature_loading()
        elif focused_button == button3:
            blank_screen()

    set_active_handlers({"down": focus_down, "ok": ok_action})

# -------- Page 0 - blank / turn off --------
def blank_screen():
    global current_screen
    current_screen = "blank"

    for widget in root.winfo_children():
        widget.destroy()

    set_active_handlers({})
    tk.Label(root, text="Turning off...", font=F("Arial", 28)).pack(pady=S(200))
    root.after(2000, home_screen)

# -------- Page 3 - initial sweep / loading --------
def show_loading_screen():
    global current_screen
    current_screen = "loading"

    set_active_handlers({})

    for widget in root.winfo_children():
        widget.destroy()

    frame = tk.Frame(root, width=WIN_W, height=WIN_H)
    frame.pack_propagate(False)
    frame.pack(expand=True)

    canvas = tk.Canvas(frame, width=WIN_W, height=WIN_H, highlightthickness=0)
    canvas.pack(expand=True)

    loading_label = tk.Label(canvas, text="Loading...", font=F("Arial", 36))
    canvas.create_window(S(240), S(200), window=loading_label)

    progress = ttk.Progressbar(canvas, orient="horizontal", length=S(400), mode="determinate")
    canvas.create_window(S(240), S(300), window=progress)

    progress["maximum"] = 100
    increment = 2.5

    def update_progress(value):
        if value <= 100:
            progress["value"] = value
            root.after(1000, update_progress, value + increment)
        else:
            def wait_and_read():
                if ser.in_waiting < 7:
                    root.after(50, wait_and_read)
                    return

                line1 = ser.readline().decode('utf-8').strip()
                line2 = ser.readline().decode('utf-8').strip()
                line3 = ser.readline().decode('utf-8').strip()
                line4 = ser.readline().decode('utf-8').strip()
                line5 = ser.readline().decode('utf-8').strip()
                line6 = ser.readline().decode('utf-8').strip()
                line7 = ser.readline().decode('utf-8').strip()  # temp & humidity

                data1 = remove_nan_ovf(line1)
                data2 = remove_nan_ovf(line2)
                data3 = remove_nan_ovf(line3)
                data4 = remove_nan_ovf(line4)
                data5 = remove_nan_ovf(line5)
                data6 = remove_nan_ovf(line6)
                # temp_hum = line7.split("&")  # not used here

                global init_phaseData1, init_phaseData2, init_phaseData3
                global init_magnitudeData1, init_magnitudeData2, init_magnitudeData3

                init_phaseData1     = np.fromstring(data1, dtype=float, sep=',')
                init_magnitudeData1 = np.fromstring(data2, dtype=float, sep=',')
                init_phaseData2     = np.fromstring(data3, dtype=float, sep=',')
                init_magnitudeData2 = np.fromstring(data4, dtype=float, sep=',')
                init_phaseData3     = np.fromstring(data5, dtype=float, sep=',')
                init_magnitudeData3 = np.fromstring(data6, dtype=float, sep=',')

                matrix1 = np.vstack([
                    init_phaseData1, init_magnitudeData1,
                    init_phaseData2, init_magnitudeData2,
                    init_phaseData3, init_magnitudeData3
                ])
                np.savetxt("/home/raspi/internship/init_phaseAndMagnitudeData.csv", matrix1.T, delimiter=",")

                show_examination_screen()

            wait_and_read()

    update_progress(0)

# -------- Page 4 - examination screen --------
def show_examination_screen():
    global current_screen, focused_button
    current_screen = "examination"

    for widget in root.winfo_children():
        widget.destroy()

    title = tk.Label(root, text="EXAMINATION", font=F("Arial", 36, "bold"))
    title.pack(pady=S(40))

    instruction = tk.Label(
        root,
        text="Please put and hold the device as close to the meat as possible",
        font=F("Arial", 24, "italic"),
        wraplength=S(440),
        justify="center"
    )
    instruction.pack(pady=S(40))

    start_button = tk.Button(root, text="START", font=F("Arial", 28), bg=DEFAULT_BUTTON_COLOR)
    start_button.pack(side="bottom", pady=S(40))

    focused_button = start_button
    update_focus(focused_button)

    def ok_action():
        if focused_button == start_button:
            ser.write(b"start")
            ser.flushInput()
            show_countdown_screen()

    set_active_handlers({"ok": ok_action})

# -------- Page 5 - countdown --------
def show_countdown_screen():
    global current_screen
    current_screen = "countdown"

    for widget in root.winfo_children():
        widget.destroy()

    set_active_handlers({})

    label = tk.Label(root, text="Hold it for:", font=F("Arial", 32, "bold"))
    label.pack(pady=S(80))

    countdown_label = tk.Label(root, text="45", font=F("Arial", 96))
    countdown_label.pack(pady=S(40))

    def countdown_timer(count):
        if count >= 0:
            countdown_label.config(text=str(count))
            root.after(1000, countdown_timer, count - 1)
        else:
            def wait_and_read_normal():
                if ser.in_waiting < 7:
                    root.after(50, wait_and_read_normal)
                    return

                line11 = ser.readline().decode('utf-8').strip()
                line22 = ser.readline().decode('utf-8').strip()
                line33 = ser.readline().decode('utf-8').strip()
                line44 = ser.readline().decode('utf-8').strip()
                line55 = ser.readline().decode('utf-8').strip()
                line66 = ser.readline().decode('utf-8').strip()
                line77 = ser.readline().decode('utf-8').strip()

                data11 = remove_nan_ovf(line11)
                data22 = remove_nan_ovf(line22)
                data33 = remove_nan_ovf(line33)
                data44 = remove_nan_ovf(line44)
                data55 = remove_nan_ovf(line55)
                data66 = remove_nan_ovf(line66)
                temp_hum2 = line77.split("&")

                global normal_phaseData1, normal_phaseData2, normal_phaseData3
                global normal_magnitudeData1, normal_magnitudeData2, normal_magnitudeData3
                global tempData2, humData2

                normal_phaseData1     = np.fromstring(data11, dtype=float, sep=',')
                normal_magnitudeData1 = np.fromstring(data22, dtype=float, sep=',')
                normal_phaseData2     = np.fromstring(data33, dtype=float, sep=',')
                normal_magnitudeData2 = np.fromstring(data44, dtype=float, sep=',')
                normal_phaseData3     = np.fromstring(data55, dtype=float, sep=',')
                normal_magnitudeData3 = np.fromstring(data66, dtype=float, sep=',')

                tempData2 = float(temp_hum2[0]) if temp_hum2 and temp_hum2[0] else 0.0
                humData2  = float(temp_hum2[1]) if len(temp_hum2) > 1 and temp_hum2[1] else 0.0

                matrix2 = np.vstack([
                    normal_phaseData1, normal_magnitudeData1,
                    normal_phaseData2, normal_magnitudeData2,
                    normal_phaseData3, normal_magnitudeData3
                ])
                np.savetxt("/home/raspi/internship/normal_phaseAndMagnitudeData.csv", matrix2.T, delimiter=",")

                show_new_buttons()

            wait_and_read_normal()

    countdown_timer(40)

# -------- Page 6 - results (measurement) --------
def show_new_buttons():
    global current_screen, btn_back, focused_button
    current_screen = "measurement_results_screen"

    for widget in root.winfo_children():
        widget.destroy()

    frame = tk.Frame(root, width=WIN_W, height=WIN_H)
    frame.pack_propagate(False)
    frame.pack(side="left", fill="both", expand=True)

    frame.grid_rowconfigure(0, weight=1)
    frame.grid_rowconfigure(1, weight=0)
    frame.grid_rowconfigure(2, weight=0)
    frame.grid_rowconfigure(3, weight=0)
    frame.grid_rowconfigure(4, weight=1)
    frame.grid_columnconfigure(0, weight=1)

    # Filter & get peak value indexes from initial sweep
    init_phaseData1_filtered = savgol_filter(init_phaseData1, window_length, polyorder)
    init_phaseData2_filtered = savgol_filter(init_phaseData2, window_length, polyorder)
    init_phaseData3_filtered = savgol_filter(init_phaseData3, window_length, polyorder)

    init_phaseData1_peak_index = np.argmax(init_phaseData1_filtered)
    init_phaseData2_peak_index = np.argmax(init_phaseData2_filtered)
    init_phaseData3_peak_index = np.argmax(init_phaseData3_filtered)

    # Filter & get peak value indexes from normal sweep
    normal_phaseData1_filtered = savgol_filter(normal_phaseData1, window_length, polyorder)
    normal_phaseData2_filtered = savgol_filter(normal_phaseData2, window_length, polyorder)
    normal_phaseData3_filtered = savgol_filter(normal_phaseData3, window_length, polyorder)

    normal_phaseData1_peak_index = np.argmax(normal_phaseData1_filtered)
    normal_phaseData2_peak_index = np.argmax(normal_phaseData2_filtered)
    normal_phaseData3_peak_index = np.argmax(normal_phaseData3_filtered)

    phase_index_diff1 = abs(init_phaseData1_peak_index - normal_phaseData1_peak_index)
    phase_index_diff2 = abs(init_phaseData2_peak_index - normal_phaseData2_peak_index)
    phase_index_diff3 = abs(init_phaseData3_peak_index - normal_phaseData3_peak_index)

    # Magnitude min/max distance diffs
    init_magnitudeData1_indexDiff   = filter_and_find_peaks(init_magnitudeData1,   window_length, polyorder)
    init_magnitudeData2_indexDiff   = filter_and_find_peaks(init_magnitudeData2,   window_length, polyorder)
    init_magnitudeData3_indexDiff   = filter_and_find_peaks(init_magnitudeData3,   window_length, polyorder)
    normal_magnitudeData1_indexDiff = filter_and_find_peaks(normal_magnitudeData1, window_length, polyorder)
    normal_magnitudeData2_indexDiff = filter_and_find_peaks(normal_magnitudeData2, window_length, polyorder)
    normal_magnitudeData3_indexDiff = filter_and_find_peaks(normal_magnitudeData3, window_length, polyorder)

    magnitudeData1Result = abs(init_magnitudeData1_indexDiff - normal_magnitudeData1_indexDiff)
    magnitudeData2Result = abs(init_magnitudeData2_indexDiff - normal_magnitudeData2_indexDiff)
    magnitudeData3Result = abs(init_magnitudeData3_indexDiff - normal_magnitudeData3_indexDiff)

    temp_value = tempData2
    humidity_value = humData2

    labels_text = [
        f"Temperature: {temp_value}°C",
        f"Humidity: {humidity_value}%",
        f"Quality: {phase_index_diff1, phase_index_diff2, phase_index_diff3}"
    ]

    for i, text in enumerate(labels_text):
        label = tk.Label(frame, text=text, font=F("Arial", 28), anchor="w")
        label.grid(row=i + 1, column=0, sticky="w", padx=S(40), pady=S(10))

    btn_back = tk.Button(frame, text="BACK", font=F("Arial", 28), command=home_screen, bg=DEFAULT_BUTTON_COLOR)
    btn_back.grid(row=5, column=0, sticky="se", padx=S(16), pady=S(16))
    update_focus(btn_back)

    def focus_left():
        update_focus(btn_back)

    def ok_action():
        if focused_button == btn_back:
            home_screen()

    set_active_handlers({"left": focus_left, "ok": ok_action})

# ======== NEW: Temperature flow ========

def parse_temperature_line(line: str):
    """
    Accepts either '25.4' or '25.4&40.2'.
    Returns (temp_float, hum_float or None).
    """
    try:
        parts = [p.strip() for p in line.split("&")]
        if len(parts) == 1:
            t = float(parts[0]) if parts[0] else 0.0
            return t, None
        elif len(parts) >= 2:
            t = float(parts[0]) if parts[0] else 0.0
            h = float(parts[1]) if parts[1] else None
            return t, h
    except Exception:
        pass
    return 0.0, None

def show_temperature_loading():
    """Screen shown right after sending b'temp'."""
    global current_screen
    current_screen = "temperature_loading"

    for widget in root.winfo_children():
        widget.destroy()

    set_active_handlers({})

    frame = tk.Frame(root, width=WIN_W, height=WIN_H)
    frame.pack_propagate(False)
    frame.pack(expand=True)

    canvas = tk.Canvas(frame, width=WIN_W, height=WIN_H, highlightthickness=0)
    canvas.pack(expand=True)

    label = tk.Label(canvas, text="Getting temperature...", font=F("Arial", 32))
    canvas.create_window(S(240), S(200), window=label)

    spinner = ttk.Progressbar(canvas, orient="horizontal", length=S(400), mode="indeterminate")
    canvas.create_window(S(240), S(280), window=spinner)
    spinner.start(10)

    # poll serial until a line arrives
    def poll_for_temp():
        if ser.in_waiting > 0:
            raw = ser.readline().decode("utf-8").strip()
            t, h = parse_temperature_line(raw)
            show_temperature_result_screen(t, h)
        else:
            root.after(50, poll_for_temp)

    poll_for_temp()

def show_temperature_result_screen(temp_value: float, humidity_value=None):
    """Result page with BACK button (same focus/OK behavior)."""
    global current_screen, focused_button
    current_screen = "temperature_result"

    for widget in root.winfo_children():
        widget.destroy()

    frame = tk.Frame(root, width=WIN_W, height=WIN_H)
    frame.pack_propagate(False)
    frame.pack(side="left", fill="both", expand=True)

    frame.grid_rowconfigure(0, weight=1)
    frame.grid_rowconfigure(1, weight=0)
    frame.grid_rowconfigure(2, weight=0)
    frame.grid_rowconfigure(3, weight=1)
    frame.grid_columnconfigure(0, weight=1)

    title = tk.Label(frame, text="TEMPERATURE", font=F("Arial", 36, "bold"))
    title.grid(row=0, column=0, padx=S(40), pady=S(20), sticky="w")

    lines = [f"Temperature: {temp_value:.2f}°C"]
    if humidity_value is not None:
        lines.append(f"Humidity: {humidity_value:.2f}%")

    for i, text in enumerate(lines, start=1):
        lbl = tk.Label(frame, text=text, font=F("Arial", 28), anchor="w")
        lbl.grid(row=i, column=0, sticky="w", padx=S(40), pady=S(10))

    btn_back = tk.Button(frame, text="BACK", font=F("Arial", 28), command=home_screen, bg=DEFAULT_BUTTON_COLOR)
    btn_back.grid(row=3, column=0, sticky="se", padx=S(16), pady=S(16))
    update_focus(btn_back)

    def focus_left():
        update_focus(btn_back)

    def ok_action():
        if focused_button == btn_back:
            home_screen()

    set_active_handlers({"left": focus_left, "ok": ok_action})

# -------------------- App start/stop --------------------
show_circle_with_text()
poll_buttons()

try:
    root.mainloop()
finally:
    try:
        lgpio.gpiochip_close(chip)
    except Exception:
        pass
