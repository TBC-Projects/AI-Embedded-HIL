module top (
    input  logic        clk,      // 100 MHz clock from onboard oscillator (W5)
    input  logic        btnU,     // Pushbutton: Up    (T18)
    input  logic        btnC,     // Pushbutton: Center (U18)
    input  logic        btnD,     // Pushbutton: Down  (W19)
    input  logic        btnL,     // Pushbutton: Left  (W18)
    input  logic        btnR,     // Pushbutton: Right (T17)
    input  logic [15:0] sw,       // 16 Slide switches (V17, V16, W16, W15, etc.)
    output logic [15:0] led,      // 16 LEDs           (U16, E19, U19, V19, etc.)
    output logic [ 3:0] an,       // 4-digit 7-seg anode control   (J17, J18, T9, J14)
    output logic        dp,       // Decimal point on 7-segment    (V7)
    output logic [ 6:0] seg       // 7-segment cathodes [A-G]      (W7, R8, V4, U4, V5, W4, V3)
);

    assign led = sw;
    assign an = 4'b0;
    assign seg = ~{btnC, btnL, btnL, btnD, btnR, btnR, btnU};
    assign dp = 1'b1;
endmodule
