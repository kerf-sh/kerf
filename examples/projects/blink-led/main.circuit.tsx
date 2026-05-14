import { Circuit } from "tscircuit"

export default (
  <board width="40mm" height="30mm">
    <chip
      name="U1"
      chipName="ATtiny85"
      footprint="DIP-8"
      pcbX={10}
      pcbY={15}
      schX={0}
      schY={0}
    />
    <led
      name="D1"
      pcbX={25}
      pcbY={15}
      schX={5}
      schY={0}
      color="red"
    />
    <resistor
      name="R1"
      resistance="220"
      footprint="0805"
      pcbX={25}
      pcbY={8}
      schX={5}
      schY={-3}
    />
    <capacitor
      name="C1"
      capacitance="10uF"
      footprint="0805"
      pcbX={10}
      pcbY={5}
      schX={0}
      schY={-3}
    />
    <connector
      name="USB"
      footprint="USB-C"
      pcbX={35}
      pcbY={20}
      schX={10}
      schY={5}
    />
    <trace from=".U1 > .pin1" to=".R1 > .pin1" />
    <trace from=".R1 > .pin2" to=".D1 > .pin1" />
    <trace from=".D1 > .pin2" to="net.GND" />
    <trace from=".C1 > .pin1" to=".U1 > .pin1" />
    <trace from=".C1 > .pin2" to="net.GND" />
    <trace from=".USB > .VCC" to=".U1 > .pin8" />
    <trace from=".USB > .GND" to="net.GND" />
  </board>
)
