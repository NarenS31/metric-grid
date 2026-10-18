#include <Wire.h>
void setup() { Serial.begin(115200); delay(1000); }
void loop() {
  pinMode(SDA, INPUT_PULLDOWN); pinMode(SCL, INPUT_PULLDOWN); delay(5);
  int sda = digitalRead(SDA), scl = digitalRead(SCL);
  Serial.printf("SDA line %s | SCL line %s | found: ",
    sda ? "OK" : "DEAD", scl ? "OK" : "DEAD");
  Wire.begin();
  int n = 0;
  for (byte a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) { Serial.printf("0x%02X ", a); n++; }
  }
  Serial.println(n ? "" : "none");
  Wire.end();
  delay(2000);
}
