#include <Wire.h>
int scanWith(int sda, int scl) {
  Wire.begin(sda, scl);
  int n = 0;
  for (byte a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) { Serial.printf("0x%02X ", a); n++; }
  }
  Wire.end();
  return n;
}
void setup() { Serial.begin(115200); delay(1000); }
void loop() {
  pinMode(SDA, INPUT); pinMode(SCL, OUTPUT); digitalWrite(SCL, LOW); delay(2);
  bool shorted = digitalRead(SDA) == LOW;
  pinMode(SCL, INPUT);
  Serial.printf("SDA-SCL bridge: %s | normal: ", shorted ? "YES" : "no");
  if (!scanWith(SDA, SCL)) Serial.print("none");
  Serial.print(" | swapped: ");
  if (!scanWith(SCL, SDA)) Serial.print("none");
  Serial.println();
  delay(2000);
}
