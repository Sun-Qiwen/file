`timescale 1ns/1ps
module tb_ddr_hdmi #(parameter WIDTH=64, parameter BAD_KIND=0, parameter BUTTON_TEST=0);
reg aclk=0,pclk=0,arst=0,prst=0,restart_btn=0;
always #5 aclk=~aclk;
always #10 pclk=~pclk;
reg [15:0] awaddr=0,araddr=0;
reg awvalid=0,wvalid=0,bready=1,arvalid=0,rready=1;
reg [31:0] wdata=0; reg [3:0] wstrb=15;
wire awready,wready,bvalid,arready,rvalid;
wire [1:0] bresp,rresp;wire [31:0] rdata;
wire [31:0] maraddr;wire [3:0] marlen;wire marvalid;reg marready=0;
reg [5:0] mrid=0;
reg hold_responses=0;
reg [63:0] mrdata=0;reg mrvalid=0,mrlast=0;reg [1:0] mrresp=0;
wire mrready; wire [23:0] pixel; wire de,hs,vs;
ddr_hdmi #(.WIDTH(WIDTH),.HEIGHT(4),.H_FP(4),.H_SYNC(4),.H_BP(4),.V_FP(1),.V_SYNC(1),.V_BP(1),.BUTTON_DEBOUNCE_CYCLES(8)) dut(
.s_axi_aclk(aclk),.s_axi_aresetn(arst),.pix_clk(pclk),.pix_rst_n(prst),.restart_btn(restart_btn),
.s_axi_awaddr(awaddr),.s_axi_awprot(3'b0),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
.s_axi_wdata(wdata),.s_axi_wstrb(wstrb),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
.s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_bready(bready),
.s_axi_araddr(araddr),.s_axi_arprot(3'b0),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
.s_axi_rdata(rdata),.s_axi_rresp(rresp),.s_axi_rvalid(rvalid),.s_axi_rready(rready),
.m_axi_araddr(maraddr),.m_axi_arlen(marlen),.m_axi_arvalid(marvalid),.m_axi_arready(marready),
.m_axi_rid(mrid),.m_axi_rdata(mrdata),.m_axi_rresp(mrresp),.m_axi_rlast(mrlast),.m_axi_rvalid(mrvalid),.m_axi_rready(mrready),
.m_axi_awready(1'b0),.m_axi_wready(1'b0),.m_axi_bid(6'b0),.m_axi_bresp(2'b0),.m_axi_bvalid(1'b0),
.vdata(pixel),.vde(de),.vhs(hs),.vvs(vs));
reg [31:0] lfsr=32'h12345678;
reg responding=0;reg [31:0] bus_address;integer beat=0,beats=0,read_requests=0;
function [15:0] sample(input [31:0] addr);
begin sample=addr>=32'h10000 ? (16'h07e0+((addr-32'h10000)>>1)) : (16'hf000+((addr-32'h1000)>>1)); end
endfunction
function [23:0] screen(input [15:0] c);
reg [7:0] r,g,b;begin r={c[15:11],c[15:13]};g={c[10:5],c[10:9]};b={c[4:0],c[4:2]};screen={r,b,g};end
endfunction
always @(negedge aclk) begin
 if(!arst)begin marready=0;mrvalid=0;responding=0; end
 else begin
 lfsr={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
 marready=!responding && lfsr[0];
 if(!mrvalid || mrready)begin
  mrvalid=0;
  if(responding && lfsr[2] && !hold_responses)begin
   mrvalid=1;mrlast=(beat==beats-1);
   mrid=(BAD_KIND==3 && beat==0)?1:0;
   mrresp=(BAD_KIND==4 && beat==0)?2:0;
   if(BAD_KIND==1 && beat==0)mrlast=1;
   if(BAD_KIND==2 && beat==beats-1)mrlast=0;
   mrdata={sample(bus_address+beat*8+6),sample(bus_address+beat*8+4),sample(bus_address+beat*8+2),sample(bus_address+beat*8)};
  end
 end
 end
end
always @(posedge aclk)if(arst)begin
 if(marvalid&&marready)begin
  if(maraddr[11:0]+(marlen+1)*8>4096)$fatal(1,"4KiB boundary");
  bus_address=maraddr;beat=0;beats=marlen+1+(BAD_KIND==5);responding=1;read_requests=read_requests+1;
 end
 if(mrvalid&&mrready)begin
  if(beat==beats-1)responding=0;
  beat=beat+1;
 end
end
task write_reg(input [15:0] addr,input [31:0] data);
begin
 @(negedge aclk);awaddr=addr;awvalid=1;
 do @(posedge aclk);while(!awready);
 @(negedge aclk);awvalid=0;
 repeat(2)@(posedge aclk);
 @(negedge aclk);wdata=data;wvalid=1;
 do @(posedge aclk);while(!wready);
 @(negedge aclk);wvalid=0;
 wait(bvalid);if(bresp!=0)$fatal(1,"AXI write response");
 @(posedge aclk);
end
endtask
task read_reg(input [15:0] addr,output [31:0] value);
begin
 @(negedge aclk);araddr=addr;arvalid=1;
 do @(posedge aclk);while(!arready);
 @(negedge aclk);arvalid=0;wait(rvalid);value=rdata;
 if(rresp!=0)$fatal(1,"AXI read response");
 @(posedge aclk);
end
endtask
integer ex0x=0,ex0y=0,ex1x=0,ex1y=0,checks=0;
reg checking=0,check_black=0;reg [31:0] expected_base=32'h1000;
always @(posedge pclk)begin
 ex1x=ex0x;ex1y=ex0y;ex0x=dut.hcnt;ex0y=dut.vcnt;
 #1;
 if(prst&&checking&&de)begin
  if(pixel!==(check_black ? 24'd0 : screen(sample(expected_base+(ex1y*WIDTH+ex1x)*2))))begin
   $display("pixel x=%0d y=%0d got=%h expected=%h",ex1x,ex1y,pixel,screen(sample(expected_base+(ex1y*WIDTH+ex1x)*2)));
   $fatal(1,"pixel sequence mismatch");
  end
  checks=checks+1;
 end
end
task check_frame(input [31:0] base);
integer initial_checks;
begin
 @(negedge pclk);
 while(dut.hcnt!=0 || dut.vcnt!=0)@(negedge pclk);
 initial_checks=checks;expected_base=base;checking=1;
 wait(checks==initial_checks+WIDTH*4);@(negedge pclk);checking=0;
end
endtask
reg [31:0] value;integer before_stop;
initial begin
 repeat(5)@(posedge aclk);@(negedge aclk);arst=1;prst=1;
 read_reg(0,value);if(value!==32'h44445231)$fatal(1,"identity");
 if(BUTTON_TEST)begin
  read_reg(16'h28,value);if(value!==0)$fatal(1,"spurious boot button event");
  // Each bounce remains shorter than the configured eight-cycle qualification.
  @(negedge aclk);restart_btn=1;repeat(3)@(negedge aclk);restart_btn=0;
  repeat(3)@(negedge aclk);restart_btn=1;repeat(2)@(negedge aclk);restart_btn=0;
  repeat(12)@(negedge aclk);
  read_reg(16'h28,value);if(value!==0)$fatal(1,"button bounce generated restart");
  @(negedge aclk);restart_btn=1;repeat(14)@(negedge aclk);
  read_reg(16'h28,value);if(value!==32'h10001)$fatal(1,"button event missing");
  repeat(100)@(negedge aclk);
  read_reg(16'h28,value);if(value!==32'h10001)$fatal(1,"held button repeated");
  @(negedge aclk);restart_btn=0;repeat(3)@(negedge aclk);restart_btn=1;
  repeat(14)@(negedge aclk);
  read_reg(16'h28,value);if(value!==32'h10001)$fatal(1,"release bounce repeated");
  @(negedge aclk);restart_btn=0;repeat(14)@(negedge aclk);
  read_reg(16'h28,value);if(value!==1)$fatal(1,"button release state");
  @(negedge aclk);restart_btn=1;repeat(14)@(negedge aclk);
  read_reg(16'h28,value);if(value!==32'h10002)$fatal(1,"second press missing");
  $display("PASS physical-button AXI count, bounce, hold, release and repress");$finish;
 end

 write_reg(16'h10,32'h1000);write_reg(16'h14,1);
 if(BAD_KIND!=0)begin
  wait(read_requests>0);repeat((WIDTH+12)*2)@(posedge pclk);
  write_reg(16'h14,2);repeat((WIDTH+12)*2)@(posedge pclk);
  read_reg(4,value);
  if(BAD_KIND!=4 && !value[3])$fatal(1,"protocol fault falsely reported idle");
  if(BAD_KIND==4 && value[3:0]!=0)$fatal(1,"legal error response did not drain");
  read_reg(16'h20,value);if(value==0)$fatal(1,"error not reported");
  $display("PASS DDR protocol/error kind %0d ownership handling",BAD_KIND);$finish;
 end
 repeat((WIDTH+12)*7*3)@(posedge pclk);
 check_frame(32'h1000);
 write_reg(16'h10,32'h10000);write_reg(16'h14,1);
 repeat((WIDTH+12)*7*3)@(posedge pclk);
 check_frame(32'h10000);
 wait(dut.state==3 && dut.request_tag[9:0]==2 && dut.beat_index==4);
 @(negedge aclk);hold_responses=1;
 repeat((WIDTH+12)*7*2)@(posedge pclk);
 check_black=1;check_frame(0);check_black=0;
 hold_responses=0;repeat((WIDTH+12)*7*2)@(posedge pclk);check_frame(32'h10000);
 read_reg(16'h0c,value);if(value!==2)$fatal(1,"two swaps expected");
 read_reg(16'h18,value);if(value!==32'h10000)$fatal(1,"front address");
 if(read_requests<20)$fatal(1,"scanout did not fetch");
 write_reg(16'h14,2);
 repeat(200)@(posedge aclk);
 read_reg(4,value);if(value[3:0]!==0)$fatal(1,"disable did not drain");
 before_stop=read_requests;repeat(300)@(posedge aclk);
 if(read_requests!=before_stop)$fatal(1,"DDR read after disable");
 $display("PASS DDR %0d verified pixels, swaps, independent AW/W, stalled reads, 4KiB and disable (%0d reads)",checks,read_requests);
 $finish;
end
initial begin #10000000;$fatal(1,"timeout");end
endmodule
