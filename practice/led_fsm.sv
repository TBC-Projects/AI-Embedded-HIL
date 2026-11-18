`timescale 1ns / 1ps

// 17-state LED finite state machine for Basys 3.
// State 0: All LEDs off.
// States 1–16: Light LEDs 0–15 sequentially.
// Transitions occur once per second using the 100 MHz clock.

module led_fsm (
    input logic clk,
    output logic [15:0] led
);

    logic [4:0] state = 0;
    logic [26:0] timer = 0;

    always_ff @(posedge clk) begin
    if (timer == 99_999_999) begin
        timer <= 0;

        if (state == 16) begin
            state <= 0;
        end else begin
            state <= state + 1;
        end

    end else begin
        timer <= timer + 1;
    end
end

always_comb begin
    case (state)
        0:  led = 16'b0000000000000000; // All OFF
        1:  led = 16'b0000000000000001; // LED0 ON
        2:  led = 16'b0000000000000010; // LED1 ON
        3:  led = 16'b0000000000000100; // LED2 ON
        4:  led = 16'b0000000000001000; // LED3 ON
        5:  led = 16'b0000000000010000; // LED4 ON
        6:  led = 16'b0000000000100000; // LED5 ON
        7:  led = 16'b0000000001000000; // LED6 ON
        8:  led = 16'b0000000010000000; // LED7 ON
        9:  led = 16'b0000000100000000; // LED8 ON
        10: led = 16'b0000001000000000; // LED9 ON
        11: led = 16'b0000010000000000; // LED10 ON
        12: led = 16'b0000100000000000; // LED11 ON
        13: led = 16'b0001000000000000; // LED12 ON
        14: led = 16'b0010000000000000; // LED13 ON
        15: led = 16'b0100000000000000; // LED14 ON
        16: led = 16'b1000000000000000; // LED15 ON
        default: led = 16'b0000000000000000;
    endcase 
end

endmodule
