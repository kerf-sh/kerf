/*
 * match fixture — firmware whose pins all exist on the PCB and are correctly wired.
 *
 * PCB has: pin 21 → SDA, pin 22 → SCL, pin 13 → LED
 * Firmware uses exactly those pins.
 */

#define SDA_PIN 21
#define SCL_PIN 22
#define LED_PIN 13

#include <Wire.h>

void setup() {
  Wire.begin(SDA_PIN, SCL_PIN);   // I2C on 21 (SDA) and 22 (SCL)
  pinMode(LED_PIN, OUTPUT);
}

void loop() {
  digitalWrite(LED_PIN, HIGH);
  delay(500);
  digitalWrite(LED_PIN, LOW);
  delay(500);
}
