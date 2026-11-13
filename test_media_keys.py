import pyautogui
import time

pyautogui.FAILSAFE = False

print("Testing media commands:")
# Test next
pyautogui.press('nexttrack')
print("Pressed nexttrack")
time.sleep(0.5)

# Test pause
pyautogui.press('playpause')
print("Pressed playpause")

