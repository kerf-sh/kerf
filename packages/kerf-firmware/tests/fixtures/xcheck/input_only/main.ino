/*
 * input_only fixture — firmware drives pin 0 (BOOT) as OUTPUT, but the PCB
 * routes pin 0 to an INPUT_ONLY_BOOT net (hardware constraint: this pin is
 * boot-strapping only and must not be driven).
 *
 * Expected violations:
 *   - wrong_load: [("0", "input-only net ('INPUT_ONLY_BOOT')")]
 */

#define LED_PIN  13
#define BOOT_PIN  0   // PCB routes this to INPUT_ONLY_BOOT

void setup() {
  pinMode(LED_PIN, OUTPUT);
  pinMode(BOOT_PIN, OUTPUT);  // WRONG: this net is input-only
}

void loop() {
  digitalWrite(LED_PIN, HIGH);
  digitalWrite(BOOT_PIN, HIGH);  // driving input-only net
  delay(500);
  digitalWrite(LED_PIN, LOW);
  digitalWrite(BOOT_PIN, LOW);
  delay(500);
}
