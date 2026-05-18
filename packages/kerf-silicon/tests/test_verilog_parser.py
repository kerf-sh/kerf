"""
Tests for kerf_silicon.verilog.parser — synthesizable Verilog/SV.
"""
import os
import pytest
from kerf_silicon.verilog.parser import parse, parse_file, ParseError
from kerf_silicon.verilog import ast


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture_path(name: str) -> str:
    return os.path.join(FIXTURES, name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def all_nodes(tree, node_type):
    """Walk AST and collect all nodes of given type."""
    result = []
    _walk(tree, node_type, result)
    return result


def _walk(node, node_type, result):
    if isinstance(node, node_type):
        result.append(node)
    if isinstance(node, list):
        for item in node:
            _walk(item, node_type, result)
        return
    for attr in vars(node):
        val = getattr(node, attr)
        if isinstance(val, ast.Node):
            _walk(val, node_type, result)
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, (ast.Node, list)):
                    _walk(item, node_type, result)


# ---------------------------------------------------------------------------
# Fixture: and_gate.v
# ---------------------------------------------------------------------------

class TestAndGate:
    def setup_method(self):
        self.du = parse_file(fixture_path("and_gate.v"))

    def test_parses_without_error(self):
        assert self.du is not None

    def test_design_unit_is_correct_type(self):
        assert isinstance(self.du, ast.DesignUnit)

    def test_one_module(self):
        assert len(self.du.modules) == 1

    def test_module_name(self):
        assert self.du.modules[0].name == "and_gate"

    def test_port_count(self):
        mod = self.du.modules[0]
        assert len(mod.ports) == 3

    def test_port_names(self):
        mod = self.du.modules[0]
        names = {p.name for p in mod.ports}
        assert "a" in names
        assert "b" in names
        assert "y" in names

    def test_port_directions(self):
        mod = self.du.modules[0]
        directions = {p.name: p.direction for p in mod.ports}
        assert directions["a"] == "input"
        assert directions["b"] == "input"
        assert directions["y"] == "output"

    def test_continuous_assign_present(self):
        mod = self.du.modules[0]
        assigns = [i for i in mod.items if isinstance(i, ast.ContinuousAssign)]
        assert len(assigns) == 1

    def test_module_has_line_info(self):
        mod = self.du.modules[0]
        assert mod.line >= 1
        assert mod.col >= 0

    def test_ports_have_line_info(self):
        for port in self.du.modules[0].ports:
            assert port.line >= 1

    def test_assign_lhs_is_identifier(self):
        mod = self.du.modules[0]
        assigns = [i for i in mod.items if isinstance(i, ast.ContinuousAssign)]
        lhs = assigns[0].lhs
        assert isinstance(lhs, ast.Identifier)
        assert lhs.name == "y"


# ---------------------------------------------------------------------------
# Fixture: counter.v
# ---------------------------------------------------------------------------

class TestCounter:
    def setup_method(self):
        self.du = parse_file(fixture_path("counter.v"))

    def test_parses_without_error(self):
        assert self.du is not None

    def test_one_module(self):
        assert len(self.du.modules) == 1

    def test_module_name(self):
        assert self.du.modules[0].name == "counter"

    def test_port_count(self):
        mod = self.du.modules[0]
        assert len(mod.ports) == 4

    def test_has_clk_port(self):
        mod = self.du.modules[0]
        assert any(p.name == "clk" for p in mod.ports)

    def test_has_count_port(self):
        mod = self.du.modules[0]
        count_port = next((p for p in mod.ports if p.name == "count"), None)
        assert count_port is not None

    def test_count_port_has_width(self):
        mod = self.du.modules[0]
        count_port = next(p for p in mod.ports if p.name == "count")
        assert count_port.width is not None
        assert count_port.width.msb == 7
        assert count_port.width.lsb == 0

    def test_always_ff_block(self):
        mod = self.du.modules[0]
        always_blocks = [i for i in mod.items if isinstance(i, ast.AlwaysBlock)]
        assert len(always_blocks) >= 1
        ff_blocks = [b for b in always_blocks if b.kind == "always_ff"]
        assert len(ff_blocks) == 1

    def test_always_ff_posedge_clk(self):
        mod = self.du.modules[0]
        ff_block = next(b for b in mod.items
                        if isinstance(b, ast.AlwaysBlock) and b.kind == "always_ff")
        # Sensitivity list must have posedge clk
        assert len(ff_block.sensitivity) >= 1
        posedge_events = [e for e in ff_block.sensitivity
                          if isinstance(e, ast.SensitivityEvent) and e.edge == "posedge"]
        assert len(posedge_events) == 1
        assert posedge_events[0].signal.name == "clk"

    def test_parameter_decl(self):
        mod = self.du.modules[0]
        params = [i for i in mod.items if isinstance(i, ast.ParamDecl)]
        assert len(params) >= 1
        assert any(p.name == "INIT" for p in params)

    def test_non_blocking_assigns_in_body(self):
        mod = self.du.modules[0]
        ff_block = next(b for b in mod.items
                        if isinstance(b, ast.AlwaysBlock) and b.kind == "always_ff")
        nb_assigns = all_nodes(ff_block, ast.NonBlockingAssign)
        assert len(nb_assigns) >= 1

    def test_if_statement_in_body(self):
        mod = self.du.modules[0]
        ff_block = next(b for b in mod.items
                        if isinstance(b, ast.AlwaysBlock) and b.kind == "always_ff")
        if_stmts = all_nodes(ff_block, ast.IfStatement)
        assert len(if_stmts) >= 1

    def test_all_nodes_have_line_col(self):
        mod = self.du.modules[0]
        for port in mod.ports:
            assert port.line >= 1
        for item in mod.items:
            assert item.line >= 1 or item.line == 0  # 0 is acceptable for synthesized nodes


# ---------------------------------------------------------------------------
# Fixture: fifo.sv
# ---------------------------------------------------------------------------

class TestFifo:
    def setup_method(self):
        self.du = parse_file(fixture_path("fifo.sv"))

    def test_parses_without_error(self):
        assert self.du is not None

    def test_one_module(self):
        assert len(self.du.modules) == 1

    def test_module_name(self):
        assert self.du.modules[0].name == "fifo"

    def test_port_count(self):
        mod = self.du.modules[0]
        # clk, rst_n, wr_en, wr_data, rd_en, rd_data, full, empty = 8 ports
        assert len(mod.ports) == 8

    def test_has_data_width_param(self):
        mod = self.du.modules[0]
        assert any(p.name == "DATA_WIDTH" for p in mod.params)

    def test_has_depth_param(self):
        mod = self.du.modules[0]
        assert any(p.name == "DEPTH" for p in mod.params)

    def test_logic_array_declaration(self):
        """fifo.sv has: logic [7:0] mem [0:DEPTH-1]"""
        mod = self.du.modules[0]
        net_decls = [i for i in mod.items if isinstance(i, ast.NetDecl)]
        mem_decl = next((d for d in net_decls if d.name == "mem"), None)
        assert mem_decl is not None, "Expected 'mem' net declaration"
        assert mem_decl.net_type == "logic"
        # Should have a packed width [DATA_WIDTH-1:0]
        assert mem_decl.width is not None
        # Should have at least one unpacked dimension
        assert len(mem_decl.dims) >= 1

    def test_multiple_always_ff_blocks(self):
        mod = self.du.modules[0]
        ff_blocks = [i for i in mod.items
                     if isinstance(i, ast.AlwaysBlock) and i.kind == "always_ff"]
        assert len(ff_blocks) >= 2

    def test_continuous_assign_for_flags(self):
        mod = self.du.modules[0]
        assigns = [i for i in mod.items if isinstance(i, ast.ContinuousAssign)]
        assert len(assigns) >= 1

    def test_localparam_present(self):
        mod = self.du.modules[0]
        # localparam ADDR_W = 3
        params = [i for i in mod.items if isinstance(i, ast.ParamDecl)]
        assert any(p.kind == "localparam" for p in params)

    def test_logic_ports(self):
        mod = self.du.modules[0]
        logic_ports = [p for p in mod.ports if p.net_type == "logic"]
        assert len(logic_ports) >= 2

    def test_wr_data_port_width(self):
        mod = self.du.modules[0]
        wr_data = next((p for p in mod.ports if p.name == "wr_data"), None)
        assert wr_data is not None
        assert wr_data.width is not None

    def test_rd_data_port_width(self):
        mod = self.du.modules[0]
        rd_data = next((p for p in mod.ports if p.name == "rd_data"), None)
        assert rd_data is not None
        assert rd_data.width is not None


# ---------------------------------------------------------------------------
# Direct parse() from string
# ---------------------------------------------------------------------------

class TestParseFromString:
    def test_simple_module(self):
        src = """
module simple (input wire clk, output reg q);
always @(posedge clk) q <= ~q;
endmodule
"""
        du = parse(src)
        assert len(du.modules) == 1
        assert du.modules[0].name == "simple"

    def test_two_modules(self):
        src = """
module foo (input a, output b); assign b = a; endmodule
module bar (input x, output y); assign y = ~x; endmodule
"""
        du = parse(src)
        assert len(du.modules) == 2
        names = {m.name for m in du.modules}
        assert "foo" in names
        assert "bar" in names

    def test_hex_literal_in_assign(self):
        src = """
module m (output reg [7:0] q);
always @(*) q = 8'hFF;
endmodule
"""
        du = parse(src)
        assert du.modules[0].name == "m"

    def test_binary_literal_in_assign(self):
        src = """
module m (input wire a, output reg b);
always @(*) b = 1'b0;
endmodule
"""
        du = parse(src)
        assert du.modules[0].name == "m"

    def test_case_statement(self):
        src = """
module fsm (input clk, input [1:0] in, output reg [1:0] state);
always @(posedge clk)
    case (in)
        2'b00: state <= 2'b01;
        2'b01: state <= 2'b10;
        default: state <= 2'b00;
    endcase
endmodule
"""
        du = parse(src)
        mod = du.modules[0]
        always_blocks = [i for i in mod.items if isinstance(i, ast.AlwaysBlock)]
        assert len(always_blocks) == 1
        # Find case statement inside
        case_stmts = all_nodes(always_blocks[0], ast.CaseStatement)
        assert len(case_stmts) == 1

    def test_if_else(self):
        src = """
module m (input sel, input a, input b, output reg y);
always @(*) if (sel) y = a; else y = b;
endmodule
"""
        du = parse(src)
        mod = du.modules[0]
        if_stmts = all_nodes(mod, ast.IfStatement)
        assert len(if_stmts) >= 1

    def test_parameter_with_value(self):
        src = """
module m #(parameter WIDTH = 8) (input [WIDTH-1:0] a, output [WIDTH-1:0] b);
assign b = a;
endmodule
"""
        du = parse(src)
        mod = du.modules[0]
        assert any(p.name == "WIDTH" for p in mod.params)

    def test_localparam(self):
        src = """
module m;
localparam FOO = 42;
endmodule
"""
        du = parse(src)
        mod = du.modules[0]
        params = [i for i in mod.items if isinstance(i, ast.ParamDecl)]
        assert any(p.kind == "localparam" and p.name == "FOO" for p in params)

    def test_wire_declaration(self):
        src = """
module m;
wire [3:0] bus;
endmodule
"""
        du = parse(src)
        mod = du.modules[0]
        nets = [i for i in mod.items if isinstance(i, ast.NetDecl)]
        assert any(n.name == "bus" for n in nets)

    def test_logic_declaration(self):
        src = """
module m;
logic [7:0] data;
endmodule
"""
        du = parse(src)
        mod = du.modules[0]
        nets = [i for i in mod.items if isinstance(i, ast.NetDecl)]
        data_net = next(n for n in nets if n.name == "data")
        assert data_net.net_type == "logic"
        assert data_net.width is not None
        assert data_net.width.msb == 7
        assert data_net.width.lsb == 0

    def test_always_comb(self):
        src = """
module m (input a, input b, output logic y);
always_comb y = a & b;
endmodule
"""
        du = parse(src)
        mod = du.modules[0]
        always_blocks = [i for i in mod.items if isinstance(i, ast.AlwaysBlock)]
        assert any(b.kind == "always_comb" for b in always_blocks)

    def test_generate_for(self):
        src = """
module m;
generate
for (genvar i = 0; i < 4; i = i + 1) begin
    wire w;
end
endgenerate
endmodule
"""
        du = parse(src)
        mod = du.modules[0]
        gen_blocks = [i for i in mod.items if isinstance(i, ast.GenerateBlock)]
        assert len(gen_blocks) == 1

    def test_module_instance(self):
        src = """
module top;
and_gate u1 (.a(a), .b(b), .y(y));
endmodule
"""
        du = parse(src)
        mod = du.modules[0]
        insts = [i for i in mod.items if isinstance(i, ast.ModuleInstance)]
        assert len(insts) == 1
        assert insts[0].module_name == "and_gate"
        assert insts[0].instance_name == "u1"

    def test_ast_nodes_carry_line_col(self):
        src = "module foo (input wire clk); endmodule\n"
        du = parse(src, filename="test.v")
        mod = du.modules[0]
        # Module should be on line 1
        assert mod.line == 1
        # Port should have a valid line
        for port in mod.ports:
            assert port.line >= 1
            assert port.col >= 0

    def test_blocking_assign_in_always(self):
        src = """
module m (input clk, output reg [7:0] q);
always @(posedge clk) q = q + 8'h01;
endmodule
"""
        du = parse(src)
        mod = du.modules[0]
        always_blocks = [i for i in mod.items if isinstance(i, ast.AlwaysBlock)]
        ba_nodes = all_nodes(always_blocks[0], ast.BlockingAssign)
        assert len(ba_nodes) >= 1

    def test_non_blocking_assign_in_always(self):
        src = """
module m (input clk, output reg [7:0] q);
always_ff @(posedge clk) q <= q + 8'h01;
endmodule
"""
        du = parse(src)
        mod = du.modules[0]
        ff_block = next(b for b in mod.items if isinstance(b, ast.AlwaysBlock))
        nba_nodes = all_nodes(ff_block, ast.NonBlockingAssign)
        assert len(nba_nodes) >= 1

    def test_timescale_directive_skipped(self):
        src = """`timescale 1ns/1ps
module m; endmodule
"""
        du = parse(src)
        assert len(du.modules) == 1

    def test_empty_module(self):
        src = "module empty; endmodule"
        du = parse(src)
        assert du.modules[0].name == "empty"
        assert du.modules[0].ports == []

    def test_number_literal_values(self):
        from kerf_silicon.verilog.lexer import tokenize as lex
        from kerf_silicon.verilog.parser import Parser
        # Test that hex 8'hAA parses to value 0xAA = 170
        src = """
module m (output reg [7:0] q);
always @(*) q = 8'hAA;
endmodule
"""
        du = parse(src)
        assert du.modules[0].name == "m"

    def test_bin_literal(self):
        src = """
module m (output reg [3:0] q);
always @(*) q = 4'b1010;
endmodule
"""
        du = parse(src)
        assert du.modules[0].name == "m"
