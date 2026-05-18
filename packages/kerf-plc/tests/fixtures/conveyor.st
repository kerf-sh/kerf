(* Conveyor POU — start/stop/e-stop control with motor output *)
FUNCTION_BLOCK Conveyor
VAR_INPUT
    start_btn  : BOOL;
    stop_btn   : BOOL;
    estop      : BOOL;
END_VAR
VAR_OUTPUT
    motor_run  : BOOL;
    fault_lamp : BOOL;
END_VAR
VAR
    running    : BOOL;
END_VAR

(* Emergency stop overrides everything *)
IF estop THEN
    running    := FALSE;
    fault_lamp := TRUE;
ELSIF start_btn AND NOT stop_btn THEN
    running    := TRUE;
    fault_lamp := FALSE;
ELSIF stop_btn THEN
    running    := FALSE;
    fault_lamp := FALSE;
ELSE
    fault_lamp := FALSE;
END_IF

motor_run := running;

END_FUNCTION_BLOCK
