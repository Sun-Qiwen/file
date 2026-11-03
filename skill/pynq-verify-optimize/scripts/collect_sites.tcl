# Read-only checkpoint inventory. Output must be a new file.
if {$argc<2 || $argc>3} {error "Usage: INPUT.dcp NEW.txt ?PBLOCK?"}
set input [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
if {[file exists $output] || $input eq $output} {error "Output must not exist or overwrite input"}
set_param general.maxThreads 2
open_checkpoint $input
current_instance
set all [get_sites -filter {SITE_TYPE == SLICEL || SITE_TYPE == SLICEM}]
if {[llength $all]==0} {error "No SLICEL/SLICEM sites; adapt this architecture explicitly"}
set occupied [lsort -unique [get_sites -of_objects [get_cells -hier -filter {IS_PRIMITIVE}] -filter {SITE_TYPE == SLICEL || SITE_TYPE == SLICEM}]]
set lines [list "part=[get_property PART [current_design]]" "device_slice_sites=[llength $all]" "occupied_slice_sites=[llength $occupied]"]
if {$argc==3} {
    set pb [get_pblocks -quiet [lindex $argv 2]]
    if {[llength $pb]!=1} {error "Expected exactly one pblock"}
    set ranges [get_property GRID_RANGES $pb];set rectangles {}
    foreach r $ranges {
        if {![regexp {^SLICE_X([0-9]+)Y([0-9]+):SLICE_X([0-9]+)Y([0-9]+)$} $r -> x0 y0 x1 y1]} {error "Unsupported non-SLICE range: $r"}
        lappend rectangles [list $x0 $y0 $x1 $y1]
    }
    if {[llength $rectangles]==0} {error "Empty Slice region"}
    set inside [dict create]
    foreach site $all {
        if {![regexp {^SLICE_X([0-9]+)Y([0-9]+)$} $site -> x y]} {error "Unknown Slice site name"}
        foreach rectangle $rectangles {
            lassign $rectangle x0 y0 x1 y1
            if {$x>=$x0 && $x<=$x1 && $y>=$y0 && $y<=$y1} {dict set inside $site 1;break}
        }
    }
    set outside 0
    foreach site $occupied {if {![dict exists $inside $site]} {incr outside}}
    lappend lines "pblock=$pb" "ranges=$ranges" "is_soft=[get_property IS_SOFT $pb]" "allowed_slice_sites=[dict size $inside]" "reserved_slice_sites=[expr {[llength $all]-[dict size $inside]}]" "occupied_outside_region=$outside"
}
set f [open $output {WRONLY CREAT EXCL}]
puts $f [join $lines "\n"]
close $f
close_design
exit
