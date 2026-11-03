`timescale 1ns/1ps
// Read-only AXI-Lite counter bank; all traffic inputs are passive taps.
module perf_monitor(
 (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axi, ASSOCIATED_RESET aresetn" *) input wire aclk,
 (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *) input wire aresetn,
 input wire [31:0] phase, input wire mac_valid,
 input wire tap_arvalid,tap_arready,tap_rvalid,tap_rready,tap_rlast,
 input wire tap_awvalid,tap_awready,tap_wvalid,tap_wready,tap_bvalid,tap_bready,
 input wire [7:0] tap_wstrb,
 input wire [7:0] s_axi_araddr,input wire s_axi_arvalid,output wire s_axi_arready,
 output reg [31:0] s_axi_rdata,output wire [1:0] s_axi_rresp,output reg s_axi_rvalid,input wire s_axi_rready,
 input wire [7:0] s_axi_awaddr,input wire s_axi_awvalid,output wire s_axi_awready,
 input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,input wire s_axi_wvalid,output wire s_axi_wready,
 output wire [1:0] s_axi_bresp,output reg s_axi_bvalid,input wire s_axi_bready
);
 assign s_axi_arready=~s_axi_rvalid;assign s_axi_rresp=0;
 assign s_axi_awready=~s_axi_bvalid;assign s_axi_wready=~s_axi_bvalid;assign s_axi_bresp=0;
 reg running;reg [7:0] rd_pending,wr_pending;
 reg [31:0] ctr[0:23];integer i;
 wire read_address=tap_arvalid&&tap_arready,read_end=tap_rvalid&&tap_rready&&tap_rlast;
 wire write_address=tap_awvalid&&tap_awready,write_end=tap_bvalid&&tap_bready;
 wire [3:0] bytes_written={3'b0,tap_wstrb[0]}+{3'b0,tap_wstrb[1]}+{3'b0,tap_wstrb[2]}+{3'b0,tap_wstrb[3]}+
                           {3'b0,tap_wstrb[4]}+{3'b0,tap_wstrb[5]}+{3'b0,tap_wstrb[6]}+{3'b0,tap_wstrb[7]};
 always @(posedge aclk) begin
  if(!aresetn) begin
   running<=0;rd_pending<=0;wr_pending<=0;s_axi_rvalid<=0;s_axi_rdata<=0;s_axi_bvalid<=0;
   for(i=0;i<24;i=i+1)ctr[i]<=0;
  end else begin
   if(s_axi_rvalid&&s_axi_rready)s_axi_rvalid<=0;
   if(s_axi_arvalid&&s_axi_arready)begin s_axi_rvalid<=1;s_axi_rdata<=(s_axi_araddr[6:2]<24)?ctr[s_axi_araddr[6:2]]:0;end
   if(s_axi_bvalid&&s_axi_bready)s_axi_bvalid<=0;
   if(s_axi_awvalid&&s_axi_wvalid&&s_axi_awready&&s_axi_wready)s_axi_bvalid<=1;
   if(!running && phase[6]) begin
    running<=1;rd_pending<=0;wr_pending<=0;
    for(i=0;i<24;i=i+1)ctr[i]<=0;
   end else if(running) begin
    if(!phase[6])running<=0;
    else begin
     ctr[0]<=ctr[0]+1;
     if(phase[0])ctr[1]<=ctr[1]+1;
     if(phase[2])ctr[2]<=ctr[2]+1;
     if(phase[3])ctr[3]<=ctr[3]+1;
     if(phase[4])ctr[4]<=ctr[4]+1;
     if(mac_valid)ctr[5]<=ctr[5]+1;
     if((tap_arvalid&&!tap_arready)||((rd_pending!=0)&&tap_rready&&!tap_rvalid))ctr[6]<=ctr[6]+1;
     if((tap_awvalid&&!tap_awready)||(tap_wvalid&&!tap_wready)||((wr_pending!=0)&&tap_bready&&!tap_bvalid))ctr[7]<=ctr[7]+1;
     if(tap_rvalid&&tap_rready)ctr[8]<=ctr[8]+8;
     if(read_address)ctr[9]<=ctr[9]+1;
     if(tap_wvalid&&tap_wready)ctr[10]<=ctr[10]+bytes_written;
     if(write_address)ctr[11]<=ctr[11]+1;
     if(phase[1])ctr[12]<=ctr[12]+1;
     if(phase[5])ctr[13]<=ctr[13]+1;
     if(phase[0]&&phase[2])ctr[14]<=ctr[14]+1;
     if(phase[7])ctr[15]<=ctr[15]+1;
     if(phase[8])ctr[16]<=ctr[16]+1;
     if(phase[9])ctr[18]<=ctr[18]+1;
     if(phase[10])ctr[19]<=ctr[19]+1;
     if(phase[11])ctr[20]<=ctr[20]+1;
     if(phase[12])ctr[21]<=ctr[21]+1;
     if(phase[13])ctr[22]<=ctr[22]+1;
     if(phase[14])ctr[23]<=ctr[23]+1;
     case({read_address,read_end}) 2'b10:rd_pending<=rd_pending+1;2'b01:rd_pending<=rd_pending-1;default:;endcase
     case({write_address,write_end}) 2'b10:wr_pending<=wr_pending+1;2'b01:wr_pending<=wr_pending-1;default:;endcase
    end
   end
  end
 end
endmodule
