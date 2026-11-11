`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 11/09/2026 07:54:08 PM
// Design Name: 
// Module Name: Clock_Ticker
// Project Name: 
// Target Devices: 
// Tool Versions: 
// Description: 
// 
// Dependencies: 
// 
// Revision:
// Revision 0.01 - File Created
// Additional Comments:
// 
//////////////////////////////////////////////////////////////////////////////////


module Clock_Ticker(
input clk, input logic rst, input logic startsignal, 
input logic [9:0] cycle_length, output logic fire_signal
);
   
    logic [9:0] ticker;

    always_ff @(posedge clk) begin  
    if (rst || startsignal) begin
        ticker <= 10'b0;
        fire_signal <= 1'b0;
    end else if((ticker >= cycle_length - 1'b1)) begin
        ticker <= 10'b0;
        fire_signal <= 1'b1;
    end else begin
        ticker <= ticker + 1'b1;
        fire_signal <= 1'b0;
    end
end
endmodule



module Clock_Ticker_testbench();
    logic clk, rst, startsignal, fire_signal;
    logic [9:0] cycle_length;
    
    Clock_Ticker dut (.clk(clk), .rst(rst), .startsignal(starsignal),
    .cycle_length(cycle_length), .fire_signal(fire_signal));
    
    parameter CLOCK_PERIOD = 100;
    
    initial begin
        clk <= 0;
        forever #(CLOCK_PERIOD/2) clk <= ~clk; // Forever toggle the clock
    end
    
    
    /*
    Test Cases:
        
    */
    initial begin
        
    end
endmodule
        