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
    
    Clock_Ticker dut (.clk(clk), .rst(rst), .startsignal(startsignal),
    .cycle_length(cycle_length), .fire_signal(fire_signal));
    
    parameter CLOCK_PERIOD = 100;
    
    initial begin
        clk <= 0;
        forever #(CLOCK_PERIOD/2) clk <= ~clk; // Forever toggle the clock
    end
    
    
    /*
    Test Cases:
        standard run
        reset signal
        startsignal signal
        Shorter/longer cycle_length
        multiple loops
        reset when cycle reaches cycle_length
    */
    initial begin
        // Test reset
        rst <= 1; startsignal <= 0; cycle_length <= 4; repeat(1) @(posedge clk);  
        rst <= 0; startsignal <= 0; cycle_length <= 4; repeat(10) @(posedge clk); // Standard Run, multiple cycles
        
        // Test reset on for multiple consecutive posedge clks
        rst <= 1; startsignal <= 0; cycle_length <= 4; repeat(6) @(posedge clk);
        
        // Test startsignal
        rst <= 0; startsignal <= 1; cycle_length <= 4; repeat(1) @(posedge clk); 
        rst <= 0; startsignal <= 0; cycle_length <= 4; repeat(8) @(posedge clk); // Standard run
        
        // Test reset and startsignal on at same time
        rst <= 1; startsignal <= 1; cycle_length <= 4; repeat(4) @(posedge clk);
        rst <= 0; startsignal <= 0; cycle_length <= 4; repeat(4) @(posedge clk);
        
        //Test different cycle_length size
        rst <= 0; startsignal <= 0; cycle_length <= 7; repeat(10) @(posedge clk);  
        

        rst <= 1; startsignal <= 0; cycle_length <= 4; repeat(1) @(posedge clk);
        
        // Test reset when cycle reaches cycle_length
        rst <= 0; startsignal <= 0; cycle_length <= 4; repeat(3) @(posedge clk);
        rst <= 1; startsignal <= 0; cycle_length <= 4; repeat(1) @(posedge clk);
        rst <= 0; startsignal <= 0; cycle_length <= 4; repeat(10) @(posedge clk);
        
        $stop; // Stops clock
    end
endmodule
        