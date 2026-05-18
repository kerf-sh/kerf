(* Blinker POU — drives pulse_out at 1 Hz using a TON timer *)
FUNCTION_BLOCK Blinker
VAR
    clock_in : BOOL;
    pulse_out : BOOL;
    t : TON;
END_VAR

(* Update the on-delay timer *)
t(IN := clock_in, PT := T#1s);

(* Latch output from timer Q output *)
pulse_out := t.Q;

END_FUNCTION_BLOCK
