# Analog Filter Design

Kerf provides a full analog filter design toolkit: order estimation, pole calculation, ladder g-values, frequency/impedance denormalisation (LP/HP/BP), and op-amp active filter component selection (Sallen-Key and MFB).

## When to use

Use these tools when you need to:
- Find the minimum filter order (Butterworth, Chebyshev-I, or Bessel) for a passband/stopband specification
- Compute normalised prototype pole locations for filter analysis or cascade design
- Get Butterworth or Chebyshev ladder g-values for passive RLC filter design
- Denormalise a prototype to LP, HP, or BP RLC element values at a target frequency and impedance
- Design a Sallen-Key or MFB second-order op-amp active filter stage
- Evaluate frequency response (magnitude, phase, group delay) at a specific frequency

Trigger keywords: Butterworth filter, Chebyshev filter, Bessel filter, filter order, filter design, lowpass filter, highpass filter, bandpass filter, LP prototype, g-values, RLC filter, Sallen-Key, MFB, Multiple-Feedback, active filter, op-amp filter, filter poles, filter response, cutoff frequency, stopband attenuation.

## Tools

| Tool | Purpose |
|---|---|
| `afilter_butterworth_order` | Minimum Butterworth LP order from passband_freq_hz, stopband_freq_hz, passband_ripple_db, stopband_atten_db |
| `afilter_chebyshev_order` | Minimum Chebyshev-I LP order from the same passband/stopband spec |
| `afilter_bessel_order` | Minimum Bessel order for a group-delay flatness target over a bandwidth ratio |
| `afilter_butterworth_poles` | Normalised LP prototype pole locations for a Butterworth filter of given order |
| `afilter_chebyshev_poles` | Normalised LP prototype poles for a Chebyshev-I filter of given order and ripple |
| `afilter_bessel_poles` | Normalised LP prototype poles for a Bessel/Thomson filter (orders 1–10) |
| `afilter_butterworth_g` | Doubly-terminated Butterworth ladder g-values for a given order |
| `afilter_chebyshev_g` | Doubly-terminated Chebyshev-I ladder g-values for given order and ripple |
| `afilter_lp_to_lp` | Denormalise LP prototype g-values → LP RLC elements at cutoff_freq_hz and impedance_ohm |
| `afilter_lp_to_hp` | Denormalise LP prototype g-values → HP RLC elements at a cutoff frequency |
| `afilter_lp_to_bp` | Denormalise LP prototype g-values → BP RLC resonator pairs at center_freq_hz and bandwidth_hz |
| `afilter_sallen_key` | Equal-component Sallen-Key 2nd-order LP op-amp design; inputs: cutoff_freq_hz, Q, gain, capacitor_f |
| `afilter_mfb` | Multiple-Feedback (Rauch) inverting 2nd-order LP op-amp design; inputs: cutoff_freq_hz, Q, gain, capacitor_f |
| `afilter_response` | Evaluates H(jω) magnitude [dB], phase [deg], and group delay [s] from poles/zeros at freq_hz |

## Example

**User ask:** "I need a 4th-order Butterworth lowpass at 10 kHz, 50 Ω terminated, to feed an ADC."

1. Call `afilter_butterworth_g` with `order=4` → get g-values.
2. Call `afilter_lp_to_lp` with those g-values, `cutoff_freq_hz=10000`, `impedance_ohm=50` → get R and C values for the ladder.
