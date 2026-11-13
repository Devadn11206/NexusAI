import os
import time
import subprocess
import ctypes
import pygetwindow as gw

u32 = ctypes.windll.user32
h_def = u32.OpenDesktopW('Default', 0, False, 0x01FF)
u32.SetThreadDesktop(h_def)

print("Launching Spotify...")
try:
    os.startfile("spotify:")
except Exception as e:
    print("startfile error:", e)
    subprocess.Popen('start "" "spotify:"', shell=True)

time.sleep(3)

found = []
for w in gw.getAllWindows():
    if w.title.strip():
        found.append(w.title)
        if "spotify" in w.title.lower():
            print(f"Spotify window found: HWND={w._hWnd}, Title='{w.title}'")

if not any("spotify" in t.lower() for t in found):
    print("Spotify not found in window titles yet. Total windows:", len(found))

