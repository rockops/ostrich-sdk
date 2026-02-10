#! /usr/bin/env bash
set -e

DEFPORT=31022
DEFENDPOINT=""
CONFIGFILE=ostrich.yaml

REMOTEDIR=tmpdir

NAME=$(basename $0)

VERSION="0.0.0-dev"

TOP=$(cd $(dirname $0) && pwd)
OSTR=$(basename $0)

YQ_REMOTE=/python-sdk/bin/yq

doscp() {
  scp -oPort=$DEFPORT -i $HOME/.ostrich/id_rsa $@ || exit 1
}

dossh() {
  test -n "$DEBUG" && >&2 echo "SSH> $@"
  ssh -t -i $HOME/.ostrich/id_rsa sdk@$DEFENDPOINT -oPort=$DEFPORT -o LogLevel=ERROR "$@" || exit 1
}

dorsync() {
  local git_ignored_files=""

  if ! command -v git &> /dev/null; then
    echo "Warning: Git is not installed. The rsync will proceed without excluding any files based on .gitignore rules."
  else
    git_ignored_files=$(git -C "$1" ls-files --exclude-standard -oi --directory)

    if [ -n "$git_ignored_files" ]; then
      echo "Info: ignoring the following files based on .gitignore rules:"
      echo "$git_ignored_files"
    fi
  fi

  rsync --delete --exclude-from=<(echo "$git_ignored_files") --checksum -avz -e "ssh -i $HOME/.ostrich/id_rsa -p $DEFPORT" $@ || exit 1
}

pluginName() {
  cat $CONFIGFILE | dossh $YQ_REMOTE -r '.plugin.name'
}


epuuid() {
  test -z "$EPUUID" && {
    >&2 echo "Error: no UUID set for endpoint $DEFENDPOINT"
    >&2 echo "Run \"ostr init\""
    exit 1
  }
  echo $EPUUID
}


remoteDir() {
  test -f $CONFIGFILE || {
    >&2 echo "Error: $CONFIGFILE not accessible"
    exit 1
  }

  test -z "$EPUUID" && {
    >&2 echo "Error: no UUID set for endpoint $DEFENDPOINT"
    >&2 echo "Run \"ostr init\""
    exit 1
  }

  echo $EPUUID/$(cat $CONFIGFILE | ssh -i $HOME/.ostrich/id_rsa sdk@$DEFENDPOINT -oPort=$DEFPORT  -o LogLevel=ERROR $YQ_REMOTE -r '.plugin.name')
}


sync() {
    echo ">> Syncing sources"

    REMOTEDIR=$(remoteDir || exit 1)

    test -n "$DEBUG" && echo REMOTEDIR=$REMOTEDIR

    DIR=$(cat $CONFIGFILE | ssh -i $HOME/.ostrich/id_rsa sdk@$DEFENDPOINT -oPort=$DEFPORT  -o LogLevel=ERROR $YQ_REMOTE -r '.template.params.src_dir')

    dossh "mkdir -p $REMOTEDIR"

    test -r $CONFIGFILE || {
      echo "$CONFIGFILE not accessible"
      exit 1
    }
  
    BASE=$(dirname $(readlink -f $CONFIGFILE))

    rsync --version > /dev/null 2>&1 && {
      dossh mkdir -p /home/sdk/$REMOTEDIR/$DIR
      dorsync $BASE/$DIR sdk@$DEFENDPOINT:$(dirname /home/sdk/$REMOTEDIR/$DIR)
    } || {
      dossh "mkdir -p $REMOTEDIR/$DIR"
      CLEAN_REMOTE=$(dossh "cd /home/sdk/$REMOTEDIR/$DIR && pwd")
      dossh rm -rf "$CLEAN_REMOTE"
      dossh mkdir -p "$CLEAN_REMOTE"
      echo
      echo "WARN - rsync not found, fallback to full copy."
      echo "       consider installling rsync for better performance"
      echo
      doscp -r $(cd $BASE/$DIR && pwd) sdk@$DEFENDPOINT:$(dirname "$CLEAN_REMOTE")
    }

    cat $CONFIGFILE | envsubst > /tmp/${CONFIGFILE}.subst
    doscp /tmp/${CONFIGFILE}.subst sdk@$DEFENDPOINT:/home/sdk/$REMOTEDIR/$(basename $CONFIGFILE) > /dev/null
    rm -f /tmp/${CONFIGFILE}.subst

}


init() {
    echo "Init connection"
    printf "SDK endpoint (%s): " "$DEFENDPOINT"
    read ENDPOINT
    test -z "$ENDPOINT" && { 
      ENDPOINT="$DEFENDPOINT"
    }

    if [ -z "$ENDPOINT" ]; then
      echo "Endpoint cannot be empty"
      exit 1
    fi

    printf "Config name (%s): " "$ENDPOINT"
    read CONFIG
    test -z "$CONFIG" && { 
      CONFIG="$ENDPOINT"
    }

    printf "Port (%s): " "$DEFPORT"
    read PORT
    test -z "$PORT" && { 
      PORT=$DEFPORT
    }

    mkdir -p $HOME/.ostrich

    echo "DEFENDPOINT=$ENDPOINT" > $HOME/.ostrich/$CONFIG.conf
    echo "DEFPORT=$PORT" >> $HOME/.ostrich/$CONFIG.conf
    echo "EPUUID=$(uuidgen 2> /dev/null || (echo $RANDOM | md5sum | head -c 20; echo;))" >> $HOME/.ostrich/$CONFIG.conf

    test -f $HOME/.ostrich/id_rsa || {
        echo "Generate key"
        ssh-keygen -t rsa -q -f "$HOME/.ostrich/id_rsa" -N ""
    }

    PUB=$(cat $HOME/.ostrich/id_rsa.pub)
    echo "Installing key"
    ssh sdk@$ENDPOINT -oPort=$PORT  -o LogLevel=ERROR "echo $PUB >> /etc/authorized_keys/sdk"

    echo "Key installed"
    export DEFENDPOINT=$ENDPOINT
    export DEFPORT=$PORT
    dossh "source /etc/profile.d/sdk.sh; ost help --nologo"


    #test -f $HOME/.ostrich/current.conf && rm -f $HOME/.ostrich/current.conf
    #ln -s $HOME/.ostrich/$CONFIG.conf $HOME/.ostrich/current.conf
    echo $CONFIG > $HOME/.ostrich/current
}


helpEndpoint() {
  echo "Usage:"
  echo "$NAME endpoint|ep get"
  echo "#  Display current endpoint"
  echo "" 
  echo "$NAME endpoint|ep <name>"
  echo "#  Switch to endpoint <name>"
  echo "" 
  echo "$NAME endpoint|ep <command>"
  echo
  echo "  Standard commands"
  echo "  - list|ls        : list the configured endpoints"
  echo "                     to add one endpoint, use \"$NAME init\""
  
}

endpointList() {
    #test -f $HOME/.ostrich/current.conf && CURR=$(basename $(readlink -f $HOME/.ostrich/current.conf) .conf)
    test -f $HOME/.ostrich/current && CURR=$(cat $HOME/.ostrich/current)
    #for EP in $(ls -1 $HOME/.ostrich/*.conf | grep -v current.conf$); do
    for EP in $(ls -1 $HOME/.ostrich/*.conf); do
      TMP=$(basename $EP .conf)
      FLAG='  '
      test "$TMP" = "$CURR" && FLAG='> '
      printf "%s%s\n" "$FLAG" "$TMP"
    done
}

endpoint() {
  case "$1" in
    "" | "list" | "ls")
      endpointList
    ;;
    "get")
      #test -f $HOME/.ostrich/current.conf && CURR=$(basename $(readlink -f $HOME/.ostrich/current.conf) .conf)
      test -f $HOME/.ostrich/current && CURR=$(cat $HOME/.ostrich/current)
      test -z "$CURR" && {
        >&2 echo "No endpoint selected"
        kill $$
      } || {
        echo $CURR
      }
    ;;
    "help" | "-h" | "--help" )
      helpEndpoint
    ;;
    *)
      test -f "$HOME/.ostrich/$1.conf" || {
        >&2 echo "Endpoint $1 does not exist"
        >&2 echo "Try \"ostr endpoint help\""
        exit 1
      }

      #rm -f $HOME/.ostrich/current.conf
      #ln -s $HOME/.ostrich/$1.conf $HOME/.ostrich/current.conf
      echo $1 > $HOME/.ostrich/current
      endpointList

    ;;
  esac
}


helpUser() {
  echo "Usage:"
  echo "$NAME user add <username> [uid] [gid]"
  echo "  Add a new user"
  echo "  If specified, use uid as user ID and gid as group ID"
  echo "  else, the first IDs are chosen"
  echo "" 
  echo "$NAME user del <username>"
  echo "  Delete user <username>"
  echo "" 
  echo "$NAME user passwd <username>"
  echo "  Change password for user <username>"
  echo "" 
  echo "$NAME user list"
  echo "  List users"
}


user() {
  case $1 in
    "add")
      test -z "$2" && helpUser || dossh -t sudo /sdk/adduser.sh $2 $3 $4
    ;;
    "del")
      test -z "$2" && helpUser || dossh -t sudo /sdk/deluser.sh $2
    ;;
    "passwd")
      test -z "$2" && helpUser || dossh -t sudo /sdk/passwd.sh $2
    ;;
    "list" | "ls")
      dossh "ls /home | grep -v root | grep -v sdk"
    ;;
    *)
      helpUser
    ;;
  esac
}


help() {

echo '                              _              
     ____   ___  _____  ___  |_| ___  __   _  
    / __ \ / __||_   _||   ) | |/ __||  |_| | 
    |(oO)| \__ \  | |  |   \ | |\__ \)   _  | 
    \_\/_/ |___/  |_|  |_|\_\|_||___/|__| |_|_  _
      ||                            ___   __| || | __
      ||                           / __| / _` || |/ /
                                   \__ \| (_| ||   < 
                                   |___/ \__,_||_|\_\
                                        R-E-M-O-T-E-->>'
echo
echo "Ostrich SDK remote commands :"
echo 
echo "Usage: $NAME [ -f <config_file> ] <command> <command arguments>"
echo "       $NAME <command> help # Get help on specific command"
echo
echo "-f         : sets the config file. Default is ostrich.yaml in current directory"
echo
echo "Standard commands"
echo "- init        : to setup the connection with the SDK environment"
echo "                you need the endpoint / port / initial password to access"
echo "- template    : get help on the supported templates"
echo "- endpoint|ep : manage endpoints"
echo "- version     : display client & server version"
echo "- config      : sets SDK configuration"
echo ""
echo "The other commands are specific to the template."
echo "Do \"$NAME template describe <template name>\" to get help on a specific template"
echo ""
echo "Advanced commands"
echo "- ssh      : open a shell in the SDK env"
echo "- put      : copy your source to the SDK env"
echo "- docker   : execute a docker commande in the SDK env"
echo "             use \"ostr docker login\" to connect to your private registry if needed"
echo "- kubectl  : execute kubectl command in the SDK env"
echo "- user     : manage users of SDK environment"
echo "- update   : get the last ostr from the current endpoint"

if [ "$1" = "ost" ]; then
  echo
  echo "======================================"
  echo
  dossh "source /etc/profile.d/sdk.sh; ost help --nologo"
else
  echo
  echo "Do \"$NAME help ost\" to get full help on the remote SDK commands"
fi

}


update() {
  REMOTE_OSTR=$(dossh "source /etc/profile.d/sdk.sh; which ostr")
  echo "Remote ostr location: $REMOTE_OSTR"
  REMOTE_OSTR=${REMOTE_OSTR/$'\r'/}
  doscp -r sdk@${DEFENDPOINT}:${REMOTE_OSTR%'\r'} $TOP/$OSTR.new
  chmod +x $TOP/$OSTR.new
  cp $TOP/$OSTR $TOP/$OSTR-v$VERSION
  NEWVERSION=$($TOP/$OSTR.new version clientonly)
  mv $TOP/$OSTR.new $TOP/$OSTR-v$NEWVERSION

  test -w $TOP/$OSTR && {
    echo -n "Update current script (y/n): "
    read UP
    if [ "$UP" == "y" ]; then
      mv $TOP/$OSTR-v$NEWVERSION $TOP/$OSTR
      echo "Script updated. To restore the previous version, execute:"
      echo "mv $TOP/$OSTR-v$VERSION $TOP/$OSTR"
    else
      echo "Current script not updated"
      echo "To update it, do:"
      echo "mv $TOP/$OSTR-v$NEWVERSION $TOP/$OSTR"
    fi    
  } || {
    echo "Can't update current script, permission denied"
  }
}


if [ -f $HOME/.ostrich/current ]; then
  . $HOME/.ostrich/$(cat $HOME/.ostrich/current).conf
fi

# Locate config file & other arguments
while [ -n "$1" ]; do
  case "$1" in
    "-f")
      shift
      CONFIGFILE=$1
      OPTIONF=$1
    ;;
    "-d" | "--debug")
      DEBUG=1
    ;;
    "--rm")
      OPTIONRM="--rm"
    ;;
    "-o")
      shift
      OUTPUT=$1
    ;;
    *)
      ARGS="$ARGS $1"
    ;;
  esac
  shift
done

test -z "$CONFIGFILE" && {
  echo "No config file specified"
  help
  exit 1
}

test -z "$ARGS" && {
  help
  exit 1
}

set $ARGS
OPERATION="$1"

OPTS="$@"

case "$OPERATION" in
  init)
    init
  ;;
  endpoint | ep)
    shift
    endpoint $@
  ;;
  ssh)
    ENDPOINT=$(endpoint get)
    echo ">> Endpoint = $ENDPOINT <<"
    shift
    dossh $@
  ;;
  put)
    ENDPOINT=$(endpoint get)
    echo ">> Endpoint = $ENDPOINT <<"
    sync
  ;;
  docker)
    ENDPOINT=$(endpoint get)
    echo ">> Endpoint = $ENDPOINT <<"
    if [ "$2" == "" ]; then
      # ostr docker (without argument) = call remote ostr docker
      sync
      dossh "cd $REMOTEDIR; source /etc/profile.d/sdk.sh; ostr $OPTS"
    else
      # if argument are passed, 
      dossh -t $@
    fi
  ;;
  kubectl)
    ENDPOINT=$(endpoint get)
    echo ">> Endpoint = $ENDPOINT <<"
    shift
    if [ -n "$OPTIONF" ]; then
      if [ "$OPTIONF" = "-" ]; then
        dossh kubectl $@ -f -
      else
        cat $OPTIONF | dossh kubectl $@ -f -
      fi
    else
      dossh kubectl $@
    fi
  ;;
  ""|help|-h|-help)
    shift
    help $@
  ;;
  template)
    ENDPOINT=$(endpoint get)
    >&2 echo ">> Endpoint = $ENDPOINT <<"
    shift
    if [ -z "$1" ]; then
      test -z "$OUTPUT" && OUTPUT=$(pluginName)

      if [ -z $OPTIONRM ]; then
        test -d $OUTPUT && {
          echo "Directory $OUTPUT must not exist. Use --rm option to automatically cleanup"
          exit 1
        }
      else
        rm -rf $OUTPUT
      fi

      rm -rf template-tmp
      mkdir -p $OUTPUT

      sync
      dossh "cd $REMOTEDIR; source /etc/profile.d/sdk.sh; ost $OPTS --rm -o template-tmp"
      doscp -r 'sdk@'$DEFENDPOINT':/home/sdk/'$REMOTEDIR'/template-tmp' .
      mv template-tmp/* $OUTPUT
      rm -rf template-tmp
    elif [ "$1" = "install" ]; then
      test -z "$2" && {
        echo "Usage: ostr template install <plugin dir>"
        exit 1
      }
      uid=$(epuuid) || exit 1
      dossh "mkdir -p /home/sdk/$uid"
      doscp -r $2 'sdk@'$DEFENDPOINT':/home/sdk/'$uid
      dossh "cd $uid; source /etc/profile.d/sdk.sh; ls; ost template install $(basename $2)"

    else
      dossh "source /etc/profile.d/sdk.sh; ost $OPTS $OPTIONRM"
    fi
  ;;
  package)
    ENDPOINT=$(endpoint get)
    echo ">> Endpoint = $ENDPOINT <<"
    sync
    dossh "cd $REMOTEDIR; source /etc/profile.d/sdk.sh; ost $OPTS"
    doscp sdk@$DEFENDPOINT:/home/sdk/$REMOTEDIR/*.iso .
    ;;
  cleanup)
    ENDPOINT=$(endpoint get)
    REMOTEDIR=$(remoteDir) || exit 1
    echo ">> Endpoint = $ENDPOINT <<"
    dossh "rm -rf /home/sdk/$REMOTEDIR || true"
  ;;
  user)
    ENDPOINT=$(endpoint get)
    echo ">> Endpoint = $ENDPOINT <<"
    shift
    user $@    
  ;;
  version)
    ENDPOINT=$(endpoint get)
    if [ "$2" == "clientonly" ]; then
      echo $VERSION
    else
      echo ">> Endpoint = $ENDPOINT <<"
      echo "ostr $VERSION"
      dossh 'source /etc/profile.d/sdk.sh; ost --version; printf "ost located in:"; which ost'
    fi
  ;;
  update)
    ENDPOINT=$(endpoint get)
    echo ">> Endpoint = $ENDPOINT <<"
    update    
  ;;
  config)
    ENDPOINT=$(endpoint get)
    echo ">> Endpoint = $ENDPOINT <<"
    dossh "source /etc/profile.d/sdk.sh; ost $@"
  ;;
  *)
    ENDPOINT=$(endpoint get)
    echo ">> Endpoint = $ENDPOINT <<"
    sync
    dossh "cd $REMOTEDIR; source /etc/profile.d/sdk.sh; ost $OPTS"
  ;;
esac

