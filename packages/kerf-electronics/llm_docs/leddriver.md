# LED Driver and Lighting Electronics Design

Kerf provides LED driver design tools covering string layout, series-resistor sizing, topology selection (linear vs switching), buck/boost CC converter design, thermal derating, and PWM dimming analysis.

## When to use

Use these tools when you need to:
- Determine the series/parallel LED string configuration for a given supply voltage, target lumen output, and LED spec
- Size a series resistor for a simple LED circuit and estimate efficiency
- Decide whether a linear (LDO-type) or switching (buck or boost) driver is appropriate
- Design a buck or boost constant-current LED driver (duty cycle, inductor, output cap, switch stress)
- Compute LED junction temperature and lumen/Vf derating from thermal resistance and ambient
- Analyse PWM dimming: average current, brightness ratio, percent flicker, ENERGY STAR compliance

Trigger keywords: LED driver, LED string, LED layout, constant current driver, buck LED driver, boost LED driver, LED thermal, lumen derating, junction temperature, forward voltage, Vf, LED efficiency, PWM dimming, flicker, LED lighting, series resistor, LED current.

## Tools

| Tool | Purpose |
|---|---|
| `led_string_layout` | Computes n_series, n_parallel, total LEDs, string voltage, total current, achievable lumens, and efficiency from supply_v, target_lumens, led_vf, led_if_a, led_lumens |
| `led_series_resistor` | Sizes a series resistor and computes resistor power, LED power, and efficiency from supply_v, led_vf, led_if_a, n_series |
| `led_driver_topology` | Recommends linear CC or switching (buck/boost) topology from supply_v, v_string_v, led_if_a, efficiency_threshold |
| `led_buck_cc_design` | Designs a buck CC LED driver: duty cycle, inductor, output cap, switch stress; inputs: v_in, v_string, i_led, fsw_hz |
| `led_boost_cc_design` | Designs a boost CC LED driver (step-up): duty cycle, inductor, output cap, switch stress; inputs: v_in, v_string, i_led, fsw_hz |
| `led_thermal_derating` | Computes LED junction temperature and derated lumens/Vf from p_dissipated_w, rth_jc, rth_cs, t_ambient_c, lm_rated, vf_rated_v |
| `led_pwm_dimming` | Computes average current, brightness ratio, percent flicker, and visible-flicker risk for pwm_freq_hz, duty_cycle, i_peak_a |

## Example

**User ask:** "I have a 24 V supply and want 3000 lm from 3.2 V / 350 mA / 120 lm LEDs. What string config do I need and should I use a buck driver?"

1. Call `led_string_layout` with `supply_v=24`, `target_lumens=3000`, `led_vf=3.2`, `led_if_a=0.35`, `led_lumens=120` → get n_series, n_parallel, string voltage.
2. Call `led_driver_topology` with the returned v_string_v and `led_if_a=0.35` → get topology recommendation.
3. If buck recommended, call `led_buck_cc_design` for inductor and cap values.
