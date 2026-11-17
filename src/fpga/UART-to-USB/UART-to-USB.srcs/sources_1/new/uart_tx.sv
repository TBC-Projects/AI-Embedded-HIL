`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: The Boring Club
// Engineer: Christian Dapena 
// 
// Create Date: 11/09/2026 07:36:19 PM
// Design Name: uart_tx
// Module Name: uart_tx
// Project Name: AI Embedded HIL Project
// Target Devices: Basys3 FPGA Board
// Tool Versions: no idea what this means
// Description: 
// 
// Dependencies: 
// 
// Revision:
// Revision 0.01 - File Created
// Additional Comments:
// 
//////////////////////////////////////////////////////////////////////////////////


module uart_tx(
input clk, input logic rst, input start, input logic [7:0] data,
 output logic tx, output logic busy);
 
 localparam [9:0] cycle_length = 10'd868;
 logic [9:0] dataframe;
 logic send_bit;
 logic [3:0] counter = 0;
 logic startsignal = 0;
 logic stop_sent;
 
 
     //see Clock_Ticker
 Clock_Ticker ticker_inst (.clk(clk), .rst(rst), 
 .startsignal(startsignal), .cycle_length(cycle_length),
  .fire_signal(send_bit));
 
always_ff @(posedge clk) begin

    if (rst) begin
        counter <= 0;
        busy <= 0;
        dataframe <= 10'b0;
        tx <= 1'b1;
        stop_sent <= 0;
        startsignal <= 1'b0;
    end else begin
        
        /*
        Shift Register will use data here
        */
        
        if(start && !busy) begin
            dataframe <= {1'b1, data, 1'b0};
            busy <= 1'b1;
            counter <= 0;
            startsignal <= 1'b1;
            stop_sent <= 1'b0;
            
        end else begin
            startsignal <= 1'b0;
        end
        
        if (busy && send_bit) begin
            if (stop_sent) begin
                busy <= 1'b0;
                stop_sent <= 1'b0;
                counter <= 0;
            end else begin
                tx <= dataframe[0];
                dataframe <= {1'b1, dataframe[9:1]};
        
                if (counter == 9)
                    stop_sent <= 1'b1;
                else
                    counter <= counter + 1;
            end
        end
    end
    


end
endmodule

//input clk, input logic rst, input start, input logic [7:0] data,
 //output logic tx, output logic busy
module uart_tx_testbench();
    logic clk, rst, start, tx, busy;
    logic [7:0] data;
    
    uart_tx dut (.clk(clk), .rst(rst), .start(start), .data(data), .tx(tx), .busy(busy));
    
    parameter CLOCK_PERIOD = 100;
    
    initial begin
        clk <= 0;
        forever #(CLOCK_PERIOD/2) clk <= ~clk; // Forever toggle the clock
    end
    
    /*
    Test Cases: 
    Test Cases Go Here
    */
    initial begin
    
    end
endmodule