# DSP and Digital Filter Design

Kerf provides DSP tools: radix-2 FFT/IFFT, DFT spectrum analysis, windowed-sinc FIR design (LP/HP/BP), FIR tap-count estimation, bilinear-transform Butterworth IIR design, RBJ biquad coefficients (LP/HP/BP/notch/peaking), frequency response evaluation, group delay, Nyquist aliasing check, and ADC SNR/ENOB calculation.

## When to use

Use these tools when you need to:
- Compute the FFT or IFFT of a sample sequence, or the one-sided magnitude/phase spectrum of a real signal
- Find the frequency of a specific DFT bin given sample rate
- Design a windowed-sinc FIR lowpass, highpass, or bandpass filter with a chosen window (rect/hann/hamming/blackman)
- Estimate how many FIR taps are needed for a given transition bandwidth and window
- Design a digital Butterworth IIR lowpass or highpass filter via the bilinear transform with frequency prewarping
- Get RBJ cookbook biquad coefficients for lowpass, highpass, bandpass, notch, or peaking EQ sections
- Evaluate H(e^jω) magnitude and phase at a single frequency from b/a coefficients
- Compute group delay at a frequency
- Check if a sample rate meets the Nyquist criterion for a signal bandwidth
- Calculate theoretical ADC SNR, ENOB, and process gain from oversampling

Trigger keywords: FFT, IFFT, DFT, spectrum, frequency analysis, FIR filter, windowed sinc, FIR design, FIR taps, Butterworth IIR, bilinear transform, biquad, lowpass, highpass, bandpass, notch filter, peaking EQ, frequency response, group delay, Nyquist, aliasing, ADC SNR, ENOB, oversampling, digital filter design, DSP.

## Tools

| Tool | Purpose |
|---|---|
| `dsp_fft` | Radix-2 Cooley-Tukey FFT of a real or complex sequence (power-of-2 length); returns complex X[k] |
| `dsp_ifft` | Radix-2 IFFT of a frequency-domain sequence; returns complex x[n] |
| `dsp_spectrum` | One-sided DFT magnitude/phase spectrum of a real signal with bin frequencies; inputs: x (samples), fs_hz |
| `dsp_bin_frequency` | Frequency of DFT bin k: f = k × fs / N; inputs: k, N, fs_hz |
| `dsp_fir_lp` | Windowed-sinc lowpass FIR coefficients; inputs: N (taps), fc_norm (normalised cutoff), window |
| `dsp_fir_hp` | Windowed-sinc highpass FIR via spectral inversion; inputs: N (odd), fc_norm, window |
| `dsp_fir_bp` | Windowed-sinc bandpass FIR (LP difference); inputs: N, fl_norm, fh_norm, window |
| `dsp_fir_order` | Estimates minimum FIR tap count for a transition bandwidth and window (harris rule-of-thumb) |
| `dsp_iir_butterworth_lp` | Digital Butterworth LP IIR via bilinear transform with prewarping; inputs: order, fc_hz, fs_hz; returns b/a coefficients |
| `dsp_iir_butterworth_hp` | Digital Butterworth HP IIR via bilinear transform; inputs: order, fc_hz, fs_hz |
| `dsp_biquad_lp` | RBJ cookbook lowpass biquad; inputs: fc_hz, fs_hz, Q; returns b/a coefficients |
| `dsp_biquad_hp` | RBJ cookbook highpass biquad; inputs: fc_hz, fs_hz, Q |
| `dsp_biquad_bp` | RBJ cookbook bandpass biquad (0 dB peak); inputs: fc_hz, fs_hz, Q |
| `dsp_biquad_notch` | RBJ cookbook notch biquad; inputs: fc_hz, fs_hz, Q |
| `dsp_biquad_peaking` | RBJ cookbook peaking EQ biquad; inputs: fc_hz, fs_hz, Q, gain_db |
| `dsp_freq_response` | Evaluates H(e^jω) magnitude/phase from b/a coefficients at a single freq_hz; inputs: b, a, freq_hz, fs_hz |
| `dsp_group_delay` | Group delay (−dφ/dω) at a frequency from b/a coefficients; inputs: b, a, freq_hz, fs_hz |
| `dsp_nyquist_check` | Checks if fs meets Nyquist for signal_bw_hz; returns oversampling ratio and alias_free flag |
| `dsp_adc_snr` | Theoretical ADC SNR, ENOB, and process gain from bits and oversampling ratio |

## Example

**User ask:** "I'm sampling a 500 Hz signal at 10 kHz. Design a 51-tap Hamming-windowed lowpass FIR to remove everything above 1 kHz, and check the group delay at 500 Hz."

1. Call `dsp_fir_lp` with `N=51`, `fc_norm=0.1` (1000/10000), `window="hamming"` → get h coefficients.
2. Call `dsp_group_delay` with those coefficients as `b`, `a=[1.0]`, `freq_hz=500`, `fs_hz=10000` → get group delay in samples and seconds.
