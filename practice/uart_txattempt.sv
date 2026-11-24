module uart_tx #(
    parameter CLK_FREQ = 100_000_000,
    parameter BD_RATE = 115_200
    )(
    input logic clk,
    input logic rst,
    input logic start,
    input logic [7:0] data,
    output logic tx,
    output logic busy
);

    logic [10:0] frame;
    logic [7:0] counter;
    logic [7:0] bit_index;

    // https://easyfpga.blog/posts/uart-implementation-ep5/

    always_ff (@posedge clk or posedge rst) begin
        if (rst) begin // initializing everything
            tx <= 1'b1;
            busy <= 1'b0;
        end else if (!busy) begin // if we're not busy, take in some data
            busy <= 1'b1;
            frame <= {1'b1, data, 1'b0}; // our 8 bit data takes up the middle of the frame
            counter <= '0;
            bit_index <= '0;
        end else if (counter == CLK_FREQ / BD_RATE - 1) begin // if we're at the spot where we want to shift stuff
            counter <= '0;

            if (bit_index == 10) begin // if we're at the final bit, go back to idle
                busy <= 1'b0;
            end else begin
                bit_index <= bit_index + 1'b1;
                frame <= {1'b1, frame[10:1]}; // drop the LSB, move our stuff along the shift register
            end
        end else begin
            counter <= counter + 1'b1; // increment our counter each clock cycle when we're not doing something
        end
    end

    tx = frame[0]; // tx takes the LSB of the frame
endmodule


module top {
    output logic [7:0] data;
    input logic clk;
    input logic busy;
    input logic rst;
}
logic charnum;

always_ff(@posedge clk or posedge rst) begin
    if (rst) begin
        charnum <= '0;
    end else if (!busy) begin
        if (charnum == 0)
            data <= "H";
            else if (charnum == 1)
            data <= "E";
            else if (charnum == 2)
            data <= "L";
            else if (charnum == 3)
            data <= "L";
            else if (charnum == 4)
            data <= "O";
            else if (charnum == 5)
            data <= "\r";
            else if (charnum == 6)
            data <= "\n";

        charnum <= charnum + 1'b1;
    end

end

endmodule