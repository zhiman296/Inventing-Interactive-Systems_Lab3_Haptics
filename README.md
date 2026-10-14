# Snow & Rain Walk

[Demo video]https://youtu.be/vbMUu-Nmarw

Snow & Rain Walk is a haptic walking experience controlled by a handheld controller.  
Push the joystick forward or backward to walk through a snowy, rainy environment. 
Each footstep produces a crunching sound and a synchronized vibration from the motor. 
Raindrops fall around you, accompanied by sounds and matching haptic feedback. The audio and vibrations work together to create an immersive sensory experience.

## How it works
- The ESP32 reads the joystick position and sends the data to the computer.
- The game uses the joystick input to move the player forward or backward through the environment.
- When a footstep or raindrop event occurs, the game plays the corresponding sound while the ESP32 triggers a synchronized vibration pattern on the motor.

## Setup Instructions
1. Connect the circuit as shown in the circuit diagram below.
2. Open the .ino file in the Arduino IDE and upload the code to the ESP32.
3. Run the game by executing Snow&RainWalk.py.
4. Hold the controller and move the joystick forward or backward to begin walking.

Circuit Connections:
<img width="2891" height="3855" alt="circuit connection" src="https://github.com/user-attachments/assets/2bce3948-061e-4134-8e8a-1c319e427951" />

## How to play
- Hold the joystick controller in one hand and the vibration motor in the other.
- Push the joystick forward. Pull the joystick backward. Release the joystick to stop.
- Listen to the crunching sounds and notice the synchronized vibrations. Different vibration intensities create the sensation of lighter and heavier footsteps.
- As you walk, listen for falling raindrops and feel the corresponding taps from the vibration motor.

