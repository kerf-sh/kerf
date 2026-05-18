// Simple 2-input AND gate
// Synthesizable Verilog-2001

module and_gate (
    input  wire a,
    input  wire b,
    output wire y
);

assign y = a & b;

endmodule
