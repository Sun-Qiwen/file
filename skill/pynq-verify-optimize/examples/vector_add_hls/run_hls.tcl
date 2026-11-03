# Parameterized HLS IP flow. This script does not create a board Overlay.
foreach key {VADD_PART VADD_CLOCK_NS VADD_OUT} {
    if {![info exists ::env($key)] || [string trim $::env($key)] eq ""} {
        error "Required environment variable missing: $key"
    }
}
set period $::env(VADD_CLOCK_NS)
if {![string is double -strict $period]} { error "VADD_CLOCK_NS must be positive and finite" }
if {[catch {expr {$period > 0.0 && $period < Inf}} good] || !$good} {
    error "VADD_CLOCK_NS must be positive and finite"
}
set stage csim
if {[info exists ::env(VADD_STAGE)]} { set stage $::env(VADD_STAGE) }
if {$stage ni {csim synth cosim export}} { error "VADD_STAGE must be csim, synth, cosim or export" }
set src [file dirname [file normalize [info script]]]
set out [file normalize $::env(VADD_OUT)]
if {[file exists $out]} { error "Output exists; choose a new VADD_OUT: $out" }
file mkdir [file dirname $out]
open_project $out
set_top vector_add
add_files [file join $src vector_add.cpp] -cflags {-std=c++14}
add_files [file join $src vector_add.hpp]
add_files -tb [file join $src testbench.cpp] -cflags {-std=c++14}
open_solution solution -flow_target vivado
set_part $::env(VADD_PART)
create_clock -period $period -name default
csim_design
if {$stage ne "csim"} { csynth_design }
if {$stage in {cosim export}} { cosim_design -rtl verilog }
if {$stage eq "export"} { export_design -format ip_catalog }
close_project
