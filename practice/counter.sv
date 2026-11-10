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
        if (!rst_n) begin
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