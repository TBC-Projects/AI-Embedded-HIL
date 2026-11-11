module counter (
    input logic clk,
    input logic btnU,
    input logic btnC,
    input logic btnD,
    input logic btnL,
    input logic btnR,
    input logic [15:0] sw,
    output logic [15:0] led,
    output logic [3:0] an,
    output logic dp,
    output logic [6:0] seg

);

    logic rst_n;
    assign led[15:0] = 16'b0;
   // assign an[3:0] <= 4'b0;
   // assign seg[6:0] <= 7'b1;
    
    logic [7:0] counter;
    // assign btnC = counter;

    assign rst_n = btnC;

    logic btnU_prev, btnD_prev;
    always_ff @(posedge clk) begin
        if (btnC) begin
            counter <= '0;
        end else begin
            if (btnU & ~btnD & ~btnU_prev) begin
                counter <= counter + 1;
                btnU_prev <= 1'b1;
            end

            if ((btnD & ~btnU & ~btnD_prev) & counter != 0) begin
                counter <= counter - 1;
                btnD_prev <= 1'b1;
            end

            if (counter > 9) begin
                counter <= '0;
            end

            btnU_prev <= btnU;
            btnD_prev <= btnD;


        end

        an <= 4'b1110;

        case(counter)
            0: seg <= 7'b1000000; // 0
            1: seg <= 7'b1111001; // 1
            2: seg <= 7'b0100100; // 2
            3: seg <= 7'b0110000; // 3
            4: seg <= 7'b0011001; // 4
            5: seg <= 7'b0010010; // 5
            6: seg <= 7'b0000010; // 6
            7: seg <= 7'b0000111; // 7 
            8: seg <= 7'b0000000; // 8
            9: seg <= 7'b0010000; // 9
            default: seg <= 7'b1111111; // nothing
        endcase
    end

    // run something that sets the segments to the given counter?
endmodule

module LIGHTIT_testbench();

    logic clk;
    logic btnU, btnC, btnD, btnL, btnR;
    logic [15:0] sw;
    logic rst;

    logic [15:0] led;
    logic [3:0] an;
    logic seg_dp;
    logic [6:0] seg;

    // Connect testbench to LIGHTII module
    LIGHTII dut (.*);

    intial clk = 0;
    always #5 clk = ~clk

     initial begin
        rst = 1;
        btnU = 0;
        btnD = 0;
        btnC = 0;
        btnL = 0;
        btnR = 0;
        sw = 0;

        #12;
        rst = 0;

        // Press Up button
        #10;
        btnU = 1;
        #10;
        btnU = 0;

        // Press Up again
        #10;
        btnU = 1;
        #10;
        btnU = 0;

        // Press Down button
        #10;
        btnD = 1;
        #10;
        btnD = 0;

        // Press Center button to reset
        #10;
        btnC = 1;
        #10;
        btnC = 0;

        #20;
        $stop;

    end

    // Display counter values
    initial begin
        $monitor("Time=%0t Counter=%0d Up=%b Down=%b Reset=%b",
                 $time, dut.counter, btnU, btnD, rst);
    end

endmodule