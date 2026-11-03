// DDR RGB565 scanout. Image data never resides in PL ROM.
// PS owns back buffers; a vblank commit transfers front-buffer ownership.
`timescale 1ns/1ps
module ddr_hdmi #(
 parameter WIDTH=1280, HEIGHT=720,
 parameter BUTTON_DEBOUNCE_CYCLES=1000000,
 parameter H_FP=110,H_SYNC=40,H_BP=220,V_FP=5,V_SYNC=5,V_BP=20,
 parameter [31:0] BUILD_ID=32'h20261102
)(
(* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 s_axi_aclk CLK", X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi_aclk, ASSOCIATED_BUSIF S_AXI:M_AXI, ASSOCIATED_RESET s_axi_aresetn, FREQ_HZ 100000000" *) input wire s_axi_aclk,
(* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 s_axi_aresetn RST", X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi_aresetn, POLARITY ACTIVE_LOW" *) input wire s_axi_aresetn,
input wire restart_btn,
input wire pix_clk,
input wire pix_rst_n,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWADDR" *) input wire [15:0] s_axi_awaddr,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWPROT" *) input wire [2:0] s_axi_awprot,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *) input wire  s_axi_awvalid,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *) output wire  s_axi_awready,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WDATA" *) input wire [31:0] s_axi_wdata,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *) input wire [3:0] s_axi_wstrb,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WVALID" *) input wire  s_axi_wvalid,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WREADY" *) output wire  s_axi_wready,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BRESP" *) output wire [1:0] s_axi_bresp,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BVALID" *) output wire  s_axi_bvalid,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BREADY" *) input wire  s_axi_bready,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *) input wire [15:0] s_axi_araddr,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARPROT" *) input wire [2:0] s_axi_arprot,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *) input wire  s_axi_arvalid,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *) output wire  s_axi_arready,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RDATA" *) output wire [31:0] s_axi_rdata,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RRESP" *) output wire [1:0] s_axi_rresp,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RVALID" *) output wire  s_axi_rvalid,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RREADY", X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXI, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 16, FREQ_HZ 100000000" *) input wire  s_axi_rready,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI ARID" *) output wire [5:0] m_axi_arid,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI ARADDR" *) output wire [31:0] m_axi_araddr,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI ARLEN" *) output wire [3:0] m_axi_arlen,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI ARSIZE" *) output wire [2:0] m_axi_arsize,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI ARBURST" *) output wire [1:0] m_axi_arburst,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI ARLOCK" *) output wire [1:0] m_axi_arlock,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI ARCACHE" *) output wire [3:0] m_axi_arcache,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI ARPROT" *) output wire [2:0] m_axi_arprot,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI ARQOS" *) output wire [3:0] m_axi_arqos,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI ARVALID" *) output wire  m_axi_arvalid,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI ARREADY", X_INTERFACE_PARAMETER = "XIL_INTERFACENAME M_AXI, PROTOCOL AXI3, DATA_WIDTH 64, ADDR_WIDTH 32, ID_WIDTH 6, FREQ_HZ 100000000, MAX_BURST_LENGTH 16, NUM_READ_OUTSTANDING 1, NUM_WRITE_OUTSTANDING 1" *) input wire  m_axi_arready,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI RID" *) input wire [5:0] m_axi_rid,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI RDATA" *) input wire [63:0] m_axi_rdata,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI RRESP" *) input wire [1:0] m_axi_rresp,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI RLAST" *) input wire  m_axi_rlast,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI RVALID" *) input wire  m_axi_rvalid,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI RREADY" *) output wire  m_axi_rready,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI AWID" *) output wire [5:0] m_axi_awid,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI AWADDR" *) output wire [31:0] m_axi_awaddr,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI AWLEN" *) output wire [3:0] m_axi_awlen,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI AWSIZE" *) output wire [2:0] m_axi_awsize,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI AWBURST" *) output wire [1:0] m_axi_awburst,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI AWLOCK" *) output wire [1:0] m_axi_awlock,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI AWCACHE" *) output wire [3:0] m_axi_awcache,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI AWPROT" *) output wire [2:0] m_axi_awprot,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI AWQOS" *) output wire [3:0] m_axi_awqos,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI AWVALID" *) output wire  m_axi_awvalid,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI AWREADY" *) input wire  m_axi_awready,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI WID" *) output wire [5:0] m_axi_wid,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI WDATA" *) output wire [63:0] m_axi_wdata,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI WSTRB" *) output wire [7:0] m_axi_wstrb,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI WLAST" *) output wire  m_axi_wlast,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI WVALID" *) output wire  m_axi_wvalid,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI WREADY" *) input wire  m_axi_wready,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI BID" *) input wire [5:0] m_axi_bid,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI BRESP" *) input wire [1:0] m_axi_bresp,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI BVALID" *) input wire  m_axi_bvalid,
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 M_AXI BREADY" *) output wire  m_axi_bready,
output reg [23:0] vdata,
output reg vde, vhs, vvs
);
localparam HT=WIDTH+H_FP+H_SYNC+H_BP, VT=HEIGHT+V_FP+V_SYNC+V_BP;
localparam BEATS=WIDTH/4;
// BTN0 is asynchronous; only the first synchronizer D pin is a timing exception.
(* ASYNC_REG="TRUE", SHREG_EXTRACT="NO" *) reg button_meta,button_sync;
localparam BUTTON_BITS=(BUTTON_DEBOUNCE_CYCLES>1)?$clog2(BUTTON_DEBOUNCE_CYCLES):1;
reg [BUTTON_BITS-1:0] button_ticks;
reg button_pressed;
reg [15:0] button_presses;
always @(posedge s_axi_aclk)begin
 if(!s_axi_aresetn)begin
  button_meta<=0;button_sync<=0;button_ticks<=0;button_pressed<=0;button_presses<=0;
 end else begin
  button_meta<=restart_btn;button_sync<=button_meta;
  if(button_sync==button_pressed)button_ticks<=0;
  else if(button_ticks==BUTTON_DEBOUNCE_CYCLES-1)begin
   button_ticks<=0;button_pressed<=button_sync;
   if(button_sync)button_presses<=button_presses+1'b1;
  end else button_ticks<=button_ticks+1'b1;
 end
end

localparam IDLE=0,SETUP=1,ADDRESS=2,READ=3,DONE=4,FAULT=5;
reg [2:0] state;
reg enabled,pending,active_valid;
reg [31:0] config_base,pending_base,active_base,presented_count,dma_errors;
reg [31:0] read_address;
reg [8:0] beat_index;
reg [25:0] request_tag,completed_tag;
reg row_error;
reg ack_toggle;

(* ram_style="block" *) reg [63:0] line_memory [0:1023];
always @(posedge s_axi_aclk)
 if(state==READ && m_axi_rvalid && m_axi_rready)
  line_memory[{request_tag[0],beat_index}]<=m_axi_rdata;

assign m_axi_arid=0;
assign m_axi_araddr=read_address;
assign m_axi_arlen=4'd15;
assign m_axi_arsize=3'd3;
assign m_axi_arburst=2'b01;
assign m_axi_arlock=0;
assign m_axi_arcache=4'b0011;
assign m_axi_arprot=0;
assign m_axi_arqos=0;
assign m_axi_arvalid=(state==ADDRESS);
assign m_axi_rready=(state==READ || state==FAULT);
assign m_axi_awid=0;
assign m_axi_awaddr=0;
assign m_axi_awlen=0;
assign m_axi_awsize=0;
assign m_axi_awburst=0;
assign m_axi_awlock=0;
assign m_axi_awcache=0;
assign m_axi_awprot=0;
assign m_axi_awqos=0;
assign m_axi_awvalid=0;
assign m_axi_wid=0;
assign m_axi_wdata=0;
assign m_axi_wstrb=0;
assign m_axi_wlast=0;
assign m_axi_wvalid=0;
assign m_axi_bready=0;

reg request_toggle;
reg [25:0] held_request;
(* ASYNC_REG="TRUE", SHREG_EXTRACT="NO" *) reg request_meta,request_sync;
(* ASYNC_REG="TRUE", SHREG_EXTRACT="NO" *) reg ack_meta,ack_sync;
(* ASYNC_REG="TRUE", SHREG_EXTRACT="NO" *) reg run_meta,run_sync;
always @(posedge s_axi_aclk)begin
 if(!s_axi_aresetn)begin request_meta<=0;request_sync<=0;end
 else begin request_meta<=request_toggle;request_sync<=request_meta;end
end

// Independent AXI-Lite AW and W channels, one outstanding response each.
reg aw_held,w_held,bvalid_reg,rvalid_reg;
reg [15:0] write_addr;
reg [31:0] write_data,rdata_reg;
reg [3:0] write_strobe;
reg [1:0] bresp_reg,rresp_reg;
assign s_axi_awready=!aw_held&&!bvalid_reg;
assign s_axi_wready=!w_held&&!bvalid_reg;
assign s_axi_bvalid=bvalid_reg;
assign s_axi_bresp=bresp_reg;
assign s_axi_arready=!rvalid_reg;
assign s_axi_rvalid=rvalid_reg;
assign s_axi_rdata=rdata_reg;
assign s_axi_rresp=rresp_reg;
wire execute=aw_held&&w_held&&!bvalid_reg;
wire base_write=write_addr==16'h10 && write_strobe==15;
wire commit_write=write_addr==16'h14 && write_strobe==15 && write_data==1 && !pending && config_base[11:0]==0 && config_base!=0;
wire stop_write=write_addr==16'h14 && write_strobe==15 && write_data==2;
wire clear_write=write_addr==16'h14 && write_strobe==15 && write_data==4 && state==IDLE;
wire write_legal=base_write||commit_write||stop_write||clear_write;
reg [31:0] underflow_count,frame_count;
reg [31:0] underflow_gray,frame_gray;
(* ASYNC_REG="TRUE", SHREG_EXTRACT="NO" *) reg [31:0] underflow_meta,underflow_sync,frame_meta,frame_sync;
function [31:0] gray_to_binary(input [31:0] gray);
integer i;begin gray_to_binary[31]=gray[31];for(i=30;i>=0;i=i-1)gray_to_binary[i]=gray_to_binary[i+1]^gray[i];end
endfunction
reg [31:0] read_value;reg read_legal;
always @*begin
 read_legal=1;
 case(s_axi_araddr)
  16'h00:read_value=32'h44445231;
  16'h04:read_value={26'd0,(dma_errors!=0),(state==FAULT),(state!=IDLE),active_valid,pending,enabled};
  16'h08:read_value=BUILD_ID;
  16'h0c:read_value=presented_count;
  16'h10:read_value=config_base;
  16'h14:read_value=0;
  16'h18:read_value=active_base;
  16'h1c:read_value=gray_to_binary(underflow_sync);
  16'h20:read_value=dma_errors;
  16'h24:read_value=gray_to_binary(frame_sync);
  16'h28:read_value={15'd0,button_pressed,button_presses};
  default:begin read_value=0;read_legal=0;end
 endcase
end
always @(posedge s_axi_aclk)begin
 if(!s_axi_aresetn)begin
  aw_held<=0;w_held<=0;bvalid_reg<=0;rvalid_reg<=0;bresp_reg<=0;rresp_reg<=0;rdata_reg<=0;
  write_addr<=0;write_data<=0;write_strobe<=0;
  underflow_meta<=0;underflow_sync<=0;frame_meta<=0;frame_sync<=0;
 end else begin
  underflow_meta<=underflow_gray;underflow_sync<=underflow_meta;
  frame_meta<=frame_gray;frame_sync<=frame_meta;
  if(s_axi_awvalid&&s_axi_awready)begin write_addr<=s_axi_awaddr;aw_held<=1;end
  if(s_axi_wvalid&&s_axi_wready)begin write_data<=s_axi_wdata;write_strobe<=s_axi_wstrb;w_held<=1;end
  if(bvalid_reg&&s_axi_bready)bvalid_reg<=0;
  if(execute)begin aw_held<=0;w_held<=0;bvalid_reg<=1;bresp_reg<=write_legal?0:2;end
  if(rvalid_reg&&s_axi_rready)rvalid_reg<=0;
  if(s_axi_arvalid&&s_axi_arready)begin rvalid_reg<=1;rdata_reg<=read_value;rresp_reg<=read_legal?0:2;end
 end
end

always @(posedge s_axi_aclk)begin
 if(!s_axi_aresetn)begin
  state<=IDLE;enabled<=0;pending<=0;active_valid<=0;config_base<=0;pending_base<=0;
  active_base<=0;presented_count<=0;dma_errors<=0;read_address<=0;beat_index<=0;
  request_tag<=0;completed_tag<=26'h3ffffff;ack_toggle<=0;row_error<=0;
 end else begin
  if(execute&&base_write)config_base<=write_data;
  if(execute&&commit_write)begin pending_base<=config_base;pending<=1;enabled<=1;end
  if(execute&&clear_write)dma_errors<=0;
  case(state)
   IDLE:if(request_sync!=ack_toggle)begin request_tag<=held_request;state<=SETUP;end
   SETUP:begin
    row_error<=0;beat_index<=0;
    if(enabled && (active_valid || (request_tag[9:0]==0 && pending)))begin
     if(request_tag[9:0]==0 && pending)begin
      active_base<=pending_base;active_valid<=1;pending<=0;presented_count<=presented_count+1;
      read_address<=pending_base;
     end else read_address<=active_base+request_tag[9:0]*(WIDTH*2);
     state<=ADDRESS;
    end else begin completed_tag<=26'h3ffffff;ack_toggle<=request_sync;state<=IDLE;end
   end
   ADDRESS:if(m_axi_arready)state<=READ;
   READ:if(m_axi_rvalid)begin
    if(m_axi_rid!=0 || m_axi_rlast!=(beat_index[3:0]==15))begin
     // Transaction ownership is unknown. Sink replies but never report idle.
     dma_errors<=dma_errors+1;row_error<=1;state<=FAULT;
    end else begin
     if(m_axi_rresp!=0)begin dma_errors<=dma_errors+1;row_error<=1;end
     if(beat_index==BEATS-1)state<=DONE;
     else begin
      beat_index<=beat_index+1;
      if(beat_index[3:0]==15)begin read_address<=read_address+128;state<=ADDRESS;end
     end
    end
   end
   DONE:begin completed_tag<=row_error?26'h3ffffff:request_tag;ack_toggle<=request_sync;state<=IDLE;end
   FAULT:state<=FAULT;
   default:state<=IDLE;
  endcase
  // Stop blocks new DMA; an accepted burst/row is always drained before idle.
  if(execute&&stop_write)begin enabled<=0;pending<=0;active_valid<=0;end
 end
end

reg [10:0] hcnt;
reg [9:0] vcnt;
reg [15:0] display_epoch;
reg completion_seen;
reg [25:0] ready_tag0,ready_tag1;
reg line_good;
reg [63:0] q_line;
reg [1:0] q_lane;
reg q_de,q_hs,q_vs,q_good;
wire tag_matches=(vcnt[0]?ready_tag1:ready_tag0)=={display_epoch,vcnt[9:0]};
wire good_now=(hcnt==0)?(run_sync&&tag_matches):line_good;
wire active=(hcnt<WIDTH && vcnt<HEIGHT);
wire [15:0] color=q_line>>(q_lane*16);
wire [7:0] red8={color[15:11],color[15:13]};
wire [7:0] green8={color[10:5],color[10:9]};
wire [7:0] blue8={color[4:0],color[4:2]};
always @(posedge pix_clk)begin
 // One synchronous read per pixel; both line banks are genuinely in BRAM.
 q_line<=line_memory[{vcnt[0],hcnt[10:2]}];
 q_lane<=hcnt[1:0];
 q_de<=active;q_hs<=hcnt>=WIDTH+H_FP && hcnt<WIDTH+H_FP+H_SYNC;
 q_vs<=vcnt>=HEIGHT+V_FP && vcnt<HEIGHT+V_FP+V_SYNC;
 q_good<=good_now&&run_sync;
 if(!pix_rst_n)begin
  hcnt<=0;vcnt<=0;request_toggle<=0;held_request<=0;display_epoch<=0;
  ack_meta<=0;ack_sync<=0;run_meta<=0;run_sync<=0;completion_seen<=0;
  ready_tag0<=26'h3ffffff;ready_tag1<=26'h3ffffff;line_good<=0;underflow_count<=0;frame_count<=0;underflow_gray<=0;frame_gray<=0;
  vdata<=0;vde<=0;vhs<=0;vvs<=0;
 end else begin
  ack_meta<=ack_toggle;ack_sync<=ack_meta;run_meta<=enabled;run_sync<=run_meta;
  underflow_gray<=(underflow_count>>1)^underflow_count;frame_gray<=(frame_count>>1)^frame_count;
  if(ack_sync!=completion_seen)begin
   completion_seen<=ack_sync;
   if(completed_tag[0])ready_tag1<=completed_tag;else ready_tag0<=completed_tag;
  end
  if(hcnt==HT-1)begin hcnt<=0;if(vcnt==VT-1)begin vcnt<=0;frame_count<=frame_count+1;end else vcnt<=vcnt+1;end
  else hcnt<=hcnt+1;
  if(hcnt==0)begin
   if(vcnt==HEIGHT)display_epoch<=display_epoch+16'd1;
   line_good<=run_sync&&tag_matches;
   if(run_sync&&vcnt<HEIGHT&&!tag_matches)underflow_count<=underflow_count+1;
   if(run_sync && request_toggle==ack_sync)begin
    if(vcnt<HEIGHT-1)begin
     held_request<={display_epoch,(vcnt+10'd1)};request_toggle<=~request_toggle;
     if((vcnt+10'd1)&1)ready_tag1<=26'h3ffffff;else ready_tag0<=26'h3ffffff;
    end
    else if(vcnt==HEIGHT)begin
     held_request<={display_epoch+16'd1,10'd0};request_toggle<=~request_toggle;ready_tag0<=26'h3ffffff;
    end
   end
  end
  vdata<=q_good?{red8,blue8,green8}:24'd0;
  vde<=q_de;vhs<=q_hs;vvs<=q_vs;
 end
end
endmodule
