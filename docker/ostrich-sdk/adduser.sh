#!/usr/bin/env bash

export LANGUAGE=C.UTF-8
export LANG=C.UTF-8
export LC_ALL=C.UTF-8


id | grep -q root || {
    echo "You need to be root. use sudo"
    exit 1
} 

test -z "$1" && {
    echo "Usage: adduser.sh <username> [uid] [gid]"
    exit 1
}

# A GID is provided
test -z "$3" || {
    addgroup --gid $3 $1
    OPTS="--gid $3"
}

# A UID is provided
test -z "$2" || {
    OPTS="$OPTS --uid $2" 
}

adduser --gecos "" $OPTS $1
test -d /home/root || {
    mkdir /home/root
    chmod 700 /home/root
}

usermod -aG sdk $1
usermod -aG docker $1

cp /etc/passwd /home/root
cp /etc/shadow /home/root
cp /etc/group /home/root
