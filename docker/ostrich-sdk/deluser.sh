#!/usr/bin/env bash

export LANGUAGE=C.UTF-8
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

id | grep -q root || {
    echo "You need to be root. use sudo"
    exit 1
} 

test -z "$1" && {
    echo "Usage: deluser.sh <username>"
    exit 1
}

deluser $1
delgroup $1

rm -rf /home/$1

test -d /home/root || {
    mkdir /home/root
    chmod 700 /home/root
}

cp /etc/passwd /home/root
cp /etc/shadow /home/root
cp /etc/group /home/root
