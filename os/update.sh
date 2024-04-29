#!/bin/bash
#
# System updates and upgrades. 
# See: https://www.geeksforgeeks.org/shell-script-to-automate-system-updates-and-upgrades-in-linux/

# below command will Update package lists
sudo apt update

# below command will Upgrade the packages that can be upgraded
sudo apt upgrade -y

# below command will Remove unnecessary packages and dependencies for good 
# memory management
sudo apt autoremove -y

# below command will Clean package cache
sudo apt clean -y

# below command will Display system update status on terminal to know if the 
# update and upgrade is successfull
echo "System updates and upgrades completed successfully."
