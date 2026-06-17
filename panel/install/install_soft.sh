#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

# ─── Local mirror resolution (no CDN) ─────────────────────────────────────────
if [ -z "$BT_MIRROR" ]; then
	for _cfg in /www/server/panel/data/mirror.conf "$(dirname "$0")/../../mirror.conf"; do
		if [ -f "$_cfg" ]; then
			. "$_cfg"
			break
		fi
	done
fi
[ -z "$BT_MIRROR" ] && BT_MIRROR="http://127.0.0.1:5050"

serverUrl="$BT_MIRROR/install"
mtype=$1
actionType=$2
name=$3
version=$4

check_dash=$(readlink -f /bin/sh)
if [ "$check_dash" = "/usr/bin/dash" ] || [ "$check_dash" = "/bin/dash" ] || [ "$check_dash" = "dash" ]; then
    if [ -f "/usr/bin/bash" ]; then
        ln -sf /usr/bin/bash /bin/sh
    elif [ -f "/bin/bash" ]; then
        ln -sf /bin/bash /bin/sh
    fi
fi

if [ ! -f 'lib.sh' ];then
	wget -O lib.sh $serverUrl/$mtype/lib.sh --no-check-certificate
fi

libNull=`cat lib.sh`
if [ "$libNull" == '' ];then
	wget --no-check-certificate -O lib.sh $serverUrl/$mtype/lib.sh
fi

wget --no-check-certificate -O $name.sh $serverUrl/$mtype/$name.sh
if [ "$actionType" == 'install' ];then
	bash lib.sh
fi

# Rewrite every CDN host inside the downloaded soft script to the local mirror,
# so tarballs/sources are also fetched locally (no download.bt.cn / aapanel.com).
MIRROR_HOST=$(echo "$BT_MIRROR" | sed 's#/*$##')
sed -i \
	-e "s#https\?://download\.bt\.cn#${MIRROR_HOST}#g" \
	-e "s#https\?://node\.aapanel\.com#${MIRROR_HOST}#g" \
	-e "s#https\?://[a-z0-9-]*\.bt\.cn#${MIRROR_HOST}#g" \
	-e "s#https\?://www\.aapanel\.com#${MIRROR_HOST}#g" \
	$name.sh

bash $name.sh $actionType $version

echo '|-Successify --- Command executed! ---'
