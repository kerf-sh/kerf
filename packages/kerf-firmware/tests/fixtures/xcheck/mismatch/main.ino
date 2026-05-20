/*
 * mismatch fixture — firmware uses pin 20 for SDA but the PCB routes SDA to pin 21.
 *
 * PCB has: pin 21 → SDA, pin 22 → SCL
 * Firmware uses: pin 20 for SDA (WRONG), pin 22 for SCL (correct)
 *
 * Expected violations:
 *   - pin_mismatch: pin 20 is used as SDA but pin 20 is NOT in the PCB footprint
 *   - OR pin 20 net is not SDA
 *   - missing_pins: ["20"] because pin 20 doesn't exist on this PCB
 */

#define SDA_PIN 20
#define SCL_PIN 22
#define LED_PIN 13

#include <Wire.h>

void setup() {
  Wire.begin(SDA_PIN, SCL_PIN);   // fw says SDA=20, but PCB has SDA on pin 21
  pinMode(LED_PIN, OUTPUT);
}

void loop() {
  digitalWrite(LED_PIN, HIGH);
  delay(500);
  digitalWrite(LED_PIN, LOW);
  delay(500);
}
