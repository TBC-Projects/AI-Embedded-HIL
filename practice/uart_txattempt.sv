module uart_tx (
    input logic clk,
    input logic rst,
    input logic start,
    input logic [7:0] data,
    output logic tx,
    output logic busy
);

logic [10:0] frame;
logic counter;
logic [8:0] bit_index;

// https://easyfpga.blog/posts/uart-implementation-ep5/

always_ff (@posedge clk or posedge rst) begin
    if (rst) begin
        tx <= 1'b1;
        busy <= 1'b0;
end else if (start) begin
        busy <= 1'b1;
        frame <= {1'b1, data, 1'b0};
        counter <= 0;
        bit_index <= '0;
