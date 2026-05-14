# Blink LED

Minimal ATtiny85 LED blinker on USB-C power.

## Files

- `main.circuit.tsx` — tscircuit schematic: ATtiny85, red LED, 220R resistor, 10µF cap, USB-C connector
- `led.simulation` — DC operating point analysis

## Circuit

- ATtiny85 pin 1 (PB5) → 220R resistor → LED anode → LED cathode → GND
- 10µF decoupling cap between VCC and GND
- USB-C provides 5V power to VCC/GND
