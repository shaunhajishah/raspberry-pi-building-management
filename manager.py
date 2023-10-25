#!/usr/bin/python3

import smbus
from RPLCD.i2c import CharLCD
import Adafruit_DHT
import RPi.GPIO as GPIO
import time
import requests
from datetime import datetime
import threading

GPIO.setwarnings(False)		# to disable warnings
GPIO.cleanup()

# Set the GPIO pins for the LEDs, Buttons, and PIR
LED_G = 12
LED_B = 23
LED_R = 18
BTN_R = 20
BTN_B = 21
BTN_Y = 6
PIR = 19

GPIO.setmode(GPIO.BCM)
# Set all the buttons and pir as inputs
GPIO.setup(BTN_R, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BTN_B, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BTN_Y, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PIR, GPIO.IN)
# Set all the led pins as outputs
GPIO.setup(LED_G, GPIO.OUT) 
GPIO.setup(LED_B, GPIO.OUT)
GPIO.setup(LED_R, GPIO.OUT)

#Global variables#
temperature = 75 # Temperature that is measured using the DHT11 sensor
humidity = 60 # Humidity value from CIMIS data
weather_index = 75 # Weather index calculated using temp and humidity
hvac_temp = 75 # HVAC temp the user sets
hvac_heat = False # State for the heater
hvac_ac = False # State for the ac
hvac_change_state = 0 # 0-no change, 1-hvac off, 2-heat on, 3-ac on, 4-paused for door/window
hvac_previous_state = False # Tracks if the hvac was previously on when paused
lights_on = False # State of the lights
fire = False # State of the fire alarm
fire_alarm_temp = 95 # Temperature the fire alarm kicks in at
door_window_open = False # State of the door/window
door_window_changed_state = False # Track if the state has changed for displaying purposes
time_counter = 0.0 # Counter used by the lights
hvac_total_kwh = 0.0 # Total energy used by the hvac


def get_temperature(): # This function uses the DHT11 sensor to get the current temperature 
    # Define which global variables are used
    global temperature
    global weather_index
    global humidity
    global fire
    global fire_alarm_temp
    global door_window_open
    DHT_type = Adafruit_DHT.DHT11 # Specify the type of sensor
    DHT_pin = 17 # GPIO pin for the sensor
    last_three = [] # Array used to store the last 3 temperature values
    while True: # Infinite loop that takes the temperature every second
        humidity, temp = Adafruit_DHT.read_retry(DHT_type, DHT_pin) # Take the temperature reading
        temp = (temp * 9/5) + 32 # Convert the temperature from celsius to fahrenheit
        last_three.append(temp) # Add the temp to the array
        if len(last_three) > 3: # If the array is larger than 3 remove the first value
            last_three.pop(0)
        temperature = sum(last_three) / len(last_three) # Calculate the average of the 3 temp values
        weather_index = round(temperature + (0.05 * humidity)) # Calculate the weather index using humidity value
        if weather_index > fire_alarm_temp: # Check if there is a fire by comparing weather_index to the fire cutoff temp
            # If there is a fire set the state and open doors/windows
            fire = True 
            door_window_open = True
        else:
            if fire: # If there is currently a fire check if it is gone
                # If there is no more fire set the state and turn off led
                fire = False
                GPIO.output(LED_G, GPIO.LOW)
                GPIO.output(LED_B, GPIO.LOW)
                GPIO.output(LED_R, GPIO.LOW)
        time.sleep(1)
        
        
        
def get_humidity():
    global humidity # Define humidity as the global variable
    url = "https://et.water.ca.gov/api/data?" # URL for CIMIS api endpoint
    while True: # Infinite loop that checks the hourly humidity value every 5 mins
        date = datetime.now().strftime("%Y-%m-%d") # Gets the current date in (yyyy-mm-dd) format
        params = { # Params used for api request
            "format": "json",
            "appKey": "3e11f877-1345-40c8-94cc-5a8a01fbbf35",
            "targets": "75", # Target 75 is the Irvine station
            "startDate": date,
            "endDate": date,
            "dataItems": "hly-rel-hum" # Aqcuires the hourly humidity value
            }
        response = requests.get(url, params=params) # Make the api call and gather response
        if response.status_code == 200: # Check if the request was successful
            try:
                data = response.json() # Convert json to python list
            except Exception as e:
                print("Error getting humidity:", e) # If json was not provided print the error
        else:
            print(f"Request failed with status code {response.status_code}") # If the request was not successful print an error
        data = data['Data']['Providers'][0]['Records'] # Extract the list of records from the list
        # Search the list for the most recent value. Start at the last value and iterate down until a value is found
        i = 23 
        while data[i]['HlyRelHum']['Value'] == None: # Iterate through the list and find the most recent value
            i -= 1
        humidity = data[i]['HlyRelHum']['Value'] # Set humidity equal to the most recent data value
        print("Humidity at",datetime.now().strftime("%H:%M -"), humidity + "%") # Print time and humidity to console
        time.sleep(300) # Wait 5 minutes
    
        

def handle_lcd():
    # Define which global variables are used
    global weather_index
    global hvac_temp
    global hvac_ac
    global hvac_heat
    global lights_on
    global hvac_change_state
    global hvac_previous_state
    global door_window_open
    global door_window_changed_state
    global hvac_total_kwh
    global fire
    i2c_address = 0x27 #Address of the lcd
    lcd = CharLCD('PCF8574', i2c_address)
    lcd.clear()
    while True: # Infinite loop that updates the lcd
        if fire: # Check if there is currently a fire
            # If there is a fire display a safety message
            lcd.clear()
            lcd.cursor_pos = (0, 1)
            lcd.write_string("Fire! Evacuate")
            lcd.cursor_pos = (1,3)
            lcd.write_string("D/W Open")
            while fire: # While there is a fire flash all the LED lights with 1 second period
                GPIO.output(LED_G, GPIO.HIGH)
                GPIO.output(LED_B, GPIO.HIGH)
                GPIO.output(LED_R, GPIO.HIGH)
                time.sleep(0.5)
                GPIO.output(LED_G, GPIO.LOW)
                GPIO.output(LED_B, GPIO.LOW)
                GPIO.output(LED_R, GPIO.LOW)
                time.sleep(0.5)
            lcd.clear()
        if door_window_changed_state: # Check if the door/window changed state
            # Clear lcd and reset cursor position
            lcd.clear()
            lcd.cursor_pos = (0, 0)
            if door_window_open: # If the door/window has been opened
                # Display message
                lcd.write_string("Door/Window Open")
                if hvac_previous_state or hvac_ac or hvac_heat: # If the hvac was running display pause message
                    lcd.cursor_pos = (1,1)
                    lcd.write_string("HVAC Halted")
            else: # If the door/window has been closed
                # Display message
                lcd.write_string("Door/Window Safe")
                if hvac_previous_state: # If hvac was previously on display resume message
                    lcd.cursor_pos = (1,1)
                    lcd.write_string("HVAC Resumed")
                    hvac_previous_state = False
            time.sleep(3) # Keep the message screen for 3 seconds then clear lcd
            lcd.clear()
            door_window_changed_state = False
        if hvac_change_state != 0: # Check if the hvac has changed state
            lcd.clear()
            energy_string = "{:.2f}".format(hvac_total_kwh) # Format the total energy number to 2 decimal places
            cost_string = "{:.2f}".format(hvac_total_kwh * 0.5) # Format the total cost number to 2 decimal places
            lcd.cursor_pos = (1, 0) # Move the cursor and print the total energy and cost strings
            lcd.write_string("E:" + energy_string + ",C:$" + cost_string)
            # Determine what the new HVAC state is and display the corresponding message
            if hvac_change_state == 1: #hvac off
                lcd.cursor_pos = (0, 2)
                lcd.write_string("HVAC is off")
            elif hvac_change_state == 2: # heat on
                lcd.cursor_pos = (0, 3)
                lcd.write_string("Heat is on")
            elif hvac_change_state == 3: # ac on
                lcd.cursor_pos = (0, 3)
                lcd.write_string("AC is on")
            time.sleep(3) # Display the new hvac state for 3 seconds then clear the lcd
            lcd.clear()
            hvac_change_state = 0
        lcd.cursor_pos = (0, 0) # Move the cursor to the starting position
        lcd.write_string(str(weather_index) + "/" + str(hvac_temp)) # Print the weather index as well as the hvac temperature 
        lcd.cursor_pos = (0,10) # MOve the cursor to print door/window status
        if door_window_open: # If the door/window is open print D:OPEN
            lcd.write_string("D:OPEN")
        else: # If the door/window is closed print D:SAFE
            lcd.write_string("D:SAFE")
        lcd.cursor_pos = (1, 0) # Move cursor to print hvac state
        # Determine the state off the hvac and print the corresponding state onto the lcd
        if hvac_ac: 
            lcd.write_string("H:AC  ")
        elif hvac_heat:
            lcd.write_string("H:HEAT")
        else:
            lcd.write_string("H:OFF ")
        lcd.cursor_pos = (1, 11) # Move the cursor to the bottom right to print the light status
        if lights_on: # If the lights rae on print L:ON
            lcd.write_string("L:ON ")
        else: # If the ligts are off print L:OFF
            lcd.write_string("L:OFF")
        
                
    
def handle_hvac():
    # Define which global variables are used
    global weather_index
    global hvac_temp
    global hvac_heat
    global hvac_ac
    global hvac_change_state
    global hvac_previous_state
    global hvac_total_kwh
    global door_window_open
    global fire
    while True: # Infinite loop that checks if hvac should be turned on/off every second
        if door_window_open and (hvac_heat or hvac_ac): #If the doors are open and the hvac is on pause it
            if hvac_heat: # If the heat was on
                hvac_previous_state = True # Set the previous state to on
                hvac_change_state = 0 # 0-no change, 1-hvac off, 2-heat on, 3-ac on, 4-paused for door/window
                hvac_heat = False # Turn the heat off
                GPIO.output(LED_R, GPIO.LOW) # Turn off the led
                hvac_total_kwh += ((time.time() - hvac_time) / 3600) * 36 # Add the energy usage to the total
            else: # If the ac was on
                hvac_previous_state = True # Set the previous state to on
                hvac_change_state = 0 
                hvac_ac = False # Turn the ac off
                GPIO.output(LED_B, GPIO.LOW) # Turn off the led
                hvac_total_kwh += ((time.time() - hvac_time) / 3600) * 18 # Add the energy usage to the total
        elif not door_window_open and (hvac_heat or hvac_ac): #If door closed and hvac on check if should be stopped
            if hvac_heat and weather_index >= hvac_temp: # If the heater is on and the temperature has reached the desired level
                hvac_change_state = 1	# 0-no change, 1-hvac off, 2-heat on, 3-ac on, 4-paused for door/window
                hvac_heat = False # Turn the heater off
                GPIO.output(LED_R, GPIO.LOW) # Turn off the led
                hvac_total_kwh += ((time.time() - hvac_time) / 3600) * 36 # Add energy usage to the total
            elif hvac_ac and weather_index <= hvac_temp: # If the ac is on and the temperature has reached the desired level
                hvac_change_state = 1
                hvac_ac = False # Turn the ac off
                GPIO.output(LED_B, GPIO.LOW) # Turn the led off
                hvac_total_kwh += ((time.time() - hvac_time) / 3600) * 18 # Add energy usage to the total
        #If hvac is off check if should be started
        elif not door_window_open and not (hvac_heat or hvac_ac): #If door closed and hvac off check if should be started
            difference = weather_index - hvac_temp # Get difference between temp and desired temp
            if difference > 2: # If the difference is 3 or greater in the positive direction turn ac on
                hvac_ac = True # Set ac on
                GPIO.output(LED_B, GPIO.HIGH) # Turn on led
                hvac_change_state = 3 # set state
            if difference < -2: # If difference is 3 or less in negative direction turn heater on
                hvac_heat = True # Set heater on
                GPIO.output(LED_R, GPIO.HIGH) # Turn on led
                hvac_change_state = 2 # Set state
            hvac_time = time.time() # Set the time hvac is turned on
        time.sleep(1)
        
    
    
def handle_button(pin): # This function handles the button clicks for hvac and door/window
    # Define which global variables are used
    global hvac_temp
    global door_window_open
    global door_window_changed_state
    if pin == BTN_Y: # If the yellow button is clicked open/close door/window
        door_window_open = not door_window_open 
        door_window_changed_state = True # Set the state to recently changed
    elif pin == BTN_R: # If the red button was pressed increase hvac temperature
        if hvac_temp != 95: # Make sure temp does not go above 95
            hvac_temp += 1
    elif pin == BTN_B: # If the blue button was pressed decrease hvac temperature
        if hvac_temp != 65: # Make sure temp does not go below 65
            hvac_temp -= 1

    
    
def light_control(): # This function handles the ambient lighting using the pir sensor
    # Define which global variables are used
    global lights_on
    global time_counter
    lights_on = True # Set the state to lights on
    GPIO.output(LED_G, GPIO.HIGH) # Turn on the led
    time_counter = time.time()  # Store current time to keep track of 10 second criteria
    while True: 
        if time.time() - time_counter >= 10:   # Check if current time is 10 or more seconds past the stored time
            GPIO.output(LED_G, GPIO.LOW) # Turn the led off
            lights_on = False # Set the state to lights off
            break
        time.sleep(0.3) # Check for time every 0.3 seconds



def handle_pir(channel): # This function is called when the pir sensor detects motion. It handles the light logic
    # Define which global variables are used
    global time_counter
    global lights_on
    if lights_on: # If the lights are currently on
        time_counter = time.time() # Reset time counter to current time
    else: # If lights are off
        t = threading.Thread(target=light_control) # Start a thread to handle lights
        t.daemon = True
        t.start() # start threading
    
    
#Humidity thread will use CIMIS api to get hourly humidity value for Irvine
humidity_thread = threading.Thread(target=get_humidity)
# Temperature thread will continually run the temperature function to indefinetly get temperature
temperature_thread = threading.Thread(target=get_temperature)
# lcd thread will continually run lcd function to update display
lcd_thread = threading.Thread(target=handle_lcd)
# Hvac thread will eun the hvac function to indefinetlly control hvac on/off
hvac_thread = threading.Thread(target=handle_hvac)

# Start the threads
humidity_thread.start()
temperature_thread.start()
lcd_thread.start()
hvac_thread.start()

# Add event detection for the buttons and pir sensor
GPIO.add_event_detect(BTN_R, GPIO.BOTH, handle_button, 400)
GPIO.add_event_detect(BTN_B, GPIO.BOTH, handle_button, 400)
GPIO.add_event_detect(BTN_Y, GPIO.BOTH, handle_button, 400)
GPIO.add_event_detect(PIR, GPIO.RISING, handle_pir)

# Loop to run program and cleanup once done
try:
    while True:
        time.sleep(1e6)
finally:
    GPIO.output(LED_G, GPIO.LOW)
    GPIO.output(LED_B, GPIO.LOW)
    GPIO.output(LED_R, GPIO.LOW)
    GPIO.cleanup()
    
