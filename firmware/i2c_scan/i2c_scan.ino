#include <Wire.h>
void setup() {
  Serial.begin(115200);
  delay(1000);
#ifdef NEOPIXEL_I2C_POWER
  pinMode(NEOPIXEL_I2C_POWER, OUTPUT);
  digitalWrite(NEOPIXEL_I2C_POWER, HIGH);
#endif
  Wire.begin();
}
void loop() {
  int n = 0;
  for (byte a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) { Serial.print("Found 0x"); Serial.println(a, HEX); n++; }
  }
  Serial.println(n ? "Done.\n" : "Nothing found. Check wiring.\n");
  delay(3000);
}
