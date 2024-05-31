#!/bin/bash

# Check if the correct number of arguments are provided
if [ "$#" -ne 5 ]; then
    echo "Usage: $0 input1.mp4 input2.mp4 input3.mp4 input4.mp4 output.mp4"
    exit 1
fi

# Input video files
input1=$1
input2=$2
input3=$3
input4=$4
output=$5

# Get the durations of the input videos
duration1=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$input1")
duration2=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$input2")
duration3=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$input3")
duration4=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$input4")

# Find the maximum duration
max_duration=$(echo "$duration1 $duration2" | awk '{print ($1 > $2) ? $1 : $2}')
max_duration=$(echo "$max_duration $duration3" | awk '{print ($1 > $2) ? $1 : $2}')
max_duration=$(echo "$max_duration $duration4" | awk '{print ($1 > $2) ? $1 : $2}')

# Function to create a looped version of a video
create_looped_video() {
    input=$1
    duration=$2
    output=$3
    ffmpeg -y -stream_loop -1 -i "$input" -c copy -t "$duration" "$output"
}

# Create looped videos
create_looped_video "$input1" "$max_duration" "_looped1.mp4"
create_looped_video "$input2" "$max_duration" "_looped2.mp4"
create_looped_video "$input3" "$max_duration" "_looped3.mp4"
create_looped_video "$input4" "$max_duration" "_looped4.mp4"

# Create the 2x2 split screen video
ffmpeg -y \
    -i looped1.mp4 -i looped2.mp4 -i looped3.mp4 -i looped4.mp4 \
    -filter_complex "
    nullsrc=size=1280x720 [base];
    [0:v] setpts=PTS-STARTPTS, scale=640x360 [upperleft];
    [1:v] setpts=PTS-STARTPTS, scale=640x360 [upperright];
    [2:v] setpts=PTS-STARTPTS, scale=640x360 [lowerleft];
    [3:v] setpts=PTS-STARTPTS, scale=640x360 [lowerright];
    [base][upperleft] overlay=shortest=1 [tmp1];
    [tmp1][upperright] overlay=shortest=1:x=640 [tmp2];
    [tmp2][lowerleft] overlay=shortest=1:y=360 [tmp3];
    [tmp3][lowerright] overlay=shortest=1:x=640:y=360
    " \
    -c:v libx264 -crf 23 -preset veryfast $output

# Clean up temporary files
rm _looped1.mp4 _looped2.mp4 _looped3.mp4 _looped4.mp4
