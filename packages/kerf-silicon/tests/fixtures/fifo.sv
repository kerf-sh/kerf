// Synchronous FIFO — depth=8, 8-bit data width
// Synthesizable SystemVerilog

module fifo #(
    parameter DATA_WIDTH = 8,
    parameter DEPTH      = 8
) (
    input  logic                  clk,
    input  logic                  rst_n,
    input  logic                  wr_en,
    input  logic [DATA_WIDTH-1:0] wr_data,
    input  logic                  rd_en,
    output logic [DATA_WIDTH-1:0] rd_data,
    output logic                  full,
    output logic                  empty
);

localparam ADDR_W = 3; // log2(DEPTH) = 3 for depth=8

// Storage array: depth entries, each DATA_WIDTH bits wide
logic [DATA_WIDTH-1:0] mem [0:DEPTH-1];

logic [ADDR_W:0] wr_ptr;
logic [ADDR_W:0] rd_ptr;

// Write pointer
always_ff @(posedge clk) begin
    if (!rst_n) begin
        wr_ptr <= '0;
    end else if (wr_en && !full) begin
        mem[wr_ptr[ADDR_W-1:0]] <= wr_data;
        wr_ptr <= wr_ptr + 1'b1;
    end
end

// Read pointer
always_ff @(posedge clk) begin
    if (!rst_n) begin
        rd_ptr <= '0;
    end else if (rd_en && !empty) begin
        rd_ptr <= rd_ptr + 1'b1;
    end
end

// Read data (registered output)
always_ff @(posedge clk) begin
    if (rd_en && !empty) begin
        rd_data <= mem[rd_ptr[ADDR_W-1:0]];
    end
end

// Status flags
assign full  = (wr_ptr[ADDR_W] != rd_ptr[ADDR_W]) &&
               (wr_ptr[ADDR_W-1:0] == rd_ptr[ADDR_W-1:0]);
assign empty = (wr_ptr == rd_ptr);

endmodule
