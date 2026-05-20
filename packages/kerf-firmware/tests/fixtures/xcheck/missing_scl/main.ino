/*
 * missing_scl fixture — firmware uses I2C but only specifies SDA; no SCL declared.
 *
 * The firmware calls Wire.begin() with only one argument (SDA).
 * This should be flagged as an incomplete I2C bus (SCL is missing).
 *
 * Expected violations:
 *   - bus_incomplete: "I2C: SDA declared (pin 21) but SCL missing from firmware"
 */

#define SDA_PIN 21
#define LED_PIN 13

#include <Wire.h>

void setup() {
  // Wire.begin with one arg — only SDA provided, SCL not specified
  // Firmware never declares SCL_PIN.
  Wire.begin(SDA_PIN);
  pinMode(LED_PIN, OUTPUT);
}

void loop() {
  // read from an I2C device — but we never configured SCL
  Wire.requestFrom(0x48, 2);
  delay(100);
}
