#!/bin/bash

# Check if the correct number of arguments are provided
if [ "$#" -ne 4 ]; then
    echo "Usage: $0 input.mp4 start_time (hh:mm:ss.ms) end_time (hh:mm:ss.ms) output.mp4"
    exit 1
fi

# Assign input arguments to variables
input_file="$1"
start_time="$2"
end_time="$3"
output_file="$4"

# Convert start_time and end_time to seconds
start_seconds=$(date -d "1970-01-01 $start_time UTC" +%s.%3N)
end_seconds=$(date -d "1970-01-01 $end_time UTC" +%s.%3N)

# Calculate fade out start time
fade_out_start_seconds=$(echo "$end_seconds - 1" | bc)

# Execute ffmpeg command
ffmpeg -i "$input_file" -ss "$start_time" -to "$end_time" -vf "fade=in:st=${start_seconds}:d=1, fade=out:st=${fade_out_start_seconds}:d=1, scale=-2:480" -c:a copy "$output_file"
