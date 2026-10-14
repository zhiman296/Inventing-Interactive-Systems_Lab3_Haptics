//  Snow & Rain Walk
// Motor driver
const int enA = 13;
const int in1 = 12;
const int in2 = 14;

// Joystick
const int joyX  = 34;   // VRx 
const int joyY  = 35;   // VRy
const int joySW = 32;   // SW button

// VIBRATION PATTERNS
// One step = start PWM, end PWM, duration in ms
struct Step {
  int startPWM;
  int endPWM;
  int durationMs;
};

// SNOW footstep (about 300 ms).
const Step snowPattern[] = {
  {0,   200, 20},    
  {200, 60,  25},
  {60,  230, 25},    
  {230, 60,  25},
  {60,  255, 30},    
  {255, 70,  25},
  {70,  230, 30},   
  {230, 50,  25},
  {50,  170, 25},    
  {170, 40,  25},
  {40,  0,   45}     
};

// RAIN drops: short taps. Three strengths.
const Step rainLightPattern[] = {
  {0,   200, 20},
  {200, 0,   30}
};

const Step rainMediumPattern[] = {
  {0,   230, 22},
  {230, 0,   35}
};

const Step rainHeavyPattern[] = {
  {0,   255, 25},
  {255, 255, 10},
  {255, 0,   40}
};

//PATTERN PLAYER
const Step* currentPattern = nullptr;
int  currentLength = 0;
int  currentScale = 100;      
int  stepIndex = 0;
unsigned long stepStartTime = 0;
bool playing = false;

void startPattern(const Step* pattern, int length, int scalePercent) {
  currentPattern = pattern;
  currentLength = length;
  currentScale = scalePercent;
  stepIndex = 0;
  stepStartTime = millis();
  playing = true;
}

// Call this every time through loop()
void updateVibration() {
  if (!playing) return;

  unsigned long elapsed = millis() - stepStartTime;
  Step s = currentPattern[stepIndex];

  // Check if current step finished.
  if (elapsed >= (unsigned long)s.durationMs) {
    stepIndex++;
    if (stepIndex >= currentLength) {
      playing = false;
      analogWrite(enA, 0);
      return;
    }
    stepStartTime = millis();
    s = currentPattern[stepIndex];
    elapsed = 0;
  }

  int pwm = map((long)elapsed, 0, s.durationMs, s.startPWM, s.endPWM);
  pwm = pwm * currentScale / 100;
  analogWrite(enA, pwm);
}

//JOYSTICK
int centerX = 2048;
int centerY = 2048;
unsigned long lastSend = 0;

int averageRead(int pin) {
  long total = 0;
  for (int i = 0; i < 30; i++) {
    total += analogRead(pin);
    delay(5);
  }
  return total / 30;
}

void sendJoystick() {
  int x = analogRead(joyX) - centerX;
  int y = analogRead(joyY) - centerY;
  int button = (digitalRead(joySW) == LOW) ? 1 : 0;

  Serial.print("J,");
  Serial.print(x);
  Serial.print(",");
  Serial.print(y);
  Serial.print(",");
  Serial.println(button);
}

void readCommands() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    switch (c) {
      // snow footsteps (same pattern, three strengths)
      case 'H': startPattern(snowPattern, sizeof(snowPattern) / sizeof(Step), 100); break;
      case 'S': startPattern(snowPattern, sizeof(snowPattern) / sizeof(Step), 88);  break;
      case 'L': startPattern(snowPattern, sizeof(snowPattern) / sizeof(Step), 74);  break;
      // rain drops
      case 'r': startPattern(rainLightPattern,  sizeof(rainLightPattern)  / sizeof(Step), 100); break;
      case 'm': startPattern(rainMediumPattern, sizeof(rainMediumPattern) / sizeof(Step), 100); break;
      case 'R': startPattern(rainHeavyPattern,  sizeof(rainHeavyPattern)  / sizeof(Step), 100); break;
      default: break;  // ignore newlines and anything else
    }
  }
}

//LOOP
void setup() {
  Serial.begin(115200);

  pinMode(enA, OUTPUT);
  pinMode(in1, OUTPUT);
  pinMode(in2, OUTPUT);
  pinMode(joySW, INPUT_PULLUP);

  // Motor direction is set once; speed is controlled by PWM on enA
  digitalWrite(in1, HIGH);
  digitalWrite(in2, LOW);
  analogWrite(enA, 0);

  // Find the joystick's resting position
  delay(500);
  centerX = averageRead(joyX);
  centerY = averageRead(joyY);
}

void loop() {
  readCommands();
  updateVibration();

  if (millis() - lastSend >= 20) {   // 50 times per second
    lastSend = millis();
    sendJoystick();
  }
}
