// 8-bit synchronous counter with synchronous reset
// Synthesizable Verilog-2001

module counter (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       enable,
    output reg  [7:0] count
);

parameter INIT = 8'h00;

always_ff @(posedge clk) begin
    if (!rst_n) begin
        count <= INIT;
    end else if (enable) begin
        count <= count + 8'h01;
    end
end

endmodule
